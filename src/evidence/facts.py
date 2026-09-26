# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""The case file at a glance, for the person reviewing a memo.

``case_facts`` reads the figures a credit memo turns on from the case file (the
application form, the bureau summary and the lending policy) and works out the ones the
policy is written in: monthly income, total debt service and its share of income. Each
comes with the policy line it is judged against and whether it is within it.

``link`` says which of those figures a finding is about, so the review screen can show
the case file's number beside the memo's. It reads the finding's own words (the problem
and the memo sentence) and, for a figure the memo got wrong, the words nearest to it.

Everything here comes from the case file the assistant saw; nothing from the answer key.
"""

from __future__ import annotations

import re
from typing import Any

_ROW = r"\|\s*{}\s*\|\s*([^|\n]+?)\s*\|"
_MONEY = r"([£€$])?\s*([\d,]+(?:\.\d+)?)"

# key: (label, the row it is read from, group). Groups keep the panel in the order an
# underwriter reads a case: can they afford it, their credit history, the loan, who they are.
_ROWS: dict[str, tuple[str, str, str]] = {
    "income": ("Gross annual income", "Gross annual income", "afford"),
    "verified": ("Income verified", "Income verified", "afford"),
    "commitments": ("Existing monthly commitments", "Existing monthly credit commitments",
                    "afford"),
    "instalment": ("Monthly instalment", "Indicative monthly instalment", "afford"),
    "file_age": ("Credit file age", "Credit file opened", "history"),
    "missed": ("Missed payments, last 24 months", "Delinquencies, last 24 months", "history"),
    "recent": ("Most recent missed payment", "Most recent delinquency", "history"),
    "amount": ("Amount", "Amount", "loan"),
    "term": ("Term", "Term", "loan"),
    "purpose": ("Purpose", "Stated purpose", "loan"),
    "employment": ("Employment type", "Employment type", "applicant"),
    "tenure": ("Time in current role", "Time in current role", "applicant"),
    "age_band": ("Age band", "Age band", "applicant"),
    "dependants": ("Dependants", "Dependants", "applicant"),
    "title": ("Title", "Title", "applicant"),
    "employer": ("Employer", "Employer", "applicant"),
    "postcode": ("Postcode", "(?:Postal code|Postcode district|Postcode)", "applicant"),
}
GROUPS = {"afford": "Affordability", "history": "Credit history", "loan": "The loan",
          "applicant": "The applicant"}
_MONEY_KEYS = ("income", "income_monthly", "commitments", "instalment", "debt_service", "room",
               "amount")
_NO_BEARING = {"age_band", "dependants", "title", "employer", "postcode", "purpose"}

# The words a memo or a finding uses for each figure. The grading refs of the checks
# ("gross_annual", "dti_ratio", ...) come through a finding's wording with "_" as " ".
_WORDS: dict[str, tuple[str, ...]] = {
    "dti": ("debt-to-income", "debt to income", "dti", "ratio", "affordab", "share of",
            "per cent of", "% of", "policy limit", "40%"),
    "debt_service": ("debt service", "total monthly", "monthly debt", "outgoings",
                     "monthly obligations"),
    "income_monthly": ("monthly income", "gross monthly", "per month"),
    "income": ("gross annual", "annual income", "income", "earn", "salary"),
    "commitments": ("existing credit", "existing monthly", "commitments", "existing debt"),
    "instalment": ("instalment", "installment", "monthly payment", "monthly repayment"),
    "room": ("largest instalment", "maximum instalment", "within the limit", "headroom"),
    "score": ("bureau score", "credit score", "score", "bureau"),
    "file_age": ("file age", "credit file", "thin file", "thin", "history length",
                 "months of history"),
    "missed": ("missed", "delinquen", "arrear", "late payment", "default"),
    "verified": ("verified", "verification", "unverified"),
    "amount": ("loan amount", "amount requested", "amount", "borrow", "facility", "loan of"),
    "term": ("term", "repayment period"),
    "purpose": ("purpose", "consolidat"),
    "employment": ("self-employed", "self employed", "employment", "employed"),
    "tenure": ("current role", "in role", "tenure", "employment stability"),
    "age_band": ("age band", "years old", "their age", "applicant's age", "age of the applicant"),
    "dependants": ("dependant", "dependent"),
    "title": ("title",),
    "employer": ("employer",),
    "postcode": ("postcode", "postal code", "where they live", "where you live"),
}


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def case_facts(case_file: str) -> list[dict[str, Any]]:
    """The figures in a case file, each ``{key, label, value, group, policy, status}``.
    ``status`` is ``ok`` or ``outside`` for a figure the policy sets a limit on,
    ``no_bearing`` for one the policy says must not count, else ``info``."""
    raw = {k: re.search(_ROW.format(row), case_file) for k, (_, row, _) in _ROWS.items()}
    val = {k: m.group(1).strip() for k, m in raw.items() if m}
    out: dict[str, dict[str, Any]] = {}

    def add(key: str, label: str, value: str, group: str, policy: str | None = None,
            status: str = "info", derived: str | None = None) -> None:
        out[key] = {"key": key, "label": label, "value": value, "group": group,
                    "policy": policy, "status": status, "derived": derived}

    money = {k: re.fullmatch(_MONEY, val.get(k, "")) for k in
             ("income", "commitments", "instalment", "amount")}
    cur = next((m.group(1) for m in money.values() if m and m.group(1)), "")
    if money["income"]:
        income = _num(money["income"].group(2))
        add("income", "Gross annual income", f"{cur}{income:,.0f}", "afford")
        add("income_monthly", "Gross monthly income", f"{cur}{income / 12:,.2f}", "afford",
            derived=f"{cur}{income:,.0f} ÷ 12")
    if "verified" in val:
        add("verified", "Income verified", val["verified"], "afford")
    for k in ("commitments", "instalment"):
        if money[k]:
            add(k, _ROWS[k][0], f"{cur}{_num(money[k].group(2)):,.0f}", "afford")
    if money["income"] and money["commitments"] and money["instalment"]:
        c, i = _num(money["commitments"].group(2)), _num(money["instalment"].group(2))
        monthly = _num(money["income"].group(2)) / 12
        ratio = (c + i) / monthly * 100
        add("debt_service", "Total monthly debt service", f"{cur}{c + i:,.0f}", "afford",
            derived=f"{cur}{c:,.0f} + {cur}{i:,.0f}")
        add("dti", "Debt service ÷ monthly income", f"{ratio:.2f}%", "afford",
            policy="at most 40%", status="ok" if ratio <= 40 else "outside",
            derived=f"{cur}{c + i:,.0f} ÷ {cur}{monthly:,.2f}")
        add("room", "Largest instalment within 40%", f"{cur}{max(0.0, 0.4 * monthly - c):,.2f}",
            "afford", derived=f"40% of {cur}{monthly:,.2f} − {cur}{c:,.0f}")
    score = re.search(r"##\s*Score\s*\n+\s*\*\*(\d{2,4})\*\*", case_file)
    if score:
        s = int(score.group(1))
        add("score", "Bureau score", str(s), "history", policy="600 or above",
            status="ok" if s >= 600 else "outside")
    if "file_age" in val:
        months = re.search(r"\((\d+) months\)", val["file_age"])
        if months:
            a = int(months.group(1))
            add("file_age", "Credit file age", f"{a} months", "history",
                policy="24 months or more", status="ok" if a >= 24 else "outside")
    if "missed" in val:
        n = int(re.sub(r"\D", "", val["missed"]) or 0)
        recent = re.search(r"(\d+) months ago", val.get("recent", ""))
        within = n > 0 and recent is not None and int(recent.group(1)) <= 12
        add("missed", "Missed payments, last 24 months",
            f"{n}" + (f", latest {recent.group(1)} months ago" if recent else ""), "history",
            policy="none in the last 12 months", status="outside" if within else "ok")
    if money["amount"]:
        add("amount", "Amount", f"{cur}{_num(money['amount'].group(2)):,.0f}", "loan")
    for k in ("term", "purpose", "employment", "tenure", "age_band", "dependants", "title",
              "employer", "postcode"):
        if k in val:
            add(k, _ROWS[k][0], val[k].replace("_", " "), _ROWS[k][2],
                policy="not a factor under the policy" if k in _NO_BEARING else None,
                status="no_bearing" if k in _NO_BEARING else "info")
    order = list(GROUPS)
    return sorted(out.values(), key=lambda f: order.index(f["group"]))


def _hits(text: str, key: str) -> list[int]:
    low = text.lower()
    # a word, or the start of one ("delinquen" finds "delinquency"; "thin" not "nothing")
    return [m.start() for w in _WORDS.get(key, ())
            for m in re.finditer(r"(?<![a-z])" + re.escape(w), low)]


def link(card: dict[str, Any], facts: list[dict[str, Any]], limit: int = 2) -> list[str]:
    """The keys of the case-file figures a finding is about, most likely first."""
    have = [f["key"] for f in facts]
    value = str(card.get("memo_value") or "")
    sentence = str(card.get("sentence") or "")
    if card.get("source") == "claim_consistency" or value.endswith("%"):
        return ["dti"] if "dti" in have else []  # the only percentage the policy is written in
    if value and sentence and value in sentence:
        # a sum the memo got wrong: the sum named nearest to it in its sentence
        at = sentence.find(value)
        near = sorted((min(abs(h - at) for h in hs), k) for k in have
                      if k in _MONEY_KEYS and (hs := _hits(sentence, k)))
        return [k for _, k in near][:limit]
    words = f"{card.get('problem') or ''}  {card.get('evidence') or ''}"
    keys = [k for k in have if _hits(words, k)]
    if not keys:
        keys = [k for k in have if _hits(sentence, k)]
    # the specific over the general: "debt service ratio" is the ratio, not the debt service
    if "dti" in keys and "debt_service" in keys and not _hits(words, "debt_service"):
        keys.remove("debt_service")
    if "income_monthly" in keys and "income" in keys:
        keys.remove("income")
    return keys[:limit]
