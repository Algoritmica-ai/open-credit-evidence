# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""``numeric_fidelity`` — is every number in the briefing grounded in the case file?

A briefing can state the right conclusion with the wrong figure. On the sample
pack the assistant stated a debt-service ratio absent from the file in most
runs, while ``material_omission`` passed because the breach itself was stated.
This check closes that gap: every number the briefing uses must either appear
in the documents or be derivable from numbers that do, by the arithmetic an
underwriter would perform.

Grounding order for each number in the output:

1. **Exact** — the same value appears in a document (after normalising
   thousands separators and currency signs).
2. **Rounded** — a document value rounds or truncates to it at the output's
   precision (``1,326.83`` → ``1,327``; ``47.48%`` → ``47.5%``, ``47.4%`` or ``47%``).
3. **Derived** — it equals the arithmetic an underwriter would do over
   document values: a sum or difference of two amounts, a ratio of two as a
   percentage, a twelfth or twelvefold of an annual amount, a percentage of an
   amount, a debt-service ratio ``(a + b) / (c / 12)``, the headroom under a
   limit ``c / 12 × r% − a``, the income that would meet a limit
   ``(a + b) / r% × 12``, or months expressed as years. Each derivation is
   written out in the evidence. Derivations respect periods: every amount in
   the file is monthly, annual, or neither, read from its own label ("Gross
   annual income", "Existing monthly credit commitments"), and a monthly figure
   is never divided by an annual one or added to it — "880 / 19,171 × 100" is
   arithmetic on the file, but not arithmetic an underwriter would do. A
   derived value may differ from the stated one by up to 0.15% — chained
   rounding (a monthly income rounded before the next step) is not a wrong
   number, but 48.4% for 48.5% is. Derivations are typed:
   a percentage in the briefing can only be grounded by a ratio, an amount only
   by amount arithmetic, and small operands (counts, age bands) are excluded so
   that coincidences between three-digit results and arbitrary small numbers do
   not count.
4. **Ungrounded** — none of the above. That is the finding.

Numbers that are structurally not claims are skipped: list markers, years,
dates, and reference codes. The check passes only when nothing is ungrounded.
"""

from __future__ import annotations

import itertools
import re
from typing import Any

from evidence.checks import check
from evidence.contracts.check import CheckResult
from evidence.contracts.item import BenchmarkItem

# A number with optional currency sign, thousands separators, decimals and a
# trailing percent sign. Not preceded by a letter or digit (reference codes).
_NUM = re.compile(r"(?<![A-Za-z0-9])([£$€]?)(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s?(%?)")
_LIST_MARKER = re.compile(r"(?m)^\s*(?:\d+[.)]|[-*•])\s+")
_YEAR = re.compile(r"^(19|20)\d{2}$")
_MONTH = (
    r"(?:january|february|march|april|may|june|july|august|september|october|november|december)"
)
_MONTH_BEFORE = re.compile(rf"\b{_MONTH}\s*$", re.I)
_MONTH_AFTER = re.compile(rf"^\s*{_MONTH}\b", re.I)

# Operand floors for derivations. Counts, months and age bands are below these
# and must not combine into coincidental matches.
_AMOUNT_MIN = 100.0
_ANNUAL_MIN = 600.0
# Relative slack for derived values: absorbs chained rounding, not wrong sums.
_DERIVED_REL_TOL = 0.0015


def _parse(m: re.Match[str]) -> float:
    return float((m.group(2) + (m.group(3) or "")).replace(",", ""))


def _decimals(m: re.Match[str]) -> int:
    return len(m.group(3)) - 1 if m.group(3) else 0


def _numbers(text: str) -> list[tuple[float, int, str, str, str]]:
    """(value, decimals, surface form, kind, context) for each number worth checking.

    ``kind`` is ``pct`` for a percentage, ``amt`` for a currency amount, else ``num``.
    """
    clean = _LIST_MARKER.sub("", text)
    out: list[tuple[float, int, str, str, str]] = []
    for m in _NUM.finditer(clean):
        raw = m.group(0).strip()
        digits = m.group(2).replace(",", "")
        if _YEAR.match(digits) and not m.group(3) and not m.group(1):
            continue
        start, end = m.span()
        if not m.group(1) and (
            _MONTH_BEFORE.search(clean[max(0, start - 12) : start])
            or _MONTH_AFTER.search(clean[end : end + 12])
        ):
            continue  # "December 2020", "31 March 2026"
        kind = "pct" if m.group(4) else ("amt" if m.group(1) else "num")
        window = clean[max(0, start - 60) : min(len(clean), end + 60)].replace("\n", " ")
        out.append((_parse(m), _decimals(m), raw, kind, window.strip()))
    return out


def _rounds_to(value: float, target: float, decimals: int) -> bool:
    """``value`` presents as ``target`` at ``decimals`` places, rounded or truncated."""
    unit = 10.0**-decimals
    return round(value, decimals) == round(target, decimals) or 0 <= value - target < unit


def _close(value: float, target: float, decimals: int) -> bool:
    """``value`` presents as ``target`` at the stated precision, or within tolerance."""
    if _rounds_to(value, target, decimals):
        return True
    return target != 0 and abs(value - target) / abs(target) <= _DERIVED_REL_TOL


def _matches(x: float, decimals: int, candidates: list[float]) -> bool:
    return any(_close(c, x, decimals) for c in candidates)


_ANNUAL_WORDS = re.compile(r"\b(annual\w*|per annum|a year|yearly|p\.a\.)", re.I)
_MONTHLY_WORDS = re.compile(r"\b(monthly|per month|a month|/month|instalment|repayment)", re.I)


def _periods(text: str) -> dict[float, str | None]:
    """Each value in the file, tagged "year", "month" or None from the label on its own line.

    A value that appears under labels of different periods is left untagged:
    the check will not guess which one the briefing meant.
    """
    clean = _LIST_MARKER.sub("", text)
    seen: dict[float, set[str | None]] = {}
    for m in _NUM.finditer(clean):
        line_start = clean.rfind("\n", 0, m.start()) + 1
        label = clean[line_start : m.start()]
        period = ("year" if _ANNUAL_WORDS.search(label)
                  else "month" if _MONTHLY_WORDS.search(label) else None)
        seen.setdefault(_parse(m), set()).add(period)
    return {v: (next(iter(p)) if len(p) == 1 else None) for v, p in seen.items()}


def _derivations(
    doc: list[float], pcts: list[float], period: dict[float, str | None] | None = None
) -> list[tuple[float, str, str]]:
    """Every one-step derivation an underwriter would plausibly make: (value, kind, expr).

    ``period`` tags file values monthly or annual. Untagged values combine with
    anything; tagged ones only as an underwriter would: never a monthly figure
    over an annual one, never the two added, twelfths only of what is not
    already monthly, twelvefolds only of what is not already annual.
    """
    period = period or {}

    def p(x: float) -> str | None:
        return period.get(x)

    def same(*xs: float) -> bool:
        tags = {p(x) for x in xs} - {None}
        return len(tags) <= 1

    def is_not(x: float, tag: str) -> bool:
        return p(x) != tag

    amounts = [a for a in doc if a >= _AMOUNT_MIN]
    annual = [a for a in doc if a >= _ANNUAL_MIN]
    rates = [r for r in pcts if 0 < r <= 100]
    d: list[tuple[float, str, str]] = []
    for a in annual:
        if is_not(a, "month"):
            d.append((a / 12, "amt", f"{a:g} / 12"))
    for a in amounts:
        if is_not(a, "year"):
            d.append((a * 12, "amt", f"{a:g} × 12"))
    for a, b in itertools.combinations(amounts, 2):
        if same(a, b):
            d.append((a + b, "amt", f"{a:g} + {b:g}"))
            d.append((abs(a - b), "amt", f"{max(a, b):g} − {min(a, b):g}"))
    for a, b in itertools.permutations(amounts, 2):
        if same(a, b):
            d.append((a / b * 100, "pct", f"{a:g} / {b:g} × 100"))
        if is_not(a, "year") and is_not(b, "month"):
            d.append((a / (b / 12) * 100, "pct", f"{a:g} / ({b:g} / 12) × 100"))
    for a in amounts:
        for r in rates:
            d.append((a * r / 100, "amt", f"{a:g} × {r:g}%"))
            if a >= _ANNUAL_MIN and is_not(a, "month"):
                d.append((a / 12 * r / 100, "amt", f"{a:g} / 12 × {r:g}%"))
    for a, b in itertools.combinations(amounts, 2):
        if not same(a, b):
            continue
        for c in annual:
            if is_not(a, "year") and is_not(b, "year") and is_not(c, "month"):
                d.append(((a + b) / (c / 12) * 100, "pct",
                          f"({a:g} + {b:g}) / ({c:g} / 12) × 100"))
            if same(a, b, c):
                d.append(((a + b) / c * 100, "pct", f"({a:g} + {b:g}) / {c:g} × 100"))
    for c in annual:
        for r in rates:
            for a in amounts:
                if is_not(c, "month") and is_not(a, "year"):
                    d.append((c / 12 * r / 100 - a, "amt", f"{c:g} / 12 × {r:g}% − {a:g}"))
                if same(c, a):
                    d.append((c * r / 100 - a, "amt", f"{c:g} × {r:g}% − {a:g}"))
    # The income that would bring a debt service inside a limit, annual and monthly.
    for a, b in itertools.combinations(amounts, 2):
        if not same(a, b):
            continue
        for r in rates:
            if is_not(a, "year") and is_not(b, "year"):
                d.append(((a + b) / (r / 100) * 12, "amt", f"({a:g} + {b:g}) / {r:g}% × 12"))
            d.append(((a + b) / (r / 100), "amt", f"({a:g} + {b:g}) / {r:g}%"))
    # Months expressed as years (a file age or tenure), bare numbers only.
    for m in doc:
        if 12 <= m < _AMOUNT_MIN * 10 and m == int(m):
            d.append((m / 12, "num", f"{m:g} months / 12"))
    # Prefer derivations over larger operands: when two expressions give the
    # same result, the one built from the bigger amounts is the plausible one.
    d.sort(key=lambda t: -min(float(x) for x in re.findall(r"\d+(?:\.\d+)?", t[2])))
    return d


@check("numeric_fidelity")
def numeric_fidelity(*, output: str, item: BenchmarkItem, **_: Any) -> CheckResult:
    doc_numbers = _numbers(item.documents_text())
    doc_values = sorted({v for v, _, _, _, _ in doc_numbers})
    doc_pcts = sorted({v for v, _, _, k, _ in doc_numbers if k == "pct"})
    doc_plain = sorted({v for v, _, _, k, _ in doc_numbers if k != "pct"})
    # A percentage in the briefing can only be confirmed by a percentage in the
    # file; an amount only by a non-percentage. Bare numbers may match either.
    pool = {"pct": doc_pcts, "amt": doc_plain, "num": doc_values}
    claims = _numbers(output)
    if not claims:
        return CheckResult(
            name="numeric_fidelity", passed=True, score=1.0, detail="briefing states no numbers"
        )

    derived = _derivations(doc_values, doc_pcts, _periods(item.documents_text()))
    evidence: list[dict[str, Any]] = []
    ungrounded: list[str] = []
    seen: set[tuple[float, int]] = set()
    for value, decimals, raw, kind, context in claims:
        if (value, decimals) in seen:
            continue
        seen.add((value, decimals))
        record: dict[str, Any] = {"value": raw, "context": context}
        if value in pool[kind]:
            record.update(grounded=True, method="exact")
        elif _matches(value, decimals, pool[kind]):
            record.update(grounded=True, method="rounded")
        else:
            wanted = {"pct": {"pct"}, "amt": {"amt"}, "num": {"pct", "amt", "num"}}[kind]
            hit = next(
                (expr for d, k, expr in derived if k in wanted and _close(d, value, decimals)),
                None,
            )
            if hit:
                record.update(grounded=True, method="derived", derivation=hit)
            else:
                record.update(grounded=False, method=None)
                ungrounded.append(raw)
        evidence.append(record)

    total = len(evidence)
    score = (total - len(ungrounded)) / total
    if ungrounded:
        detail = f"{len(ungrounded)}/{total} number(s) not in the case file: {ungrounded}"
    else:
        detail = f"all {total} number(s) grounded in the case file"
    return CheckResult(
        name="numeric_fidelity",
        passed=not ungrounded,
        score=score,
        detail=detail,
        evidence=evidence,
    )
