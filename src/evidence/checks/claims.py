# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""``claim_consistency`` — does the briefing's own figure support the breach it claims?

"The total monthly debt service exceeds the 40% affordability threshold …
this represents 33.2%." Each sentence passes on its own: 40% is in the policy,
33.2% is the right ratio, and neither sentence compares two numbers. Together
they say a limit was breached and then show that it was not. The underwriter is
told the wrong reason for the referral.

The item names the quantities a briefing may hold against a policy limit
(``claim_aliases`` — for a loan, the debt-to-income ratio: "debt service",
"DTI", "affordability", …). For each:

1. **Claims** — a sentence that names the quantity and says it is above or
   below a percentage: "exceeds the 40% threshold", "within the 40% limit".
2. **Figures** — every other percentage the briefing gives for that quantity:
   "represents 33.2%", "a DTI of 47.5%".
3. **Contradiction** — a claim that the quantity is above L next to a figure at
   or below L, or the reverse.

Conditions, targets and remedies are neither claims nor figures ("would need
to fall below 40%", "reduce it to 38%", "so that debt service does not exceed
40%", "e.g. below 35%"). A percentage equal to the limit is the limit,
not a figure. The check passes when nothing contradicts; a briefing that makes
no claim passes.
"""

from __future__ import annotations

import re
from typing import Any

from evidence.checks import check
from evidence.checks.comparison import _CONDITIONAL, _sentences
from evidence.contracts.check import CheckResult
from evidence.contracts.item import BenchmarkItem

_PCT = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?%")
_ABOVE = r"exceed\w*|above|over|breach\w*|greater than|higher than|more than|in excess of"
_BELOW = r"below|under|within|less than|lower than|beneath|short of"
# relation, up to 30 characters, then the limit
_CLAIM = re.compile(
    rf"\b(?P<rel>{_ABOVE}|{_BELOW})\b(?P<gap>[^%\d]{{0,30}}?)(?P<lim>\d+(?:\.\d+)?)\s?%", re.I
)
# What a remedy looks like: "reduce the instalment so that debt service falls below
# 40%", "e.g. below 35%". Before a relation, these make it a target, not a claim.
_REMEDY = re.compile(r"\b(so that|in order to|so as to|bring\w*|reduc\w*|lower\w*|increas\w*|"
                     r"e\.g\.|for example|such as|aim\w*|target\w*)", re.I)
_TARGET = re.compile(rf"\b({_ABOVE}|{_BELOW}|to|at most|at least|no more than)\s*(the\s+)?$", re.I)
_NEGATION = re.compile(r"\b(not|n't|no longer|never)\b[^,;]{0,20}$", re.I)


def _names(sentence: str, aliases: list[str]) -> bool:
    low = sentence.lower()
    return any(re.search(rf"\b{re.escape(a.lower())}\b", low) for a in aliases if a)


def _claims(sentence: str) -> list[dict[str, Any]]:
    out = []
    for m in _CLAIM.finditer(sentence):
        before = sentence[: m.start()]
        if _CONDITIONAL.search(before) or _REMEDY.search(before):
            continue  # "would need to fall below 40%", "so that it falls below 40%": targets
        above = re.fullmatch(_ABOVE, m.group("rel"), re.I) is not None
        if _NEGATION.search(before):
            above = not above  # "does not exceed 40%"
        out.append({"limit": float(m.group("lim")), "above": above,
                    "says": m.group(0).strip(), "span": m.span("lim")})
    return out


def _figures(sentence: str, limits: set[float], claim_spans: list[tuple[int, int]]) -> list[float]:
    out = []
    for m in _PCT.finditer(sentence):
        value = float(m.group(1))
        if value in limits or any(a <= m.start(1) < b for a, b in claim_spans):
            continue  # the limit itself
        before = sentence[max(0, m.start() - 40) : m.start()]
        lead = sentence[: m.start()]
        if _CONDITIONAL.search(lead) or _REMEDY.search(lead) or _TARGET.search(before):
            continue  # a condition or a target, not the figure as it stands
        out.append(value)
    return out


@check("claim_consistency")
def claim_consistency(*, output: str, item: BenchmarkItem, **_: Any) -> CheckResult:
    quantities = {q: a for q, a in item.grading.claim_aliases.items() if a}
    if not quantities:
        return CheckResult(name="claim_consistency", passed=True, score=1.0,
                           detail="no limited quantity declared")
    sentences = _sentences(output)
    evidence: list[dict[str, Any]] = []
    contradictions = 0
    for q, aliases in quantities.items():
        about = [s for s in sentences if _names(s, aliases)]
        claims = [(s, c) for s in about for c in _claims(s)]
        if not claims:
            continue
        limits = {c["limit"] for _, c in claims}
        figures = [(s, v) for s in about
                   for v in _figures(s, limits, [c["span"] for s2, c in claims if s2 is s])]
        for s, c in claims:
            wrong = [(fs, v) for fs, v in figures
                     if (c["above"] and v <= c["limit"]) or (not c["above"] and v >= c["limit"])]
            entry = {"quantity": q, "claim": c["says"], "claim_sentence": s,
                     "claims": ("above " if c["above"] else "at or below ") + f"{c['limit']:g}%",
                     "figures": sorted({v for _, v in figures}), "holds": not wrong}
            if wrong:
                contradictions += 1
                entry |= {"contradicted_by": wrong[0][1], "figure_sentence": wrong[0][0]}
            evidence.append(entry)

    if not evidence:
        return CheckResult(name="claim_consistency", passed=True, score=1.0,
                           detail="no limit claim stated")
    score = 1.0 - contradictions / len(evidence)
    if contradictions:
        bad = [f"claims {e['claims']}, states {e['contradicted_by']:g}%"
               for e in evidence if not e["holds"]]
        detail = f"{contradictions}/{len(evidence)} limit claim(s) contradicted: {bad}"
    else:
        detail = f"all {len(evidence)} limit claim(s) consistent with the figures stated"
    return CheckResult(name="claim_consistency", passed=not contradictions,
                       score=round(score, 4), detail=detail, evidence=evidence)
