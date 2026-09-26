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
        "designer": DESIGNER,
        "limits": {"items": SHARED_MAX_ITEMS, "repeats": SHARED_MAX_REPEATS} if SHARED else None,
    }


@app.get("/api/packs")
def packs() -> list[dict[str, Any]]:
    used: dict[str, int] = {}  # how many tests each case set has been used in
    for mf in RUNS.glob("*/manifest.json"):
        try:
            pid = (_read_json(mf).get("pack") or {}).get("pack_id")
        except (OSError, ValueError):
            continue
        if pid:
            used[pid] = used.get(pid, 0) + 1
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
                "bank_figures": bool(p.manifest.get("bank_figures")),
                "built_at": p.manifest.get("built_at"),
                "used_in_tests": used.get(p.pack_id, 0),
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
            opts.get("market", "sample"),
            opts.get("bank_figures", False),
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
    market: str = Form("sample"),
    bank_figures: bool = Form(False),
) -> dict[str, Any]:
    """Generate a new pack from an SDD spec (uploaded, or the bundled recipe)."""
    from evidence.packs.credit_underwriting import MARKETS

    pack_id = _safe_name(pack_id, "pack")
    if market not in MARKETS:
        raise HTTPException(400, f"market must be one of {sorted(MARKETS)}")
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
                "market": market,
                "bank_figures": bank_figures,
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
            panel=opts["panel"],
            setup=opts.get("setup", "as_is"),
            log=log,
            should_stop=lambda: job.get("cancel", False),
        )
        if manifest["transcripts"]:
            write_evidence(out, pack.obligations)
        if opts.get("panel") and manifest["transcripts"] and not manifest["cancelled"]:
            _panel_phase(job, pack, out, log)
        with _lock:
            job.update(
                status="cancelled" if manifest["cancelled"] or job.get("panel_stopped")
                else "done",
                phase="done",
                run_id=manifest["run_id"],
                transcripts=manifest["transcripts"],
            )
        if job.get("panel_remaining") and not job.get("cancel"):
            _finish_panel(job, pack, out)
    except Exception as exc:  # noqa: BLE001 — the browser needs the message, not a 500
        with _lock:
            job.update(status="error", error=f"{type(exc).__name__}: {exc}")


def _panel_phase(job: dict[str, Any], pack: Pack, out: Path, log: Any) -> None:
    """The three-agent panel over the finished run. It runs in the NemoClaw sandbox when
    EVIDENCE_PANEL_SSH names the cluster, else here against the judge endpoint. A panel
    that fails leaves the run sealed without it; the job says why."""
    from evidence import panel_run

    with _lock:
        job.update(phase="panel", done=0, total=job["total"])
        job["log"].append("  second opinion: three AI reviewers")
    runtime = "nemoclaw" if os.environ.get("EVIDENCE_PANEL_SSH") else "direct"
    workers = int(os.environ.get("EVIDENCE_PANEL_WORKERS", "8"))
    quorum = float(os.environ.get("EVIDENCE_PANEL_QUORUM", "0.9"))
    try:
        res = panel_run.panel_over_run(out, pack, runtime=runtime, workers=workers, log=log,
                                       should_stop=lambda: job.get("cancel", False),
                                       quorum=quorum if quorum < 1 else None,
                                       grace_s=float(os.environ.get("EVIDENCE_PANEL_GRACE_S",
                                                                    "60")))
        note = None if res["ok"] else res["message"]
        if res.get("stopped"):
            with _lock:
                job["panel_stopped"] = True
        if res.get("partial"):  # sealed at the quorum: the rest are reviewed after the result
            with _lock:
                job["panel_remaining"] = res["remaining"]
                job["log"].append(f"  panel sealed at {res['briefings']} of {res['planned']}; "
                                  f"{res['remaining']} more are reviewed next")
    except Exception as exc:  # noqa: BLE001 — the evaluation stands without the panel
        note = f"{type(exc).__name__}: {exc}"
    if note:
        with _lock:
            job["panel_error"] = note
            job["log"].append(f"  panel stopped: {note}")


def _finish_panel(job: dict[str, Any], pack: Pack, out: Path) -> None:
    """After a result sealed at the quorum: review the briefings that were left, and seal
    the run again. The test is already done; the job says how many are still coming."""
    from evidence import panel_run

    runtime = "nemoclaw" if os.environ.get("EVIDENCE_PANEL_SSH") else "direct"
    try:
        res = panel_run.panel_over_run(out, pack, runtime=runtime,
                                       workers=int(os.environ.get("EVIDENCE_PANEL_WORKERS", "8")),
                                       log=lambda s: None)
        with _lock:
            job["panel_remaining"] = 0 if res["ok"] else job.get("panel_remaining")
            if not res["ok"]:
                job["panel_error"] = res["message"]
    except Exception as exc:  # noqa: BLE001
        with _lock:
            job["panel_error"] = f"{type(exc).__name__}: {exc}"


@app.get("/api/jobs")
def jobs() -> list[dict[str, Any]]:
    """Tests running now, newest first, for the home page."""
    with _lock:
        rows = [{"job_id": k} | {x: v.get(x) for x in ("status", "phase", "done", "total",
                                                       "run_id", "started", "panel")}
                for k, v in _jobs.items() if v.get("status") == "running"]
    return sorted(rows, key=lambda r: r["started"] or "", reverse=True)


def make_fresh_pack(from_pack: str, keep: int | None = None,
                    bank_figures: bool = True) -> dict[str, Any]:
    """New cases from the same recipe, market and size as ``from_pack``, with a new seed and
    the figures the bank's systems compute. Checked to share no case file with any other
    pack of the same family: the assistant has never seen them."""
    import random

    from evidence.packs.credit_underwriting import build

    src = _pack(from_pack)
    m = src.manifest
    family = re.sub(r"-s\d+$", "", src.pack_id)
    used = {int(x) for p in PACKS.glob(f"{family}-s*")
            if (x := p.name.rsplit("-s", 1)[1]).isdigit()}
    used.add(int((m.get("sdd") or {}).get("seed") or 0))
    seed = next(s for s in iter(lambda: random.SystemRandom().randrange(1000, 100000), None)
                if s not in used)
    pack_id = f"{family}-s{seed}"
    t0 = datetime.now(UTC)
    keep = max(5, min(int(keep or len(src.items)), 200))
    generated = max(int((m.get("sdd") or {}).get("generated") or 700), keep * 35)
    # only referred applications become cases: when a seed yields too few, generate more
    for _ in range(4):
        manifest = build(generated, keep, seed, PACKS / pack_id, pack_id, None,
                         m.get("market") or "sample", bank_figures=bank_figures)
        if manifest["items"] >= keep:
            break
        generated *= 2
    fresh = _pack(pack_id)
    seen = {c.content for p in PACKS.glob(f"{family}*/items.jsonl") if p.parent.name != pack_id
            for it in load_pack(p.parent).items for c in it.context
            if c.renderer == "application_form"}
    shared = sum(1 for it in fresh.items for c in it.context
                 if c.renderer == "application_form" and c.content in seen)
    return {"pack_id": pack_id, "seed": seed, "from": src.pack_id, "items": manifest["items"],
            "shared_with_other_packs": shared, "seconds": round(
                (datetime.now(UTC) - t0).total_seconds(), 1), "links": SDD_LINKS}


@app.post("/api/packs/fresh")
def fresh_pack(payload: dict[str, Any] = _BODY) -> dict[str, Any]:
    """Generate new cases the assistant has never seen, with the Synthetic Data Designer."""
    try:
        return make_fresh_pack(str(payload.get("from", "")), payload.get("keep"),
                               bool(payload.get("bank_figures", True)))
    except ImportError as exc:
        raise HTTPException(501, "the Synthetic Data Designer is not installed: "
                            "pip install -e '.[generate]'") from exc


def _retest_worker(job_id: str, from_run: str, setup: str) -> None:
    """New cases, then the assistant as it is and with the change on those same cases,
    then the comparison: the proof, or not, that the change helps."""
    from evidence.evidence.compare import compare_runs

    job = _jobs[job_id]

    def phase(name: str, total: int = 0) -> None:
        with _lock:
            job.update(phase=name, done=0, total=total)

    def log(line: str) -> None:
        with _lock:
            job["log"].append(line)
            mm = re.match(r"\s*(\d+)/(\d+)", line)
            if mm:
                job["done"], job["total"] = int(mm.group(1)), int(mm.group(2))

    try:
        base = _read_json(_run_dir(from_run) / "manifest.json")
        phase("cases")
        # new cases, as many as the test being re-tested used
        cases = int(base.get("transcripts") or 0) // max(1, int(base.get("repeats") or 1))
        fresh = make_fresh_pack(base["pack"]["pack_id"], cases or None)
        pack = _pack(fresh["pack_id"])
        with _lock:
            job.update(pack_id=fresh["pack_id"], seed=fresh["seed"],
                       shared_with_other_packs=fresh["shared_with_other_packs"])
        stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
        runs_made = {}
        for name, which in (("before", "as_is"), ("after", setup)):
            if job.get("cancel"):
                break
            phase(name, len(pack.items) * int(base.get("repeats") or 3))
            out = RUNS / f"{fresh['pack_id']}-{stamp}-{name}"
            mf = run_pack(pack, out, repeats=int(base.get("repeats") or 3), judge=False,
                          setup=which, log=log, should_stop=lambda: job.get("cancel", False))
            if mf["transcripts"]:
                write_evidence(out, pack.obligations)
            runs_made[name] = out.name
            with _lock:
                job[name] = out.name
        if len(runs_made) == 2 and not job.get("cancel"):
            phase("compare")
            c = compare_runs(RUNS / runs_made["before"], RUNS / runs_made["after"])
            with _lock:
                job["verdict"] = c["verdict"]
        with _lock:
            job.update(status="cancelled" if job.get("cancel") else "done", phase="done")
    except Exception as exc:  # noqa: BLE001 — the browser needs the message
        with _lock:
            job.update(status="error", error=f"{type(exc).__name__}: {exc}")


@app.post("/api/retest")
def retest(payload: dict[str, Any] = _BODY) -> dict[str, Any]:
    """Test a change on new cases: the assistant as it is and with the change, same cases."""
    from evidence.contracts.item import SETUPS

    from_run = _safe_name(str(payload.get("from_run", "")), "run")
    _run_dir(from_run)
    setup = str(payload.get("setup", "with_figures"))
    if setup not in SETUPS or setup == "as_is":
        raise HTTPException(400, f"setup must be one of {sorted(set(SETUPS) - {'as_is'})}")
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {"status": "running", "kind": "retest", "phase": "cases", "done": 0,
                     "total": 0, "log": [], "from_run": from_run, "setup": setup,
                     "started": datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")}
    threading.Thread(target=_retest_worker, args=(job_id, from_run, setup), daemon=True).start()
    return {"job_id": job_id}


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
    panel = bool(payload.get("panel", False)) and judge
    setup = str(payload.get("setup", "as_is"))
    if setup == "with_figures" and not any(i.has_bank_figures() for i in pack.items):
        raise HTTPException(400, "these cases hold no figures from the bank's systems")
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
        "phase": "memos",
        "panel": panel,
        "done": 0,
        "total": total,
        "log": [],
        "run_id": out.name,
        "started": stamp,
        "cases": limit or len(pack.items),
        "repeats": repeats,
    }
    threading.Thread(
        target=_job_worker,
        args=(
            job_id,
            pack,
            out,
            {"repeats": repeats, "judge": judge, "limit": limit, "corpus": corpus,
             "panel": panel, "setup": setup},
        ),
        daemon=True,
    ).start()
    return {"job_id": job_id, "run_id": out.name, "total": total}


@app.post("/api/run/{job_id}/cancel")
def cancel_run(job_id: str) -> dict[str, Any]:
    """Ask the worker to stop: no memo or panel review starts, and a review in progress ends
    at its next turn. Everything finished is kept and sealed."""
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    with _lock:
        job["cancel"] = True
        job["log"].append("  stop requested — finishing the calls in flight")
    return {"job_id": job_id, "cancel": True}


@app.get("/api/run/{job_id}")
def run_status(job_id: str) -> dict[str, Any]:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    with _lock:
        return dict(job)


def _headline(run: Path) -> dict[str, Any]:
    """What a business reader needs first: the verdict and how many memos had an error."""
    dec = run / "evidence" / "decision.json"
    verdict = _read_json(dec).get("verdict") if dec.is_file() else None
    bad: set[str] = set()
    memos: set[str] = set()
    res = run / "results.jsonl"
    if res.is_file():
        for line in res.read_text(encoding="utf-8").splitlines():
            if line:
                r = json.loads(line)
                key = f"{r['item_id']}#{r['repeat']}"
                memos.add(key)
                if r.get("passed") is False:
                    bad.add(key)
    return {"verdict": verdict, "memos": len(memos), "memos_with_error": len(bad),
            "reviewed": (run / "review" / "records.jsonl").is_file(),
            "panel": (run / "panel" / "records.jsonl").is_file()}


_numbers_lock = threading.Lock()


def _test_numbers(rows: list[dict[str, Any]]) -> dict[str, int]:
    """A short number per finished test (Test 1, Test 2, ...) in the order they finished,
    kept in runs/test-numbers.json so a number never changes once given."""
    path = RUNS / "test-numbers.json"
    with _numbers_lock:
        try:
            nums = {k: int(v) for k, v in json.loads(path.read_text()).items()}
        except (OSError, ValueError, AttributeError):
            nums = {}
        new = sorted((r for r in rows if r["run_id"] not in nums and r["sealed"]
                      and r["transcripts"]), key=lambda r: r.get("finished_at") or "")
        if new:
            top = max(nums.values(), default=0)
            for i, r in enumerate(new, 1):
                nums[r["run_id"]] = top + i
            try:
                path.write_text(json.dumps(nums, indent=1, sort_keys=True))
            except OSError:
                pass  # a read-only evidence folder: numbered for this listing only
        return nums


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
                "cases": (m.get("transcripts") or 0) // max(1, int(m.get("repeats") or 1)),
                "started_at": m.get("started_at"),
                "finished_at": m.get("finished_at"),
                "sealed": (path.parent / "checksums.sha256").is_file(),
                **_headline(path.parent),
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
    nums = _test_numbers(out)
    for r in out:
        r["test_no"] = nums.get(r["run_id"])
    return out


def _stages(run: Path) -> dict[str, Any]:
    """Where a run stands in test, review, improve, and the one next step."""
    from evidence import review

    q = _review_queue(run)
    s = review.summary(run, q)
    done = review.reviews(run)
    flagged = [m for m in q if m["lane"] in ("red", "amber")]
    checked = sum(1 for m in flagged if m["memo"] in done)
    fb = run / "feedback" / "manifest.json"
    if not done:
        rv = "not_started"
    elif checked < len(flagged):
        rv = "in_progress"
    else:
        rv = "done"
    if fb.is_file():
        im = "done"
    elif rv == "done" or s["needs_adjudication"] or s["settled"]:
        im = "in_progress"
    else:
        im = "not_started"
    step = "review" if rv != "done" else "improve" if im != "done" else "test"
    return {"review": rv, "improve": im, "next": step, "flagged": len(flagged),
            "flagged_checked": checked, "reviewed": len(done), "memos": len(q),
            "lanes": s["lanes"], "needs_adjudication": s["needs_adjudication"],
            "feedback_built": fb.is_file()}


@app.get("/api/overview")
def overview(run: str | None = None, pending: bool = False) -> dict[str, Any]:
    """The home page: the latest sealed test (or ``run``), where it stands, what is running;
    with ``pending``, also every test with flagged memos still to check."""
    rows = [r for r in runs() if r["sealed"] and r["transcripts"]]
    current = next((r for r in rows if r["run_id"] == run), None) if run else None
    if current is None and rows:
        current = max(rows, key=lambda r: r.get("finished_at") or "")
    out: dict[str, Any] = {"run": None, "jobs": jobs(), "tests": len(rows), "to_review": []}
    if current:
        out["run"] = {k: current[k] for k in ("run_id", "test_no", "pack", "sut", "started_at",
                                              "finished_at", "verdict", "memos",
                                              "memos_with_error", "panel", "cases", "repeats")}
        out["stages"] = _stages(_run_dir(current["run_id"]))
    # every test with flagged memos still to check, newest first
    newest = sorted(rows, key=lambda r: r.get("finished_at") or "", reverse=True)
    for r in newest if pending else []:
        st = out["stages"] if current and r["run_id"] == current["run_id"] else _stages(
            _run_dir(r["run_id"]))
        if st["flagged_checked"] < st["flagged"]:
            out["to_review"].append({k: r[k] for k in ("run_id", "test_no", "pack", "started_at",
                                                       "finished_at", "cases", "repeats")}
                                    | {"flagged": st["flagged"],
                                       "flagged_checked": st["flagged_checked"]})
    return out


@app.get("/api/runs/{run_id}")
def run_detail(run_id: str) -> dict[str, Any]:
    path = _run_dir(run_id)
    ev = path / "evidence"
    return {
        "run_id": run_id,
        "headline": _headline(path),
        "panel": _read_json(ev / "panel.json") if (ev / "panel.json").is_file() else None,
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


# ------------------------------------------------------------------ review and feedback


def _review_queue(run: Path) -> list[dict[str, Any]]:
    from evidence import review

    pack_id = _read_json(run / "manifest.json")["pack"]["pack_id"]
    try:
        items = {i.item_id: i for i in _pack(pack_id).items}
    except HTTPException:
        items = {}
    return review.queue(run, items)


def _reseal(run: Path) -> None:
    from evidence.evidence import write_evidence

    write_evidence(run)


@app.get("/api/review/{run_id}")
def review_queue(run_id: str) -> dict[str, Any]:
    """The run's memos as a review queue: lane, findings and whether each was reviewed."""
    from evidence import review

    run = _run_dir(run_id)
    q = _review_queue(run)
    done = review.reviews(run)
    return {"summary": review.summary(run, q), "evaluator": review.evaluator(run, q),
            "memos": [{k: m[k] for k in ("memo", "case", "repeat", "lane", "failing_checks",
                                         "panel_flag")}
                      | {"findings": len(m["cards"]), "reviewed": m["memo"] in done}
                      for m in q]}


@app.get("/api/review/{run_id}/memo")
def review_memo(run_id: str, memo: str) -> dict[str, Any]:
    """One memo to review: its text, its findings as cards, the case file, any earlier review."""
    from evidence import review

    run = _run_dir(run_id)
    m = next((x for x in _review_queue(run) if x["memo"] == memo), None)
    if m is None:
        raise HTTPException(404, "memo not in this run")
    pack_id = _read_json(run / "manifest.json")["pack"]["pack_id"]
    try:
        item = next(i for i in _pack(pack_id).items if i.item_id == m["item_id"])
        case_file = [{"title": d.renderer.replace("_", " ").capitalize(), "content": d.content}
                     for d in item.context]
    except (HTTPException, StopIteration):
        case_file = []
    return m | {"case_file": case_file, "review": review.reviews(run).get(memo),
                "reasons": list(review.REASONS)}


def _coach_call() -> tuple[Any, str]:
    """The coach's model: the judge endpoint, called directly (its own conversation)."""
    from evidence import panel

    ep = endpoint_for("judge")
    key = os.environ.get("NVIDIA_API_KEY") if ep.is_build else None

    def call(**kw: Any) -> dict[str, Any]:
        return panel.chat(ep.base_url, api_key=key, **kw)

    return call, ep.model_id


def _coach_evidence(run: Path, memo: str) -> tuple[dict[str, Any], str]:
    """A memo under review and what the coach reads about it: the memo, the case file, the
    engine's reference figures and the checks. Never the answer key."""
    from evidence import coach
    from evidence.panel_run import reference_figures

    m = next((x for x in _review_queue(run) if x["memo"] == memo), None)
    if m is None:
        raise HTTPException(404, "memo not in this run")
    pack_id = _read_json(run / "manifest.json")["pack"]["pack_id"]
    try:
        item = next(i for i in _pack(pack_id).items if i.item_id == m["item_id"])
        case_file = item.documents_text()
    except (HTTPException, StopIteration):
        case_file = ""
    checks = [r for r in map(json.loads, (run / "results.jsonl").read_text().splitlines())
              if r["item_id"] == m["item_id"] and r["repeat"] == m["repeat"]
              and str(r.get("judge", "")).startswith("check:")]
    return m, coach.evidence_block(m["text"], m["cards"], case_file,
                                   reference_figures(case_file), checks)


@app.post("/api/review/{run_id}/coach/prepare")
def review_coach_prepare(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """The coach's note on every finding of a memo, for each possible answer, prepared once
    per memo: the page asks when the memo opens, and for the next memo ahead of time."""
    from evidence import coach

    run = _run_dir(run_id)
    memo = str(payload.get("memo", ""))
    m, evidence = _coach_evidence(run, memo)
    call, model = _coach_call()
    s, new = coach.for_memo(run_id, memo, model)
    try:
        if new:
            coach.prepare(s, evidence=evidence, cards=m["cards"], call=call)
        return coach.notes_of(s)
    except OSError as exc:
        coach.close(s.id)  # the next request tries again
        raise HTTPException(502, f"the coach could not be reached: {exc}") from exc


@app.post("/api/review/{run_id}/coach")
def review_coach(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """One exchange with the coach about a memo under review: it reads the reviewer's current
    answers (and their message, if any) and asks about the ones the evidence does not bear
    out. A separate conversation per review; it does not see the answer key."""
    from evidence import coach

    run = _run_dir(run_id)
    memo = str(payload.get("memo", ""))
    m, evidence = _coach_evidence(run, memo)
    call, model = _coach_call()
    s = coach.get(payload.get("session_id"))
    if s is None or s.run != run_id or s.memo != memo:
        s = coach.start(run_id, memo, model)
    try:
        return coach.turn(s, evidence=evidence, cards=m["cards"],
                          verdicts=list(payload.get("verdicts") or []),
                          raised=list(payload.get("raised") or []),
                          message=(str(payload.get("message") or "").strip() or None), call=call)
    except OSError as exc:
        raise HTTPException(502, f"the coach could not be reached: {exc}") from exc


@app.post("/api/review/{run_id}/submit")
def review_submit(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    from evidence import coach, review

    run = _run_dir(run_id)
    s = coach.get(payload.get("coach_session"))
    verdicts = list(payload.get("verdicts") or [])
    kept = coach.record(s, verdicts, list(payload.get("first_answers") or [])) if (
        s and s.run == run_id and s.memo == payload.get("memo") and s.turns) else None
    try:
        rec = review.submit(run, str(payload.get("memo", "")), str(payload.get("reviewer", "")),
                            verdicts, list(payload.get("raised") or []),
                            payload.get("seconds"), _review_queue(run), coach=kept)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _reseal(run)
    if kept:
        coach.close(kept["session"])
    return rec


@app.get("/api/review/{run_id}/adjudication")
def review_adjudication(run_id: str) -> list[dict[str, Any]]:
    """Verdicts model risk must rule on before they can train anything."""
    from evidence import review

    run = _run_dir(run_id)
    return [x for x in review.labels(run, _review_queue(run))
            if x["standing"] == "needs_adjudication"]


@app.post("/api/review/{run_id}/adjudicate")
def review_adjudicate(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    from evidence import review

    run = _run_dir(run_id)
    try:
        rec = review.adjudicate(run, str(payload.get("verdict_id", "")),
                                str(payload.get("decision", "")), str(payload.get("by", "")),
                                str(payload.get("note", "")))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _reseal(run)
    return rec


@app.post("/api/review/{run_id}/feedback")
def review_feedback(run_id: str) -> dict[str, Any]:
    """Build the feedback pack from the settled verdicts and seal it with the run."""
    from evidence import review

    run = _run_dir(run_id)
    manifest = review.build_feedback(run, _review_queue(run))
    _reseal(run)
    return manifest


@app.get("/api/review/{run_id}/handover.zip")
def review_handover(run_id: str) -> Response:
    """The fine-tuning handover for the engineering team, as one zip."""
    h = _run_dir(run_id) / "feedback" / "handover"
    if not h.is_dir():
        raise HTTPException(404, "build the feedback pack first")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(h.iterdir()):
            z.write(f, f"{run_id}-handover/{f.name}")
    return Response(buf.getvalue(), media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="{run_id}-fine-tuning-handover.zip"'})


@app.get("/api/review/{run_id}/feedback/{name}")
def review_feedback_file(run_id: str, name: str) -> FileResponse:
    if name not in ("sft.jsonl", "preferences.jsonl", "judge_labels.jsonl", "check_fixes.jsonl",
                    "manifest.json"):
        raise HTTPException(404, "no such feedback file")
    path = _run_dir(run_id) / "feedback" / name
    if not path.is_file():
        raise HTTPException(404, "feedback pack not built yet")
    return FileResponse(path, filename=f"{run_id}-{name}")


# ------------------------------------------------------------------ pages


@app.middleware("http")
async def _no_stale_pages(request: Any, call_next: Any) -> Any:
    """Browsers revalidate the page, script and styles each time, so an upgrade shows at once."""
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/advanced/")
def advanced() -> FileResponse:
    """The full engine console: packs, corpora, runs, verify and the tamper demo."""
    return FileResponse(STATIC / "advanced" / "index.html")


@app.get("/advanced")
def advanced_slash() -> Response:
    from fastapi.responses import RedirectResponse

    return RedirectResponse("/advanced/")


# The Synthetic Data Designer (src/sdd), which generates the test cases, starts with the UI
# and is served at /sdd/: open a recipe (credit_underwriting among them), change it, run it.
try:
    from sdd.web.app import app as _designer

    DESIGNER: dict[str, Any] | None = {"url": "/sdd/"}
except ImportError:  # the generate extra is not installed: the evidence UI works without it
    _designer, DESIGNER = None, None


@app.get("/sdd")
def designer_slash() -> Response:
    from fastapi.responses import RedirectResponse

    if _designer is None:
        raise HTTPException(501, "the Synthetic Data Designer is not installed: "
                            "pip install -e '.[web]'")
    return RedirectResponse("/sdd/")


if _designer is not None:
    app.mount("/sdd", _designer, name="designer")
app.mount("/", StaticFiles(directory=STATIC), name="static")


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="warning")
