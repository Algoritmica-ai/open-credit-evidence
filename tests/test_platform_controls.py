"""Tests for FINOS AI Steel Thread control-evidence normalization."""

import json
from pathlib import Path
from typing import Any

import pytest

from open_credit_evidence.evidence import (
    TamperVerificationError,
    create_evidence_report,
    verify_evidence_report,
)
from open_credit_evidence.omission_check import check_omissions
from open_credit_evidence.platform_controls import (
    STEEL_THREAD_REVISION,
    normalize_steel_thread_report,
)
from open_credit_evidence.regulations import evaluate_case_regulations
from open_credit_evidence.schemas import Case, RegulatoryContext, Summary
from tests.fixtures.summaries import CASE_001_GOOD_SUMMARY

REPO_ROOT = Path(__file__).parent.parent


def _platform_payload() -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(
        (
            REPO_ROOT / "platforms/ai-steel-thread/compliance-report.example.json"
        ).read_text(encoding="utf-8")
    )
    return payload


def _italy_context() -> RegulatoryContext:
    payload = json.loads(
        (REPO_ROOT / "regulations/IT/case-context.example.json").read_text(encoding="utf-8")
    )
    return RegulatoryContext.model_validate(payload)


def test_complete_same_case_platform_report_is_verified() -> None:
    evidence = normalize_steel_thread_report(_platform_payload(), "IT-LOAN-001")

    assert evidence.claim_status == "verified"
    assert evidence.controls == {"mi-1": True, "mi-4": True, "mi-5": True, "mi-11": True}
    assert evidence.instance_snapshot is True
    assert evidence.total_tokens == 1250
    assert evidence.estimated_cost_usd == 0.0125
    assert evidence.issues == []


def test_unextended_demo_report_is_linked_not_verified() -> None:
    payload = _platform_payload()
    payload.pop("openCreditEvidence")

    evidence = normalize_steel_thread_report(payload, "IT-LOAN-001")

    assert evidence.claim_status == "linked"
    assert "No explicit OpenCredit activity/report link is attached" in evidence.issues


def test_case_mismatch_blocks_verified_claim() -> None:
    evidence = normalize_steel_thread_report(_platform_payload(), "OTHER-CASE")

    assert evidence.claim_status == "linked"
    assert any("does not match case_id" in issue for issue in evidence.issues)


def test_control_profile_is_pinned_to_adapter_revision() -> None:
    profile = json.loads(
        (REPO_ROOT / "platforms/ai-steel-thread/control-profile.json").read_text(
            encoding="utf-8"
        )
    )
    assert profile["source_revision"] == STEEL_THREAD_REVISION


def test_platform_and_regulatory_evidence_are_tamper_evident(mock_case_001: Case) -> None:
    case = mock_case_001.model_copy(deep=True)
    case.metadata.case_id = "IT-LOAN-001"
    case.metadata.regulatory_context = _italy_context()
    summary = Summary(
        case_id=case.metadata.case_id,
        text=CASE_001_GOOD_SUMMARY,
        model="test",
    )
    marking = check_omissions(case, summary)
    regulatory = evaluate_case_regulations(case)
    platform = normalize_steel_thread_report(_platform_payload(), case.metadata.case_id)
    report = create_evidence_report(
        case,
        summary,
        marking,
        regulatory_assessment=regulatory,
        platform_controls=platform,
    )

    assert verify_evidence_report(report) is True
    assert report.platform_controls is not None
    report.platform_controls.total_tokens += 1

    with pytest.raises(TamperVerificationError, match="Governance fingerprint"):
        verify_evidence_report(report)
