# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Local web UI — a thin HTTP layer over the engine, in the shape of the Synthetic
Data Designer's: a step rail on the left, one view per step, no build step, no CDN.

Every endpoint unpacks a request, calls one engine function and returns its
result. Logic belongs in the engine where the CLI can reach it too.

- **Runs happen on a worker thread, not in the request.** A run against a
  hosted endpoint takes minutes; the browser gets a job id and polls.
- **The gate needs no model.** ``/api/gate`` marks a briefing typed in the
  browser against an item's sealed key, so the catch can be shown offline.
- **The tamper demo never touches a real run.** It copies the run, edits one
  digit in the copy, verifies both and returns what the verifier said.
- **Paths from the browser are untrusted.** Pack, run and transcript names are
  resolved against their roots before anything is read.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import threading
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from evidence import __version__
from evidence.adapters.nvidia_build import endpoint_for
from evidence.checks import available_checks, run_checks
from evidence.contracts.item import BenchmarkItem
from evidence.evidence import verify_run, write_evidence
from evidence.pack import Pack, load_pack
from evidence.regulations import assess
from evidence.runner import run_pack

_BODY = Body(...)
_OPTIONAL_BODY = Body(default={})
_FILE = File(...)
_OPTIONAL_FILE = File(default=None)
_FORM = Form(...)
_OPTIONAL_FORM = Form(default=None)
STATIC = Path(__file__).parent / "static"
ROOT = Path(os.environ.get("EVIDENCE_ROOT") or Path.cwd())
PACKS = ROOT / "packs"
RUNS = ROOT / "runs"
_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()

app = FastAPI(title="Credit Evidence Engine", version=__version__)


# ----------------------------------------------------------------- helpers


def _safe_name(name: str, what: str) -> str:
    if not _SAFE.match(name) or ".." in name:
        raise HTTPException(400, f"invalid {what} name")
    return name


def _pack(pack_id: str) -> Pack:
    path = PACKS / _safe_name(pack_id, "pack")
    if not (path / "items.jsonl").is_file():
        raise HTTPException(404, f"pack {pack_id} not found")
    return load_pack(path)


def _run_dir(run_id: str) -> Path:
    path = RUNS / _safe_name(run_id, "run")
    if not (path / "manifest.json").is_file():
        raise HTTPException(404, f"run {run_id} not found")
    return path


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _item_summary(item) -> dict[str, Any]:
    g = item.grading
    return {
        "item_id": item.item_id,
        "case": item.item_id.split(":")[2],
        "disposition": g.disposition,
        "difficulty": item.tags.get("difficulty"),
        "must_state": [g.omission_labels.get(r, r) for r in g.omission_refs],
        "drivers": [g.driver_labels.get(r, r) for r in g.driver_refs],
        "decoys": [r for r in g.decoy_refs if g.decoy_aliases.get(r)],
        "flip": [f.model_dump() for f in g.flip_refs],
        "checks": item.deterministic_checks,
        "judges": item.judges,
    }


# ------------------------------------------------------------------- packs


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    roles = {}
    for role in ("assistant", "judge", "embed"):
        ep = endpoint_for(role)
        roles[role] = {
            "model": ep.model_id,
            "endpoint": ep.base_url,
            "where": "cloud" if ep.is_build else "on-prem",
        }
    return {
        "version": __version__,
        "checks": available_checks(),
        "roles": roles,
        "has_key": bool(os.environ.get("NVIDIA_API_KEY")),
    }


@app.get("/api/packs")
def packs() -> list[dict[str, Any]]:
    out = []
    for path in sorted(PACKS.glob("*/items.jsonl")):
        try:
            p = load_pack(path.parent)
        except Exception as exc:  # noqa: BLE001 — a broken pack is listed, not hidden
            out.append({"pack_id": path.parent.name, "error": str(exc)})
            continue
        out.append(
            {
                "pack_id": p.pack_id,
                "version": p.version,
                "items": len(p.items),
                "domain": p.manifest.get("domain"),
                "checks": p.checks_declared(),
                "judges": p.judges_declared(),
                "jurisdiction": p.regulatory_context.jurisdiction if p.regulatory_context else None,
                "obligations": [
                    {"id": o["id"], "title": o.get("title"), "level": o.get("level")}
                    for o in p.obligations.get("obligations", [])
                ],
                "sdd": p.manifest.get("sdd"),
                "warnings": p.warnings,
            }
        )
    return out


@app.get("/api/packs/{pack_id}/items")
def pack_items(pack_id: str) -> list[dict[str, Any]]:
    return [_item_summary(i) for i in _pack(pack_id).items]


@app.get("/api/packs/{pack_id}/items/{case}")
def pack_item(pack_id: str, case: str) -> dict[str, Any]:
    for item in _pack(pack_id).items:
        if item.item_id.split(":")[2] == _safe_name(case, "case"):
            return _item_summary(item) | {
                "prompt": item.prompt,
                "documents": [{"renderer": c.renderer, "content": c.content} for c in item.context],
            }
    raise HTTPException(404, "case not found")


@app.post("/api/gate")
def gate(payload: dict[str, Any] = _BODY) -> dict[str, Any]:
    """Mark a briefing against an item's key. No model involved."""
    pack = _pack(str(payload.get("pack", "")))
    case = _safe_name(str(payload.get("case", "")), "case")
    briefing = str(payload.get("briefing", ""))
    item = next((i for i in pack.items if i.item_id.split(":")[2] == case), None)
    if item is None:
        raise HTTPException(404, "case not found")
    names = payload.get("checks") or item.deterministic_checks
    results = run_checks(list(names), output=briefing, item=item)
    return {"results": [{"name": r.name} | r.to_score() for r in results]}


@app.get("/api/packs/{pack_id}/rules")
def pack_rules(pack_id: str) -> dict[str, Any]:
    return assess(_pack(pack_id).regulatory_context).model_dump()


@app.get("/api/corpora")
def corpora() -> list[dict[str, Any]]:
    from evidence.corpus import list_corpora

    return list_corpora()


@app.get("/api/corpora/{jurisdiction}/passages")
def corpus_passages(jurisdiction: str) -> list[dict[str, Any]]:
    from evidence.corpus import default_regulations_root

    path = (
        default_regulations_root() / _safe_name(jurisdiction, "corpus") / "index" / "passages.jsonl"
    )
    if not path.is_file():
        raise HTTPException(404, "corpus not built")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _corpus_worker(job_id: str, jurisdiction: str) -> None:
    job = _jobs[job_id]
    try:
        from evidence.corpus import build_corpus

        m = build_corpus(jurisdiction)
        with _lock:
            job.update(status="done", passages=m["passages"], corpus_sha256=m["corpus_sha256"])
    except Exception as exc:  # noqa: BLE001
        with _lock:
            job.update(status="error", error=f"{type(exc).__name__}: {exc}")


@app.post("/api/corpora/{jurisdiction}/build")
def build_corpus_job(jurisdiction: str) -> dict[str, Any]:
    j = _safe_name(jurisdiction, "corpus")
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {"status": "running", "kind": "corpus", "log": [], "done": 0, "total": 1}
    threading.Thread(target=_corpus_worker, args=(job_id, j), daemon=True).start()
    return {"job_id": job_id, "jurisdiction": j}


@app.get("/api/schema/item")
def item_schema() -> dict[str, Any]:
    """The pack format: JSON schema of one line of items.jsonl."""
    return BenchmarkItem.model_json_schema()


def _build_worker(job_id: str, opts: dict[str, Any]) -> None:
    job = _jobs[job_id]
    try:
        from evidence.packs.credit_underwriting import build

        manifest = build(
            opts["n"],
            opts["keep"],
            opts["seed"],
            PACKS / opts["pack_id"],
            opts["pack_id"],
            opts.get("spec"),
        )
        with _lock:
            job.update(
                status="done",
                pack_id=opts["pack_id"],
                items=manifest["items"],
                population=manifest.get("population"),
            )
    except ImportError:
        with _lock:
            job.update(
                status="error",
                error="Synthetic Data Designer is not installed: pip install -e '.[generate]'",
            )
    except Exception as exc:  # noqa: BLE001
        with _lock:
            job.update(status="error", error=f"{type(exc).__name__}: {exc}")


@app.post("/api/packs/build")
async def build_pack(
    pack_id: str = _FORM,
    n: int = _FORM,
    keep: int = _FORM,
    seed: int = _FORM,
    spec: UploadFile | None = _OPTIONAL_FILE,
) -> dict[str, Any]:
    """Generate a new pack from an SDD spec (uploaded, or the bundled recipe)."""
    pack_id = _safe_name(pack_id, "pack")
    if (PACKS / pack_id / "items.jsonl").is_file():
        raise HTTPException(400, f"pack {pack_id} already exists")
    spec_path = None
    if spec is not None and spec.filename:
        if not spec.filename.lower().endswith((".yaml", ".yml")):
            raise HTTPException(400, "the spec must be a YAML file")
        (PACKS / pack_id).mkdir(parents=True, exist_ok=True)
        spec_path = PACKS / pack_id / "spec.yaml"
        spec_path.write_bytes(await spec.read())
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {"status": "running", "kind": "build", "log": [], "done": 0, "total": 1}
    threading.Thread(
        target=_build_worker,
        args=(
            job_id,
            {
                "pack_id": pack_id,
                "n": max(50, min(n, 20000)),
                "keep": max(1, min(keep, 500)),
                "seed": seed,
                "spec": spec_path,
            },
        ),
        daemon=True,
    ).start()
    return {"job_id": job_id, "pack_id": pack_id}


@app.post("/api/packs/upload")
async def upload_pack(
    archive: UploadFile = _FILE, pack_id: str | None = _OPTIONAL_FORM
) -> dict[str, Any]:
    """Install a pack built elsewhere: a zip with items.jsonl and manifest.json (+ obligations)."""
    data = await archive.read()
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise HTTPException(400, "not a zip file") from exc
    names = {Path(n).name: n for n in zf.namelist() if not n.endswith("/")}
    if "items.jsonl" not in names or "manifest.json" not in names:
        raise HTTPException(400, "the zip must contain items.jsonl and manifest.json")
    manifest = json.loads(zf.read(names["manifest.json"]))
    pid = _safe_name(pack_id or str(manifest.get("pack_id", "")), "pack")
    dest = PACKS / pid
    if (dest / "items.jsonl").is_file():
        raise HTTPException(400, f"pack {pid} already exists")
    dest.mkdir(parents=True, exist_ok=True)
    for base, member in names.items():
        if base in (
            "items.jsonl",
            "manifest.json",
            "obligations.yaml",
            "regulatory_context.json",
            "README.md",
        ):
            (dest / base).write_bytes(zf.read(member))
    try:
        pack = load_pack(dest)
    except Exception as exc:  # noqa: BLE001 — report the validation error, remove the pack
        shutil.rmtree(dest)
        raise HTTPException(400, f"pack rejected: {exc}") from exc
    return {"pack_id": pack.pack_id, "items": len(pack.items), "warnings": pack.warnings}


# -------------------------------------------------------------------- runs


def _job_worker(job_id: str, pack: Pack, out: Path, opts: dict[str, Any]) -> None:
    job = _jobs[job_id]

    def log(line: str) -> None:
        with _lock:
            job["log"].append(line)
            m = re.match(r"\s*(\d+)/(\d+)", line)
            if m:
                job["done"], job["total"] = int(m.group(1)), int(m.group(2))

    try:
        manifest = run_pack(
            pack,
            out,
            repeats=opts["repeats"],
            judge=opts["judge"],
            limit=opts["limit"],
            log=log,
            should_stop=lambda: job.get("cancel", False),
        )
        if manifest["transcripts"]:
            write_evidence(out, pack.obligations)
        with _lock:
            job.update(
                status="cancelled" if manifest["cancelled"] else "done",
                run_id=manifest["run_id"],
                transcripts=manifest["transcripts"],
            )
    except Exception as exc:  # noqa: BLE001 — the browser needs the message, not a 500
        with _lock:
            job.update(status="error", error=f"{type(exc).__name__}: {exc}")


@app.post("/api/run")
def start_run(payload: dict[str, Any] = _BODY) -> dict[str, Any]:
    pack = _pack(str(payload.get("pack", "")))
    repeats = max(1, min(int(payload.get("repeats", 1)), 10))
    limit = payload.get("limit")
    limit = max(1, min(int(limit), len(pack.items))) if limit else None
    judge = bool(payload.get("judge", True))
    corpus = payload.get("corpus", "EU")
    corpus = None if corpus in (None, "", "none") else _safe_name(str(corpus), "corpus")
    if not os.environ.get("NVIDIA_API_KEY") and endpoint_for("assistant").is_build:
        raise HTTPException(400, "NVIDIA_API_KEY is not set and the assistant is on NVIDIA Build")
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    out = RUNS / f"{pack.pack_id}-{stamp}"
    job_id = uuid.uuid4().hex[:12]
    total = (limit or len(pack.items)) * repeats
    _jobs[job_id] = {
        "status": "running",
        "done": 0,
        "total": total,
        "log": [],
        "run_id": out.name,
        "started": stamp,
    }
    threading.Thread(
        target=_job_worker,
        args=(
            job_id,
            pack,
            out,
            {"repeats": repeats, "judge": judge, "limit": limit, "corpus": corpus},
        ),
        daemon=True,
    ).start()
    return {"job_id": job_id, "run_id": out.name, "total": total}


@app.post("/api/run/{job_id}/cancel")
def cancel_run(job_id: str) -> dict[str, Any]:
    """Ask the worker to stop before its next model call. Completed briefings are kept."""
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    with _lock:
        job["cancel"] = True
        job["log"].append("  cancel requested — finishing the call in flight")
    return {"job_id": job_id, "cancel": True}


@app.get("/api/run/{job_id}")
def run_status(job_id: str) -> dict[str, Any]:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    with _lock:
        return dict(job)


@app.get("/api/runs")
def runs() -> list[dict[str, Any]]:
    out = []
    for path in sorted(RUNS.glob("*/manifest.json"), reverse=True):
        m = _read_json(path)
        summary_path = path.parent / "evidence" / "summary.json"
        checks = _read_json(summary_path)["checks"] if summary_path.is_file() else {}
        out.append(
            {
                "run_id": path.parent.name,
                "pack": m.get("pack", {}),
                "sut": m.get("sut", {}),
                "judge": m.get("judge"),
                "repeats": m.get("repeats"),
                "transcripts": m.get("transcripts"),
                "finished_at": m.get("finished_at"),
                "sealed": (path.parent / "checksums.sha256").is_file(),
                "checks": {
                    k: {
                        "passed": v["passed"],
                        "failed": v["failed"],
                        "gated": v["gated"],
                        "mean_value": v["mean_value"],
                    }
                    for k, v in checks.items()
                },
            }
        )
    return out


@app.get("/api/runs/{run_id}")
def run_detail(run_id: str) -> dict[str, Any]:
    path = _run_dir(run_id)
    ev = path / "evidence"
    return {
        "run_id": run_id,
        "manifest": _read_json(path / "manifest.json"),
        "summary": _read_json(ev / "summary.json") if (ev / "summary.json").is_file() else None,
        "report": (ev / "report.md").read_text(encoding="utf-8")
        if (ev / "report.md").is_file()
        else None,
        "regulations": _read_json(path / "regulations.json")
        if (path / "regulations.json").is_file()
        else None,
        "transcripts": sorted(p.name for p in (path / "transcripts").glob("*.json")),
        "sealed": (path / "checksums.sha256").is_file(),
    }


@app.get("/api/runs/{run_id}/results")
def run_results(run_id: str) -> list[dict[str, Any]]:
    path = _run_dir(run_id) / "results.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


@app.get("/api/runs/{run_id}/transcripts/{name}")
def transcript(run_id: str, name: str) -> Any:
    path = _run_dir(run_id) / "transcripts" / _safe_name(name, "transcript")
    if not path.is_file():
        raise HTTPException(404, "transcript not found")
    return _read_json(path)


@app.post("/api/runs/{run_id}/verify")
def verify(run_id: str, payload: dict[str, Any] = _OPTIONAL_BODY) -> dict[str, Any]:
    path = _run_dir(run_id)
    recompute = bool(payload.get("recompute"))
    pack = None
    if recompute:
        pack_id = _read_json(path / "manifest.json")["pack"]["pack_id"]
        pack = _pack(pack_id)
    v = verify_run(path, pack, recompute=recompute)
    return v.__dict__


@app.post("/api/runs/{run_id}/tamper-demo")
def tamper_demo(run_id: str, payload: dict[str, Any] = _OPTIONAL_BODY) -> dict[str, Any]:
    """Copy the run, change one digit in one transcript, verify both. The original is untouched."""
    src = _run_dir(run_id)
    if not (src / "checksums.sha256").is_file():
        raise HTTPException(400, "run is not sealed")
    dst = RUNS / f"{run_id}-tampered"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    names = sorted(p.name for p in (dst / "transcripts").glob("*.json"))
    if not names:
        raise HTTPException(400, "run has no transcripts")
    name = _safe_name(str(payload.get("transcript") or names[0]), "transcript")
    target = dst / "transcripts" / name
    text = target.read_text(encoding="utf-8")
    m = re.search(r"(\d)(\d)(?=%|\s|\.|,)", text[text.find('"output"') :])
    if not m:
        raise HTTPException(400, "no digit to change in that transcript")
    pos = text.find('"output"') + m.start(2)
    new_digit = str((int(text[pos]) + 1) % 10)
    edited = text[:pos] + new_digit + text[pos + 1 :]
    target.write_text(edited, encoding="utf-8")
    return {
        "original": verify_run(src).__dict__,
        "tampered": verify_run(dst).__dict__,
        "edit": {
            "transcript": name,
            "from": text[pos - 12 : pos + 4],
            "to": edited[pos - 12 : pos + 4],
        },
        "copy": dst.name,
    }


# ------------------------------------------------------------------ static


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/", StaticFiles(directory=STATIC), name="static")


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="warning")
