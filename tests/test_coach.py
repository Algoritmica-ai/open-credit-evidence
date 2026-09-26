# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""The review coach: its conversation, what it sees, and what the review keeps of it."""

import json

from evidence import coach

CARDS = [
    {"card_id": "c1", "kind": "Claim contradicts the memo's own figure", "known_answer": True,
     "problem": "Says the ratio is above 40%, but the memo gives 36.5%",
     "sentence": "The debt service exceeds the 40% threshold.", "evidence": "36.5%"},
    {"card_id": "c2", "kind": "Found by the AI review panel", "known_answer": False,
     "problem": "Calls a 44-month file thin", "sentence": "", "evidence": "44 months"},
]


def _reply(obj_or_text):
    text = obj_or_text if isinstance(obj_or_text, str) else json.dumps(obj_or_text)
    return {"choices": [{"message": {"content": text}}], "usage": {"completion_tokens": 9}}


def test_the_coach_challenges_answers_and_the_review_keeps_the_before_and_after():
    seen = []

    def call(model, messages, **kw):
        seen.append({"messages": [dict(m) for m in messages], "kw": kw})
        if len(seen) == 1:
            return _reply({"challenges": [{"finding": 1, "also": [2], "question": "Why right?",
                                           "evidence": "36.55% — within the 40% limit"}],
                           "reply": "Look at the ratio."})
        return _reply({"challenges": [], "reply": "Your answers hold."})

    s = coach.start("run", "memo#r0", "super")
    before = [{"card_id": "c1", "action": "dispute", "reason": "wrong_figure"},
              {"card_id": "c2", "action": "confirm"}]
    r1 = coach.turn(s, evidence="E", cards=CARDS, verdicts=before, raised=[], message=None,
                    call=call)
    assert r1["challenges"][0]["card_id"] == "c1" and r1["challenges"][0]["also_card_ids"] == ["c2"]
    first = seen[0]["messages"]
    assert first[0]["content"] == coach.SYSTEM and "the memo is right" in first[1]["content"]
    assert "answer key" not in first[1]["content"].lower()  # it is given evidence, not answers
    after = [{"card_id": "c1", "action": "confirm"}, {"card_id": "c2", "action": "confirm"}]
    r2 = coach.turn(s, evidence="E", cards=CARDS, verdicts=after, raised=[],
                    message="I see it now.", call=call)
    assert r2["challenges"] == [] and r2["turn"] == 2
    assert "THE UNDERWRITER SAYS: I see it now." in seen[1]["messages"][-1]["content"]
    kept = coach.record(s, after)
    assert kept["changed_after_coach"] == ["c1"] and kept["challenged"] == ["c1", "c2"]
    assert kept["answers_before"][0]["action"] == "dispute" and kept["turns"] == 2


def test_an_answer_lost_to_reasoning_is_asked_for_again_answer_only():
    calls = []

    def call(model, messages, **kw):
        calls.append(kw)
        return _reply("") if len(calls) == 1 else _reply({"challenges": [], "reply": "ok"})

    s = coach.start("run", "m", "super")
    r = coach.turn(s, evidence="E", cards=CARDS, verdicts=[], raised=[], message=None, call=call)
    assert r["reply"] == "ok" and calls[1].get("json_only") is True


def test_notes_are_prepared_once_per_memo_and_waited_for_by_a_second_request():
    import threading

    gate, calls = threading.Event(), []

    def call(model, messages, **kw):
        calls.append(messages)
        gate.wait(5)
        return _reply({"notes": [{"finding": 1, "evidence": "36.5% is under 40%.",
                                  "if_wrong": "Noted.", "if_right": "Where is 36.5% above 40%?",
                                  "if_unsure": "Compare the ratio with the limit."},
                                 {"finding": 9, "evidence": "not a finding"}]})

    s, new = coach.for_memo("run", "prep#r0", "super")
    assert new
    t = threading.Thread(target=coach.prepare, kwargs={"s": s, "evidence": "E", "cards": CARDS,
                                                       "call": call})
    t.start()
    again, new2 = coach.for_memo("run", "prep#r0", "super")  # the page opening a prefetched memo
    assert again is s and not new2
    got = {}
    w = threading.Thread(target=lambda: got.update(coach.notes_of(again)))
    w.start()
    gate.set()
    t.join()
    w.join()
    assert len(calls) == 1 and set(got["notes"]) == {"c1"}  # finding 9 does not exist
    assert "Prepare a note for every finding" in calls[0][1]["content"]
    assert "answer key" not in calls[0][1]["content"].lower()
    # a later check continues the same conversation, with the notes in it
    r = coach.turn(s, evidence="E", cards=CARDS, verdicts=[{"card_id": "c1", "action": "confirm"}],
                   raised=[], message=None, call=lambda **kw: _reply({"challenges": [],
                                                                       "reply": "ok"}))
    assert r["session_id"] == s.id and s.messages[2]["role"] == "assistant"
    kept = coach.record(s, [{"card_id": "c1", "action": "confirm"}],
                        [{"card_id": "c1", "action": "dispute"}])
    assert kept["answers_before"][0]["action"] == "dispute"
    assert kept["changed_after_coach"] == ["c1"]
    assert kept["challenged"] == [] and kept["notes"]["c1"]["evidence"].startswith("36.5%")
    coach.close(s.id)
    assert coach.for_memo("run", "prep#r0", "super")[1]  # closed: the next open prepares anew


def test_a_failed_preparation_is_reported_and_tried_again_next_time():
    def call(model, messages, **kw):
        raise OSError("connection refused")

    s, _ = coach.for_memo("run", "fail#r0", "super")
    try:
        coach.prepare(s, evidence="E", cards=CARDS, call=call)
    except OSError:
        pass
    try:
        coach.notes_of(s)
        raise AssertionError("expected the failure to be reported")
    except OSError as exc:
        assert "refused" in str(exc)
