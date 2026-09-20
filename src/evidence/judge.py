# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""The readability judge — a model asked what a formula cannot answer, against the
regulation that sets the standard.

The judge is handed the briefing and the passages of regulation retrieved for it
(from a built corpus, see :mod:`evidence.corpus`) and asked three things: could
the underwriter understand it, could they tell what would need to change, and
does it give them enough to disagree with or override it. It must cite the
passage it relied on, and the citation must be one it was given. It is **not**
asked whether the briefing is complete or correct; the deterministic checks own
that.

Which model answers is a deployment decision (``EVIDENCE_JUDGE_BASE_URL`` /
``EVIDENCE_JUDGE_MODEL``): Nemotron 3 Ultra on NVIDIA Build, or a distilled
Nano served on-prem. Every record names the model, the endpoint, the passages
it saw and the corpus version they came from.
"""

from __future__ import annotations

import json
import re
from typing import Any

from evidence.adapters.nvidia_build import chat
from evidence.contracts.item import BenchmarkItem
from evidence.corpus import Corpus, Passage

FIELDS = ("intelligible", "actionable", "overridable")
MAX_PER_FIELD = 2
# Thinking tokens count against max_tokens on a reasoning model; leave room.
JUDGE_MAX_TOKENS = 2500
PASSAGES_PER_CALL = 2

RUBRIC = (
    "You are grading an underwriter briefing written by an AI assistant. The assistant "
    "supports a human who makes a credit decision; under the EU AI Act this is a high-risk "
    "use, and the regulation passages below set the standard for what that human must be "
    "able to do with the assistant's output.\n\n"
    "Grade readability and oversight only. Answer with one JSON object and nothing else:\n"
    '{"intelligible": 0-2, "actionable": 0-2, "overridable": 0-2, '
    '"citation": "<passage id>", "reason": "one or two sentences"}\n'
    "intelligible: could an underwriter understand the briefing without re-reading the "
    "file (0 no, 1 partly, 2 yes).\n"
    "actionable: can they tell what would need to change for a different outcome "
    "(0 no, 1 partly, 2 yes).\n"
    "overridable: does the briefing give them enough to disagree with it or reverse it — "
    "the reasons and the facts they rest on (0 no, 1 partly, 2 yes).\n"
    "citation: the id of the passage you relied on most; it must be one of the passages "
    "given below.\n"
    "Do not grade whether the briefing is complete or numerically correct; that is checked "
    "elsewhere."
)
# The retrieval query is the standard the judge applies, not the briefing:
# which passage governs is a property of the task, and a briefing's own words
# (income, ratio, instalment) would pull in nothing useful. The briefing's
# opening is appended so a corpus with domain-specific passages can still
# rank them.
RETRIEVAL_QUERY = (
    "Human oversight of a high-risk AI system used to evaluate the creditworthiness of a "
    "natural person: the person overseeing it must be able to understand and correctly "
    "interpret its output, and to decide to disregard, override or reverse it."
)
_JSON = re.compile(r"\{.*?\}", re.S)
_FIELDS = re.compile(
    r'"intelligible"\s*:\s*(\d)\D+"actionable"\s*:\s*(\d)(?:\D+"overridable"\s*:\s*(\d))?', re.S
)


def parse_scores(text: str) -> dict[str, Any] | None:
    """First JSON object in the reply with the score fields, else None."""
    for m in _JSON.finditer(text):
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
        if {"intelligible", "actionable"} <= obj.keys():
            try:
                for f in FIELDS:
                    if f in obj:
                        obj[f] = max(0, min(MAX_PER_FIELD, int(obj[f])))
            except (TypeError, ValueError):
                continue
            return obj
    # A truncated reply may still carry the scores before the cut.
    m = _FIELDS.search(text)
    if m:
        obj = {
            "intelligible": int(m.group(1)),
            "actionable": int(m.group(2)),
            "reason": "(reply truncated; scores recovered)",
        }
        if m.group(3):
            obj["overridable"] = int(m.group(3))
        return obj
    return None


def passages_block(passages: list[Passage]) -> str:
    return "\n\n".join(f"[{p.passage_id}] {p.citation} — {p.title}\n{p.text}" for p in passages)


def judge_readability(
    *,
    output: str,
    item: BenchmarkItem,
    corpus: Corpus | None = None,
    max_tokens: int = JUDGE_MAX_TOKENS,
) -> dict[str, Any]:
    """One judge call, returned in the same record shape as a check score."""
    passages: list[Passage] = []
    if corpus is not None:
        query = f"{RETRIEVAL_QUERY}\n\n{output[:500]}"
        passages = [p for p, _ in corpus.retrieve(query, k=PASSAGES_PER_CALL)]
    system = RUBRIC + (
        "\n\nREGULATION PASSAGES:\n\n" + passages_block(passages) if passages else ""
    )
    r = chat("judge", system=system, user=f"BRIEFING:\n{output}", max_tokens=max_tokens)
    scores = parse_scores(r.text)
    base: dict[str, Any] = {
        "judge": f"model:{r.model_id}",
        "judge_trace_id": r.raw_id,
        "endpoint": r.endpoint,
        "prompt_version": r.prompt_version,
        "latency_ms": r.latency_ms,
        "passages": [p.passage_id for p in passages],
        "corpus_sha256": corpus.sha256 if corpus else None,
        "needs_audit": True,  # a model opinion is always auditable
    }
    if scores is None:
        return base | {
            "value": None,
            "passed": None,
            "detail": "judge reply was not parseable JSON",
            "evidence": [{"raw": r.text[:500]}],
        }
    given = {p.passage_id for p in passages}
    citation = str(scores.get("citation", "")).strip()
    citation_ok = (citation in given) if passages else None
    fields = {f: scores[f] for f in FIELDS if f in scores}
    total = sum(fields.values())
    return (
        base
        | {
            "value": round(total / (MAX_PER_FIELD * len(fields)), 3) if fields else None,
            "passed": None,  # readability is reported, not gated
            "detail": str(scores.get("reason", ""))[:400],
            "evidence": [
                fields | {"citation": citation or None, "citation_in_passages": citation_ok}
            ],
        }
    )
