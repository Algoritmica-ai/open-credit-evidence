"""Pytest configuration and shared fixtures."""

import json
from datetime import datetime
from pathlib import Path
from typing import Generator

import pytest

from open_credit_evidence.schemas import (
    Case,
    CaseDocument,
    CaseMetadata,
    CriticalFact,
    FactCategory,
    Severity,
    Summary,
)


@pytest.fixture
def cases_dir() -> Path:
    """Path to the cases directory."""
    return Path(__file__).parent.parent / "cases"


@pytest.fixture
def sample_case_001_dir(cases_dir: Path) -> Path:
    """Path to sample case 001."""
    return cases_dir / "sample_case_001"


@pytest.fixture
def sample_case_002_dir(cases_dir: Path) -> Path:
    """Path to sample case 002."""
    return cases_dir / "sample_case_002"


@pytest.fixture
def case_001_critical_facts() -> list[CriticalFact]:
    """Critical facts for case 001."""
    return [
        CriticalFact(
            id="cf_001",
            category=FactCategory.CREDIT_SCORE,
            fact="CIBIL score is 682, at boundary of minimum threshold 680",
            severity=Severity.HIGH,
            source="bureau_report.md",
        ),
        CriticalFact(
            id="cf_002",
            category=FactCategory.DELINQUENCY,
            fact="30-day late payment on SBI credit card in June 2026",
            severity=Severity.HIGH,
            source="bureau_report.md",
        ),
        CriticalFact(
            id="cf_003",
            category=FactCategory.ENQUIRY_PATTERN,
            fact="Recent loan enquiry from Kotak Mahindra Bank 7 days prior suggests credit shopping or prior decline",
            severity=Severity.HIGH,
            source="bureau_report.md",
        ),
        CriticalFact(
            id="cf_004",
            category=FactCategory.DEBT_TO_INCOME,
            fact="Existing debt-to-income ratio is 38%",
            severity=Severity.MEDIUM,
            source="application.md, bureau_report.md",
        ),
    ]


@pytest.fixture
def case_002_critical_facts() -> list[CriticalFact]:
    """Critical facts for case 002."""
    return [
        CriticalFact(
            id="cf_001",
            category=FactCategory.CREDIT_UTILIZATION,
            fact="Credit card utilization is critically high at 60%+",
            severity=Severity.CRITICAL,
            source="bureau_report.md",
        ),
        CriticalFact(
            id="cf_002",
            category=FactCategory.ENQUIRY_PATTERN,
            fact="Three personal loan enquiries in 45 days indicates aggressive credit seeking behavior",
            severity=Severity.HIGH,
            source="bureau_report.md",
        ),
        CriticalFact(
            id="cf_003",
            category=FactCategory.DEBT_PATTERN,
            fact="Debt consolidation purpose combined with high revolving debt suggests cash flow stress",
            severity=Severity.HIGH,
            source="application.md, bureau_report.md",
        ),
        CriticalFact(
            id="cf_004",
            category=FactCategory.PAYMENT_BEHAVIOR,
            fact="Making only minimum payments on credit cards despite high income",
            severity=Severity.MEDIUM,
            source="bureau_report.md",
        ),
    ]


@pytest.fixture
def mock_case_001(case_001_critical_facts: list[CriticalFact]) -> Case:
    """Create a mock Case object for case 001."""
    metadata = CaseMetadata(
        case_id="LOAN-2026-09-001",
        case_type="referred_loan_application",
        created_at=datetime(2026, 9, 5, 10, 30, 45),
        documents=[
            CaseDocument(
                name="application.md",
                type="loan_application",
                description="Primary loan application form",
            ),
            CaseDocument(
                name="bureau_report.md",
                type="credit_bureau_report",
                description="CIBIL TransUnion credit report",
            ),
        ],
        critical_facts=case_001_critical_facts,
        referral_reason="Score at boundary threshold with multiple warning indicators",
    )

    return Case(
        metadata=metadata,
        documents={
            "application.md": CaseDocument(
                name="application.md",
                type="loan_application",
                description="Primary loan application form",
                content="Mock application content",
                fingerprint="abc123",
            ),
            "bureau_report.md": CaseDocument(
                name="bureau_report.md",
                type="credit_bureau_report",
                description="CIBIL TransUnion credit report",
                content="Mock bureau content",
                fingerprint="def456",
            ),
        },
        fingerprint="combined_fingerprint_001",
    )


@pytest.fixture
def mock_case_002(case_002_critical_facts: list[CriticalFact]) -> Case:
    """Create a mock Case object for case 002."""
    metadata = CaseMetadata(
        case_id="LOAN-2026-09-002",
        case_type="referred_loan_application",
        created_at=datetime(2026, 9, 6, 14, 22, 18),
        documents=[
            CaseDocument(
                name="application.md",
                type="loan_application",
                description="Primary loan application form",
            ),
            CaseDocument(
                name="bureau_report.md",
                type="credit_bureau_report",
                description="CIBIL TransUnion credit report",
            ),
        ],
        critical_facts=case_002_critical_facts,
        referral_reason="High amount debt consolidation loan with concerning credit utilization pattern",
    )

    return Case(
        metadata=metadata,
        documents={
            "application.md": CaseDocument(
                name="application.md",
                type="loan_application",
                description="Primary loan application form",
                content="Mock application content",
                fingerprint="ghi789",
            ),
            "bureau_report.md": CaseDocument(
                name="bureau_report.md",
                type="credit_bureau_report",
                description="CIBIL TransUnion credit report",
                content="Mock bureau content",
                fingerprint="jkl012",
            ),
        },
        fingerprint="combined_fingerprint_002",
    )


@pytest.fixture
def tmp_case_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary case directory for testing."""
    case_dir = tmp_path / "test_case"
    case_dir.mkdir()

    (case_dir / "application.md").write_text("# Test Application\nTest content")
    (case_dir / "bureau_report.md").write_text("# Test Bureau Report\nTest content")

    metadata = {
        "case_id": "TEST-001",
        "case_type": "test",
        "created_at": "2026-09-05T10:00:00+05:30",
        "documents": [
            {"name": "application.md", "type": "loan_application", "description": "Test app"},
            {"name": "bureau_report.md", "type": "credit_bureau_report", "description": "Test bureau"},
        ],
        "critical_facts": [
            {
                "id": "cf_001",
                "category": "credit_score",
                "fact": "Test fact",
                "severity": "high",
                "source": "application.md",
            }
        ],
    }
    (case_dir / "metadata.json").write_text(json.dumps(metadata))

    yield case_dir
