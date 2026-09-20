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
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "PACKS", ROOT / "packs")
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
