"""Data models for OpenCredit Evidence.

Defines typed schemas for cases, summaries, and evidence reports.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Severity(StrEnum):
    """Severity level for critical facts."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FactCategory(StrEnum):
    """Categories of decision-critical facts."""

    CREDIT_SCORE = "credit_score"
    DELINQUENCY = "delinquency"
    ENQUIRY_PATTERN = "enquiry_pattern"
    DEBT_TO_INCOME = "debt_to_income"
    CREDIT_UTILIZATION = "credit_utilization"
    DEBT_PATTERN = "debt_pattern"
    PAYMENT_BEHAVIOR = "payment_behavior"
    EMPLOYMENT = "employment"
    COLLATERAL = "collateral"
    OTHER = "other"


class CriticalFact(BaseModel):
    """A decision-critical fact from source documents."""

    id: str = Field(..., description="Unique identifier for the fact")
    category: FactCategory = Field(..., description="Category of the critical fact")
    fact: str = Field(..., description="The critical fact statement")
    severity: Severity = Field(..., description="Severity level")
    source: str = Field(..., description="Source document(s) containing this fact")
    evidence_text: str | None = Field(
        None, description="Exact text from source document supporting this fact"
    )


class CaseDocument(BaseModel):
    """A document within a case."""

    name: str = Field(..., description="Filename of the document")
    type: str = Field(
        ..., description="Document type (loan_application, credit_bureau_report, etc)"
    )
    description: str = Field(..., description="Human-readable description")
    content: str | None = Field(None, description="Full text content of the document")
    fingerprint: str | None = Field(None, description="SHA-256 hash of document content")


class CaseMetadata(BaseModel):
    """Metadata for a loan application case."""

    case_id: str = Field(..., description="Unique case identifier")
    case_type: str = Field(..., description="Type of case")
    created_at: datetime = Field(..., description="When the case was created")
    documents: list[CaseDocument] = Field(default_factory=list)
    critical_facts: list[CriticalFact] = Field(default_factory=list)
    referral_reason: str | None = Field(None, description="Why the case was referred")


class Case(BaseModel):
    """A complete loan application case with all documents."""

    metadata: CaseMetadata = Field(..., description="Case metadata")
    documents: dict[str, CaseDocument] = Field(
        default_factory=dict, description="Document name to document mapping"
    )
    fingerprint: str = Field(..., description="Combined fingerprint of all documents")
    loaded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Summary(BaseModel):
    """An AI-generated summary of a loan application case."""

    case_id: str = Field(..., description="ID of the case being summarized")
    text: str = Field(..., description="The summary text")
    model: str = Field(..., description="Model used to generate the summary")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    prompt_tokens: int | None = Field(None, description="Tokens used in prompt")
    completion_tokens: int | None = Field(None, description="Tokens in completion")


class OmissionResult(BaseModel):
    """Result of checking a single critical fact for omission."""

    fact_id: str = Field(..., description="ID of the critical fact checked")
    fact: CriticalFact = Field(..., description="The critical fact")
    is_present: bool = Field(..., description="Whether fact is present in summary")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    matched_text: str | None = Field(None, description="Text in summary matching this fact")
    reason: str = Field(..., description="Explanation for the determination")


class MarkingResult(BaseModel):
    """Complete marking result for omission checking."""

    case_id: str = Field(..., description="ID of the case")
    summary_fingerprint: str = Field(..., description="Fingerprint of the summary checked")
    total_facts: int = Field(..., description="Total critical facts to check")
    facts_present: int = Field(..., description="Facts found in summary")
    facts_omitted: int = Field(..., description="Facts missing from summary")
    omission_rate: float = Field(..., ge=0.0, le=1.0, description="Fraction of facts omitted")
    passed: bool = Field(..., description="Whether the summary passed omission check")
    results: list[OmissionResult] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvidenceReport(BaseModel):
    """Evidence report with tamper-proof chain."""

    report_id: str = Field(..., description="Unique report identifier")
    case_id: str = Field(..., description="ID of the case")
    case_fingerprint: str = Field(..., description="Fingerprint of source case")
    summary: Summary = Field(..., description="The generated summary")
    marking_result: MarkingResult = Field(..., description="Omission check results")
    chain_fingerprint: str = Field(..., description="Fingerprint of the complete chain")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_verification_payload(self) -> dict[str, Any]:
        """Extract payload needed for tamper verification."""
        return {
            "report_id": self.report_id,
            "case_id": self.case_id,
            "case_fingerprint": self.case_fingerprint,
            "summary_text": self.summary.text,
            "marking_passed": self.marking_result.passed,
            "omission_rate": self.marking_result.omission_rate,
        }
