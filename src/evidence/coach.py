# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""The coach: a second pair of eyes that debates a reviewer's answers before they are saved.

One inference session per memo review, separate from the judge panel and from every other
review. The coach sees what the reviewer sees (the memo, the findings with their evidence,
the case file, the rule checks) plus the reference figures computed from the case file, and
the reviewer's current answers. It does not see the answer key. It asks about answers that
look inconsistent with the evidence and points at the evidence; it never says what to
answer. The reviewer can change an answer, argue back, or keep their answers and save.

The review keeps the answers from before the coach and the final ones, and the whole
conversation, so the evidence shows which answers the coach changed, and whether that made
them agree more or less with the known answers.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from evidence import panel

COACH_VERSION = "coach-v1"
MAX_TOKENS = 4000
MAX_SESSIONS = 200  # sessions live in memory until the review is saved

SYSTEM = (
    "You are the coach beside a credit underwriter who is reviewing a memo an AI assistant "
    "wrote for a referred loan application. Automatic checks and a panel of AI reviewers "
    "raised findings on the memo; for each finding the underwriter answers whether the memo "
    "is wrong there, and may add problems of their own.\n\n"
    "Your job is to challenge the underwriter's answers before they are saved, so that each "
    "one rests on the evidence. You do not decide and you do not give verdicts. Where an "
    "answer looks inconsistent with the case file, the reference figures or the check "
    "evidence, ask one short question and quote the evidence it rests on. Where an answer "
    "agrees with the evidence, say nothing about it. You may point at a problem in the memo "
    "that no finding covers. Never tell the underwriter what to answer, and never state a "
    "conclusion about the memo (not \"so the memo is wrong\"): say what the evidence shows "
    "and leave the conclusion to them. When two findings are about the same sentence, ask "
    "once and name both. When they reply, answer their point directly and briefly from the "
    "evidence; if they are right, say so.\n\n"
    "The reference figures were computed exactly from the case file and are correct. A "
    "difference that rounding explains (under half a percentage point) is not an error.\n\n"
    "Answer with one JSON object and nothing else: "
    '{"challenges": [{"finding": <the finding number, or null for something no finding '
    'covers>, "also": [<other finding numbers about the same sentence>], "question": "one '
    'short question", "evidence": "the line or figure it rests on"}], "reply": "one or two '
    'sentences to the underwriter"}. At most three challenges, the most important first; '
    "none when every answer holds."
)

ANSWER_WORDS = {
    "confirm": "the memo is wrong here",
    "dispute": "the memo is right",
    "needs_more": "not sure",
    None: "not answered yet",
}
REASON_WORDS = {
    "wrong_figure": "the figure is correct",
    "wrong_policy_reading": "the policy was read correctly",
    "not_material": "it doesn't change the decision",
    "finding_wrong": "the finding itself is mistaken",
}


@dataclass
class Session:
    """One coach conversation, for one review of one memo."""

    id: str
    run: str
    memo: str
    model: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    turns: list[dict[str, Any]] = field(default_factory=list)
    first_answers: list[dict[str, Any]] | None = None
    started_at: str = field(default_factory=lambda: _now())
    used_at: float = field(default_factory=time.time)


_sessions: dict[str, Session] = {}
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def evidence_block(memo_text: str, cards: list[dict[str, Any]], case_file: str,
                   figures: str | None, checks: list[dict[str, Any]]) -> str:
    """What the coach knows about the memo: the same as the reviewer, plus the figures."""
    found = "\n".join(
        f"Finding {n}: {c.get('kind')}. {c.get('problem')}"
        + (f"\n  Memo sentence: \"{c['sentence']}\"" if c.get("sentence") else "")
        + (f"\n  Evidence given: {c['evidence']}" if c.get("evidence") else "")
        + f"\n  Raised by: {'a rule check' if c.get('known_answer') else 'the AI reviewers'}"
        for n, c in enumerate(cards, 1))
    rule = "\n".join(f"{c['check']}: {'pass' if c['passed'] else 'FAIL'} — {c.get('detail')}"
                     for c in checks) or "none"
    return (f"THE MEMO:\n{memo_text}\n\nTHE FINDINGS:\n{found or 'none'}\n\n"
            f"THE CASE FILE:\n{case_file}\n\n"
            + (f"REFERENCE FIGURES:\n{figures}\n\n" if figures else "")
            + f"RULE CHECKS ON THIS MEMO:\n{rule}")


def answers_block(cards: list[dict[str, Any]], verdicts: list[dict[str, Any]],
                  raised: list[dict[str, Any]]) -> str:
    by_card = {v.get("card_id"): v for v in verdicts}
    lines = []
    for n, c in enumerate(cards, 1):
        v = by_card.get(c["card_id"]) or {}
        line = f"Finding {n}: {ANSWER_WORDS.get(v.get('action'), v.get('action'))}"
        if v.get("reason"):
            line += f", because {REASON_WORDS.get(v['reason'], v['reason'])}"
        if v.get("correction"):
            line += f"; they would write instead: \"{v['correction']}\""
        lines.append(line)
    for r in raised:
        lines.append(f"A problem they added: {r.get('problem')}"
                     + (f" (in \"{r['sentence']}\")" if r.get("sentence") else ""))
    return "\n".join(lines) or "no answers yet"


def _snapshot(verdicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v.get(k) for k in ("card_id", "action", "reason", "correction")}
            for v in verdicts]


def get(session_id: str | None) -> Session | None:
    with _lock:
        return _sessions.get(session_id or "")


def start(run: str, memo: str, model: str) -> Session:
    with _lock:
        if len(_sessions) >= MAX_SESSIONS:  # the oldest unsaved conversations go first
            for sid in sorted(_sessions, key=lambda k: _sessions[k].used_at)[:20]:
                _sessions.pop(sid, None)
        s = Session(id=uuid.uuid4().hex[:12], run=run, memo=memo, model=model)
        _sessions[s.id] = s
        return s


def turn(s: Session, *, evidence: str, cards: list[dict[str, Any]],
         verdicts: list[dict[str, Any]], raised: list[dict[str, Any]], message: str | None,
         call: Callable[..., dict[str, Any]]) -> dict[str, Any]:
    """One exchange: the coach reads the reviewer's current answers (and their message, if
    any) and replies with its challenges. ``call`` is panel.chat bound to an endpoint."""
    answers = answers_block(cards, verdicts, raised)
    if not s.messages:
        s.first_answers = _snapshot(verdicts)
        s.messages = [{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": f"{evidence}\n\nTHE UNDERWRITER'S ANSWERS:\n"
                                                  f"{answers}\n\nCheck their answers."}]
    else:
        s.messages.append({"role": "user", "content": f"THE UNDERWRITER'S ANSWERS NOW:\n"
                           f"{answers}" + (f"\n\nTHE UNDERWRITER SAYS: {message}"
                                           if message else "\n\nCheck their answers again.")})
    t0 = time.time()
    reply = call(model=s.model, messages=s.messages, max_tokens=MAX_TOKENS)
    text = ((reply.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    parsed = panel.parse_json(text, ("challenges",))
    if parsed is None:  # the answer went on reasoning: once more, answer only
        s.messages.append({"role": "assistant", "content": text})
        s.messages.append({"role": "user", "content": "Give your answer now: the JSON object "
                           "asked for, and nothing else."})
        reply = call(model=s.model, messages=s.messages, max_tokens=MAX_TOKENS, json_only=True)
        text = ((reply.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        parsed = panel.parse_json(text, ("challenges",))
    parsed = parsed or {"challenges": [], "reply": "The coach could not answer this time."}
    challenges = []
    for ch in parsed.get("challenges") or []:
        if not isinstance(ch, dict) or not ch.get("question"):
            continue
        n = ch.get("finding")
        n = n if isinstance(n, int) and 1 <= n <= len(cards) else None
        also = [a for a in ch.get("also") or [] if isinstance(a, int) and 1 <= a <= len(cards)
                and a != n]
        challenges.append({"finding": n, "card_id": cards[n - 1]["card_id"] if n else None,
                           "also": also, "also_card_ids": [cards[a - 1]["card_id"] for a in also],
                           "question": str(ch["question"])[:600],
                           "evidence": str(ch.get("evidence") or "")[:600]})
    out = {"challenges": challenges[:3], "reply": str(parsed.get("reply") or "")[:800]}
    s.messages.append({"role": "assistant", "content": json.dumps(out, ensure_ascii=False)})
    s.turns.append({"at": _now(), "answers": _snapshot(verdicts), "message": message,
                    "coach": out, "latency_ms": int((time.time() - t0) * 1000),
                    "usage": reply.get("usage")})
    s.used_at = time.time()
    return {"session_id": s.id, "turn": len(s.turns)} | out


def record(s: Session, final: list[dict[str, Any]]) -> dict[str, Any]:
    """What the review keeps of the conversation: the answers before the coach, which
    answers changed after it, what it challenged, and every exchange."""
    first = {v["card_id"]: v for v in (s.first_answers or [])}
    changed = sorted(v["card_id"] for v in final
                     if v.get("card_id") in first
                     and (first[v["card_id"]].get("action"), first[v["card_id"]].get("reason"))
                     != (v.get("action"), v.get("reason")))
    challenged = sorted({cid for t in s.turns for c in t["coach"]["challenges"]
                         for cid in [c.get("card_id"), *c.get("also_card_ids", [])] if cid})
    return {"session": s.id, "version": COACH_VERSION, "model": s.model,
            "started_at": s.started_at, "turns": len(s.turns),
            "answers_before": s.first_answers or [], "changed_after_coach": changed,
            "challenged": challenged,
            "conversation": [{k: t[k] for k in ("at", "message", "coach", "latency_ms")}
                             for t in s.turns]}


def close(session_id: str) -> None:
    with _lock:
        _sessions.pop(session_id, None)
