"""Tests for the Nemotron runner module."""

import pytest

from open_credit_evidence.runner import (
    NemotronClient,
    get_summary_fingerprint,
    run_case,
)
from open_credit_evidence.schemas import Case, Summary


class TestNemotronClient:
    """Tests for NemotronClient."""

    def test_client_not_configured_without_api_key(self) -> None:
        """Client should report not configured without API key."""
        client = NemotronClient(api_key="")
        assert client.is_configured is False

    def test_client_configured_with_api_key(self) -> None:
        """Client should report configured with API key."""
        client = NemotronClient(api_key="test-key")
        assert client.is_configured is True

    def test_client_uses_environment_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Client should use environment variables for defaults."""
        monkeypatch.setenv("NEMOTRON_BASE_URL", "https://test.api.com")
        monkeypatch.setenv("NEMOTRON_API_KEY", "env-key")
        monkeypatch.setenv("NEMOTRON_MODEL", "test-model")

        client = NemotronClient()

        assert client.base_url == "https://test.api.com"
        assert client.api_key == "env-key"
        assert client.model == "test-model"

    @pytest.mark.asyncio
    async def test_stub_summary_when_not_configured(self, mock_case_001: Case) -> None:
        """Should generate stub summary when API not configured."""
        client = NemotronClient(api_key="")

        summary = await client.generate_summary(mock_case_001)

        assert summary.case_id == mock_case_001.metadata.case_id
        assert "STUB" in summary.text
        assert summary.model == "stub"


class TestRunCase:
    """Tests for the run_case function."""

    @pytest.mark.asyncio
    async def test_run_case_returns_summary(self, mock_case_001: Case) -> None:
        """run_case should return a Summary object."""
        summary = await run_case(mock_case_001)

        assert isinstance(summary, Summary)
        assert summary.case_id == mock_case_001.metadata.case_id
        assert summary.text is not None
        assert summary.model is not None


class TestSummaryFingerprint:
    """Tests for summary fingerprinting."""

    def test_fingerprint_deterministic(self) -> None:
        """Same summary text should produce same fingerprint."""
        summary = Summary(case_id="test", text="Test summary text", model="test")

        fp1 = get_summary_fingerprint(summary)
        fp2 = get_summary_fingerprint(summary)

        assert fp1 == fp2

    def test_fingerprint_changes_with_text(self) -> None:
        """Different summary text should produce different fingerprint."""
        summary1 = Summary(case_id="test", text="Text A", model="test")
        summary2 = Summary(case_id="test", text="Text B", model="test")

        assert get_summary_fingerprint(summary1) != get_summary_fingerprint(summary2)
