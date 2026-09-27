# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""numeric_fidelity version 2, on figures and memo sentences from case APP000128 of the
26 September capability run; check versions; re-checking a sealed run."""

import json

import pytest

from evidence.checks import check_versions, run_checks
from evidence.contracts.item import BenchmarkItem, GradingSpec, ItemContext
from evidence.evidence.verify import verify_recompute
from evidence.recheck import recheck

APPLICATION = (
    "# Personal Loan Application\n\n**Reference:** APP000128\n\n"
    "| Employment type | self_employed |\n| Time in current role | 158 months |\n"
    "| Postal code | 01067 |\n| Gross annual income | €31,043 |\n"
    "| Existing monthly credit commitments | €633 |\n| Dependants | 3 |\n"
    "| Amount | €20,451 |\n| Term | 36 months |\n| Indicative monthly instalment | €688 |\n"
)
BUREAU = "**688** *(range 0–999)*\n| Credit file opened | September 2021 (66 months) |\n"
POLICY = (
    "**Policy version:** PL-2026.1\n**Applies to:** unsecured personal loans, €2,000 to "
    "€40,000\n\n| Total monthly debt service, as a share of gross monthly income | Must not "
    "exceed **40%** |\n| Bureau score | Below 600 requires underwriter review |\n"
)
FIGURES = (
    "| Gross monthly income | €2,586.92 |\n| Total monthly debt service | €1,321 |\n"
    "| Debt service as a share of gross monthly income | 51.1% | at most 40% | No |\n"
)


def item(with_figures: bool = False) -> BenchmarkItem:
    docs = [ItemContext(renderer="application_form", variant="complete", content=APPLICATION),
            ItemContext(renderer="bureau_summary", variant="complete", content=BUREAU),
            ItemContext(renderer="lending_policy", variant="complete", content=POLICY)]
    if with_figures:
        docs.append(ItemContext(renderer="rules_engine", variant="complete", content=FIGURES))
    return BenchmarkItem(item_id="t:case_review:APP000128:complete", pack="t",
                         domain="credit_underwriting", task="case_review", prompt="Summarise.",
                         context=docs, deterministic_checks=["numeric_fidelity"],
                         grading=GradingSpec(disposition="refer"))


def numeric(out: str, version: int | None = None, **kw):
    versions = {"numeric_fidelity": version} if version else None
    (r,) = run_checks(["numeric_fidelity"], output=out, item=item(**kw), versions=versions)
    return r


WRONG = ("The monthly instalment would need to be approximately €327 (bringing total debt "
         "service to €960 / 40%).")


def test_a_policy_version_and_a_postal_code_do_not_ground_a_wrong_figure():
    old = numeric(WRONG, version=1)
    assert "€960" not in old.detail  # version 1 grounded it as 2026.1 − 1067
    assert any(e.get("derivation") == "2026.1 − 1067" for e in old.evidence)
    new = numeric(WRONG)
    assert not new.passed and "€327" in new.detail and "€960" in new.detail


def test_the_debt_service_ratio_is_explained_as_an_underwriter_works_it_out():
    r = numeric("Debt service of €1,321 is 51% of gross monthly income (€2,587).")
    assert r.passed, r.detail
    how = {e["value"]: e.get("derivation") for e in r.evidence}
    assert how["51%"] == "(633 + 688) / (31043 / 12) × 100"
    assert how["€2,587"] == "31043 / 12"


def test_the_right_headroom_is_still_grounded():
    out = ("Debt service must fall to €1,034.77 or less (40% of €2,586.92); the instalment "
           "would need to be €401.77 or lower.")
    r = numeric(out, with_figures=True)
    assert r.passed, r.detail
    assert r.evidence[0]["derivation"] == "2586.92 × 40%"


def test_a_gap_in_percentage_points_is_the_difference_of_two_percentages():
    out = ("Debt service is 51.1% of gross monthly income. This is 11.1 percentage points "
           "above the maximum allowable 40%.")
    assert not numeric(out, version=1, with_figures=True).passed  # the false alarm
    r = numeric(out, with_figures=True)
    assert r.passed, r.detail
    assert any(e.get("derivation") == "51.1% − 40%" for e in r.evidence)
    # also from a percentage the memo itself grounds, not only one in the file
    assert numeric("Debt service is 51.1%, 11.1 pp over the 40% limit.").passed
    wrong = numeric("Debt service is 51.1%, 12.1 percentage points above the 40% limit.")
    assert not wrong.passed and "12.1" in wrong.detail


def test_months_still_become_years_and_a_rounded_length_is_borne_out():
    assert numeric("In role for 158 months (about 13.2 years).").passed
    for ok in ("over 10 years", "almost 14 years", "about 13 years"):
        assert numeric(f"In the current role for 158 months ({ok}).").passed, ok
    for wrong in ("over 15 years", "almost 20 years"):
        assert not numeric(f"In the current role for 158 months ({wrong}).").passed, wrong


def test_labels_range_limits_and_years_with_months():
    assert numeric("Option 3 (Additional Income): verify further income.").passed
    assert numeric("In the current role for 158 months (13 years and 2 months).").passed
    assert not numeric("In the current role for 158 months (13 years and 9 months).").passed
    # €2,000 is the bottom of the policy's range: "688 / 2000 × 100" grounds nothing
    assert numeric("The instalment is 34.4% of the minimum loan.", version=1).passed
    assert not numeric("The instalment is 34.4% of the minimum loan.").passed


def test_the_amount_over_the_limit_is_grounded():
    # 633 + 688 − 31,043 / 12 × 40% = 286.23: what commitments would have to fall by
    r = numeric("Reduce existing credit commitments by at least €286 per month.")
    assert r.passed, r.detail
    assert r.evidence[0]["derivation"] == "633 + 688 − 31043 / 12 × 40%"
    assert not numeric("Reduce existing credit commitments by at least €250 per month.").passed


def test_versions_are_listed_and_an_unknown_one_is_refused():
    assert check_versions(["numeric_fidelity", "decoy_citation"]) == {
        "numeric_fidelity": 2, "decoy_citation": 1}
    with pytest.raises(ValueError, match="no version 3"):
        numeric(WRONG, version=3)


MEMOS = [
    "Debt service is 51.1%, 11.1 percentage points above the 40% limit.",  # v1 false alarm
    "The instalment could rise so that total debt service is €960.",  # v1 missed it
]


def _run(tmp_path, versions):
    """A sealed run of two memos, scored with numeric_fidelity version 1."""
    from evidence.contracts.transcript import SUTPins, Transcript
    from evidence.evidence.writer import seal
    from evidence.pack import Pack

    run = tmp_path / "runs" / "r1"
    (run / "transcripts").mkdir(parents=True)
    it = item()
    rows = []
    for rep, memo in enumerate(MEMOS):
        rows.append({"item_id": it.item_id, "repeat": rep, "check": "numeric_fidelity",
                     **numeric(memo, version=1).to_score()})
        t = Transcript(item_id=it.item_id, run_id="r1", repeat=rep, output=memo,
                       sut=SUTPins(model_id="m", prompt_version="p", params={}),
                       system_prompt="s", user_prompt="u", latency_ms=1, tokens_in=1,
                       tokens_out=1, started_at="2026-09-27T00:00:00+00:00", sha256="x")
        (run / "transcripts" / f"t-r{rep}.json").write_text(t.model_dump_json())
    (run / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    manifest = {"setup": "as_is", "checks": ["numeric_fidelity"], "pack": {"pack_id": "t"}}
    if versions:
        manifest["check_versions"] = versions
    (run / "manifest.json").write_text(json.dumps(manifest))
    seal(run)
    return run, Pack(path=tmp_path / "t", manifest={"pack_id": "t"}, items=[it], obligations={})


def test_a_run_scored_before_versions_re_derives_with_version_1(tmp_path):
    run, pack = _run(tmp_path, None)
    assert [numeric(m, version=1).passed for m in MEMOS] == [False, True]
    v = verify_recompute(run, pack)
    assert v.ok and v.recomputed == 2, v.disagreements


def test_a_recheck_shows_what_the_new_version_changes_and_leaves_the_run_alone(tmp_path):
    run, pack = _run(tmp_path, {"numeric_fidelity": 1})
    before = (run / "results.jsonl").read_text()
    out = recheck(run, pack, root=tmp_path / "rechecks")
    r = json.loads((out / "recheck.json").read_text())
    assert r["changed_checks"] == {"numeric_fidelity": [1, 2]} and r["unreproduced"] == 0
    assert r["clean"] == {"before": 1, "after": 1}
    assert r["now_clean"] == ["t:case_review:APP000128:complete#0"]
    assert r["now_flagged"] == ["t:case_review:APP000128:complete#1"]
    md = (out / "recheck.md").read_text()
    assert "Memos now found wrong (1)" in md and "€960" in md
    assert "Memos now found right (1)" in md
    assert (run / "results.jsonl").read_text() == before
    assert (out / "checksums.sha256").is_file()
