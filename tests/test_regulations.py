"""Tests for jurisdiction ruleset coverage and evidence checks."""

import json
from pathlib import Path

from open_credit_evidence.regulations import evaluate_case_regulations, load_ruleset
from open_credit_evidence.schemas import Case, RegulatoryContext

REPO_ROOT = Path(__file__).parent.parent


def _italy_context() -> RegulatoryContext:
    payload = json.loads(
        (REPO_ROOT / "regulations/IT/case-context.example.json").read_text(encoding="utf-8")
    )
    return RegulatoryContext.model_validate(payload)


def test_italy_ruleset_has_unique_stable_ids() -> None:
    ruleset, fingerprint = load_ruleset("IT")
    ids = [rule["id"] for rule in ruleset["rules"]]

    assert len(ids) == len(set(ids))
    assert all(rule_id.startswith("IT-") for rule_id in ids)
    assert len(fingerprint) == 64


def test_complete_italy_evidence_evaluates_every_rule(mock_case_001: Case) -> None:
    case = mock_case_001.model_copy(deep=True)
    case.metadata.regulatory_context = _italy_context()

    assessment = evaluate_case_regulations(case)

    assert assessment.status == "pass"
    assert assessment.coverage_complete is True
    assert len(assessment.evaluated_rule_ids) == assessment.total_rules
    assert assessment.failed_rules == 0
    assert assessment.advisory_rules > 0
    assert any(finding.status == "not_applicable" for finding in assessment.findings)


def test_missing_required_evidence_fails_case(mock_case_001: Case) -> None:
    case = mock_case_001.model_copy(deep=True)
    context = _italy_context()
    context.evidence.pop("creditworthiness_assessment")
    case.metadata.regulatory_context = context

    assessment = evaluate_case_regulations(case)

    assert assessment.status == "fail"
    assert assessment.coverage_complete is True
    finding = next(
        item for item in assessment.findings if item.rule_id == "IT-TUB-124-BIS-CURRENT"
    )
    assert finding.status == "fail"
    assert finding.missing_evidence == ["creditworthiness_assessment"]


def test_case_without_regulatory_context_is_never_silently_passed(mock_case_001: Case) -> None:
    assessment = evaluate_case_regulations(mock_case_001)

    assert assessment.status == "unscoped"
    assert assessment.coverage_complete is False
    assert assessment.ruleset_id is None

