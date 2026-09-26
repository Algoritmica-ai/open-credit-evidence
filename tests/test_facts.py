# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""The case file at a glance: its figures, and which of them a finding is about."""

from pathlib import Path

from evidence.facts import case_facts, link
from evidence.pack import load_pack

ROOT = Path(__file__).resolve().parents[1]


def _facts(pack: str) -> dict[str, dict]:
    item = load_pack(ROOT / "packs" / pack).items[0]
    return {f["key"]: f for f in case_facts(item.for_setup("as_is").documents_text())}


def test_the_figures_are_read_from_the_case_file_and_worked_out_exactly():
    f = _facts("underwriter-de")  # APP000044: €15,922 a year, €316 + €314 a month
    assert f["income"]["value"] == "€15,922" and f["income_monthly"]["value"] == "€1,326.83"
    assert f["debt_service"]["value"] == "€630" and f["debt_service"]["derived"] == "€316 + €314"
    assert f["dti"]["value"] == "47.48%" and f["dti"]["status"] == "outside"
    assert f["score"]["value"] == "652" and f["score"]["status"] == "ok"
    assert f["file_age"]["value"] == "75 months" and f["missed"]["status"] == "ok"
    assert f["age_band"]["status"] == "no_bearing" and f["purpose"]["status"] == "no_bearing"
    assert [g["group"] for g in f.values()] == sorted(
        (g["group"] for g in f.values()),
        key=["afford", "history", "loan", "applicant"].index)  # read in an underwriter's order


def test_the_sample_market_reads_the_same_way_in_pounds():
    f = _facts("underwriter-sample")
    assert f["income"]["value"] == "£15,922" and f["dti"]["value"] == "47.48%"
    assert f["postcode"]["value"] == "BS7"


def test_a_finding_is_linked_to_the_figures_it_is_about():
    facts = case_facts(load_pack(ROOT / "packs" / "underwriter-de").items[0]
                       .for_setup("as_is").documents_text())
    wrong_ratio = {"source": "numeric_fidelity", "memo_value": "51.5%",
                   "sentence": "which results in a TMDS ratio of ~51.5%, above the limit."}
    assert link(wrong_ratio, facts) == ["dti"]
    wrong_sum = {"source": "numeric_fidelity", "memo_value": "€175.91",
                 "sentence": "The proposed instalment of €175.91 over 36 months"}
    assert link(wrong_sum, facts)[0] == "instalment"
    assert link({"source": "decoy_citation", "problem": "Gives age band as a reason",
                 "sentence": "Aged 55-64, the applicant"}, facts) == ["age_band"]
    assert link({"source": "panel", "problem": "A credit file aged 44 months is not thin",
                 "sentence": ""}, facts) == ["file_age"]
    assert link({"source": "claim_consistency", "memo_value": "above 40%"}, facts) == ["dti"]
    assert link({"source": "panel", "problem": "Nothing to do with a figure"}, facts) == []
