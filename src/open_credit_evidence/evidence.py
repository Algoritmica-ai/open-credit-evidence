"""Evidence report generation and tamper verification.

Creates tamper-proof evidence reports and verifies their integrity.
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from open_credit_evidence.loader import compute_fingerprint
from open_credit_evidence.schemas import (
    Case,
    EvidenceReport,
    MarkingResult,
    Summary,
)

logger = structlog.get_logger()


class TamperVerificationError(Exception):
    """Raised when evidence report tampering is detected."""

    def __init__(self, report_id: str, reason: str):
        self.report_id = report_id
        self.reason = reason
        super().__init__(f"Tamper detected in report {report_id}: {reason}")


def compute_chain_fingerprint(
    case_fingerprint: str,
    summary_fingerprint: str,
    marking_fingerprint: str,
) -> str:
    """Compute the chain fingerprint for tamper detection.

    The chain fingerprint ties together the case, summary, and marking
    results into a single verifiable hash.

    Args:
        case_fingerprint: Fingerprint of the source case
        summary_fingerprint: Fingerprint of the generated summary
        marking_fingerprint: Fingerprint of the marking result

    Returns:
        Combined chain fingerprint
    """
    chain_data = f"{case_fingerprint}|{summary_fingerprint}|{marking_fingerprint}"
    return compute_fingerprint(chain_data)


def compute_marking_fingerprint(result: MarkingResult) -> str:
    """Compute fingerprint of marking result.

    Args:
        result: The marking result to fingerprint

    Returns:
        SHA-256 fingerprint
    """
    marking_data = {
        "case_id": result.case_id,
        "total_facts": result.total_facts,
        "facts_present": result.facts_present,
        "facts_omitted": result.facts_omitted,
        "passed": result.passed,
        "fact_results": [
            {"fact_id": r.fact_id, "is_present": r.is_present, "confidence": r.confidence}
            for r in result.results
        ],
    }
    return compute_fingerprint(json.dumps(marking_data, sort_keys=True))


def generate_report_id() -> str:
    """Generate a unique report ID.

    Returns:
        UUID-based report identifier
    """
    return f"EVR-{datetime.now(UTC).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"


def create_evidence_report(
    case: Case,
    summary: Summary,
    marking_result: MarkingResult,
    metadata: dict[str, Any] | None = None,
) -> EvidenceReport:
    """Create a tamper-proof evidence report.

    Args:
        case: The source case
        summary: The generated summary
        marking_result: The omission check results
        metadata: Optional additional metadata

    Returns:
        EvidenceReport with chain fingerprint
    """
    report_id = generate_report_id()

    summary_fingerprint = compute_fingerprint(summary.text)
    marking_fingerprint = compute_marking_fingerprint(marking_result)
    chain_fingerprint = compute_chain_fingerprint(
        case.fingerprint,
        summary_fingerprint,
        marking_fingerprint,
    )

    report = EvidenceReport(
        report_id=report_id,
        case_id=case.metadata.case_id,
        case_fingerprint=case.fingerprint,
        summary=summary,
        marking_result=marking_result,
        chain_fingerprint=chain_fingerprint,
        created_at=datetime.now(UTC),
        metadata=metadata or {},
    )

    logger.info(
        "evidence_report_created",
        report_id=report_id,
        case_id=case.metadata.case_id,
        passed=marking_result.passed,
        chain_fingerprint=chain_fingerprint[:16] + "...",
    )

    return report


def verify_evidence_report(
    report: EvidenceReport,
    expected_case_fingerprint: str | None = None,
) -> bool:
    """Verify that an evidence report has not been tampered with.

    Recomputes the chain fingerprint and verifies it matches.

    Args:
        report: The report to verify
        expected_case_fingerprint: Optional case fingerprint to verify against

    Returns:
        True if verification passes

    Raises:
        TamperVerificationError: If tampering is detected
    """
    logger.info("verifying_report", report_id=report.report_id)

    summary_fingerprint = compute_fingerprint(report.summary.text)
    marking_fingerprint = compute_marking_fingerprint(report.marking_result)

    expected_chain = compute_chain_fingerprint(
        report.case_fingerprint,
        summary_fingerprint,
        marking_fingerprint,
    )

    if expected_chain != report.chain_fingerprint:
        raise TamperVerificationError(
            report.report_id,
            f"Chain fingerprint mismatch: expected {expected_chain[:16]}..., "
            f"got {report.chain_fingerprint[:16]}...",
        )

    if expected_case_fingerprint and report.case_fingerprint != expected_case_fingerprint:
        raise TamperVerificationError(
            report.report_id,
            f"Case fingerprint mismatch: expected {expected_case_fingerprint[:16]}..., "
            f"got {report.case_fingerprint[:16]}...",
        )

    logger.info(
        "report_verified",
        report_id=report.report_id,
        chain_fingerprint=report.chain_fingerprint[:16] + "...",
    )

    return True


def save_evidence_report(report: EvidenceReport, output_path: Path) -> None:
    """Save evidence report to a JSON file.

    Args:
        report: The report to save
        output_path: Where to save the report
    """
    report_dict = report.model_dump(mode="json")
    output_path.write_text(json.dumps(report_dict, indent=2, default=str), encoding="utf-8")
    logger.info("report_saved", path=str(output_path), report_id=report.report_id)


def load_evidence_report(input_path: Path) -> EvidenceReport:
    """Load evidence report from a JSON file.

    Args:
        input_path: Path to the report file

    Returns:
        Loaded EvidenceReport

    Raises:
        ValueError: If file is invalid
    """
    data = json.loads(input_path.read_text(encoding="utf-8"))
    return EvidenceReport.model_validate(data)


class EvidenceReportBuilder:
    """Builder for creating evidence reports step by step.

    Useful when processing happens in stages.
    """

    def __init__(self) -> None:
        self._case: Case | None = None
        self._summary: Summary | None = None
        self._marking_result: MarkingResult | None = None
        self._metadata: dict[str, Any] = {}

    def with_case(self, case: Case) -> "EvidenceReportBuilder":
        """Set the source case."""
        self._case = case
        return self

    def with_summary(self, summary: Summary) -> "EvidenceReportBuilder":
        """Set the generated summary."""
        self._summary = summary
        return self

    def with_marking_result(self, result: MarkingResult) -> "EvidenceReportBuilder":
        """Set the marking result."""
        self._marking_result = result
        return self

    def with_metadata(self, key: str, value: Any) -> "EvidenceReportBuilder":
        """Add metadata."""
        self._metadata[key] = value
        return self

    def build(self) -> EvidenceReport:
        """Build the evidence report.

        Raises:
            ValueError: If required components are missing
        """
        if self._case is None:
            raise ValueError("Case is required")
        if self._summary is None:
            raise ValueError("Summary is required")
        if self._marking_result is None:
            raise ValueError("Marking result is required")

        return create_evidence_report(
            self._case,
            self._summary,
            self._marking_result,
            self._metadata,
        )
