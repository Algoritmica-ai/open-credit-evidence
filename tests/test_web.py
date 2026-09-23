# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""The web layer: thin endpoints over the engine, driven through the test client.

Runs use the same stubbed model as the runner tests, so a whole run — start,
poll, evidence, verify, tamper demo — completes here without a network.
"""

import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="the web UI needs the [web] extra")

from fastapi.testclient import TestClient  # noqa: E402

from evidence.adapters.nvidia_build import ChatResponse  # noqa: E402
from evidence.web import app as web  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    not (ROOT / "packs" / "underwriter-sample" / "items.jsonl").exists(), reason="pack not built"
)


@pytest.fixture
def client(tmp_path, monkeypatch, regulations_root):
    # A throwaway copy of the packs directory, so uploads and builds never touch the repo.
    import shutil

    shutil.copytree(
        ROOT / "packs" / "underwriter-sample", tmp_path / "packs" / "underwriter-sample"
    )
    monkeypatch.setattr(web, "PACKS", tmp_path / "packs")
    monkeypatch.setattr(web, "RUNS", tmp_path / "runs")
    monkeypatch.setenv("NVIDIA_API_KEY", "test")

    def chat(role, system, user, *, max_tokens=2048, **_):
        if role == "judge":
            return ChatResponse(
                '{"intelligible": 2, "actionable": 2, "reason": "r"}',
                "stub-judge",
                "p",
                {},
                3,
                5,
                5,
                "j",
                "http://stub/v1",
            )
        return ChatResponse(
            "Debt service 47% exceeds the 40% policy limit. Score 652.",
            "stub",
            "p",
            {"seed": 7},
            3,
            5,
            5,
            "a",
            "http://stub/v1",
        )

    monkeypatch.setattr("evidence.runner.chat", chat)
    monkeypatch.setattr("evidence.judge.chat", chat)
    monkeypatch.setattr(
        "evidence.corpus.embed", lambda texts, input_type: [[1.0, 0, 0, 0]] * len(texts)
    )
    return TestClient(web.app)


def test_index_meta_and_packs(client):
    assert client.get("/").status_code == 200
    m = client.get("/api/meta").json()
    assert "material_omission" in m["checks"] and m["roles"]["assistant"]["model"]
    packs = client.get("/api/packs").json()
    assert packs[0]["pack_id"] == "underwriter-sample" and packs[0]["items"] == 20
    items = client.get("/api/packs/underwriter-sample/items").json()
    assert len(items) == 20 and items[0]["must_state"]
    case = client.get(f"/api/packs/underwriter-sample/items/{items[0]['case']}").json()
    assert len(case["documents"]) == 3


def test_gate_marks_without_a_model(client):
    items = client.get("/api/packs/underwriter-sample/items").json()
    r = client.post(
        "/api/gate",
        json={
            "pack": "underwriter-sample",
            "case": items[0]["case"],
            "briefing": "The applicant looks fine.",
        },
    ).json()
    names = {x["name"]: x for x in r["results"]}
    assert not names["material_omission"]["passed"]


def test_bad_names_are_rejected(client):
    assert client.get("/api/packs/../etc/items").status_code in (400, 404)
    assert client.get("/api/runs/nope").status_code == 404
    assert client.get("/api/packs/underwriter-sample/items/../../x").status_code in (400, 404)


def test_run_evidence_verify_and_tamper(client):
    job = client.post(
        "/api/run", json={"pack": "underwriter-sample", "repeats": 2, "limit": 2}
    ).json()
    for _ in range(200):
        j = client.get(f"/api/run/{job['job_id']}").json()
        if j["status"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert j["status"] == "done", j
    assert j["done"] == 4 and j["total"] == 4
    runs = client.get("/api/runs").json()
    assert runs[0]["run_id"] == job["run_id"] and runs[0]["sealed"]
    d = client.get(f"/api/runs/{job['run_id']}").json()
    assert d["summary"]["checks"]["material_omission"]["results"] == 4
    assert "Human oversight" in d["report"]
    t = client.get(f"/api/runs/{job['run_id']}/transcripts/{d['transcripts'][0]}").json()
    assert t["output"].startswith("Debt service")
    v = client.post(f"/api/runs/{job['run_id']}/verify", json={"recompute": True}).json()
    assert v["ok"] and v["recomputed"] == 4 * 4
    demo = client.post(f"/api/runs/{job['run_id']}/tamper-demo", json={}).json()
    assert demo["original"]["ok"] and not demo["tampered"]["ok"]
    assert demo["tampered"]["mismatched"] == [f"transcripts/{demo['edit']['transcript']}"]
    # the original run is untouched
    assert client.post(f"/api/runs/{job['run_id']}/verify", json={}).json()["ok"]


def test_schema_upload_and_results(client, tmp_path):
    schema = client.get("/api/schema/item").json()
    assert "item_id" in schema["properties"]
    # a pack zipped from the sample pack installs under a new id, and rejects garbage
    import io
    import zipfile

    src = ROOT / "packs" / "underwriter-sample"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name in ("items.jsonl", "manifest.json", "obligations.yaml"):
            zf.write(src / name, name)
    r = client.post(
        "/api/packs/upload",
        files={"archive": ("p.zip", buf.getvalue())},
        data={"pack_id": "uploaded-copy"},
    )
    assert r.status_code == 400 and "already" not in r.json()["detail"] or r.status_code == 200
    bad = client.post("/api/packs/upload", files={"archive": ("x.zip", b"not a zip")})
    assert bad.status_code == 400


def test_cancel_keeps_completed_briefings(client):
    job = client.post(
        "/api/run", json={"pack": "underwriter-sample", "repeats": 1, "limit": 5, "judge": False}
    ).json()
    client.post(f"/api/run/{job['job_id']}/cancel")
    for _ in range(200):
        j = client.get(f"/api/run/{job['job_id']}").json()
        if j["status"] in ("done", "cancelled", "error"):
            break
        time.sleep(0.05)
    assert j["status"] in ("done", "cancelled")
    if j["status"] == "cancelled" and j.get("transcripts"):
        d = client.get(f"/api/runs/{job['run_id']}").json()
        assert d["manifest"]["cancelled"] and d["sealed"]
        assert client.post(f"/api/runs/{job['run_id']}/verify", json={}).json()["ok"]


def test_shared_workspace_mode(tmp_path, monkeypatch, regulations_root):
    """EVIDENCE_WORKSPACE seeds a writable copy; EVIDENCE_SHARED caps runs and flags the page."""
    import importlib

    monkeypatch.setenv("EVIDENCE_ROOT", str(ROOT))
    monkeypatch.setenv("EVIDENCE_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("EVIDENCE_SHARED", "1")
    monkeypatch.delenv("EVIDENCE_RULESETS_DIR", raising=False)
    mod = importlib.reload(web)
    try:
        assert (tmp_path / "ws" / "packs" / "underwriter-sample" / "items.jsonl").is_file()
        assert mod.PACKS == tmp_path / "ws" / "packs"
        c = TestClient(mod.app)
        m = c.get("/api/meta").json()
        assert m["shared"] and m["limits"] == {"items": 5, "repeats": 2}
    finally:
        monkeypatch.delenv("EVIDENCE_WORKSPACE")
        monkeypatch.delenv("EVIDENCE_SHARED")
        importlib.reload(web)


def test_coverage_names_article_requirements_and_check_basis(client):
    cov = client.get("/api/packs/underwriter-sample/coverage").json()
    by_id = {o["id"]: o for o in cov["obligations"]}
    art14 = by_id["eu-ai-act:14"]
    assert art14["level"] == "evidences" and "override" in art14["requires"]
    names = {c["name"]: c for c in art14["check_basis"]}
    assert names["material_omission"]["registered"] and names["material_omission"]["tests"]
    assert art14["judge"]["name"] == "readability"
    art15 = {c["name"]: c for c in by_id["eu-ai-act:15"]["check_basis"]}
    assert art15["driver_recall"]["registered"] is False  # planned, never counted
    assert by_id["eu-ai-act:10"]["level"] == "does_not_cover"
    assert "ai-act-art-14#4" in cov["passages"]


def test_run_detail_carries_decision_and_compare_works(tmp_path, monkeypatch):
    """The Evidence step reads decision/diagnosis/recommendations; Compare pairs two runs."""
    import shutil

    runs = tmp_path / "runs"
    for name in ("2026-09-20-build", "2026-09-20-onprem"):
        shutil.copytree(ROOT / "runs" / name, runs / name)
    monkeypatch.setattr(web, "RUNS", runs)
    c = TestClient(web.app)
    d = c.get("/api/runs/2026-09-20-onprem").json()
    assert d["decision"]["verdict"] in ("GO", "GO WITH CONDITIONS", "NO-GO", "INCONCLUSIVE")
    assert d["diagnosis"]["causes"] and d["recommendations"]
    cmp = c.get("/api/compare", params={"before": "2026-09-20-build",
                                         "after": "2026-09-20-onprem"}).json()
    assert cmp["verdict"] in ("ACCEPT", "REJECT", "INCONCLUSIVE", "NO EFFECT")
    assert any(ch["what"] == "assistant endpoint" for ch in cmp["changed"])
    assert c.get("/api/compare", params={"before": "x", "after": "x"}).status_code == 400
