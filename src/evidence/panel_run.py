# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Run the judge panel (:mod:`evidence.panel`) over a finished run, and record it.

    evidence panel runs/<run>                       # the panel here, on the judge endpoint
    evidence panel runs/<run> --runtime nemoclaw    # inside the NemoClaw sandbox on the node

The panel reads what the run already holds: each briefing, the case file it was
written from, and the deterministic check results on it. The engine packs these
into one bundle per briefing, with the regulation passages retrieved for the
three questions. The panel's records go to ``panel/records.jsonl`` in the run,
what ran and where to ``panel/manifest.json``; the evidence pack is rebuilt and
the run sealed again. The panel is reported next to the judge, never gated.

With ``--runtime nemoclaw`` the bundles and ``panel.py`` are copied to the GPU
node and run inside the ``evidence-judge`` sandbox. The panel's one destination is
the managed inference route (``https://inference.local/v1``), which OpenShell
routes to the team's judge; everything the sandbox may reach is set by its
network policy, whose entry names and hash the runtime record keeps.
``scripts/cluster/panel_nemoclaw.sh`` does the copying; the hosts come from
``EVIDENCE_PANEL_SSH`` ("<login host> <node>").
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evidence import panel
from evidence.adapters.nvidia_build import endpoint_for
from evidence.contracts.transcript import Transcript
from evidence.corpus import Corpus
from evidence.judge import retrieve_for_fields
from evidence.pack import Pack

EVIDENCE_CHARS = 3000
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "cluster" / "panel_nemoclaw.sh"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def bundles(run: Path, pack: Pack, corpus: Corpus | None, limit: int | None = None
            ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """One bundle per briefing in the run, and what they were built from."""
    items = {i.item_id: i for i in pack.items}
    results: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for line in (run / "results.jsonl").read_text(encoding="utf-8").splitlines():
        if line:
            r = json.loads(line)
            if str(r.get("judge", "")).startswith("check:"):
                results.setdefault((r["item_id"], r["repeat"]), []).append(r)
    passages: list[dict[str, Any]] = []
    by_field: dict[str, list[str]] = {}
    if corpus is not None:
        found, by_field = retrieve_for_fields(corpus)
        passages = [{"passage_id": p.passage_id, "citation": p.citation, "title": p.title,
                     "text": p.text} for p in found]
    out = []
    for path in sorted((run / "transcripts").glob("*.json")):
        t = Transcript.model_validate_json(path.read_text(encoding="utf-8"))
        item = items.get(t.item_id)
        if item is None:
            continue
        checks = [{"name": r["check"], "passed": r["passed"], "value": r["value"],
                   "detail": r["detail"],
                   "evidence": json.dumps(r.get("evidence"), ensure_ascii=False)[:EVIDENCE_CHARS]}
                  for r in results.get((t.item_id, t.repeat), [])]
        out.append({"item_id": t.item_id, "repeat": t.repeat, "briefing": t.output,
                    "transcript_sha256": t.sha256, "case_file": item.documents_text(),
                    "checks": checks, "passages": passages})
    out.sort(key=lambda b: (b["item_id"], b["repeat"]))
    if limit:
        keep = sorted({b["item_id"] for b in out})[:limit]
        out = [b for b in out if b["item_id"] in keep]
    facts = {"briefings": len(out), "passages_by_field": by_field,
             "corpus": {"jurisdiction": corpus.jurisdiction, "corpus_sha256": corpus.sha256}
             if corpus else None}
    return out, facts


def run_direct(bundle_list: list[dict[str, Any]], *, workers: int, log: Any,
               models: dict[str, str] | None = None) -> tuple[list[dict[str, Any]], dict]:
    """The panel in this process, against the judge endpoint."""
    ep = endpoint_for("judge")
    key = os.environ.get("NVIDIA_API_KEY") if ep.is_build else None
    models = models or {r: ep.model_id for r in ("reader", "challenger", "arbiter")}

    def call(**kw: Any) -> dict[str, Any]:
        return panel.chat(ep.base_url, api_key=key, **kw)

    records = panel.run_many(bundle_list, call=call, models=models, workers=workers, log=log)
    return records, {"kind": "direct", "endpoint": ep.base_url, "models": models}


def run_nemoclaw(bundle_list: list[dict[str, Any]], *, workers: int, log: Any,
                 models: dict[str, str] | None = None) -> tuple[list[dict[str, Any]], dict]:
    """The panel inside the NemoClaw sandbox on the node, via panel_nemoclaw.sh."""
    hosts = os.environ.get("EVIDENCE_PANEL_SSH", "").split()
    if len(hosts) != 2:
        raise RuntimeError("set EVIDENCE_PANEL_SSH to '<login host> <node>', e.g. "
                           "'codefest rtx-3se-06-04'")
    model = (models or {}).get("reader") or "nano-judge"
    with tempfile.TemporaryDirectory() as tmp:
        job = Path(tmp)
        (job / "bundles.jsonl").write_text(
            "".join(json.dumps(b, ensure_ascii=False) + "\n" for b in bundle_list),
            encoding="utf-8")
        (job / "panel.py").write_bytes(Path(panel.__file__).read_bytes())
        log(f"  running {len(bundle_list)} briefings in the NemoClaw sandbox on {hosts[1]}")
        subprocess.run(["bash", str(SCRIPT), str(job), hosts[0], hosts[1], model,
                        str(workers)], check=True)
        records = [json.loads(x) for x in (job / "records.jsonl").read_text(
            encoding="utf-8").splitlines() if x.strip()]
        runtime = json.loads((job / "runtime.json").read_text(encoding="utf-8"))
    return records, runtime | {"kind": "nemoclaw",
                               "models": {r: model for r in ("reader", "challenger",
                                                             "arbiter")}}


def record(run: Path, records: list[dict[str, Any]], facts: dict[str, Any],
           runtime: dict[str, Any], started: str) -> dict[str, Any]:
    """Keep the last good record per briefing, write panel/, and describe what ran."""
    latest: dict[tuple[str, int], dict[str, Any]] = {}
    prior = run / "panel" / "records.jsonl"
    if prior.is_file():  # a resumed panel keeps what an earlier pass finished
        for line in prior.read_text(encoding="utf-8").splitlines():
            if line:
                r = json.loads(line)
                latest[(r["item_id"], r["repeat"])] = r
    for r in records:
        key = (r["item_id"], r["repeat"])
        if not r.get("error") or key not in latest or latest[key].get("error"):
            latest[key] = r
    rows = [latest[k] for k in sorted(latest)]
    (run / "panel").mkdir(exist_ok=True)
    body = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)
    (run / "panel" / "records.jsonl").write_text(body, encoding="utf-8")
    manifest = {
        "panel": panel.PANEL_VERSION,
        "panel_py_sha256": hashlib.sha256(Path(panel.__file__).read_bytes()).hexdigest(),
        "runtime": runtime,
        "started_at": started, "finished_at": _now(),
        "briefings": len(rows), "errors": sum(1 for r in rows if r.get("error")),
        "corpus": facts.get("corpus"), "passages_by_field": facts.get("passages_by_field"),
        "roles": {"reader": "scores the briefing as the underwriter would, no case file",
                  "challenger": "checks it against the case file and the deterministic "
                                "checks, with tools",
                  "arbiter": "final scores, citations and whether a person should review it"},
        "gated": False,
    }
    (run / "panel" / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n",
                                                 encoding="utf-8")
    return manifest
