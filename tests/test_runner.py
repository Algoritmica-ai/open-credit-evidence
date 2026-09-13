"""Tests for the Nemotron runner module."""

import json

import httpx
import pytest

from open_credit_evidence.runner import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    NemotronClient,
    NemotronClientError,
    build_context,
    build_summarization_prompt,
    get_summary_fingerprint,
    resolve_api_key,
    run_case,
)
from open_credit_evidence.schemas import Case, Summary


class _AsyncMockTransport(httpx.AsyncBaseTransport):
    def __init__(self, handler):
        self._handler = handler

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = self._handler(request)
        response._request = request  # noqa: SLF001
        return response


class TestResolveApiKey:
    def test_prefers_nvidia_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NVIDIA_API_KEY", "nvidia-key")
        monkeypatch.setenv("NEMOTRON_API_KEY", "legacy-key")
        assert resolve_api_key() == "nvidia-key"

    def test_falls_back_to_nemotron_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        monkeypatch.setenv("NEMOTRON_API_KEY", "legacy-key")
        assert resolve_api_key() == "legacy-key"


class TestBuildContext:
    def test_concatenates_whole_files_in_metadata_order(self, mock_case_001: Case) -> None:
        context = build_context(mock_case_001)
        assert "=== application.md (loan_application) ===" in context
        assert "=== bureau_report.md (credit_bureau_report) ===" in context
        assert "Mock application content" in context
        assert "Mock bureau content" in context
        assert context.index("application.md") < context.index("bureau_report.md")

    def test_prompt_includes_underwriter_instruction(self, mock_case_001: Case) -> None:
        prompt = build_summarization_prompt(mock_case_001)
        assert "underwriter" in prompt.lower()
        assert "material credit risk" in prompt.lower()
        assert mock_case_001.metadata.case_id in prompt
        assert "Mock application content" in prompt


class TestNemotronClient:
    def test_client_not_configured_without_api_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        monkeypatch.delenv("NEMOTRON_API_KEY", raising=False)
        client = NemotronClient(api_key="")
        assert client.is_configured is False

    def test_client_configured_with_api_key(self) -> None:
        client = NemotronClient(api_key="test-key", stub=False)
        assert client.is_configured is True

    def test_client_uses_environment_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NEMOTRON_BASE_URL", "https://test.api.com")
        monkeypatch.setenv("NEMOTRON_API_KEY", "env-key")
        monkeypatch.setenv("NEMOTRON_MODEL", "test-model")
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

        client = NemotronClient()

        assert client.base_url == "https://test.api.com"
        assert client.api_key == "env-key"
        assert client.model == "test-model"

    def test_default_model_and_base_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NEMOTRON_BASE_URL", raising=False)
        monkeypatch.delenv("NVIDIA_BASE_URL", raising=False)
        monkeypatch.delenv("NEMOTRON_MODEL", raising=False)
        monkeypatch.delenv("NVIDIA_MODEL", raising=False)
        client = NemotronClient(api_key="")
        assert client.base_url == DEFAULT_BASE_URL
        assert client.model == DEFAULT_MODEL

    def test_thinking_off_by_default_in_payload(
        self, mock_case_001: Case, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("NEMOTRON_ENABLE_THINKING", raising=False)
        client = NemotronClient(api_key="k", stub=False, enable_thinking=None)
        payload = client.chat_payload(mock_case_001)
        assert payload["chat_template_kwargs"]["enable_thinking"] is False
        assert payload["model"] == DEFAULT_MODEL

    @pytest.mark.asyncio
    async def test_stub_summary_when_not_configured(self, mock_case_001: Case) -> None:
        client = NemotronClient(api_key="")

        summary = await client.generate_summary(mock_case_001)

        assert summary.case_id == mock_case_001.metadata.case_id
        assert "STUB" in summary.text
        assert summary.model == "stub"


@pytest.mark.nvidia_http
class TestNemotronLiveClientMocked:
    @pytest.mark.asyncio
    async def test_posts_openai_compatible_chat_completions(
        self, mock_case_001: Case
    ) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["body"] = json.loads(request.content)
            captured["auth"] = request.headers.get("authorization")
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "Underwriter summary: CIBIL 682 at threshold.",
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20},
                },
            )

        transport = _AsyncMockTransport(handler)
        client = NemotronClient(
            api_key="nvapi-test",
            stub=False,
            enable_thinking=False,
            transport=transport,
        )
        summary = await client.generate_summary(mock_case_001)
        await client.close()

        assert summary.text.startswith("Underwriter summary")
        assert summary.model == DEFAULT_MODEL
        assert summary.prompt_tokens == 10
        assert captured["auth"] == "Bearer nvapi-test"
        assert captured["url"].rstrip("/").endswith("/chat/completions")
        body = captured["body"]
        assert body["model"] == DEFAULT_MODEL
        assert body["stream"] is False
        assert body["chat_template_kwargs"]["enable_thinking"] is False
        user_content = body["messages"][1]["content"]
        assert "Mock application content" in user_content
        assert "underwriter" in user_content.lower()

    @pytest.mark.asyncio
    async def test_http_error_raises(self, mock_case_001: Case) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text="unauthorized")

        client = NemotronClient(
            api_key="bad",
            stub=False,
            transport=_AsyncMockTransport(handler),
        )
        with pytest.raises(NemotronClientError, match="401"):
            await client.generate_summary(mock_case_001)
        await client.close()

    @pytest.mark.asyncio
    async def test_ignores_reasoning_content(self, mock_case_001: Case) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "Final underwriter summary.",
                                "reasoning_content": "secret chain of thought",
                            }
                        }
                    ]
                },
            )

        client = NemotronClient(
            api_key="k",
            stub=False,
            transport=_AsyncMockTransport(handler),
        )
        summary = await client.generate_summary(mock_case_001)
        await client.close()
        assert summary.text == "Final underwriter summary."
        assert "secret chain of thought" not in summary.text


class TestRunCase:
    @pytest.mark.asyncio
    async def test_run_case_returns_summary(self, mock_case_001: Case) -> None:
        """run_case should return a Summary object (stub offline)."""
        summary = await run_case(mock_case_001)

        assert isinstance(summary, Summary)
        assert summary.case_id == mock_case_001.metadata.case_id
        assert summary.text is not None
        assert summary.model is not None


class TestSummaryFingerprint:
    def test_fingerprint_deterministic(self) -> None:
        summary = Summary(case_id="test", text="Test summary text", model="test")

        fp1 = get_summary_fingerprint(summary)
        fp2 = get_summary_fingerprint(summary)

        assert fp1 == fp2

    def test_fingerprint_changes_with_text(self) -> None:
        summary1 = Summary(case_id="test", text="Text A", model="test")
        summary2 = Summary(case_id="test", text="Text B", model="test")

        assert get_summary_fingerprint(summary1) != get_summary_fingerprint(summary2)
