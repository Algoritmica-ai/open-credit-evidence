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

import importlib.util
import io
import json
import os
import re
import shutil
import tempfile
import threading
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from evidence import __version__
from evidence.adapters.nvidia_build import endpoint_for
from evidence.checks import available_checks, run_checks
from evidence.contracts.item import BenchmarkItem
from evidence.evidence import verify_run, write_evidence
from evidence.evidence.readers import READERS
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

# A hosted instance (a Hugging Face Space, say) runs from a read-only image as a
# user who cannot write to it. EVIDENCE_WORKSPACE names a writable directory;
# packs, runs and regulations are copied there once and used from there.
# EVIDENCE_SHARED tells the page it is a shared demo: the models are whatever
# the environment points at (NVIDIA Build, usually), runs are capped, and
# nothing uploaded is private.
WORKSPACE = Path(os.environ["EVIDENCE_WORKSPACE"]) if os.environ.get("EVIDENCE_WORKSPACE") else None
SHARED = bool(os.environ.get("EVIDENCE_SHARED"))
SHARED_MAX_ITEMS = 5
SHARED_MAX_REPEATS = 2


def _seed_workspace() -> tuple[Path, Path]:
    if WORKSPACE is None:
        return ROOT / "packs", ROOT / "runs"
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    for name in ("packs", "runs", "regulations"):
        src, dst = ROOT / name, WORKSPACE / name
        if src.is_dir() and not dst.exists():
            shutil.copytree(src, dst)
    os.environ.setdefault("EVIDENCE_RULESETS_DIR", str(WORKSPACE / "regulations"))
    return WORKSPACE / "packs", WORKSPACE / "runs"


PACKS, RUNS = _seed_workspace()
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
        "shared": SHARED,
        "limits": {"items": SHARED_MAX_ITEMS, "repeats": SHARED_MAX_REPEATS} if SHARED else None,
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


SDD_LINKS = {
    "space": "https://huggingface.co/spaces/Algoritmica/synthetic-data-designer",
    "source": "https://github.com/Algoritmica-ai/deeploans/tree/main/synthetic-data-designer",
}


def _spec_path(pack: Pack) -> Path | None:
    """The SDD recipe a pack was generated from: a repo path, or spec.yaml kept in the pack."""
    name = (pack.manifest.get("sdd") or {}).get("spec")
    if not name:
        return None
    for base in (ROOT, pack.path):
        path = (base / name).resolve()
        if path.is_file() and path.suffix in (".yaml", ".yml") and (
            path.is_relative_to(ROOT.resolve()) or path.is_relative_to(pack.path.resolve())
        ):
            return path
    return None


def _recipe(spec: Path) -> dict[str, Any]:
    """What the recipe hides, what it writes out, and what has no path to the outcome.

    Read from the YAML itself, so it works without SDD installed. A column is
    hidden when its role is ``helper`` (dropped before the data is written),
    read from the hidden tier when ``derived``, and has no path to the outcome
    when its description says DECOY.
    """
    doc = yaml.safe_load(spec.read_text(encoding="utf-8")) or {}
    cols = doc.get("columns") or []
    helpers = [c["name"] for c in cols if c.get("role") == "helper"]
    return {
        "title": (doc.get("meta") or {}).get("title"),
        "hidden": [n for n in helpers if not n.startswith("_")],
        "noise_terms": sum(1 for n in helpers if n.startswith("_")),
        "derived": [c["name"] for c in cols if c.get("role") == "derived"],
        "independent": [
            c["name"] for c in cols
            if c.get("role") == "static" and c["name"] != "application_id"
            and not str(c.get("description", "")).upper().startswith("DECOY")
        ],
        "no_path": [
            c["name"] for c in cols
            if str(c.get("description", "")).upper().startswith("DECOY")
        ],
    }


@app.get("/api/packs/{pack_id}/sdd")
def pack_sdd(pack_id: str) -> dict[str, Any]:
    """Where a pack's cases came from: the SDD recipe, the run of it, and the scorecard's cut."""
    pack = _pack(pack_id)
    spec = _spec_path(pack)
    recipe = _recipe(spec) if spec else None
    marked = sorted({r for i in pack.items for r in i.grading.decoy_refs})
    return {
        "pack_id": pack.pack_id,
        "sdd": pack.manifest.get("sdd"),
        "population": pack.manifest.get("population"),
        "cases": len(pack.items),
        "scorecard_version": pack.manifest.get("scorecard_version"),
        "built_at": pack.manifest.get("built_at"),
        "recipe": recipe,
        "decoys_marked": marked,
        "no_path_not_marked": sorted(set(recipe["no_path"]) - set(marked)) if recipe else [],
        "spec_download": f"/api/packs/{pack.pack_id}/spec" if spec else None,
        "sdd_installed": importlib.util.find_spec("sdd") is not None,
        "links": SDD_LINKS,
    }


@app.get("/api/packs/{pack_id}/spec")
def pack_spec(pack_id: str) -> FileResponse:
    spec = _spec_path(_pack(pack_id))
    if spec is None:
        raise HTTPException(404, "this pack does not carry its SDD recipe")
    return FileResponse(spec, media_type="application/yaml", filename=spec.name)


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


@app.get("/api/packs/{pack_id}/coverage")
def pack_coverage(pack_id: str) -> dict[str, Any]:
    """What the pack claims per EU AI Act article, which check tests it and why, and the text."""
    from evidence.aggregate import by_obligation
    from evidence.corpus import default_regulations_root

    pack = _pack(pack_id)
    rows = by_obligation(pack.obligations, {})
    corpus = str(pack.obligations.get("corpus") or "EU")
    passages: dict[str, Any] = {}
    path = default_regulations_root() / _safe_name(corpus, "corpus") / "index" / "passages.jsonl"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line:
                rec = json.loads(line)
                passages[rec["passage_id"]] = rec
    return {
        "framework": pack.obligations.get("framework"),
        "in_scope_because": pack.obligations.get("in_scope_because"),
        "corpus": corpus,
        "obligations": rows,
        "passages": {
            pid: passages[pid] for ob in rows for pid in ob["passages"] if pid in passages
        },
    }


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
    if SHARED:
        repeats = min(repeats, SHARED_MAX_REPEATS)
        limit = min(limit or SHARED_MAX_ITEMS, SHARED_MAX_ITEMS)
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
        if path.parent.name.endswith("-tampered"):
            continue  # left behind by the tamper demo of an older version
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
        # decision, root causes, recommendations — absent on runs written by an older engine
        **{
            name: _read_json(ev / f"{name}.json") if (ev / f"{name}.json").is_file() else None
            for name in ("decision", "diagnosis", "recommendations")
        },
        "transcripts": sorted(p.name for p in (path / "transcripts").glob("*.json")),
        "sealed": (path / "checksums.sha256").is_file(),
        "readers": [
            {"name": name} | meta | {"available": (ev / "readers" / f"{name}.md").is_file()}
            for name, meta in READERS.items()
        ],
    }


@app.get("/api/runs/{run_id}/pdf/{name}")
def run_pdf(run_id: str, name: str) -> Response:
    """One report as a PDF, with the run's timestamps and checksums. Needs Chrome on the host."""
    from evidence.evidence.export import DOCUMENTS, export_run, find_chrome

    if name not in DOCUMENTS:
        raise HTTPException(404, f"no document {name!r}; documents: {', '.join(DOCUMENTS)}")
    run = _run_dir(run_id)
    if not (run / "checksums.sha256").is_file():
        raise HTTPException(400, "run is not sealed")
    if find_chrome() is None:
        raise HTTPException(501, "PDF export needs Chrome or Chromium on this host; use Print")
    with tempfile.TemporaryDirectory(prefix="evidence-pdf-") as tmp:
        try:
            res = export_run(run, Path(tmp), [name])
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        data = Path(res["written"][0]).read_bytes()
    return Response(data, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{run_id}-{name}.pdf"'})


@app.get("/api/runs/{run_id}/readers/{name}")
def run_reader(run_id: str, name: str) -> FileResponse:
    """One reader's report, as markdown: business, credit-risk, compliance, operations, …"""
    if name not in READERS:
        raise HTTPException(404, f"no reader {name!r}; readers: {', '.join(READERS)}")
    path = _run_dir(run_id) / "evidence" / "readers" / f"{name}.md"
    if not path.is_file():
        raise HTTPException(404, "this run was written before reader reports; rewrite it")
    return FileResponse(path, media_type="text/markdown; charset=utf-8",
                        filename=f"{run_id}-{name}.md")


@app.get("/api/compare")
def compare(before: str, after: str) -> dict[str, Any]:
    """Did a change help? Two runs of the same pack, case by case."""
    from evidence.evidence.compare import compare_runs

    if before == after:
        raise HTTPException(400, "choose two different runs")
    return compare_runs(_run_dir(before), _run_dir(after))


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
    """Copy the run, change one digit in one transcript, verify both. The original is untouched.

    The copy lives in a temporary directory and is deleted once verified, so it
    never appears among the runs as if it were one.
    """
    src = _run_dir(run_id)
    if not (src / "checksums.sha256").is_file():
        raise HTTPException(400, "run is not sealed")
    with tempfile.TemporaryDirectory(prefix="evidence-tamper-") as tmp:
        return _tamper_copy(src, Path(tmp) / f"{run_id}-tampered", payload)


def _tamper_copy(src: Path, dst: Path, payload: dict[str, Any]) -> dict[str, Any]:
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
        "copy": f"{dst.name} (temporary, deleted after verifying)",
    }


# ------------------------------------------------------------------ static


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/", StaticFiles(directory=STATIC), name="static")


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="warning")
