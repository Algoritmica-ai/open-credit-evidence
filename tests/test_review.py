# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Review and feedback on a committed run: queue, verdicts, label checking, feedback pack."""

import json
import shutil
from pathlib import Path

import pytest

from evidence import review
from evidence.evidence import verify_run, write_evidence
from evidence.pack import load_pack

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs" / "2026-09-24-onprem-super"
PACK = ROOT / "packs" / "underwriter-sample"
pytestmark = pytest.mark.skipif(not (RUN / "panel" / "records.jsonl").is_file(),
                                reason="committed Super run not present")


@pytest.fixture
def run(tmp_path):
    dst = tmp_path / RUN.name
    shutil.copytree(RUN, dst)
    return dst


@pytest.fixture
def q(run):
    return review.queue(run, {i.item_id: i for i in load_pack(PACK).items})


def test_queue_has_every_memo_in_lanes_with_cards(q):
    assert len(q) == 60
    lanes = {m["lane"] for m in q}
    assert lanes <= {"red", "amber", "green"} and "red" in lanes
    red = next(m for m in q if m["lane"] == "red")
    assert red["cards"] and all(c["card_id"] and c["problem"] for c in red["cards"])
    assert any(c["known_answer"] for c in red["cards"])
    # a card's sentence is taken from the memo itself
    quoted = [c for m in q for c in m["cards"] if c["sentence"]]
    located = [c for c in quoted if c["span"]]
    assert len(located) > 0.8 * len(quoted)
    assert all(any(c["sentence"] in m["text"] for m in q) for c in located)
    # ids are stable: building the queue twice gives the same cards
    assert [c["card_id"] for c in red["cards"]] == [c["card_id"] for c in next(
        m for m in review.queue(RUN, {}) if m["memo"] == red["memo"])["cards"]]


def test_review_labels_adjudication_and_feedback_pack(run, q):
    red = [m for m in q if m["lane"] == "red" and any(c["sentence"] and c["sentence"] in m["text"]
                                                     for c in m["cards"])][:2]
    a, b = red
    # memo a: every finding confirmed and corrected
    va = [{"card_id": c["card_id"], "action": "confirm",
           "correction": (c["sentence"] + " [corrected]") if c["sentence"] else "Added fact."}
          for c in a["cards"]]
    review.submit(run, a["memo"], "r1", va, seconds=90, queue_items=q)
    # memo b: a known-answer finding disputed, and a new finding raised
    known = next(c for c in b["cards"] if c["known_answer"])
    vb = [{"card_id": c["card_id"], "action": "dispute", "reason": "wrong_figure"}
          if c is known else {"card_id": c["card_id"], "action": "confirm"} for c in b["cards"]]
    review.submit(run, b["memo"], "r1", vb, raised=[{"problem": "wrong applicant name"}],
                  seconds=40, queue_items=q)
    with pytest.raises(ValueError, match="needs a reason"):
        review.submit(run, b["memo"], "r1", [{"card_id": known["card_id"], "action": "dispute"}],
                      queue_items=q)

    lab = review.labels(run, q)
    pending = [x for x in lab if x["standing"] == "needs_adjudication"]
    assert {x["verdict"]["action"] for x in pending} == {"dispute", "raise"}
    assert all(x["standing"] == "agrees" for x in lab if x["memo"] == a["memo"]
               and x["card"]["known_answer"])
    # model risk: the disputed check finding stands; the raised finding is upheld
    for x in pending:
        review.adjudicate(run, x["verdict_id"], "reject" if x["verdict"]["action"] == "dispute"
                          else "uphold", "mr1")
    s = review.summary(run, q)
    assert s["reviewed"] == 2 and s["needs_adjudication"] == 0 and s["rejected"] == 1
    assert s["automation_bias_memos"] == 0

    m = review.build_feedback(run, q)
    sft = [json.loads(x) for x in (run / "feedback" / "sft.jsonl").read_text().splitlines()]
    assert m["counts"]["sft.jsonl"] == len(sft) >= 1
    target = sft[0]["messages"][-1]["content"]
    assert "[corrected]" in target and sft[0]["provenance"]["memo"] == a["memo"]
    pref = json.loads((run / "feedback" / "preferences.jsonl").read_text().splitlines()[0])
    assert pref["chosen"] != pref["rejected"]
    judge = [json.loads(x) for x in (run / "feedback" / "judge_labels.jsonl").read_text()
             .splitlines()]
    # the disputed finding was ruled a real error: it trains the judge as one
    assert any(j["label"] and j["basis"] == "adjudicated" for j in judge)
    assert m["personal_data"].startswith("none")

    write_evidence(run)
    v = verify_run(run, load_pack(PACK), recompute=True)
    assert v.ok, v.message
    rv = json.loads((run / "evidence" / "review.json").read_text())
    assert rv["reviewed"] == 2 and "# Review" in (run / "evidence" / "review.md").read_text()


def test_a_signed_off_memo_with_a_known_error_is_automation_bias(run, q):
    m = next(x for x in q if x["lane"] == "red")
    review.submit(run, m["memo"], "r2", [{"card_id": c["card_id"], "action": "dispute",
                                          "reason": "not_material"} for c in m["cards"]],
                  queue_items=q)
    assert review.summary(run, q)["automation_bias_memos"] == 1
