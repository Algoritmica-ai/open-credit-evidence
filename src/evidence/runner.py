# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Run a pack against the assistant under test: items × repeats → transcripts → results.

Resumable: a transcript that already exists on disk is reused, so a killed run
continues where it stopped and a finished run re-scores without new model
calls. Every call is recorded with the model id, endpoint, prompt hash,
parameters, tokens and latency — the run manifest is built from these.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evidence import __version__
from evidence.adapters.nvidia_build import chat, endpoint_for
from evidence.checks import run_checks
from evidence.contracts.item import BenchmarkItem
from evidence.contracts.transcript import SUTPins, Transcript
from evidence.judge import judge_readability
from evidence.pack import Pack
from evidence.regulations import assess

ASSISTANT_MAX_TOKENS = 900


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _safe(item_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", item_id)


def transcript_path(out: Path, item_id: str, repeat: int) -> Path:
    return out / "transcripts" / f"{_safe(item_id)}-r{repeat}.json"


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _transcript_sha(item_id: str, sut: SUTPins, system: str, user: str, output: str) -> str:
    h = hashlib.sha256()
    for part in (item_id, json.dumps(sut.model_dump(), sort_keys=True), system, user, output):
        h.update(part.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def call_assistant(item: BenchmarkItem, run_id: str, repeat: int) -> Transcript:
    """One recorded call. The assistant sees the task prompt and every document."""
    user = item.documents_text()
    started = _now()
    r = chat("assistant", system=item.prompt, user=user, max_tokens=ASSISTANT_MAX_TOKENS)
    sut = SUTPins(
        model_id=r.model_id, prompt_version=r.prompt_version, params=r.params, endpoint=r.endpoint
    )
    return Transcript(
        item_id=item.item_id,
        run_id=run_id,
        repeat=repeat,
        sut=sut,
        system_prompt=item.prompt,
        user_prompt=user,
        output=r.text,
        latency_ms=r.latency_ms,
        tokens_in=r.tokens_in,
        tokens_out=r.tokens_out,
        provider_id=r.raw_id,
        started_at=started,
        sha256=_transcript_sha(item.item_id, sut, item.prompt, user, r.text),
    )


def run_pack(
    pack: Pack,
    out: Path,
    *,
    repeats: int = 1,
    checks: list[str] | None = None,
    judge: bool = True,
    limit: int | None = None,
    log: Callable[[str], None] = print,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Execute the pack. Returns the run manifest; writes transcripts and results.jsonl.

    ``should_stop`` is polled before every model call. When it returns True the
    run stops cleanly: what was completed is scored and sealed, the manifest
    records ``cancelled: true`` and the real transcript count, and a later run
    into the same directory resumes from the transcripts on disk.
    """
    out.mkdir(parents=True, exist_ok=True)
    (out / "transcripts").mkdir(exist_ok=True)
    run_id = out.name
    items = pack.items[:limit] if limit else pack.items
    started = _now()

    results_path = out / "results.jsonl"
    results: list[dict[str, Any]] = []
    calls_made = 0
    total = len(items) * repeats
    done = 0
    cancelled = False
    for item in items:
        names = checks if checks is not None else item.deterministic_checks
        want_judge = judge and ("readability" in item.judges or judge is True)
        for rep in range(repeats):
            if should_stop is not None and should_stop():
                cancelled = True
                break
            path = transcript_path(out, item.item_id, rep)
            if path.is_file():
                t = Transcript.model_validate_json(path.read_text(encoding="utf-8"))
            else:
                t = call_assistant(item, run_id, rep)
                path.write_text(t.model_dump_json(indent=2), encoding="utf-8")
                calls_made += 1
            for c in run_checks(names, output=t.output, item=item):
                results.append(
                    {"item_id": item.item_id, "repeat": rep, "check": c.name} | c.to_score()
                )
            if want_judge:
                rec = judge_readability(output=t.output, item=item)
                results.append(
                    {"item_id": item.item_id, "repeat": rep, "check": "readability"} | rec
                )
            done += 1
            log(
                f"  {done}/{total}  {item.item_id.split(':')[2]} r{rep}  {t.latency_ms / 1000:.1f}s"
            )

    with results_path.open("w", encoding="utf-8") as fh:
        for rec in results:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    assistant_ep = endpoint_for("assistant")
    judge_ep = endpoint_for("judge") if judge else None
    regulatory = assess(pack.regulatory_context)
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "engine": {
            "package": "credit-evidence-engine",
            "version": __version__,
            "git_commit": _git_commit(),
        },
        "pack": {
            "pack_id": pack.pack_id,
            "version": pack.version,
            "items_sha256": pack.items_sha256,
            "items": len(items),
            "domain": pack.manifest.get("domain"),
            "scorecard_version": pack.manifest.get("scorecard_version"),
            "sdd": pack.manifest.get("sdd"),
        },
        "sut": {
            "role": "assistant",
            "model_id": assistant_ep.model_id,
            "endpoint": assistant_ep.base_url,
            "on_prem": not assistant_ep.is_build,
            "max_tokens": ASSISTANT_MAX_TOKENS,
        },
        "judge": (
            {
                "model_id": judge_ep.model_id,
                "endpoint": judge_ep.base_url,
                "on_prem": not judge_ep.is_build,
                "rubric": "readability",
            }
            if judge_ep
            else None
        ),
        "checks": checks if checks is not None else pack.checks_declared(),
        "repeats": repeats,
        "transcripts": done,
        "planned": total,
        "cancelled": cancelled,
        "model_calls_made": calls_made,
        "regulatory": {
            "jurisdiction": regulatory.jurisdiction,
            "ruleset_id": regulatory.ruleset_id,
            "ruleset_version": regulatory.ruleset_version,
            "ruleset_sha256": regulatory.ruleset_sha256,
            "context_sha256": regulatory.context_sha256,
            "status": regulatory.status,
        },
        "started_at": started,
        "finished_at": _now(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out / "regulations.json").write_text(regulatory.model_dump_json(indent=2), encoding="utf-8")
    return manifest
