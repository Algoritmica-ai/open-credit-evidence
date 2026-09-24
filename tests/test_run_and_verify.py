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
        "comparison_fidelity",
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
    assert v.recomputed == 8 * 5


def test_rerun_is_resumable_without_new_calls(stubbed, tmp_path):
    out = tmp_path / "run2"
    run_pack(stubbed, out, repeats=1, limit=3, log=lambda s: None)
    m2 = run_pack(stubbed, out, repeats=1, limit=3, log=lambda s: None)
    assert m2["model_calls_made"] == 0


def test_every_briefing_names_the_model_that_wrote_it(stubbed, tmp_path):
    from conftest import STUB_FINGERPRINT

    out = tmp_path / "fp"
    m = run_pack(stubbed, out, repeats=1, limit=2, log=lambda s: None)
    for p in (out / "transcripts").glob("*.json"):
        assert json.loads(p.read_text())["sut"]["fingerprint"] == STUB_FINGERPRINT
    assert m["models"]["assistant"]["fingerprint"] == STUB_FINGERPRINT
    assert m["models"]["judge"]["fingerprint"] == STUB_FINGERPRINT
    assert not m["models"]["assistant"].get("changed_during_run")
    judged = [json.loads(x) for x in (out / "results.jsonl").read_text().splitlines()]
    assert {r["model_fingerprint"] for r in judged if r["check"] == "readability"} == {
        STUB_FINGERPRINT}
    # a re-score makes no calls: it keeps the fingerprints of the pass that made them
    m2 = run_pack(stubbed, out, repeats=1, limit=2, log=lambda s: None)
    assert m2["model_calls_made"] == 0 and m2["models"] == m["models"]
    write_evidence(out, stubbed.obligations)
    assert "Assistant model fingerprint: `ffffffffffffffff…`" in (
        out / "evidence" / "report.md").read_text()


def test_a_model_swapped_mid_run_is_flagged(stubbed, tmp_path, monkeypatch):
    calls = {"n": 0}

    def drifting(role):
        calls["n"] += 1
        return {"role": role, "level": "weights", "components": {},
                "fingerprint": ("a" if calls["n"] <= 3 else "b") * 64}

    monkeypatch.setattr("evidence.runner.model_fingerprint", drifting)
    m = run_pack(stubbed, tmp_path / "drift", repeats=1, limit=1, log=lambda s: None)
    assert m["models"]["assistant"]["changed_during_run"]
    assert m["models"]["assistant"]["fingerprint_end"] == "b" * 64


def test_rescore_keeps_when_the_calls_happened(stubbed, tmp_path):
    # A re-score makes no calls; its manifest must still say when the calls were made.
    out = tmp_path / "run3"
    m1 = run_pack(stubbed, out, repeats=1, limit=2, log=lambda s: None)
    for p in (out / "transcripts").glob("*.json"):
        t = json.loads(p.read_text())
        t["started_at"] = "2026-09-20T09:00:00+00:00"
        p.write_text(json.dumps(t))
    m2 = run_pack(stubbed, out, repeats=1, limit=2, log=lambda s: None)
    assert m2["model_calls_made"] == 0
    assert m2["started_at"] == "2026-09-20T09:00:00+00:00"
    assert m2["finished_at"].startswith("2026-09-20T09:00:00")  # + 7 ms latency
    assert m2["scored_at"] >= m1["scored_at"]


def test_judge_corpus_comes_from_its_records(stubbed, tmp_path, monkeypatch):
    # Records reused from a pass with no passages must not be credited to a corpus.
    out = tmp_path / "run4"
    run_pack(stubbed, out, repeats=1, limit=1, corpus=None, log=lambda s: None)

    from evidence.corpus import Corpus

    class FakeCorpus(Corpus):
        jurisdiction, sha256, backend = "EU", "abc", "cosine"
        manifest = {"passages": 1, "embed_model": "m"}

        def __init__(self):  # no index on disk
            pass

        def retrieve(self, *a, **k):
            return []

        def close(self):
            pass

    m = run_pack(stubbed, out, repeats=1, limit=1, corpus=FakeCorpus(), log=lambda s: None)
    assert m["judge"]["corpus"] is None
    assert m["judge"]["corpus_note"] == "judge records carry no regulation passages"


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
