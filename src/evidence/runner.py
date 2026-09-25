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
import os
import re
import subprocess
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from evidence import __version__
from evidence.adapters.nvidia_build import BUILD_HOST, chat, endpoint_for
from evidence.checks import run_checks
from evidence.contracts.item import BenchmarkItem
from evidence.contracts.transcript import SUTPins, Transcript
from evidence.corpus import Corpus
from evidence.fingerprint import model_fingerprint
from evidence.judge import judge_readability
from evidence.pack import Pack
from evidence.regulations import assess

ASSISTANT_MAX_TOKENS = 900


class EmbedderMismatch(RuntimeError):
    """The embedder at hand would not retrieve from the index as the one that built it."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _safe(item_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", item_id)


def transcript_path(out: Path, item_id: str, repeat: int) -> Path:
    return out / "transcripts" / f"{_safe(item_id)}-r{repeat}.json"


def _call_window(transcripts: list[Transcript], started: str, calls_made: int) -> tuple[str, str]:
    """When the model calls happened, from the transcripts.

    A run re-scored from transcripts already on disk makes no calls; stamping it
    with the time of the re-score would say the whole run took no time at all.
    """
    if not transcripts:
        return started, _now()
    first = min(t.started_at for t in transcripts)
    last = max(
        datetime.fromisoformat(t.started_at) + timedelta(milliseconds=t.latency_ms or 0)
        for t in transcripts
    )
    end = _now() if calls_made else last.astimezone(UTC).isoformat(timespec="seconds")
    return min(first, started), end


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


def _fingerprint(role: str, log: Callable[[str], None]) -> dict[str, Any]:
    """The model serving ``role`` now. Never fails a run: an unreachable detail is recorded."""
    try:
        fp = model_fingerprint(role)
    except Exception as exc:  # noqa: BLE001 — a fingerprint must not cost the run
        fp = {"role": role, "level": "unavailable", "fingerprint": None, "error": str(exc)}
    fp["checked_at"] = _now()
    log(f"  {role} model {str(fp.get('fingerprint'))[:16]} ({fp['level']})")
    return fp


def call_assistant(item: BenchmarkItem, run_id: str, repeat: int,
                   fingerprint: str | None = None) -> Transcript:
    """One recorded call. The assistant sees the task prompt and every document."""
    user = item.documents_text()
    started = _now()
    r = chat("assistant", system=item.prompt, user=user, max_tokens=ASSISTANT_MAX_TOKENS)
    sut = SUTPins(
        model_id=r.model_id, prompt_version=r.prompt_version, params=r.params, endpoint=r.endpoint,
        fingerprint=fingerprint,
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
    corpus: Corpus | str | None = "EU",
    panel: bool = False,
    workers: int | None = None,
) -> dict[str, Any]:
    """Execute the pack. Returns the run manifest; writes transcripts and results.jsonl.

    ``panel`` says the three-agent panel will review these briefings: the single
    judge is then skipped (the panel's Reader, scoring each briefing alone, is the
    lone-judge view) and the manifest says so.

    ``workers`` memos are written and judged at once (default ``EVIDENCE_WORKERS``, else
    8); the checks are pure computation and take no time next to the model calls.

    ``corpus`` is the regulation corpus the judge retrieves from — a built
    :class:`Corpus`, a jurisdiction code, or None for a judge with no passages.
    A jurisdiction whose index is not built is reported and the judge runs
    without passages.

    ``should_stop`` is polled before every model call. When it returns True the
    run stops cleanly: what was completed is scored and sealed, the manifest
    records ``cancelled: true`` and the real transcript count, and a later run
    into the same directory resumes from the transcripts on disk.
    """
    judge = judge and not panel
    workers = workers or int(os.environ.get("EVIDENCE_WORKERS", "8"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "transcripts").mkdir(exist_ok=True)
    run_id = out.name
    items = pack.items[:limit] if limit else pack.items
    started = _now()

    results_path = out / "results.jsonl"
    # Judge records from an earlier pass over this directory are reused, like
    # transcripts: re-scoring a run must not cost model calls.
    prior_judge: dict[tuple[str, int], dict[str, Any]] = {}
    if results_path.is_file():
        for line in results_path.read_text(encoding="utf-8").splitlines():
            if line:
                rec = json.loads(line)
                if rec.get("check") == "readability" and rec.get("value") is not None:
                    prior_judge[(rec["item_id"], rec["repeat"])] = rec
    corpus_obj: Corpus | None = None
    corpus_note: str | None = None
    if judge and corpus is not None:
        if isinstance(corpus, Corpus):
            corpus_obj = corpus
        else:
            try:
                corpus_obj = Corpus(corpus)
            except FileNotFoundError as exc:
                corpus_note = str(exc)
                log(f"  warning: {exc}; judge runs without regulation passages")
    # Which model, exactly, served each role — taken just before the first call a
    # role makes in this pass, and again at the end. A pass that makes no calls
    # (a re-score from transcripts on disk) keeps what the earlier pass recorded:
    # today's servers did not write yesterday's briefings.
    previous = {}
    if (out / "manifest.json").is_file():
        previous = json.loads((out / "manifest.json").read_text(encoding="utf-8")).get("models") \
            or {}
    fps: dict[str, dict[str, Any]] = {}
    previous_corpus: dict[str, Any] = {}
    if (out / "manifest.json").is_file():
        previous_corpus = ((json.loads((out / "manifest.json").read_text(encoding="utf-8"))
                            .get("judge") or {}).get("corpus") or {})

    def fp_for(role: str) -> str | None:
        if role not in fps:
            fps[role] = _fingerprint(role, log)
        return fps[role].get("fingerprint")

    # The index is only valid for the embedder that built it. If this pass will
    # retrieve, check that before the first model call of any kind.
    embedder_check: dict[str, Any] | None = None
    if corpus_obj is not None and any(
        (judge and ("readability" in it.judges or judge is True))
        and (it.item_id, rep) not in prior_judge
        for it in items for rep in range(repeats)
    ):
        embedder_check = corpus_obj.check_embedder()
        if not embedder_check["ok"]:
            raise EmbedderMismatch(
                f"the embedder serving {embedder_check['query_embed_model']} does not reproduce "
                f"the {corpus_obj.jurisdiction} index (built with "
                f"{embedder_check['index_embed_model']}): cosine "
                f"{embedder_check['cosine']} on {embedder_check['probe']}, dimension "
                f"{embedder_check['dimension']} vs {embedder_check['index_dimension']}; needs "
                f"{embedder_check['min_cosine']}. Rebuild the index against this embedder "
                f"(evidence corpus build {corpus_obj.jurisdiction}) or point EVIDENCE_EMBED_* at "
                "the one that built it. No model was called."
            )
        log(f"  corpus {corpus_obj.jurisdiction}: embedder reproduces the index "
            f"(cosine {embedder_check['cosine']} on {embedder_check['probe']})")

    total = len(items) * repeats
    jobs = [(item, rep) for item in items for rep in range(repeats)]

    def wants_judge(item: BenchmarkItem) -> bool:
        return bool(judge and ("readability" in item.judges or judge is True))

    # Fingerprint each model once, before the calls fan out across threads.
    if any(not transcript_path(out, it.item_id, rep).is_file() for it, rep in jobs):
        fp_for("assistant")
    if any(wants_judge(it) and (it.item_id, rep) not in prior_judge for it, rep in jobs):
        fp_for("judge")
        if corpus_obj is not None:
            fp_for("embed")  # the retrieval query is embedded on the node

    lock = threading.Lock()
    progress = {"done": 0, "calls": 0, "failed": False}

    def one(job: tuple[BenchmarkItem, int]) -> tuple[Transcript, list[dict[str, Any]]] | None:
        """One memo: the assistant's call (or its transcript on disk), the checks, the judge."""
        item, rep = job
        if progress["failed"] or (should_stop is not None and should_stop()):
            return None
        try:
            path = transcript_path(out, item.item_id, rep)
            called = False
            if path.is_file():
                t = Transcript.model_validate_json(path.read_text(encoding="utf-8"))
            else:
                t = call_assistant(item, run_id, rep, fp_for("assistant"))
                path.write_text(t.model_dump_json(indent=2), encoding="utf-8")
                called = True
            names = checks if checks is not None else item.deterministic_checks
            rows = [{"item_id": item.item_id, "repeat": rep, "check": c.name} | c.to_score()
                    for c in run_checks(names, output=t.output, item=item)]
            if wants_judge(item):
                rec = prior_judge.get((item.item_id, rep))
                if rec is None:
                    rec = {"item_id": item.item_id, "repeat": rep, "check": "readability",
                           "model_fingerprint": fp_for("judge")}
                    rec |= judge_readability(output=t.output, item=item, corpus=corpus_obj)
                rows.append(rec)
        except BaseException:
            progress["failed"] = True  # the memos not yet started are not started
            raise
        with lock:
            progress["done"] += 1
            progress["calls"] += called
            log(f"  {progress['done']}/{total}  {item.item_id.split(':')[2]} r{rep}  "
                f"{t.latency_ms / 1000:.1f}s")
        return t, rows

    # Memos are independent: their model calls run side by side. The results keep the
    # pack's order, so a run written in parallel is the same as one written in sequence.
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        finished = list(pool.map(one, jobs))

    results: list[dict[str, Any]] = []
    transcripts: list[Transcript] = []
    judge_seen: dict[str, Any] | None = None
    cancelled = any(f is None for f in finished)
    for f in finished:
        if f is None:
            continue
        t, rows = f
        transcripts.append(t)
        results.extend(rows)
        rec = next((r for r in rows if r["check"] == "readability"), None)
        if rec is not None and judge_seen is None:
            judge_seen = {"model_id": rec["judge"].removeprefix("model:"),
                          "endpoint": rec.get("endpoint")}
    done = len(transcripts)
    calls_made = progress["calls"]

    with results_path.open("w", encoding="utf-8") as fh:
        for rec in results:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # What ran is what the transcripts say ran. The environment may have changed
    # since the first call; the manifest must describe the calls, not the .env.
    if transcripts:
        first = transcripts[0].sut
        sut_block = {
            "role": "assistant",
            "model_id": first.model_id,
            "endpoint": first.endpoint,
            "on_prem": bool(first.endpoint) and BUILD_HOST not in (first.endpoint or ""),
            "prompt_version": first.prompt_version,
            "params": first.params,
            "max_tokens": ASSISTANT_MAX_TOKENS,
            "endpoints_seen": sorted({t.sut.endpoint or "" for t in transcripts}),
        }
    else:
        ep = endpoint_for("assistant")
        sut_block = {
            "role": "assistant",
            "model_id": ep.model_id,
            "endpoint": ep.base_url,
            "on_prem": not ep.is_build,
            "max_tokens": ASSISTANT_MAX_TOKENS,
        }
    judge_block = None
    if judge and judge_seen:
        # Which corpus the judge saw is what its records say, not what this call
        # was given: records reused from an earlier pass may have had none.
        used = {r.get("corpus_sha256") for r in results if r.get("check") == "readability"}
        if corpus_obj is not None and used != {corpus_obj.sha256}:
            corpus_note = (
                "judge records carry no regulation passages" if used == {None}
                else f"judge records carry corpus sha256 {sorted(map(str, used))}"
            )
            corpus_obj.close()
            corpus_obj = None
        judge_block = {
            "model_id": judge_seen["model_id"],
            "endpoint": judge_seen["endpoint"],
            "corpus": (
                {
                    "jurisdiction": corpus_obj.jurisdiction,
                    "corpus_sha256": corpus_obj.sha256,
                    "passages": corpus_obj.manifest["passages"],
                    "embed_model": corpus_obj.manifest["embed_model"],
                    "index_backend": corpus_obj.backend,
                    "embedder_check": embedder_check or (
                        previous_corpus.get("embedder_check")
                        if previous_corpus.get("corpus_sha256") == corpus_obj.sha256 else None),
                    "source_check": corpus_obj.source_check(),
                }
                if corpus_obj
                else None
            ),
            "corpus_note": corpus_note,
            "on_prem": bool(judge_seen["endpoint"])
            and BUILD_HOST not in (judge_seen["endpoint"] or ""),
            "rubric": "readability",
        }
    models = dict(previous)
    for role, first in fps.items():
        last = _fingerprint(role, log)
        entry = first | {"checked_at": [first["checked_at"], last["checked_at"]]}
        if last.get("fingerprint") != first.get("fingerprint"):
            entry |= {"changed_during_run": True, "fingerprint_end": last.get("fingerprint")}
        models[role] = entry
    # A resumed run can hold briefings from more than one server start.
    seen = sorted({t.sut.fingerprint for t in transcripts if t.sut.fingerprint})
    if "assistant" in models and seen:
        models["assistant"]["seen_in_transcripts"] = seen
        if len(seen) > 1:
            models["assistant"]["changed_during_run"] = True

    regulatory = assess(pack.regulatory_context)
    window = _call_window(transcripts, started, calls_made)
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
        "sut": sut_block,
        "judge": judge_block,
        **({"single_judge": "skipped: the three-agent panel reviews these briefings"}
           if panel else {}),
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
        "models": models,
        "started_at": window[0],
        "finished_at": window[1],
        "scored_at": _now(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out / "regulations.json").write_text(regulatory.model_dump_json(indent=2), encoding="utf-8")
    if corpus_obj is not None:
        corpus_obj.close()
    return manifest
