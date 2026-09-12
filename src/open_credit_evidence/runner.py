"""Runner for Nemotron assistant interface.

Sends cases to NVIDIA Build / Nemotron API for summary generation.
This is a stub implementation for Week 1.
"""

import os
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from open_credit_evidence.loader import compute_fingerprint
from open_credit_evidence.schemas import Case, Summary

logger = structlog.get_logger()


class NemotronClientError(Exception):
    """Raised when Nemotron API call fails."""

    pass


class NemotronClient:
    """Client for NVIDIA Nemotron API.

    This is a stub implementation. In production, this would make actual
    API calls to NVIDIA Build hosted Nemotron.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ):
        """Initialize Nemotron client.

        Args:
            base_url: API base URL. Defaults to NEMOTRON_BASE_URL env var.
            api_key: API key. Defaults to NEMOTRON_API_KEY env var.
            model: Model to use. Defaults to NEMOTRON_MODEL env var.
        """
        self.base_url = base_url or os.getenv(
            "NEMOTRON_BASE_URL", "https://integrate.api.nvidia.com/v1"
        )
        self.api_key = api_key or os.getenv("NEMOTRON_API_KEY", "")
        self.model = model or os.getenv("NEMOTRON_MODEL", "nvidia/nemotron-4-340b-instruct")

        self._client: httpx.AsyncClient | None = None

    @property
    def is_configured(self) -> bool:
        """Check if client has valid configuration."""
        return bool(self.api_key and self.base_url)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=60.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _build_summarization_prompt(self, case: Case) -> str:
        """Build the prompt for case summarization.

        Args:
            case: The case to summarize

        Returns:
            Formatted prompt string
        """
        docs_text = []
        for name, doc in case.documents.items():
            if doc.content:
                docs_text.append(f"=== {name} ===\n{doc.content}")

        combined_docs = "\n\n".join(docs_text)

        prompt = f"""You are a credit analyst reviewing a referred loan application.

Analyze the following documents and provide a concise summary that captures all
decision-critical information. Your summary MUST include:

1. Key applicant details and loan request
2. Credit score and its significance
3. Any delinquencies or negative marks
4. Debt-to-income analysis
5. Any concerning patterns (enquiries, utilization, etc.)
6. Risk indicators that warrant attention
7. Your assessment of the referral reason

IMPORTANT: Do not omit any negative indicators or risk factors. Every critical
fact that could influence a lending decision must be included.

=== CASE DOCUMENTS ===

{combined_docs}

=== END DOCUMENTS ===

Provide your summary:"""

        return prompt

    async def generate_summary(self, case: Case) -> Summary:
        """Generate a summary for a loan application case.

        Args:
            case: The case to summarize

        Returns:
            Generated Summary object

        Raises:
            NemotronClientError: If API call fails
        """
        logger.info(
            "generating_summary",
            case_id=case.metadata.case_id,
            model=self.model,
        )

        prompt = self._build_summarization_prompt(case)

        if not self.is_configured:
            logger.warning("nemotron_not_configured", using="stub_response")
            return self._generate_stub_summary(case, prompt)

        try:
            client = await self._get_client()
            response = await client.post(
                "/chat/completions",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 2000,
                },
            )
            response.raise_for_status()
            data = response.json()

            summary_text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})

            return Summary(
                case_id=case.metadata.case_id,
                text=summary_text,
                model=self.model,
                generated_at=datetime.now(UTC),
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
            )

        except httpx.HTTPStatusError as e:
            raise NemotronClientError(f"API error: {e.response.status_code}") from e
        except httpx.RequestError as e:
            raise NemotronClientError(f"Request failed: {e}") from e

    def _generate_stub_summary(self, case: Case, prompt: str) -> Summary:
        """Generate a stub summary for testing when API is not configured.

        This allows development and testing without actual API calls.
        """
        case_id = case.metadata.case_id

        stub_text = f"""LOAN APPLICATION SUMMARY - {case_id}

[STUB SUMMARY - Nemotron API not configured]

This is a placeholder summary generated without actual API calls.
Configure NEMOTRON_API_KEY to enable real summary generation.

Case ID: {case_id}
Documents: {len(case.documents)}
Critical Facts: {len(case.metadata.critical_facts)}
Referral Reason: {case.metadata.referral_reason or 'Not specified'}

To test omission detection, use the test fixtures in tests/fixtures/
which contain pre-generated good and bad summaries.
"""

        return Summary(
            case_id=case_id,
            text=stub_text,
            model="stub",
            generated_at=datetime.now(UTC),
            prompt_tokens=len(prompt.split()),
            completion_tokens=len(stub_text.split()),
        )


async def run_case(
    case: Case,
    client: NemotronClient | None = None,
) -> Summary:
    """Run a case through the summarization pipeline.

    Args:
        case: The case to process
        client: Optional NemotronClient. Creates one if not provided.

    Returns:
        Generated summary
    """
    if client is None:
        client = NemotronClient()

    try:
        return await client.generate_summary(case)
    finally:
        if client:
            await client.close()


def get_summary_fingerprint(summary: Summary) -> str:
    """Compute fingerprint of a summary for verification.

    Args:
        summary: The summary to fingerprint

    Returns:
        SHA-256 fingerprint of summary text
    """
    return compute_fingerprint(summary.text)
