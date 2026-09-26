# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""The web layer: thin endpoints over the engine, driven through the test client.

Runs use the same stubbed model as the runner tests, so a whole run — start,
poll, evidence, verify, tamper demo — completes here without a network.
"""

import json
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
    # retrieval keeps the fake embedder the index was built with (regulations_root):
    # a run refuses an embedder that does not reproduce its index
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
    assert j["status"] == "done", j.get("error") or j
    assert j["done"] == 4 and j["total"] == 4
    runs = client.get("/api/runs").json()
    assert runs[0]["run_id"] == job["run_id"] and runs[0]["sealed"]
    d = client.get(f"/api/runs/{job['run_id']}").json()
    assert d["summary"]["checks"]["material_omission"]["results"] == 4
    assert "Human oversight" in d["report"]
    t = client.get(f"/api/runs/{job['run_id']}/transcripts/{d['transcripts'][0]}").json()
    assert t["output"].startswith("Debt service")
    v = client.post(f"/api/runs/{job['run_id']}/verify", json={"recompute": True}).json()
    assert v["ok"] and v["recomputed"] == 4 * 6
    demo = client.post(f"/api/runs/{job['run_id']}/tamper-demo", json={}).json()
    assert demo["original"]["ok"] and not demo["tampered"]["ok"]
    assert demo["tampered"]["mismatched"] == [f"transcripts/{demo['edit']['transcript']}"]
    # the tampered copy was temporary: it is not left among the runs
    assert [r["run_id"] for r in client.get("/api/runs").json()] == [job["run_id"]]
    # the original run is untouched
    assert client.post(f"/api/runs/{job['run_id']}/verify", json={}).json()["ok"]
    # one report per reader, each served as markdown
    readers = {r["name"]: r for r in d["readers"]}
    assert set(readers) == {"business", "credit-risk", "compliance", "operations", "vendor",
                            "auditor"}
    assert all(r["available"] for r in readers.values())
    biz = client.get(f"/api/runs/{job['run_id']}/readers/business")
    assert biz.status_code == 200 and biz.text.startswith("# underwriter-sample — the assistant")
    assert client.get(f"/api/runs/{job['run_id']}/readers/nobody").status_code == 404
    # the same report as a PDF: printed by a local browser, or a clear 501 without one
    from evidence.evidence import export

    assert client.get(f"/api/runs/{job['run_id']}/pdf/nobody").status_code == 404
    if export.find_chrome():
        pdf = client.get(f"/api/runs/{job['run_id']}/pdf/business")
        assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"
    original = export.find_chrome
    export.find_chrome = lambda: None
    try:
        assert client.get(f"/api/runs/{job['run_id']}/pdf/business").status_code == 501
    finally:
        export.find_chrome = original
    # the export left nothing inside the run: it still verifies
    assert client.post(f"/api/runs/{job['run_id']}/verify", json={}).json()["ok"]



def test_pack_shows_where_its_cases_come_from(client):
    d = client.get("/api/packs/underwriter-sample/sdd").json()
    assert d["sdd"]["seed"] == 7 and d["population"]["refer"] == 25 and d["cases"] == 20
    assert d["recipe"]["hidden"] == ["capacity_tier"]
    assert "bureau_score" in d["recipe"]["derived"]
    assert "age_band" in d["recipe"]["no_path"] and "age_band" in d["decoys_marked"]
    # no path to the outcome in the recipe, but not marked as a decoy in the pack
    assert d["no_path_not_marked"] == ["tenure_months"]
    assert d["links"]["space"].startswith("https://huggingface.co/spaces/Algoritmica/")
    spec = client.get(d["spec_download"])
    assert spec.status_code == 200 and "capacity_tier" in spec.text


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


def test_review_endpoints_on_a_copy_of_a_committed_run(tmp_path, monkeypatch):
    import shutil

    src = ROOT / "runs" / "2026-09-24-onprem-super"
    if not (src / "panel" / "records.jsonl").is_file():
        pytest.skip("committed Super run not present")
    runs = tmp_path / "runs"
    shutil.copytree(src, runs / src.name)
    monkeypatch.setattr(web, "RUNS", runs)
    monkeypatch.setattr(web, "PACKS", ROOT / "packs")
    c = TestClient(web.app)
    ov = c.get("/api/overview").json()
    assert ov["run"]["run_id"] == src.name and ov["jobs"] == []
    assert ov["stages"]["review"] == "not_started" and ov["stages"]["next"] == "review"
    assert ov["stages"]["flagged"] == ov["stages"]["lanes"]["red"] + ov["stages"]["lanes"]["amber"]
    q = c.get(f"/api/review/{src.name}").json()
    assert q["summary"]["memos"] == 60 and q["memos"][0]["lane"] == "red"
    memo = q["memos"][0]["memo"]
    m = c.get(f"/api/review/{src.name}/memo", params={"memo": memo}).json()
    assert m["cards"] and m["case_file"] and m["text"]
    bad = c.post(f"/api/review/{src.name}/submit",
                 json={"memo": memo, "reviewer": "t",
                       "verdicts": [{"card_id": m["cards"][0]["card_id"], "action": "dispute"}]})
    assert bad.status_code == 400
    ok = c.post(f"/api/review/{src.name}/submit",
                json={"memo": memo, "reviewer": "t", "seconds": 12,
                      "verdicts": [{"card_id": x["card_id"], "action": "confirm",
                                    "correction": "fixed"} for x in m["cards"]]})
    assert ok.status_code == 200
    st = c.get("/api/overview", params={"run": src.name}).json()["stages"]
    assert st["review"] == "in_progress" and st["flagged_checked"] == 1
    assert c.post(f"/api/runs/{src.name}/verify", json={}).json()["ok"]
    fb = c.post(f"/api/review/{src.name}/feedback").json()
    assert fb["counts"]["judge_labels.jsonl"] >= 1
    assert c.get(f"/api/review/{src.name}/feedback/manifest.json").status_code == 200
    assert c.get("/api/overview").json()["stages"]["feedback_built"]
    import io
    import zipfile

    z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/review/{src.name}/handover.zip").content))
    names = {n.split("/", 1)[1] for n in z.namelist()}
    assert {"sft_train.jsonl", "dpo_train.jsonl", "judge_labels.jsonl", "training_config.yaml",
            "README.md", "manifest.json"} <= names
    ev = c.get(f"/api/review/{src.name}").json()["evaluator"]
    assert ev["panel"]["memos_with_a_rule_failure"] + ev["panel"]["memos_passing_every_rule"] == 60
    d = c.get(f"/api/runs/{src.name}").json()
    assert d["panel"]["briefings"] == 60 and d["headline"]["memos"] == 60
    assert "Credit Evidence" in c.get("/").text
    assert c.get("/advanced/").status_code == 200


def test_a_test_started_from_the_browser_can_run_the_panel(client, monkeypatch):
    calls = []

    def fake_panel(run, pack, **kw):
        calls.append((run.name, kw["runtime"]))
        kw["log"]("  1/2  x r0  value 1.0  ok")
        return {"ok": True, "message": "panel: done", "briefings": 2, "planned": 2}

    monkeypatch.delenv("EVIDENCE_PANEL_SSH", raising=False)
    monkeypatch.setattr("evidence.panel_run.panel_over_run", fake_panel)
    job = client.post("/api/run", json={"pack": "underwriter-sample", "repeats": 1, "limit": 2,
                                        "panel": True}).json()
    assert [j["job_id"] for j in client.get("/api/jobs").json()] in ([job["job_id"]], [])
    for _ in range(200):
        j = client.get(f"/api/run/{job['job_id']}").json()
        if j["status"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert j["status"] == "done" and j["phase"] == "done" and j["panel"], j
    assert calls == [(job["run_id"], "direct")] and "panel_error" not in j
    d = client.get(f"/api/runs/{job['run_id']}").json()
    assert d["manifest"]["judge"] is None and d["manifest"]["single_judge"]  # the Reader stands in
    assert client.get("/api/jobs").json() == []


def test_a_failed_panel_leaves_the_test_standing(client, monkeypatch):
    def broken(run, pack, **kw):
        raise RuntimeError("judge unreachable")

    monkeypatch.setattr("evidence.panel_run.panel_over_run", broken)
    job = client.post("/api/run", json={"pack": "underwriter-sample", "repeats": 1, "limit": 1,
                                        "panel": True}).json()
    for _ in range(200):
        j = client.get(f"/api/run/{job['job_id']}").json()
        if j["status"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert j["status"] == "done" and "judge unreachable" in j["panel_error"]
    assert client.post(f"/api/runs/{job['run_id']}/verify", json={}).json()["ok"]


def test_a_test_can_be_stopped_during_the_panel(client, monkeypatch):
    def slow_panel(run, pack, **kw):
        for _ in range(400):
            if kw["should_stop"]():
                return {"ok": True, "stopped": True, "message": "panel stopped", "briefings": 0,
                        "planned": 2}
            time.sleep(0.01)
        return {"ok": True, "message": "never stopped", "briefings": 2, "planned": 2}

    monkeypatch.setattr("evidence.panel_run.panel_over_run", slow_panel)
    job = client.post("/api/run", json={"pack": "underwriter-sample", "repeats": 1, "limit": 2,
                                        "panel": True}).json()
    for _ in range(200):
        if client.get(f"/api/run/{job['job_id']}").json()["phase"] == "panel":
            break
        time.sleep(0.02)
    client.post(f"/api/run/{job['job_id']}/cancel")
    for _ in range(200):
        j = client.get(f"/api/run/{job['job_id']}").json()
        if j["status"] != "running":
            break
        time.sleep(0.02)
    assert j["status"] == "cancelled" and j["transcripts"] == 2 and "panel_error" not in j
    assert client.post(f"/api/runs/{job['run_id']}/verify", json={}).json()["ok"]


def _with_bank_figures(src, dst, pack_id):
    """A copy of a pack whose case files carry a rules-engine document, as fresh packs do."""
    import hashlib
    import shutil

    shutil.copytree(src, dst)
    items = [json.loads(x) for x in (dst / "items.jsonl").read_text().splitlines()]
    for it in items:
        it["item_id"] = it["item_id"].replace(src.name + ":", pack_id + ":", 1)
        it["pack"] = pack_id
        it["context"].append({"renderer": "rules_engine", "variant": "complete",
                              "content": "# Figures from the Bank's Systems\n\n| Debt service "
                                         "as a share of gross monthly income | 47.0% |"})
    (dst / "items.jsonl").write_text("".join(json.dumps(it) + "\n" for it in items))
    m = json.loads((dst / "manifest.json").read_text())
    m.update(pack_id=pack_id, bank_figures=True,
             items_sha256=hashlib.sha256((dst / "items.jsonl").read_bytes()).hexdigest())
    (dst / "manifest.json").write_text(json.dumps(m))


def test_a_change_is_tested_on_new_cases_as_it_is_and_with_the_change(client, monkeypatch,
                                                                       tmp_path):
    seen = []

    def fake_fresh(from_pack):
        pid = "underwriter-sample-s4242"
        _with_bank_figures(web.PACKS / from_pack, web.PACKS / pid, pid)
        return {"pack_id": pid, "seed": 4242, "from": from_pack, "items": 20,
                "shared_with_other_packs": 0, "seconds": 0.1, "links": web.SDD_LINKS}

    def chat(role, system, user, **_):
        seen.append("Figures from the Bank" in user)
        return ChatResponse("Debt service 47% exceeds the 40% policy limit.", "stub", "p",
                            {"seed": 7}, 3, 5, 5, "a", "http://stub/v1")

    monkeypatch.setattr(web, "make_fresh_pack", fake_fresh)
    base = client.post("/api/run", json={"pack": "underwriter-sample", "repeats": 1, "limit": 2,
                                         "judge": False}).json()
    for _ in range(200):
        if client.get(f"/api/run/{base['job_id']}").json()["status"] != "running":
            break
        time.sleep(0.05)
    monkeypatch.setattr("evidence.runner.chat", chat)
    assert client.post("/api/retest", json={"from_run": base["run_id"], "setup": "as_is"}
                       ).status_code == 400
    job = client.post("/api/retest", json={"from_run": base["run_id"]}).json()
    for _ in range(400):
        j = client.get(f"/api/run/{job['job_id']}").json()
        if j["status"] != "running":
            break
        time.sleep(0.05)
    assert j["status"] == "done" and j["verdict"] and j["seed"] == 4242, j
    b = client.get(f"/api/runs/{j['before']}").json()["manifest"]
    a = client.get(f"/api/runs/{j['after']}").json()["manifest"]
    assert (b["setup"], a["setup"]) == ("as_is", "with_figures")
    assert b["pack"]["pack_id"] == a["pack"]["pack_id"] == "underwriter-sample-s4242"
    assert seen.count(True) == seen.count(False) == 20  # the figures went to one side only
    for r in (j["before"], j["after"]):
        assert client.post(f"/api/runs/{r}/verify", json={"recompute": True}).json()["ok"]
    c = client.get("/api/compare", params={"before": j["before"], "after": j["after"]}).json()
    assert [x["what"] for x in c["changed"] if x["what"] != "engine commit"] == [
        "assistant setup"]


def test_new_cases_come_from_the_synthetic_data_designer(client):
    pytest.importorskip("sdd")
    import shutil

    shutil.copytree(ROOT / "packs" / "underwriter-de", web.PACKS / "underwriter-de")
    f = client.post("/api/packs/fresh", json={"from": "underwriter-de"}).json()
    assert f["pack_id"].startswith("underwriter-de-s") and f["shared_with_other_packs"] == 0
    listed = {p["pack_id"]: p for p in client.get("/api/packs").json()}
    assert listed[f["pack_id"]]["bank_figures"] and listed[f["pack_id"]]["items"] == 20
    assert f["links"]["space"].startswith("https://huggingface.co/spaces/")
