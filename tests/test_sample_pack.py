# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""The built sample pack holds the properties the design depends on."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from evidence.checks import run_checks
from evidence.contracts.item import BenchmarkItem

PACK = Path(__file__).resolve().parents[1] / "packs" / "underwriter-sample"
OUTCOME_WORDS = re.compile(
    r"\b(approve[ds]?|accepted|granted|declin(e|ed)|reject(ed)?|refus(e|ed)|"
    r"unsuccessful|turned down|denied|refer(red)?|manual review|escalated)\b",
    re.IGNORECASE,
)

pytestmark = pytest.mark.skipif(
    not (PACK / "items.jsonl").exists(),
    reason="sample pack not built; run scripts/build_sample_pack.py",
)


def _items() -> list[BenchmarkItem]:
    return [BenchmarkItem.model_validate_json(line) for line in (PACK / "items.jsonl").open()]


def test_manifest_checksum_matches_items() -> None:
    m = json.loads((PACK / "manifest.json").read_text())
    assert m["items_sha256"] == hashlib.sha256((PACK / "items.jsonl").read_bytes()).hexdigest()
    assert m["ceiling"]["claimed"] is False


def test_every_item_is_a_referral_with_omission_targets() -> None:
    items = _items()
    assert len(items) == 20
    for it in items:
        assert it.grading.disposition == "refer"
        assert it.grading.omission_refs, it.item_id
        assert set(it.grading.omission_refs) <= set(it.grading.omission_labels)


def test_documents_never_state_the_outcome() -> None:
    for it in _items():
        for doc in it.context:
            assert not OUTCOME_WORDS.search(doc.content), (it.item_id, doc.renderer)


def test_answer_key_does_not_travel() -> None:
    def keys(obj: object) -> set[str]:
        out: set[str] = set()
        if isinstance(obj, dict):
            for k, v in obj.items():
                out.add(k)
                out |= keys(v)
        elif isinstance(obj, list):
            for v in obj:
                out |= keys(v)
        return out

    for line in (PACK / "items.jsonl").open():
        assert not {"contributions", "margin", "threshold", "score"} & keys(json.loads(line))
    # Flip refs carry field and direction only.
    for it in _items():
        for f in it.grading.flip_refs:
            assert set(f.model_dump()) == {"ref", "direction"}
        for alts in it.grading.flip_alternatives.values():
            for f in alts:
                assert set(f.model_dump()) == {"ref", "direction"}


def test_decoys_and_drivers_are_disjoint() -> None:
    for it in _items():
        g = it.grading
        assert not set(g.driver_refs) & set(g.decoy_refs), it.item_id


def test_decoys_are_the_declared_irrelevant_fields() -> None:
    # Tenure has zero weight but is an ordinary underwriting consideration; a weighted
    # field that contributes nothing for one applicant is not a decoy either.
    from evidence.packs.credit_underwriting import DECOYS

    for it in _items():
        assert set(it.grading.decoy_refs) == set(DECOYS), it.item_id
        assert "tenure_months" not in it.grading.decoy_refs
        assert "comparison_fidelity" in it.deterministic_checks
        assert "claim_consistency" in it.deterministic_checks and it.grading.claim_aliases


def test_a_debt_ratio_lever_accepts_every_cure_the_policy_names() -> None:
    # "a reduced facility, a longer term, or additional verified income" — and lower commitments
    seen = 0
    for it in _items():
        for f in it.grading.flip_refs:
            if f.ref == "gross_annual":
                seen += 1
                alts = {(a.ref, a.direction) for a in it.grading.flip_alternatives[f.ref]}
                assert alts == {("amount", "decrease"), ("term_months", "increase"),
                                ("existing_credit_monthly", "decrease")}
                assert all(it.grading.flip_aliases.get(r) for r, _ in alts)
    assert seen


def test_negative_control_fails_on_every_real_item() -> None:
    """A briefing that mentions only strengths omits the driver on every referred case."""
    strengths_only = (
        "Strong applicant with a solid bureau score and a long credit file. Employment and "
        "income position are stable and income is verified. Recommend approval."
    )
    for it in _items():
        (r,) = run_checks(["material_omission"], output=strengths_only, item=it)
        assert not r.passed, it.item_id


DE = Path(__file__).resolve().parents[1] / "packs" / "underwriter-de"


@pytest.mark.skipif(not (DE / "items.jsonl").exists(), reason="German pack not built")
def test_german_pack_is_the_sample_in_euros_under_german_rules():
    import json

    a = [json.loads(x) for x in (PACK / "items.jsonl").read_text().splitlines()]
    b = [json.loads(x) for x in (DE / "items.jsonl").read_text().splitlines()]
    case = lambda it: it["item_id"].split(":")[2]  # noqa: E731
    assert [case(x) for x in a] == [case(x) for x in b]
    assert all(x["grading"] == y["grading"] for x, y in zip(a, b, strict=True))
    assert "£" not in (DE / "items.jsonl").read_text()
    assert "€" in b[0]["context"][0]["content"]
    m = json.loads((DE / "manifest.json").read_text())
    assert (m["market"], m["currency"]) == ("de", "€")
    ctx = json.loads((DE / "regulatory_context.json").read_text())
    assert ctx["jurisdiction"] == "DE"


def test_german_rule_pack_evaluates():
    import json

    from evidence.contracts.regulatory import RegulatoryContext
    from evidence.regulations import assess

    root = Path(__file__).resolve().parents[1] / "regulations" / "DE"
    a = assess(RegulatoryContext.model_validate_json((root / "case-context.example.json")
                                                     .read_text()))
    status = {f.rule_id: f.status for f in a.findings}
    assert status["DE-BGB-505A-1"] == "pass" and status["DE-BDSG-30-6"] == "advisory"
    rules = json.loads((root / "ruleset.json").read_text())["rules"]
    assert {r["enforcement"] for r in rules if r["citation"].endswith("n.F.")} == {"transition"}
