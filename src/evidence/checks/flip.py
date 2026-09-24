# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""``flip_accuracy`` — did the briefing name what would change the outcome?

The item carries ``flip_refs``: the field that would flip the disposition and
the direction it would have to move — never the threshold. The check looks for
a sentence that names the field (by any alias) together with a direction word
consistent with the declared one.

An outcome can usually be changed more than one way. ``flip_alternatives``
lists, per flip ref, the other levers that change the same outcome — for a
debt-to-income breach: a smaller loan, a longer term, lower existing
commitments — and naming any one of them with its direction counts. A briefing
that says "debt service must be reduced" has named a way to change the outcome
even though it did not mention income.

Scoring per flip ref: 1.0 if it or an alternative is named with the right
direction, 0.5 if one is named with no direction or the wrong one, 0.0 if none
is. The check passes only when every declared lever is named with its direction.
"""

from __future__ import annotations

import re
from typing import Any

from evidence.checks import check
from evidence.contracts.check import CheckResult
from evidence.contracts.item import BenchmarkItem

# Stems, not words: "increase\w*" misses "increasing" and "reduce\w*" misses
# "reducing", which is how most briefings phrase a lever.
_DIRECTION = {
    "increase": re.compile(
        r"\b(increas\w*|higher|rais\w*|more|additional|greater|improv\w*|grow\w*|"
        r"longer|older|boost\w*|supplement\w*|extra|extend\w*|extension|"
        r"ris(?:e|es|en|ing)|rose)\b",
        re.I,
    ),
    "decrease": re.compile(
        r"\b(decreas\w*|lower\w*|reduc\w*|less|smaller|fewer|cut\w*|"
        r"shorter|pa(?:y|ys|ying|id) (?:off|down)|clear\w*)\b",
        re.I,
    ),
}


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


@check("flip_accuracy")
def flip_accuracy(*, output: str, item: BenchmarkItem, **_: Any) -> CheckResult:
    g = item.grading
    if not g.flip_refs:
        return CheckResult(
            name="flip_accuracy", passed=True, score=1.0, detail="no flip lever declared"
        )

    sentences = _sentences(output)
    evidence: list[dict[str, Any]] = []
    total = 0.0
    for flip in g.flip_refs:
        accepted = [flip, *g.flip_alternatives.get(flip.ref, [])]
        reads = [_read(lever, g.flip_aliases, sentences) for lever in accepted]
        right = next((r for r in reads if r.get("direction") == r["expected"]), None)
        named = next((r for r in reads if r["found"]), None)
        best = right or named or reads[0]
        total += 1.0 if right else 0.5 if named else 0.0
        entry = {"lever": flip.ref} | best
        if len(accepted) > 1:
            entry["accepted"] = [f"{x.ref} {x.direction}" for x in accepted]
        evidence.append(entry)

    score = total / len(g.flip_refs)
    passed = score == 1.0
    missing = [e["lever"] for e in evidence if not e["found"]]
    undirected = [e["ref"] for e in evidence if e["found"] and e.get("direction") != e["expected"]]
    if passed:
        detail = f"named {len(g.flip_refs)} lever(s) with the right direction"
    else:
        parts = []
        if missing:
            parts.append(f"lever not named: {missing}")
        if undirected:
            parts.append(f"named without the right direction: {undirected}")
        detail = "; ".join(parts)
    return CheckResult(
        name="flip_accuracy", passed=passed, score=score, detail=detail, evidence=evidence
    )


def _read(lever: Any, aliases: dict[str, list[str]], sentences: list[str]) -> dict[str, Any]:
    """Is this lever named, and with which direction?"""
    forms = [a for a in aliases.get(lever.ref, []) if a] or [lever.ref.replace("_", " ")]
    named = [
        s for s in sentences
        if any(re.search(rf"\b{re.escape(a.lower())}\b", s.lower()) for a in forms)
    ]
    out: dict[str, Any] = {"ref": lever.ref, "expected": lever.direction, "found": bool(named)}
    if not named:
        return out
    want = _DIRECTION[lever.direction]
    other = _DIRECTION["decrease" if lever.direction == "increase" else "increase"]
    with_dir = [s for s in named if want.search(s)]
    if with_dir:
        return out | {"direction": lever.direction, "sentence": with_dir[0]}
    wrong = [s for s in named if other.search(s)]
    return out | {"direction": "opposite" if wrong else None, "sentence": (wrong or named)[0]}
