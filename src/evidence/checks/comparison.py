# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""``comparison_fidelity`` — does every comparison the briefing states hold?

"The bureau score of 652 is below the 600 threshold" passes every other check:
both numbers are in the case file, the lever is named, nothing irrelevant is
blamed, and the judge scores it as clear. It is wrong, and it tells the
underwriter a rule was breached when it was not. This check reads each sentence
that states one number is below or above another and tests it. It needs no case
knowledge: a stated comparison between two numbers is true or false on its face.

A comparison is read when a number, a relation and a second number appear in
that order in one clause::

    <A>  up to 40 characters, no digits, brackets, quotes or colons  <relation>  up to 25  <B>

- *below*: below, under, less than, lower than, beneath, short of (A < B);
  at or below (A ≤ B)
- *above*: above, over, exceeds, greater than, higher than, more than, in excess
  of, breaches (A > B); at or above (A ≥ B)
- a negation just before the relation ("does not exceed", "is not below") turns
  it round

Skipped, because they are not statements about the case as it stands:
conditions and targets ("would need to fall below 40%", "if the score rose above
600") — a modal or conditional word between A and the relation; and pairs of
different kinds (a percentage against an amount, a duration against a count),
which is also how "£9,323 over 36 months" is not read as a comparison.

The check passes when no stated comparison is false. A briefing that states no
comparison passes.
"""

from __future__ import annotations

import re
from typing import Any

from evidence.checks import check
from evidence.contracts.check import CheckResult
from evidence.contracts.item import BenchmarkItem

_NUM = re.compile(
    r"(?<![A-Za-z0-9.])([£$€]?)(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s?(%?)"
    r"(?:\s*-?\s*(months?|years?|weeks?|days?)\b)?",
    re.I,
)
_YEAR = re.compile(r"^(19|20)\d{2}$")
_LIST_MARKER = re.compile(r"(?m)^\s*(?:\d+[.)]|[-*•])\s+")

# Longest first, so "at or below" is not read as "below".
_RELATIONS: list[tuple[str, str]] = [
    (r"at or below", "le"),
    (r"at or above", "ge"),
    (r"in excess of", "gt"),
    (r"less than", "lt"),
    (r"lower than", "lt"),
    (r"short of", "lt"),
    (r"greater than", "gt"),
    (r"higher than", "gt"),
    (r"more than", "gt"),
    (r"below", "lt"),
    (r"under", "lt"),
    (r"beneath", "lt"),
    (r"above", "gt"),
    (r"over", "gt"),
    (r"exceed(?:s|ed|ing)?", "gt"),
    (r"breach(?:es|ed|ing)?", "gt"),
]
_REL = re.compile(r"\b(" + "|".join(p for p, _ in _RELATIONS) + r")\b", re.I)
_NEGATION = re.compile(r"\b(not|n't|no|never)\s+$", re.I)
_CONDITIONAL = re.compile(
    r"\b(would|could|should|must|might|need|needs|needed|to|if|unless|once|when|until|"
    r"were|require|requires|required)\b",
    re.I,
)
_BARRIER = re.compile(r"[\d()\[\]\"“”:;]")
_PRE_MAX = 40
_POST_MAX = 25
_OPS = {
    "lt": lambda a, b: a < b,
    "le": lambda a, b: a <= b,
    "gt": lambda a, b: a > b,
    "ge": lambda a, b: a >= b,
}
_NEGATED = {"lt": "ge", "le": "gt", "gt": "le", "ge": "lt"}
_SYMBOL = {"lt": "<", "le": "≤", "gt": ">", "ge": "≥"}


def _kind(m: re.Match[str]) -> str:
    if m.group(4):
        return "pct"
    if m.group(1):
        return "amt"
    if m.group(5):
        return "dur"
    return "num"


def _numbers(sentence: str) -> list[re.Match[str]]:
    out = []
    for m in _NUM.finditer(sentence):
        if _YEAR.match(m.group(2)) and not (m.group(1) or m.group(3) or m.group(4)):
            continue
        out.append(m)
    return out


def _value(m: re.Match[str]) -> float:
    return float((m.group(2) + (m.group(3) or "")).replace(",", ""))


def _sentences(text: str) -> list[str]:
    clean = _LIST_MARKER.sub("", text).replace("**", "").replace("__", "")
    parts = re.split(r"(?<=[.!?])\s+|\n+", clean)
    return [p.strip() for p in parts if p.strip()]


def comparisons(text: str) -> list[dict[str, Any]]:
    """Every stated comparison in ``text``, each with whether it holds."""
    found: list[dict[str, Any]] = []
    for s in _sentences(text):
        nums = _numbers(s)
        for a, b in zip(nums, nums[1:], strict=False):
            gap = s[a.end() : b.start()]
            rel = _REL.search(gap)
            if not rel:
                continue
            pre, post = gap[: rel.start()], gap[rel.end() :]
            if len(pre) > _PRE_MAX or len(post) > _POST_MAX:
                continue
            if _BARRIER.search(pre) or _BARRIER.search(post) or _CONDITIONAL.search(pre):
                continue
            if _kind(a) != _kind(b):
                continue
            op = next(o for p, o in _RELATIONS if re.fullmatch(p, rel.group(1), re.I))
            if _NEGATION.search(pre):
                op = _NEGATED[op]
            left, right = _value(a), _value(b)
            found.append(
                {
                    "sentence": s,
                    "left": a.group(0).strip(),
                    "relation": rel.group(1).lower(),
                    "right": b.group(0).strip(),
                    "reads_as": f"{left:g} {_SYMBOL[op]} {right:g}",
                    "holds": _OPS[op](left, right),
                }
            )
    return found


@check("comparison_fidelity")
def comparison_fidelity(*, output: str, item: BenchmarkItem, **_: Any) -> CheckResult:
    found = comparisons(output)
    if not found:
        return CheckResult(
            name="comparison_fidelity", passed=True, score=1.0, detail="no comparison stated"
        )
    false = [c for c in found if not c["holds"]]
    score = 1.0 - len(false) / len(found)
    if false:
        shown = [f"{c['left']} {c['relation']} {c['right']}" for c in false]
        detail = f"{len(false)}/{len(found)} stated comparison(s) false: {shown}"
    else:
        detail = f"all {len(found)} stated comparison(s) hold"
    return CheckResult(
        name="comparison_fidelity",
        passed=not false,
        score=round(score, 4),
        detail=detail,
        evidence=found,
    )
