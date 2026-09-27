# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Training data from a teacher: new cases apart from every test, memos kept only when
the checks pass, sealed. The teacher here is a stand-in; no model is called."""

import json
import shutil
from pathlib import Path

import pytest

from evidence import distill
from evidence.contracts.check import CheckResult
from evidence.evidence.verify import verify_run
from evidence.pack import load_pack

pytest.importorskip("sdd", reason="the case generator needs the [generate] extra")

GOOD, BAD = "PASS: a memo the checks accept", "The ratio is 99.9%."


@pytest.fixture
def ws(tmp_path, monkeypatch):
    packs = tmp_path / "packs"
    shutil.copytree(Path("packs/underwriter-de"), packs / "underwriter-de")
    monkeypatch.setattr(distill, "PACKS", packs)
    monkeypatch.setattr(distill, "ROOT", tmp_path / "training")

    # the checks have their own tests; here a memo passes when it says PASS
    def checks(names, *, output, item, versions=None):
        return [CheckResult(name=n, passed=output.startswith("PASS"), score=1.0,
                            detail="stand-in") for n in names]

    monkeypatch.setattr(distill, "run_checks", checks)
    return tmp_path


def test_new_cases_share_no_application_or_seed_with_a_test_pack(ws):
    n = distill.make_cases("t", 6, "underwriter-de", log=lambda _: None)
    assert n == 6
    seeds, forms = distill.taken(training=False)
    items = distill.cases("t")
    assert len(items) == 6 and not {distill._application(i) for i in items} & forms
    (pack,) = (ws / "training" / "t" / "cases").iterdir()
    assert pack.name.startswith("train-underwriter-de-s")
    assert int(load_pack(pack).manifest["sdd"]["seed"]) not in seeds
    # and the training cases are taken from then on
    assert int(load_pack(pack).manifest["sdd"]["seed"]) in distill.taken()[0]


def test_the_teacher_is_kept_only_when_the_checks_pass_and_the_run_resumes(ws):
    distill.make_cases("t", 3, "underwriter-de", log=lambda _: None)
    items = distill.cases("t")
    calls: list[str] = []
    repairs: list[dict] = []

    def teacher(system, user, previous=None):
        item = next(i for i in items if i.documents_text() == user)
        calls.append(item.item_id)
        if previous:
            repairs.append(previous)
        first = calls.count(item.item_id) == 1
        # case 0 passes at once; case 1 fails, then passes; case 2 always fails
        if item is items[2] or (item is items[1] and first):
            return {"memo": BAD, "model": "stand-in"}
        return {"memo": GOOD, "model": "stand-in"}

    counts = distill.teach("t", ask=teacher, workers=1, log=lambda _: None)
    assert counts == {"cases": 3, "kept": 2, "failed_checks": 3, "too_long": 0, "errors": 0}
    # a retry is shown the memo that failed and what the checks found
    assert len(repairs) == 2 and all(r["memo"] == BAD and r["failed"] for r in repairs)
    # nothing left to do: kept cases and cases out of attempts are skipped
    assert distill.teach("t", ask=teacher, workers=1, log=lambda _: None)["cases"] == 0
    rows = [json.loads(x) for x in (ws / "training/t/teacher.jsonl").read_text().splitlines()]
    assert all(r["checks"] for r in rows) and sum(r["kept"] for r in rows) == 2


def test_the_data_is_chat_format_split_by_case_and_sealed(ws, tmp_path):
    distill.make_cases("t", 4, "underwriter-de", log=lambda _: None)
    distill.teach("t", ask=lambda s, u: {"memo": GOOD, "model": "stand-in"}, workers=1,
                  log=lambda _: None)
    handover = _handover(tmp_path)
    out = distill.build("t", feedback=[handover], log=lambda _: None)
    train = [json.loads(x) for x in (out / "sft/train.jsonl").read_text().splitlines()]
    val = [json.loads(x) for x in (out / "sft/val.jsonl").read_text().splitlines()]
    assert len(val) == 1 and len(train) == 3 + 1  # 3 teacher cases, 1 corrected memo
    assert not {x["item_id"] for x in train} & {x["item_id"] for x in val}
    assert [m["role"] for m in train[0]["messages"]] == ["system", "user", "assistant"]
    m = json.loads((out / "manifest.json").read_text())
    assert m["cases_kept"] == 4 and m["shared_with_test_packs"] == 0
    assert m["feedback_from_test_packs"] == ["underwriter-de"]
    assert "compare a model trained on this data on other cases" in (out / "README.md").read_text()
    assert verify_run(out).ok


def test_the_final_answer_leaves_the_thinking_out():
    thought = {"content": "weighing it up...</think>\n\nThe memo."}
    assert distill.final_answer(thought) == "The memo."
    assert distill.final_answer({"content": "The memo.", "reasoning_content": "x"}) == "The memo."


def _handover(tmp_path) -> Path:
    run = tmp_path / "runs" / "r"
    h = run / "feedback" / "handover"
    h.mkdir(parents=True)
    (run / "manifest.json").write_text(json.dumps({"pack": {"pack_id": "underwriter-de"}}))
    (h / "sft_train.jsonl").write_text(json.dumps({"messages": [
        {"role": "system", "content": "s"}, {"role": "user", "content": "u"},
        {"role": "assistant", "content": "corrected"}], "item_id": "x"}) + "\n")
    return h
