"""Tests for omission detection.

These tests verify that the omission checker correctly identifies
when summaries are missing critical facts.
"""

from open_credit_evidence.omission_check import OmissionChecker, check_omissions
from open_credit_evidence.schemas import Case, Summary
from tests.fixtures.summaries import (
    CASE_001_BAD_SUMMARY_OMITS_DELINQUENCY,
    CASE_001_BAD_SUMMARY_OMITS_ENQUIRY,
    CASE_001_GOOD_SUMMARY,
    CASE_002_BAD_SUMMARY_OMITS_ENQUIRIES,
    CASE_002_BAD_SUMMARY_OMITS_UTILIZATION,
    CASE_002_GOOD_SUMMARY,
)


class TestOmissionChecker:
    """Tests for the OmissionChecker class."""

    def test_good_summary_passes_case_001(self, mock_case_001: Case) -> None:
        """A complete summary should pass omission check."""
        summary = Summary(
            case_id=mock_case_001.metadata.case_id,
            text=CASE_001_GOOD_SUMMARY,
            model="test",
        )

        result = check_omissions(mock_case_001, summary)

        assert result.passed is True, f"Good summary should pass. Omitted: {result.facts_omitted}"
        assert result.facts_omitted == 0

    def test_bad_summary_fails_when_delinquency_omitted(self, mock_case_001: Case) -> None:
        """Summary omitting delinquency should fail."""
        summary = Summary(
            case_id=mock_case_001.metadata.case_id,
            text=CASE_001_BAD_SUMMARY_OMITS_DELINQUENCY,
            model="test",
        )

        result = check_omissions(mock_case_001, summary)

        assert result.passed is False, "Summary omitting delinquency should fail"
        assert result.facts_omitted > 0

        omitted_fact_ids = [r.fact_id for r in result.results if not r.is_present]
        assert "cf_002" in omitted_fact_ids, "Should detect delinquency fact as omitted"

    def test_bad_summary_fails_when_enquiry_omitted(self, mock_case_001: Case) -> None:
        """Summary omitting Kotak enquiry should fail."""
        summary = Summary(
            case_id=mock_case_001.metadata.case_id,
            text=CASE_001_BAD_SUMMARY_OMITS_ENQUIRY,
            model="test",
        )

        result = check_omissions(mock_case_001, summary)

        assert result.passed is False, "Summary omitting enquiry pattern should fail"

        omitted_fact_ids = [r.fact_id for r in result.results if not r.is_present]
        assert "cf_003" in omitted_fact_ids, "Should detect Kotak enquiry fact as omitted"

    def test_good_summary_passes_case_002(self, mock_case_002: Case) -> None:
        """Complete summary for case 002 should pass."""
        summary = Summary(
            case_id=mock_case_002.metadata.case_id,
            text=CASE_002_GOOD_SUMMARY,
            model="test",
        )

        result = check_omissions(mock_case_002, summary)

        assert result.passed is True, f"Good summary should pass. Results: {result.results}"
        assert result.omission_rate == 0.0

    def test_bad_summary_fails_when_utilization_omitted(self, mock_case_002: Case) -> None:
        """Summary omitting critical utilization fact should fail."""
        summary = Summary(
            case_id=mock_case_002.metadata.case_id,
            text=CASE_002_BAD_SUMMARY_OMITS_UTILIZATION,
            model="test",
        )

        result = check_omissions(mock_case_002, summary)

        assert result.passed is False, "Summary omitting utilization should fail"

        omitted_fact_ids = [r.fact_id for r in result.results if not r.is_present]
        assert "cf_001" in omitted_fact_ids, "Should detect utilization fact as omitted"

    def test_bad_summary_fails_when_enquiries_omitted(self, mock_case_002: Case) -> None:
        """Summary omitting enquiry pattern should fail."""
        summary = Summary(
            case_id=mock_case_002.metadata.case_id,
            text=CASE_002_BAD_SUMMARY_OMITS_ENQUIRIES,
            model="test",
        )

        result = check_omissions(mock_case_002, summary)

        assert result.passed is False, "Summary omitting enquiries should fail"

        omitted_fact_ids = [r.fact_id for r in result.results if not r.is_present]
        assert "cf_002" in omitted_fact_ids, "Should detect enquiry pattern fact as omitted"


class TestOmissionCheckerConfiguration:
    """Tests for OmissionChecker configuration options."""

    def test_confidence_threshold_affects_detection(self, mock_case_001: Case) -> None:
        """Higher confidence threshold should be stricter."""
        summary = Summary(
            case_id=mock_case_001.metadata.case_id,
            text="CIBIL score 682 mentioned but details sparse",
            model="test",
        )

        lenient_checker = OmissionChecker(confidence_threshold=0.1)
        strict_checker = OmissionChecker(confidence_threshold=0.9)

        lenient_result = lenient_checker.check_summary(mock_case_001, summary)
        strict_result = strict_checker.check_summary(mock_case_001, summary)

        assert strict_result.facts_omitted >= lenient_result.facts_omitted

    def test_marking_result_has_correct_structure(self, mock_case_001: Case) -> None:
        """Marking result should have all required fields."""
        summary = Summary(
            case_id=mock_case_001.metadata.case_id,
            text=CASE_001_GOOD_SUMMARY,
            model="test",
        )

        result = check_omissions(mock_case_001, summary)

        assert result.case_id == mock_case_001.metadata.case_id
        assert result.total_facts == len(mock_case_001.metadata.critical_facts)
        assert result.facts_present + result.facts_omitted == result.total_facts
        assert 0.0 <= result.omission_rate <= 1.0
        assert len(result.results) == result.total_facts
        assert result.summary_fingerprint is not None
        assert result.checked_at is not None


class TestOmissionResultDetails:
    """Tests for detailed omission result information."""

    def test_omission_result_includes_fact_details(self, mock_case_001: Case) -> None:
        """Each result should include the full fact information."""
        summary = Summary(
            case_id=mock_case_001.metadata.case_id,
            text=CASE_001_GOOD_SUMMARY,
            model="test",
        )

        result = check_omissions(mock_case_001, summary)

        for omission_result in result.results:
            assert omission_result.fact_id is not None
            assert omission_result.fact is not None
            assert omission_result.reason is not None
            assert 0.0 <= omission_result.confidence <= 1.0

    def test_present_facts_have_matched_text(self, mock_case_001: Case) -> None:
        """Facts that are present should include matched text."""
        summary = Summary(
            case_id=mock_case_001.metadata.case_id,
            text=CASE_001_GOOD_SUMMARY,
            model="test",
        )

        result = check_omissions(mock_case_001, summary)

        present_results = [r for r in result.results if r.is_present]
        for r in present_results:
            if r.confidence > 0:
                assert r.matched_text is not None or r.reason
