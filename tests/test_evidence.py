"""Tests for evidence report generation and tamper verification."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from open_credit_evidence.evidence import (
    EvidenceReportBuilder,
    TamperVerificationError,
    compute_chain_fingerprint,
    compute_marking_fingerprint,
    create_evidence_report,
    load_evidence_report,
    save_evidence_report,
    verify_evidence_report,
)
from open_credit_evidence.loader import compute_fingerprint
from open_credit_evidence.omission_check import check_omissions
from open_credit_evidence.schemas import Case, EvidenceReport, MarkingResult, Summary
from tests.fixtures.summaries import CASE_001_GOOD_SUMMARY


class TestChainFingerprint:
    """Tests for chain fingerprint computation."""

    def test_chain_fingerprint_deterministic(self) -> None:
        """Same inputs should always produce same chain fingerprint."""
        fp = compute_chain_fingerprint("case_fp", "summary_fp", "marking_fp")
        fp2 = compute_chain_fingerprint("case_fp", "summary_fp", "marking_fp")
        assert fp == fp2

    def test_chain_fingerprint_changes_with_any_input(self) -> None:
        """Chain fingerprint should change if any component changes."""
        base = compute_chain_fingerprint("case_fp", "summary_fp", "marking_fp")

        changed_case = compute_chain_fingerprint("case_fp_changed", "summary_fp", "marking_fp")
        changed_summary = compute_chain_fingerprint("case_fp", "summary_fp_changed", "marking_fp")
        changed_marking = compute_chain_fingerprint("case_fp", "summary_fp", "marking_fp_changed")

        assert base != changed_case
        assert base != changed_summary
        assert base != changed_marking


class TestEvidenceReportCreation:
    """Tests for creating evidence reports."""

    def test_create_report_with_valid_inputs(self, mock_case_001: Case) -> None:
        """Should create report with all required fields."""
        summary = Summary(
            case_id=mock_case_001.metadata.case_id,
            text=CASE_001_GOOD_SUMMARY,
            model="test",
        )
        marking = check_omissions(mock_case_001, summary)

        report = create_evidence_report(mock_case_001, summary, marking)

        assert report.report_id.startswith("EVR-")
        assert report.case_id == mock_case_001.metadata.case_id
        assert report.case_fingerprint == mock_case_001.fingerprint
        assert report.summary == summary
        assert report.marking_result == marking
        assert report.chain_fingerprint is not None
        assert report.created_at is not None

    def test_report_chain_fingerprint_is_valid(self, mock_case_001: Case) -> None:
        """Chain fingerprint should be verifiable."""
        summary = Summary(
            case_id=mock_case_001.metadata.case_id,
            text=CASE_001_GOOD_SUMMARY,
            model="test",
        )
        marking = check_omissions(mock_case_001, summary)
        report = create_evidence_report(mock_case_001, summary, marking)

        summary_fp = compute_fingerprint(summary.text)
        marking_fp = compute_marking_fingerprint(marking)
        expected_chain = compute_chain_fingerprint(
            mock_case_001.fingerprint, summary_fp, marking_fp
        )

        assert report.chain_fingerprint == expected_chain


class TestEvidenceReportVerification:
    """Tests for evidence report verification."""

    def test_verify_valid_report(self, mock_case_001: Case) -> None:
        """Verification should pass for untampered report."""
        summary = Summary(
            case_id=mock_case_001.metadata.case_id,
            text=CASE_001_GOOD_SUMMARY,
            model="test",
        )
        marking = check_omissions(mock_case_001, summary)
        report = create_evidence_report(mock_case_001, summary, marking)

        assert verify_evidence_report(report) is True

    def test_verify_with_expected_case_fingerprint(self, mock_case_001: Case) -> None:
        """Verification should pass with correct case fingerprint."""
        summary = Summary(
            case_id=mock_case_001.metadata.case_id,
            text=CASE_001_GOOD_SUMMARY,
            model="test",
        )
        marking = check_omissions(mock_case_001, summary)
        report = create_evidence_report(mock_case_001, summary, marking)

        assert verify_evidence_report(report, mock_case_001.fingerprint) is True

    def test_verify_fails_with_wrong_case_fingerprint(self, mock_case_001: Case) -> None:
        """Verification should fail with wrong case fingerprint."""
        summary = Summary(
            case_id=mock_case_001.metadata.case_id,
            text=CASE_001_GOOD_SUMMARY,
            model="test",
        )
        marking = check_omissions(mock_case_001, summary)
        report = create_evidence_report(mock_case_001, summary, marking)

        with pytest.raises(TamperVerificationError, match="Case fingerprint"):
            verify_evidence_report(report, "wrong_fingerprint")

    def test_verify_fails_on_tampered_summary(self, mock_case_001: Case) -> None:
        """Verification should fail if summary text was modified."""
        summary = Summary(
            case_id=mock_case_001.metadata.case_id,
            text=CASE_001_GOOD_SUMMARY,
            model="test",
        )
        marking = check_omissions(mock_case_001, summary)
        report = create_evidence_report(mock_case_001, summary, marking)

        report.summary.text = "TAMPERED SUMMARY TEXT"

        with pytest.raises(TamperVerificationError, match="Chain fingerprint"):
            verify_evidence_report(report)

    def test_verify_fails_on_tampered_marking(self, mock_case_001: Case) -> None:
        """Verification should fail if marking result was modified."""
        summary = Summary(
            case_id=mock_case_001.metadata.case_id,
            text=CASE_001_GOOD_SUMMARY,
            model="test",
        )
        marking = check_omissions(mock_case_001, summary)
        report = create_evidence_report(mock_case_001, summary, marking)

        report.marking_result.passed = not report.marking_result.passed

        with pytest.raises(TamperVerificationError, match="Chain fingerprint"):
            verify_evidence_report(report)


class TestEvidenceReportPersistence:
    """Tests for saving and loading evidence reports."""

    def test_save_and_load_report(self, mock_case_001: Case, tmp_path: Path) -> None:
        """Report should survive save/load cycle unchanged."""
        summary = Summary(
            case_id=mock_case_001.metadata.case_id,
            text=CASE_001_GOOD_SUMMARY,
            model="test",
        )
        marking = check_omissions(mock_case_001, summary)
        original = create_evidence_report(mock_case_001, summary, marking)

        report_path = tmp_path / "report.json"
        save_evidence_report(original, report_path)

        loaded = load_evidence_report(report_path)

        assert loaded.report_id == original.report_id
        assert loaded.case_id == original.case_id
        assert loaded.chain_fingerprint == original.chain_fingerprint
        assert loaded.marking_result.passed == original.marking_result.passed

    def test_loaded_report_verifies(self, mock_case_001: Case, tmp_path: Path) -> None:
        """Loaded report should still pass verification."""
        summary = Summary(
            case_id=mock_case_001.metadata.case_id,
            text=CASE_001_GOOD_SUMMARY,
            model="test",
        )
        marking = check_omissions(mock_case_001, summary)
        original = create_evidence_report(mock_case_001, summary, marking)

        report_path = tmp_path / "report.json"
        save_evidence_report(original, report_path)
        loaded = load_evidence_report(report_path)

        assert verify_evidence_report(loaded) is True


class TestEvidenceReportBuilder:
    """Tests for the builder pattern."""

    def test_builder_creates_valid_report(self, mock_case_001: Case) -> None:
        """Builder should create valid report."""
        summary = Summary(
            case_id=mock_case_001.metadata.case_id,
            text=CASE_001_GOOD_SUMMARY,
            model="test",
        )
        marking = check_omissions(mock_case_001, summary)

        report = (
            EvidenceReportBuilder()
            .with_case(mock_case_001)
            .with_summary(summary)
            .with_marking_result(marking)
            .with_metadata("test_key", "test_value")
            .build()
        )

        assert report.report_id is not None
        assert report.metadata["test_key"] == "test_value"
        assert verify_evidence_report(report) is True

    def test_builder_fails_without_required_components(self) -> None:
        """Builder should fail if required components missing."""
        with pytest.raises(ValueError, match="Case is required"):
            EvidenceReportBuilder().build()
