"""Tests for case loading and fingerprint verification."""

import json
from pathlib import Path

import pytest

from open_credit_evidence.loader import (
    CaseLoadError,
    TamperDetectedError,
    compute_combined_fingerprint,
    compute_fingerprint,
    load_case,
    load_document,
    verify_case_integrity,
)


class TestFingerprinting:
    """Tests for fingerprint computation."""

    def test_compute_fingerprint_deterministic(self) -> None:
        """Same content should always produce same fingerprint."""
        content = "Test content for fingerprinting"
        fp1 = compute_fingerprint(content)
        fp2 = compute_fingerprint(content)
        assert fp1 == fp2

    def test_compute_fingerprint_different_content(self) -> None:
        """Different content should produce different fingerprints."""
        fp1 = compute_fingerprint("Content A")
        fp2 = compute_fingerprint("Content B")
        assert fp1 != fp2

    def test_fingerprint_format(self) -> None:
        """Fingerprint should be a valid SHA-256 hex string."""
        fp = compute_fingerprint("test")
        assert len(fp) == 64
        assert all(c in "0123456789abcdef" for c in fp)

    def test_combined_fingerprint_order_independent(self) -> None:
        """Combined fingerprint should be order-independent (sorted)."""
        fps = ["abc123", "def456", "ghi789"]
        combined1 = compute_combined_fingerprint(fps)
        combined2 = compute_combined_fingerprint(list(reversed(fps)))
        assert combined1 == combined2

    def test_combined_fingerprint_changes_with_content(self) -> None:
        """Combined fingerprint should change if any component changes."""
        fps1 = ["abc123", "def456"]
        fps2 = ["abc123", "def457"]
        combined1 = compute_combined_fingerprint(fps1)
        combined2 = compute_combined_fingerprint(fps2)
        assert combined1 != combined2


class TestLoadDocument:
    """Tests for loading individual documents."""

    def test_load_document_creates_fingerprint(self, tmp_path: Path) -> None:
        """Loading a document should compute its fingerprint."""
        doc_path = tmp_path / "test.md"
        content = "# Test Document\nSome content here"
        doc_path.write_text(content)

        doc = load_document(doc_path)

        assert doc.name == "test.md"
        assert doc.content == content
        assert doc.fingerprint == compute_fingerprint(content)

    def test_load_document_detects_type(self, tmp_path: Path) -> None:
        """Document type should be inferred from filename."""
        app_path = tmp_path / "application.md"
        app_path.write_text("Application content")
        bureau_path = tmp_path / "bureau_report.md"
        bureau_path.write_text("Bureau content")

        app_doc = load_document(app_path)
        bureau_doc = load_document(bureau_path)

        assert app_doc.type == "loan_application"
        assert bureau_doc.type == "credit_bureau_report"


class TestLoadCase:
    """Tests for loading complete cases."""

    def test_load_case_success(self, sample_case_001_dir: Path) -> None:
        """Should successfully load a valid case."""
        case = load_case(sample_case_001_dir)

        assert case.metadata.case_id == "LOAN-2026-09-001"
        assert len(case.documents) == 2
        assert "application.md" in case.documents
        assert "bureau_report.md" in case.documents
        assert case.fingerprint is not None

    def test_load_case_computes_fingerprints(self, sample_case_001_dir: Path) -> None:
        """All documents should have fingerprints computed."""
        case = load_case(sample_case_001_dir)

        for name, doc in case.documents.items():
            assert doc.fingerprint is not None
            assert len(doc.fingerprint) == 64

    def test_load_case_preserves_critical_facts(self, sample_case_001_dir: Path) -> None:
        """Critical facts from metadata should be preserved."""
        case = load_case(sample_case_001_dir)

        assert len(case.metadata.critical_facts) > 0
        fact = case.metadata.critical_facts[0]
        assert fact.id is not None
        assert fact.fact is not None
        assert fact.severity is not None

    def test_load_case_missing_directory(self) -> None:
        """Should raise error for non-existent directory."""
        with pytest.raises(CaseLoadError, match="not found"):
            load_case(Path("/nonexistent/path"))

    def test_load_case_missing_metadata(self, tmp_path: Path) -> None:
        """Should raise error if metadata.json is missing."""
        (tmp_path / "document.md").write_text("content")

        with pytest.raises(CaseLoadError, match="metadata.json"):
            load_case(tmp_path)

    def test_load_case_with_fingerprint_verification(self, tmp_case_dir: Path) -> None:
        """Should verify fingerprints when provided."""
        case = load_case(tmp_case_dir)
        app_fingerprint = case.documents["application.md"].fingerprint

        case_reloaded = load_case(
            tmp_case_dir,
            verify_fingerprints={"application.md": app_fingerprint},
        )
        assert case_reloaded is not None

    def test_load_case_detects_tamper(self, tmp_case_dir: Path) -> None:
        """Should detect when document has been tampered with."""
        with pytest.raises(TamperDetectedError):
            load_case(
                tmp_case_dir,
                verify_fingerprints={"application.md": "wrong_fingerprint"},
            )


class TestCaseIntegrity:
    """Tests for case integrity verification."""

    def test_verify_case_integrity_valid(self, sample_case_001_dir: Path) -> None:
        """Integrity check should pass for unchanged case."""
        case = load_case(sample_case_001_dir)
        assert verify_case_integrity(case, case.fingerprint) is True

    def test_verify_case_integrity_invalid(self, sample_case_001_dir: Path) -> None:
        """Integrity check should fail for wrong fingerprint."""
        case = load_case(sample_case_001_dir)
        assert verify_case_integrity(case, "wrong_fingerprint") is False

    def test_fingerprint_changes_on_modification(self, tmp_case_dir: Path) -> None:
        """Case fingerprint should change if documents are modified."""
        case1 = load_case(tmp_case_dir)
        original_fingerprint = case1.fingerprint

        doc_path = tmp_case_dir / "application.md"
        doc_path.write_text("# Modified Application\nNew content")

        case2 = load_case(tmp_case_dir)

        assert case2.fingerprint != original_fingerprint
