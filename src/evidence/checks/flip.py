# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""``flip_accuracy`` — did the briefing name what would change the outcome?

The item carries ``flip_refs``: the field that would flip the disposition and
the direction it would have to move — never the threshold. The check looks for
a sentence that names the field (by any alias) together with a direction word
consistent with the declared one.

Scoring per flip ref: 1.0 if the field is named with the right direction,
0.5 if the field is named with no direction or the wrong one, 0.0 if absent.
The check passes only when every declared lever is named with its direction.
"""

from __future__ import annotations

import re
from typing import Any

from evidence.checks import check
from evidence.contracts.check import CheckResult
from evidence.contracts.item import BenchmarkItem

_DIRECTION = {
    "increase": re.compile(
        r"\b(increase\w*|higher|raise\w*|more|additional|greater|improve\w*|grow\w*|"
        r"longer|older|boost\w*|supplement\w*|extra)\b",
        re.I,
    ),
    "decrease": re.compile(
        r"\b(decrease\w*|lower\w*|reduce\w*|reduction|less|smaller|fewer|cut\w*|"
        r"shorter|pay(?:ing)? (?:off|down)|clear\w*)\b",
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
        aliases = [a for a in g.flip_aliases.get(flip.ref, []) if a] or [flip.ref.replace("_", " ")]
        named = [
            s
            for s in sentences
            if any(re.search(rf"\b{re.escape(a.lower())}\b", s.lower()) for a in aliases)
        ]
        if not named:
            evidence.append({"ref": flip.ref, "expected": flip.direction, "found": False})
            continue
        want = _DIRECTION[flip.direction]
        other = _DIRECTION["decrease" if flip.direction == "increase" else "increase"]
        with_dir = [s for s in named if want.search(s)]
        if with_dir:
            total += 1.0
            evidence.append(
                {
                    "ref": flip.ref,
                    "expected": flip.direction,
                    "found": True,
                    "direction": flip.direction,
                    "sentence": with_dir[0],
                }
            )
        else:
            total += 0.5
            wrong = [s for s in named if other.search(s)]
            evidence.append(
                {
                    "ref": flip.ref,
                    "expected": flip.direction,
                    "found": True,
                    "direction": "opposite" if wrong else None,
                    "sentence": (wrong or named)[0],
                }
            )

    score = total / len(g.flip_refs)
    passed = score == 1.0
    missing = [e["ref"] for e in evidence if not e["found"]]
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
