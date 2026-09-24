# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""numeric_fidelity, comparison_fidelity, decoy_citation and flip_accuracy on a hand-built item."""

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


def _with_alternatives():
    it = item()
    it.grading.flip_alternatives = {"gross_annual": [
        FlipRef(ref="amount", direction="decrease"),
        FlipRef(ref="term_months", direction="increase"),
        FlipRef(ref="existing_credit_monthly", direction="decrease"),
    ]}
    it.grading.flip_aliases |= {
        "amount": ["loan amount", "facility"],
        "term_months": ["term"],
        "existing_credit_monthly": ["existing commitments", "debt service"],
    }
    return it


def test_an_alternative_lever_counts():
    # the briefing that exposed it: the lever is debt service, not income
    out = ("For the application to fall within policy, the total monthly debt service must be "
           "reduced to 40% of gross monthly income.")
    (r,) = run_checks(["flip_accuracy"], output=out, item=_with_alternatives())
    assert r.passed, r.detail
    e = r.evidence[0]
    assert (e["lever"], e["ref"], e["direction"]) == ("gross_annual", "existing_credit_monthly",
                                                      "decrease")
    assert "amount decrease" in e["accepted"]


def test_alternatives_still_need_their_direction():
    out = "The loan amount and the term are unusual for this income."
    (r,) = run_checks(["flip_accuracy"], output=out, item=_with_alternatives())
    assert not r.passed and r.score == 0.5


def test_ing_forms_carry_a_direction():
    for out in ("This could be fixed by increasing verified income.",
                "Reducing the loan amount would bring it within policy.",
                "The score would need to rise above 600."):
        it = _with_alternatives()
        it.grading.flip_refs.append(FlipRef(ref="bureau_score", direction="increase"))
        it.grading.flip_aliases["bureau_score"] = ["score"]
        (r,) = run_checks(["flip_accuracy"], output=out, item=it)
        assert any(e.get("direction") == e["expected"] for e in r.evidence), out


def test_lever_absent_is_zero():
    out = "The bureau score would need to improve."
    (r,) = run_checks(["flip_accuracy"], output=out, item=item())
    assert not r.passed and r.score == 0.0


def test_two_step_underwriter_arithmetic_is_grounded():
    # headroom under the limit, the income that meets it, months as years, chained rounding
    out = (
        "The instalment would need to be capped at £214.73; the income would need to reach "
        "£18,900 a year. The file is 75 months old (about 6.2 years). "
        "40% of monthly income is £530.90."
    )
    (r,) = run_checks(["numeric_fidelity"], output=out, item=item())
    assert r.passed, r.detail


def test_tolerance_does_not_excuse_a_wrong_ratio():
    out = "The ratio is 47.2%."  # true 47.5%; 0.6% off, well outside chained rounding
    (r,) = run_checks(["numeric_fidelity"], output=out, item=item())
    assert not r.passed


# ---------------------------------------------------------------- comparison


def test_false_comparison_fails():
    out = "The bureau score of 652 is below the 600 threshold requiring review."
    (r,) = run_checks(["comparison_fidelity"], output=out, item=item())
    assert not r.passed and r.score == 0.0
    assert r.evidence[0]["reads_as"] == "652 < 600"


def test_true_comparisons_pass():
    out = (
        "Debt service is 47.5%, which exceeds the policy maximum of 40%. The score of 652 is "
        "above the 600 threshold. The file is 75 months old, exceeding the 24-month minimum."
    )
    (r,) = run_checks(["comparison_fidelity"], output=out, item=item())
    assert r.passed and len(r.evidence) == 3, r.evidence


def test_negation_turns_the_relation_round():
    out = "At 36.7%, the ratio does not exceed the 40% limit."
    (r,) = run_checks(["comparison_fidelity"], output=out, item=item())
    assert r.passed and r.evidence[0]["reads_as"] == "36.7 ≤ 40"


def test_targets_and_mixed_kinds_are_not_comparisons():
    out = (
        "The ratio of 47.5% would need to fall below 40%. A loan of £9,323 over 36 months. "
        "Income of £1,327 is above 40% of the limit."
    )
    (r,) = run_checks(["comparison_fidelity"], output=out, item=item())
    assert r.passed and r.detail == "no comparison stated", r.evidence


# ------------------------------------------------ periods and claims


def test_a_monthly_figure_over_an_annual_one_is_not_grounded():
    # (316 + 314) / 15,922 × 100 = 3.96%: arithmetic on the file, not a debt ratio
    out = "Debt service of £630 is 3.96% of gross income."
    (r,) = run_checks(["numeric_fidelity"], output=out, item=item())
    assert not r.passed and "3.96%" in r.detail
    # the ratio an underwriter computes, monthly over monthly, still is
    (r,) = run_checks(["numeric_fidelity"], output="Debt service is 47.5% of income.", item=item())
    assert r.passed, r.detail


def _claims_item():
    it = item()
    it.grading.claim_aliases = {"dti_ratio": ["debt service", "dti", "affordability"]}
    return it


def test_a_breach_its_own_figure_denies_fails():
    out = ("Referred because total monthly debt service exceeds the 40% affordability threshold. "
           "Against monthly income of £2,303, this represents a debt service ratio of 33.2%.")
    (r,) = run_checks(["claim_consistency"], output=out, item=_claims_item())
    assert not r.passed
    assert r.evidence[0]["claims"] == "above 40%" and r.evidence[0]["contradicted_by"] == 33.2


def test_a_breach_its_figure_supports_passes():
    out = ("Debt service exceeds the 40% threshold. The debt service ratio is 47.5%, "
           "and would need to fall below 40% for approval.")
    (r,) = run_checks(["claim_consistency"], output=out, item=_claims_item())
    assert r.passed, r.detail


def test_remedies_and_targets_are_not_claims():
    out = ("The DTI is 47.5%. Reduce the loan amount so that debt service does not exceed 40% "
           "of income, e.g. below 35%.")
    (r,) = run_checks(["claim_consistency"], output=out, item=_claims_item())
    assert r.passed and r.detail == "no limit claim stated", r.evidence


def test_a_negated_claim_turns_round():
    out = "Debt service does not exceed the 40% limit: the DTI is 47.5%."
    (r,) = run_checks(["claim_consistency"], output=out, item=_claims_item())
    assert not r.passed and r.evidence[0]["claims"] == "at or below 40%"
