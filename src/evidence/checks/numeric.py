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

**Version 2** (the current one) tightened grounding, after a memo's wrong figure was
found grounded as "2026.1 − 1067": the policy version minus the postal code.

- Amount arithmetic takes only amounts the file states as money (with a currency sign),
  and percentages. Scores, counts, postal codes and policy versions are not operands.
  Only numbers the file gives in months become years.
- Among derivations that give the same number, the one an underwriter would make is
  written into the evidence: a debt-service ratio before a ratio of any two amounts.
- How far a debt service is over a limit (``a + b − c / 12 × r%``), the amount by which
  commitments would have to fall, is a derivation.
- A rounded length in years ("over 10 years", "almost 14 years", "about 13 years") is
  grounded when a number of months in the file bears it out.
- The ends of a stated range ("€2,000 to €40,000") are limits and are not operands; a
  label ("Option 3") is not a figure; "14 years and 9 months" is grounded by 177 months.
- A number without a percent sign is not grounded by a percentage calculation: "almost
  20 years" is not "688 / (40,000 / 12) × 100".
- A gap between two percentages ("11.1 percentage points above the 40% limit") is
  grounded when it is the difference of two percentages the file or the briefing's own
  grounded figures state. A number followed by "percentage points" is grounded only that
  way.

Version 1 stays runnable (``version=1``), so runs scored with it re-derive as scored.
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


_YEARS_WORDS = {"over": "gt", "more than": "gt", "above": "gt", "almost": "lt",
                "nearly": "lt", "under": "lt", "less than": "lt", "about": "eq",
                "approximately": "eq", "around": "eq", "roughly": "eq", "some": "eq"}
# "€2,000 to €40,000": the ends of a range are limits, not figures to calculate with
_RANGE = re.compile(r"([£$€])\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*(?:to|–|-|and)\s*"
                    r"[£$€]\s?(\d{1,3}(?:,\d{3})+|\d+)")
# "Option 3", "Step 2": a label, not a figure
_LABEL_BEFORE = re.compile(r"\b(?:option|step|scenario|alternative|phase|stage|tier|level|"
                           r"point|part|case)\s*#?\s*$", re.I)
_MONTHS = re.compile(r"(?<![\d.,])(\d+)\s*(?:months?|monate?n?)\b", re.I)
_POINTS = re.compile(r"^\s*-?\s*(?:percentage[- ]points?|pp\b|points?\b|prozentpunkte?)",
                     re.I)


def _numbers(text: str) -> list[tuple[float, int, str, str, str]]:
    """(value, decimals, surface form, kind, context) for each number worth checking.

    ``kind`` is ``pct`` for a percentage, ``amt`` for a currency amount, ``pts`` for a
    gap in percentage points, ``lbl`` for a label ("Option 3"), else ``num``.
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
        kind = ("pts" if _POINTS.match(clean[end : end + 30])
                else "pct" if m.group(4) else "amt" if m.group(1)
                else "lbl" if _LABEL_BEFORE.search(clean[max(0, start - 14) : start])
                else "num")
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
    doc: list[float], pcts: list[float], period: dict[float, str | None] | None = None,
    *, counts: list[float] | None = None, ranked: bool = False,
) -> list[tuple[float, str, str]]:
    """Every one-step derivation an underwriter would plausibly make: (value, kind, expr).

    ``period`` tags file values monthly or annual. Untagged values combine with
    anything; tagged ones only as an underwriter would: never a monthly figure
    over an annual one, never the two added, twelfths only of what is not
    already monthly, twelvefolds only of what is not already annual.

    ``doc`` are the operands of amount arithmetic; ``counts`` (``doc`` if not given) the
    numbers that may be months. ``ranked`` orders the result by how usual each kind of
    derivation is for an underwriter, then by operand size; otherwise by operand size.
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
    rank: dict[str, int] = {}  # 0: what an underwriter usually works out; 2: least usual

    def add(value: float, kind: str, expr: str, r: int) -> None:
        d.append((value, kind, expr))
        rank.setdefault(expr, r)

    for a in annual:
        if is_not(a, "month"):
            add(a / 12, "amt", f"{a:g} / 12", 0)
    for a in amounts:
        if is_not(a, "year"):
            add(a * 12, "amt", f"{a:g} × 12", 0)
    for a, b in itertools.combinations(amounts, 2):
        if same(a, b):
            add(a + b, "amt", f"{a:g} + {b:g}", 0)
            add(abs(a - b), "amt", f"{max(a, b):g} − {min(a, b):g}", 1)
    for a, b in itertools.permutations(amounts, 2):
        if same(a, b):
            add(a / b * 100, "pct", f"{a:g} / {b:g} × 100", 2)
        if is_not(a, "year") and is_not(b, "month"):
            add(a / (b / 12) * 100, "pct", f"{a:g} / ({b:g} / 12) × 100", 1)
    for a in amounts:
        for r in rates:
            add(a * r / 100, "amt", f"{a:g} × {r:g}%", 0)
            if a >= _ANNUAL_MIN and is_not(a, "month"):
                add(a / 12 * r / 100, "amt", f"{a:g} / 12 × {r:g}%", 0)
    for a, b in itertools.combinations(amounts, 2):
        if not same(a, b):
            continue
        for c in annual:
            if is_not(a, "year") and is_not(b, "year") and is_not(c, "month"):
                add((a + b) / (c / 12) * 100, "pct", f"({a:g} + {b:g}) / ({c:g} / 12) × 100", 0)
            if same(a, b, c):
                add((a + b) / c * 100, "pct", f"({a:g} + {b:g}) / {c:g} × 100", 0)
    for c in annual:
        for r in rates:
            for a in amounts:
                if is_not(c, "month") and is_not(a, "year"):
                    add(c / 12 * r / 100 - a, "amt", f"{c:g} / 12 × {r:g}% − {a:g}", 0)
                    if counts is not None:  # version 2: how far a debt service is over a limit
                        for b in amounts:
                            if a < b and is_not(b, "year"):
                                add(a + b - c / 12 * r / 100, "amt",
                                    f"{a:g} + {b:g} − {c:g} / 12 × {r:g}%", 0)
                if same(c, a):
                    add(c * r / 100 - a, "amt", f"{c:g} × {r:g}% − {a:g}", 0)
    # The income that would bring a debt service inside a limit, annual and monthly.
    for a, b in itertools.combinations(amounts, 2):
        if not same(a, b):
            continue
        for r in rates:
            if is_not(a, "year") and is_not(b, "year"):
                add((a + b) / (r / 100) * 12, "amt", f"({a:g} + {b:g}) / {r:g}% × 12", 1)
            add((a + b) / (r / 100), "amt", f"({a:g} + {b:g}) / {r:g}%", 1)
    # Months expressed as years (a file age or tenure), bare numbers only.
    for m in doc if counts is None else counts:
        if 12 <= m < _AMOUNT_MIN * 10 and m == int(m):
            add(m / 12, "num", f"{m:g} months / 12", 0)

    # When two expressions give the same result, the one built from the bigger amounts
    # is the plausible one; ranked, the usual kind of working comes first.
    def size(t: tuple[float, str, str]) -> float:
        return -min(float(x) for x in re.findall(r"\d+(?:\.\d+)?", t[2]))

    d.sort(key=(lambda t: (rank[t[2]], size(t))) if ranked else size)
    return d


def _years(raw: str, value: float, context: str, months: list[float]) -> str | None:
    """A length in years ("over 10 years", "14 years and 9 months") that a number of months
    in the file bears out."""
    both = re.search(rf"\b(\d+)\s+years?\s+and\s+{re.escape(raw)}\s+months?\b", context, re.I)
    if both and (total := int(both.group(1)) * 12 + value) in months:
        return f"{total:g} months = {both.group(1)} years and {raw} months"
    words = "|".join(sorted(_YEARS_WORDS, key=len, reverse=True))
    m = re.search(rf"\b({words})\s+{re.escape(raw)}\s*(?:years?|yrs|jahre?n?)\b", context, re.I)
    if not m:
        return None
    how = _YEARS_WORDS[m.group(1).lower()]
    for n in months:
        years = n / 12
        if n >= 12 and n == int(n) and (
                (how == "gt" and value < years) or (how == "lt" and 0 < value - years < 1)
                or (how == "eq" and round(years) == value)):
            return f"{n:g} months / 12 = {years:.1f} years ({m.group(1)} {raw})"
    return None


@check("numeric_fidelity", version=2)
def numeric_fidelity(*, output: str, item: BenchmarkItem, version: int = 2,
                     **_: Any) -> CheckResult:
    doc_numbers = _numbers(item.documents_text())
    if version == 1:  # gaps in points and labels were ordinary numbers
        doc_numbers = [(v, d, r, "num" if k in ("pts", "lbl") else k, c)
                       for v, d, r, k, c in doc_numbers]
    doc_values = sorted({v for v, _, _, _, _ in doc_numbers})
    doc_pcts = sorted({v for v, _, _, k, _ in doc_numbers if k == "pct"})
    doc_plain = sorted({v for v, _, _, k, _ in doc_numbers if k != "pct"})
    # A percentage in the briefing can only be confirmed by a percentage in the
    # file; an amount only by a non-percentage. Bare numbers may match either.
    pool = {"pct": doc_pcts, "amt": doc_plain, "num": doc_values, "pts": doc_pcts}
    claims = _numbers(output)
    if version == 1:
        claims = [(v, d, r, "num" if k in ("pts", "lbl") else k, c) for v, d, r, k, c in claims]
    else:
        claims = [c for c in claims if c[3] != "lbl"]
    if not claims:
        return CheckResult(
            name="numeric_fidelity", passed=True, score=1.0, detail="briefing states no numbers"
        )

    periods = _periods(item.documents_text())
    counts: list[float] = []
    if version == 1:
        derived = _derivations(doc_values, doc_pcts, periods)
    else:
        limits = {float(x.replace(",", "")) for m in _RANGE.finditer(item.documents_text())
                  for x in (m.group(2), m.group(3))}
        money = sorted({v for v, _, _, k, _ in doc_numbers if k == "amt"} - limits)
        counts = sorted({float(m) for m in _MONTHS.findall(item.documents_text())})
        derived = _derivations(money, doc_pcts, periods, counts=counts, ranked=True)
    evidence: list[dict[str, Any]] = []
    gaps: list[tuple[dict[str, Any], float, int]] = []  # gaps in points, grounded last
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
            if kind == "pts":  # needs every percentage the briefing grounds: done below
                gaps.append((record, value, decimals))
                evidence.append(record)
                continue
            # a bare number is not grounded by a percentage calculation after version 1
            wanted = {"pct": {"pct"}, "amt": {"amt"},
                      "num": {"pct", "amt", "num"} if version == 1 else {"amt", "num"}}[kind]
            hit = next(
                (expr for d, k, expr in derived if k in wanted and _close(d, value, decimals)),
                None,
            )
            if not hit and version > 1 and kind == "num":
                hit = _years(raw, value, context, counts)
            if hit:
                record.update(grounded=True, method="derived", derivation=hit)
            else:
                record.update(grounded=False, method=None)
                ungrounded.append(raw)
        evidence.append(record)

    # A gap in points is the difference of two percentages stated in the file or grounded
    # in the briefing ("51.1%, 11.1 percentage points above the 40% limit").
    stated = sorted(set(doc_pcts) | {v for v, _, r, k, _ in claims if k == "pct" and any(
        e["value"] == r and e.get("grounded") for e in evidence)})
    for record, value, decimals in gaps:
        hit = next((f"{a:g}% − {b:g}%" for a, b in itertools.permutations(stated, 2)
                    if a > b and _close(a - b, value, decimals)), None)
        if hit:
            record.update(grounded=True, method="derived", derivation=hit)
        else:
            record.update(grounded=False, method=None)
            ungrounded.append(record["value"])

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
