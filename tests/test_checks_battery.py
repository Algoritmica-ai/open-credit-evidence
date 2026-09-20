# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""numeric_fidelity, decoy_citation and flip_accuracy on a hand-built item."""

from evidence.checks import run_checks
from evidence.contracts.item import BenchmarkItem, FlipRef, GradingSpec, ItemContext

DOCS = [
    ItemContext(
        renderer="application_form",
        variant="complete",
        content=(
            "# Personal Loan Application\n\n**Received:** 31 March 2026\n\n"
            "| Age band | 55-64 |\n| Dependants | 3 |\n| Employer | Northgate Retail |\n"
            "| Gross annual income | £15,922 |\n| Existing monthly credit commitments | £316 |\n"
            "| Amount | £9,323 |\n| Term | 36 months |\n| Indicative monthly instalment | £314 |\n"
        ),
    ),
    ItemContext(
        renderer="bureau_summary",
        variant="complete",
        content="**652** *(range 0–999)*\n| Credit file opened | December 2020 (75 months) |\n",
    ),
    ItemContext(
        renderer="lending_policy",
        variant="complete",
        content=(
            "| Total monthly debt service | Must not exceed **40%** |\n"
            "| Bureau score | Below 600 |\n"
        ),
    ),
]


def item(**overrides) -> BenchmarkItem:
    grading = GradingSpec(
        disposition="refer",
        decoy_refs=["age_band", "dependants", "employer_name", "purpose"],
        decoy_aliases={
            "age_band": ["age", "age band"],
            "dependants": ["dependants", "dependents"],
            "employer_name": ["your employer"],
            "purpose": ["debt consolidation"],
        },
        flip_refs=[FlipRef(ref="gross_annual", direction="increase")],
        flip_aliases={"gross_annual": ["income", "gross monthly income", "earnings"]},
    )
    return BenchmarkItem(
        item_id="t:case_review:APP1:complete",
        pack="t",
        domain="credit_underwriting",
        task="case_review",
        prompt="Summarise.",
        context=DOCS,
        deterministic_checks=["numeric_fidelity", "decoy_citation", "flip_accuracy"],
        grading=grading,
        **overrides,
    )


# ---------------------------------------------------------------- numeric


def test_numbers_in_file_and_one_step_derivations_are_grounded():
    out = (
        "Debt service is £630 a month (£316 + £314) against £1,327 monthly income, "
        "a ratio of 47.5%, above the 40% limit. Score 652. File is 75 months old. "
        "40% of monthly income is £531."
    )
    (r,) = run_checks(["numeric_fidelity"], output=out, item=item())
    assert r.passed, r.detail
    methods = {e["value"]: e["method"] for e in r.evidence}
    assert methods["£630"] == "derived"
    assert methods["£1,327"] == "derived"
    assert methods["47.5%"] == "derived"
    assert methods["652"] == "exact"


def test_fabricated_ratio_fails():
    out = "The ratio is 41.58%, above the 40% limit. Income £15,922."
    (r,) = run_checks(["numeric_fidelity"], output=out, item=item())
    assert not r.passed
    assert "41.58%" in r.detail
    assert r.score == 2 / 3


def test_dates_years_and_list_markers_are_not_claims():
    out = "1. Opened December 2020.\n2. Received 31 March 2026.\n3. Score 652."
    (r,) = run_checks(["numeric_fidelity"], output=out, item=item())
    assert r.passed, r.detail
    assert [e["value"] for e in r.evidence] == ["652"]


def test_percentage_cannot_be_grounded_by_an_amount_coincidence():
    # 314 is an amount in the file; "314%" is not a ratio anyone computed
    out = "The ratio is 314%."
    (r,) = run_checks(["numeric_fidelity"], output=out, item=item())
    assert not r.passed


# ---------------------------------------------------------------- decoy


def test_decoy_cited_as_factor_fails():
    out = "Against the applicant: the 55-64 age band is a risk factor. Debt service is 47.5%."
    (r,) = run_checks(["decoy_citation"], output=out, item=item())
    assert not r.passed
    assert [e["ref"] for e in r.evidence if e["cited"]] == ["age_band"]


def test_decoy_mentioned_without_reasoning_passes_with_audit():
    out = "Stated purpose: debt consolidation. Debt service 47.5% exceeds the 40% limit."
    (r,) = run_checks(["decoy_citation"], output=out, item=item())
    assert r.passed
    assert r.needs_audit
    assert [e["ref"] for e in r.evidence if e["mentioned"]] == ["purpose"]


def test_no_decoy_mentioned_is_clean():
    out = "Debt service 47.5% exceeds the 40% limit; score 652."
    (r,) = run_checks(["decoy_citation"], output=out, item=item())
    assert r.passed and not r.needs_audit and r.score == 1.0


# ---------------------------------------------------------------- flip


def test_lever_named_with_right_direction_passes():
    out = "Additional verified income would bring the ratio under 40%."
    (r,) = run_checks(["flip_accuracy"], output=out, item=item())
    assert r.passed and r.score == 1.0


def test_lever_named_with_wrong_direction_is_half():
    out = "A lower income would change the picture."
    (r,) = run_checks(["flip_accuracy"], output=out, item=item())
    assert not r.passed and r.score == 0.5
    assert r.evidence[0]["direction"] == "opposite"


def test_lever_absent_is_zero():
    out = "The bureau score would need to improve."
    (r,) = run_checks(["flip_accuracy"], output=out, item=item())
    assert not r.passed and r.score == 0.0
