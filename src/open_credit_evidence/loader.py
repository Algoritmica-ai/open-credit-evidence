"""Case loader with fingerprint verification.

Loads case documents from disk and computes cryptographic fingerprints
to ensure tamper detection.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import structlog

from open_credit_evidence.schemas import (
    Case,
    CaseDocument,
    CaseMetadata,
    CriticalFact,
    FactCategory,
    Severity,
)

logger = structlog.get_logger()


class TamperDetectedError(Exception):
    """Raised when document tampering is detected."""

    def __init__(self, document: str, expected: str, actual: str):
        self.document = document
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Tamper detected in {document}: expected fingerprint {expected[:16]}..., "
            f"got {actual[:16]}..."
        )


class CaseLoadError(Exception):
    """Raised when case loading fails."""

    pass


def compute_fingerprint(content: str) -> str:
    """Compute SHA-256 fingerprint of content.

    Args:
        content: Text content to fingerprint

    Returns:
        Hexadecimal SHA-256 hash
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def compute_combined_fingerprint(fingerprints: list[str]) -> str:
    """Compute combined fingerprint from multiple document fingerprints.

    Args:
        fingerprints: List of individual document fingerprints

    Returns:
        Combined hexadecimal SHA-256 hash
    """
    combined = "|".join(sorted(fingerprints))
    return compute_fingerprint(combined)


def load_document(path: Path) -> CaseDocument:
    """Load a single document and compute its fingerprint.

    Args:
        path: Path to the document file

    Returns:
        CaseDocument with content and fingerprint
    """
    content = path.read_text(encoding="utf-8")
    fingerprint = compute_fingerprint(content)

    doc_type = "unknown"
    if "application" in path.name.lower():
        doc_type = "loan_application"
    elif "bureau" in path.name.lower():
        doc_type = "credit_bureau_report"

    return CaseDocument(
        name=path.name,
        type=doc_type,
        description=f"Document: {path.name}",
        content=content,
        fingerprint=fingerprint,
    )


def load_metadata(path: Path) -> CaseMetadata:
    """Load case metadata from JSON file.

    Args:
        path: Path to metadata.json

    Returns:
        CaseMetadata object

    Raises:
        CaseLoadError: If metadata is invalid
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))

        critical_facts = []
        for cf in data.get("critical_facts", []):
            critical_facts.append(
                CriticalFact(
                    id=cf["id"],
                    category=FactCategory(cf["category"]),
                    fact=cf["fact"],
                    severity=Severity(cf["severity"]),
                    source=cf["source"],
                )
            )

        documents = []
        for doc in data.get("documents", []):
            documents.append(
                CaseDocument(
                    name=doc["name"],
                    type=doc["type"],
                    description=doc["description"],
                )
            )

        return CaseMetadata(
            case_id=data["case_id"],
            case_type=data["case_type"],
            created_at=datetime.fromisoformat(data["created_at"]),
            documents=documents,
            critical_facts=critical_facts,
            referral_reason=data.get("referral_reason"),
        )
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        raise CaseLoadError(f"Invalid metadata in {path}: {e}") from e


def load_case(
    case_dir: Path | str,
    verify_fingerprints: dict[str, str] | None = None,
) -> Case:
    """Load a complete case from a directory.

    Args:
        case_dir: Path to case directory containing documents and metadata.json
        verify_fingerprints: Optional dict of document name -> expected fingerprint.
            If provided, will raise TamperDetectedError on mismatch.

    Returns:
        Loaded Case object with all documents and combined fingerprint

    Raises:
        CaseLoadError: If case cannot be loaded
        TamperDetectedError: If fingerprint verification fails
    """
    case_path = Path(case_dir)

    if not case_path.is_dir():
        raise CaseLoadError(f"Case directory not found: {case_path}")

    metadata_path = case_path / "metadata.json"
    if not metadata_path.exists():
        raise CaseLoadError(f"metadata.json not found in {case_path}")

    logger.info("loading_case", case_dir=str(case_path))

    metadata = load_metadata(metadata_path)
    documents: dict[str, CaseDocument] = {}
    fingerprints: list[str] = []

    for doc_info in metadata.documents:
        doc_path = case_path / doc_info.name
        if not doc_path.exists():
            raise CaseLoadError(f"Document not found: {doc_path}")

        doc = load_document(doc_path)
        doc.type = doc_info.type
        doc.description = doc_info.description

        if verify_fingerprints and doc.name in verify_fingerprints:
            expected = verify_fingerprints[doc.name]
            if doc.fingerprint != expected:
                raise TamperDetectedError(doc.name, expected, doc.fingerprint)

        documents[doc.name] = doc
        fingerprints.append(doc.fingerprint)  # type: ignore

        logger.debug(
            "loaded_document",
            name=doc.name,
            fingerprint=doc.fingerprint[:16] + "...",
        )

    combined_fingerprint = compute_combined_fingerprint(fingerprints)

    metadata.documents = list(documents.values())

    case = Case(
        metadata=metadata,
        documents=documents,
        fingerprint=combined_fingerprint,
        loaded_at=datetime.now(UTC),
    )

    logger.info(
        "case_loaded",
        case_id=metadata.case_id,
        num_documents=len(documents),
        num_critical_facts=len(metadata.critical_facts),
        fingerprint=combined_fingerprint[:16] + "...",
    )

    return case


def verify_case_integrity(case: Case, expected_fingerprint: str) -> bool:
    """Verify that a case has not been tampered with.

    Args:
        case: The case to verify
        expected_fingerprint: The expected combined fingerprint

    Returns:
        True if fingerprint matches, False otherwise
    """
    return case.fingerprint == expected_fingerprint


def save_fingerprints(case: Case, output_path: Path) -> None:
    """Save case fingerprints to a JSON file for later verification.

    Args:
        case: The case whose fingerprints to save
        output_path: Where to save the fingerprint file
    """
    fingerprints = {
        "case_id": case.metadata.case_id,
        "combined_fingerprint": case.fingerprint,
        "documents": {
            name: doc.fingerprint for name, doc in case.documents.items() if doc.fingerprint
        },
        "saved_at": datetime.now(UTC).isoformat(),
    }

    output_path.write_text(json.dumps(fingerprints, indent=2), encoding="utf-8")
    logger.info("fingerprints_saved", path=str(output_path))
