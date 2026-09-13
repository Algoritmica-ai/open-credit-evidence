"""OpenCredit Evidence - Credit Decision Verification System.

4-week plan: Credit Evidence Engine for OpenCredit Evidence Hackathon.
"""

__version__ = "0.1.0"

from open_credit_evidence.schemas import (
    Case,
    CaseDocument,
    CriticalFact,
    EvidenceReport,
    MarkingResult,
    OmissionResult,
    Summary,
)

__all__ = [
    "Case",
    "CaseDocument",
    "CriticalFact",
    "EvidenceReport",
    "MarkingResult",
    "OmissionResult",
    "Summary",
]
