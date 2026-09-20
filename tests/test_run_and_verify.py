# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Runner → evidence pack → verify, with the model calls stubbed.

The stub answers every item with the same two briefings, one complete and one
that omits the policy limit and states a fabricated ratio, so the run has both
passes and failures to report. No network.
"""

import json
from pathlib import Path

import pytest

from evidence.adapters.nvidia_build import ChatResponse
from evidence.evidence import verify_run, write_evidence
from evidence.pack import load_pack
from evidence.runner import run_pack

PACK = Path(__file__).resolve().parents[1] / "packs" / "underwriter-sample"
pytestmark = pytest.mark.skipif(not (PACK / "items.jsonl").exists(), reason="sample pack not built")

GOOD = (
    "Referred because total monthly debt service exceeds the 40% policy limit. "
    "Debt service is £{ds} against gross monthly income of £{mi} ({dti}%). "
    "Bureau score {score}. Additional verified income would bring the ratio under 40%."
)
BAD = (
    "The applicant has a high level of existing credit, at 38.2% of income, which is "
    "a concern given the age band. Consider options."
)


def _stub_chat(item_lookup):
    calls = {"n": 0}

    def chat(role, system, user, *, max_tokens=2048, **_):
        calls["n"] += 1
        if role == "judge":
            text = '{"intelligible": 2, "actionable": 1, "reason": "clear"}'
            return ChatResponse(text, "stub-judge", "p", {}, 5, 10, 10, "j1", "http://stub/v1")
        item = item_lookup(system, user)
        d = item.grading
        # numbers straight from the case file, so GOOD is numerically grounded
        import re

        doc = item.documents_text()
        inst = int(re.search(r"instalment \| £([\d,]+)", doc).group(1).replace(",", ""))
        comm = int(re.search(r"commitments \| £([\d,]+)", doc).group(1).replace(",", ""))
        inc = int(re.search(r"Gross annual income \| £([\d,]+)", doc).group(1).replace(",", ""))
        score = re.search(r"\*\*(\d{3})\*\*", doc).group(1)
        mi = inc / 12
        text = GOOD.format(
            ds=inst + comm, mi=f"{mi:,.0f}", dti=f"{(inst + comm) / mi * 100:.1f}", score=score
        )
        if calls["n"] % 3 == 0:  # every third assistant call is the bad briefing
            text = BAD
        assert d.omission_refs
        return ChatResponse(
            text, "stub-assistant", "p", {"seed": 7}, 7, 100, 50, "a1", "http://stub/v1"
        )

    return chat


@pytest.fixture
def stubbed(monkeypatch, regulations_root):
    pack = load_pack(PACK)
    by_prompt = {i.documents_text(): i for i in pack.items}

    def lookup(system, user):
        return by_prompt[user]

    monkeypatch.setattr("evidence.runner.chat", _stub_chat(lookup))
    monkeypatch.setattr("evidence.judge.chat", _stub_chat(lookup))
    return pack


def test_run_writes_transcripts_results_and_sealed_evidence(stubbed, tmp_path):
    out = tmp_path / "run1"
    manifest = run_pack(stubbed, out, repeats=2, limit=4, log=lambda s: None)
    assert manifest["transcripts"] == 8 and manifest["model_calls_made"] == 8
    assert len(list((out / "transcripts").glob("*.json"))) == 8
    results = [json.loads(line) for line in (out / "results.jsonl").read_text().splitlines()]
    checks = {r["check"] for r in results}
    assert checks == {
        "material_omission",
        "numeric_fidelity",
        "decoy_citation",
        "flip_accuracy",
        "readability",
    }
    assert manifest["regulatory"]["status"] == "pass"
    res = write_evidence(out, stubbed.obligations)
    assert (out / "evidence" / "report.md").is_file()
    assert (out / "checksums.sha256").is_file()
    report = (out / "evidence" / "report.md").read_text()
    assert "Human oversight" in report and "NOT COVERED" in report.upper()
    assert res["summary"]["checks"]["material_omission"]["failed"] >= 1
    v = verify_run(out, stubbed, recompute=True)
    assert v.ok, v.message
    assert v.recomputed == 8 * 4


def test_rerun_is_resumable_without_new_calls(stubbed, tmp_path):
    out = tmp_path / "run2"
    run_pack(stubbed, out, repeats=1, limit=3, log=lambda s: None)
    m2 = run_pack(stubbed, out, repeats=1, limit=3, log=lambda s: None)
    assert m2["model_calls_made"] == 0


def test_tamper_is_detected_and_named(stubbed, tmp_path):
    out = tmp_path / "run3"
    run_pack(stubbed, out, repeats=1, limit=2, judge=False, log=lambda s: None)
    write_evidence(out, stubbed.obligations)
    assert verify_run(out).ok
    t = next((out / "transcripts").glob("*.json"))
    t.write_text(t.read_text().replace("40%", "45%", 1))
    v = verify_run(out)
    assert not v.ok
    assert v.mismatched == [f"transcripts/{t.name}"]


def test_edited_result_does_not_rederive(stubbed, tmp_path):
    out = tmp_path / "run4"
    run_pack(stubbed, out, repeats=1, limit=2, judge=False, log=lambda s: None)
    write_evidence(out, stubbed.obligations)
    rp = out / "results.jsonl"
    rows = [json.loads(line) for line in rp.read_text().splitlines()]
    rows[0]["passed"] = not rows[0]["passed"]
    rp.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    v = verify_run(out, stubbed, recompute=True)
    assert not v.ok
    assert "results.jsonl" in v.mismatched
    assert len(v.disagreements) == 1


def test_unlisted_file_fails_integrity(stubbed, tmp_path):
    out = tmp_path / "run5"
    run_pack(stubbed, out, repeats=1, limit=1, judge=False, log=lambda s: None)
    write_evidence(out, stubbed.obligations)
    (out / "evidence" / "extra.txt").write_text("x")
    v = verify_run(out)
    assert not v.ok and v.unlisted == ["evidence/extra.txt"]
