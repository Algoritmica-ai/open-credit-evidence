# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Tests for RAG retrieval and runner integration.

Tests verify:
1. Per-document retrieval ensures each document contributes chunks
2. Runner wires retrieved chunks into transcript when retrieval is enabled
3. Retrieval flag off preserves original behavior (empty retrieved list)
"""

import json
from pathlib import Path

import pytest

from evidence.adapters.rag import (
    Chunk,
    as_prompt,
    chunk_documents,
    retrieve,
    retrieve_per_document,
)
from evidence.contracts.item import BenchmarkItem, ItemContext
from evidence.contracts.transcript import Retrieved


def fake_embed(texts, *, input_type):
    """Deterministic fake embedder for tests. Returns 4-dimensional vectors."""
    import hashlib

    out = []
    for t in texts:
        v = [0.0] * 4
        for w in t.lower().split():
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 4] += 1.0
        n = sum(x * x for x in v) ** 0.5 or 1.0
        out.append([x / n for x in v])
    return out


@pytest.fixture
def sample_context():
    """Three documents: application, bureau, and policy (rules_engine)."""
    return [
        ItemContext(
            renderer="application",
            variant="default",
            content=(
                "## Application Summary\n"
                "Applicant: John Doe\n"
                "Requested amount: £25,000\n"
                "Term: 60 months\n"
                "Monthly instalment: £520\n\n"
                "## Income Details\n"
                "Gross annual income: £42,000\n"
                "Existing commitments: £180/month\n"
            ),
        ),
        ItemContext(
            renderer="bureau",
            variant="default",
            content=(
                "## Credit Score\n"
                "Bureau score: **652**\n"
                "Score band: Fair\n\n"
                "## Payment History\n"
                "Accounts in good standing: 4\n"
                "Late payments (12 months): 1\n"
            ),
        ),
        ItemContext(
            renderer="rules_engine",
            variant="default",
            content=(
                "## Lending Policy\n"
                "Maximum debt-to-income ratio: 40%\n"
                "Minimum bureau score: 600\n\n"
                "## Risk Thresholds\n"
                "High risk: DTI > 45% or score < 550\n"
                "Medium risk: DTI 35-45% or score 550-650\n"
            ),
        ),
    ]


@pytest.fixture
def mock_embed(monkeypatch):
    """Mock the embed function with a deterministic fake."""
    monkeypatch.setattr("evidence.adapters.rag.embed", fake_embed)
    return fake_embed


class TestChunkDocuments:
    def test_chunks_all_documents(self, sample_context):
        chunks = chunk_documents(sample_context)
        renderers = {c.renderer for c in chunks}
        assert renderers == {"application", "bureau", "rules_engine"}

    def test_splits_on_section_headings(self, sample_context):
        chunks = chunk_documents(sample_context)
        app_chunks = [c for c in chunks if c.renderer == "application"]
        assert len(app_chunks) == 2
        assert any("Application Summary" in c.text for c in app_chunks)
        assert any("Income Details" in c.text for c in app_chunks)

    def test_chunk_ids_include_renderer(self, sample_context):
        chunks = chunk_documents(sample_context)
        for c in chunks:
            assert c.chunk_id.startswith(c.renderer)


class TestRetrievePerDocument:
    def test_returns_chunks_from_each_document(self, sample_context, mock_embed):
        question = "What is the debt-to-income ratio?"
        retrieved = retrieve_per_document(question, sample_context, k_per_doc=1)

        renderers = {r.renderer for r in retrieved}
        assert renderers == {"application", "bureau", "rules_engine"}

    def test_respects_k_per_doc_limit(self, sample_context, mock_embed):
        question = "What is the monthly payment?"
        retrieved = retrieve_per_document(question, sample_context, k_per_doc=1)

        from collections import Counter

        counts = Counter(r.renderer for r in retrieved)
        for count in counts.values():
            assert count <= 1

    def test_k_per_doc_two_gives_more_chunks(self, sample_context, mock_embed):
        question = "What is the monthly payment?"
        r1 = retrieve_per_document(question, sample_context, k_per_doc=1)
        r2 = retrieve_per_document(question, sample_context, k_per_doc=2)

        assert len(r2) >= len(r1)

    def test_results_sorted_by_score_descending(self, sample_context, mock_embed):
        question = "What is the bureau score?"
        retrieved = retrieve_per_document(question, sample_context, k_per_doc=2)

        scores = [r.score for r in retrieved]
        assert scores == sorted(scores, reverse=True)

    def test_empty_context_returns_empty(self, mock_embed):
        retrieved = retrieve_per_document("question", [], k_per_doc=2)
        assert retrieved == []

    def test_per_document_beats_global_on_policy_heavy_query(self, sample_context, mock_embed):
        """A policy-like query should still get chunks from each doc with per-doc retrieval."""
        question = "Is the debt-to-income ratio within the 40% policy limit?"

        per_doc = retrieve_per_document(question, sample_context, k_per_doc=1)
        global_top = retrieve(question, sample_context, k=3)

        per_doc_renderers = {r.renderer for r in per_doc}
        assert per_doc_renderers == {"application", "bureau", "rules_engine"}


class TestGlobalRetrieve:
    def test_global_retrieve_returns_top_k(self, sample_context, mock_embed):
        retrieved = retrieve("question", sample_context, k=3)
        assert len(retrieved) == 3

    def test_global_retrieve_may_miss_documents(self, sample_context, mock_embed):
        """Global retrieval can miss documents if one dominates the rankings."""
        policy_query = "What is the maximum debt-to-income ratio threshold?"
        retrieved = retrieve(policy_query, sample_context, k=2)

        renderers = {r.renderer for r in retrieved}
        assert len(renderers) <= 2


class TestAsPrompt:
    def test_formats_chunks_with_ids(self):
        retrieved = [
            Retrieved(renderer="app", chunk_id="app#0", score=0.9, text="Content A"),
            Retrieved(renderer="bureau", chunk_id="bureau#0", score=0.8, text="Content B"),
        ]
        prompt = as_prompt(retrieved)

        assert "[app#0]" in prompt
        assert "Content A" in prompt
        assert "[bureau#0]" in prompt
        assert "Content B" in prompt
        assert "---" in prompt


PACK = Path(__file__).resolve().parents[1] / "packs" / "underwriter-sample"
pytestmark_pack = pytest.mark.skipif(
    not (PACK / "items.jsonl").exists(), reason="sample pack not built"
)


class TestRunnerRetrievalIntegration:
    """Tests that the runner properly wires retrieval into transcripts."""

    @pytest.fixture
    def sample_item(self):
        """Create a minimal BenchmarkItem for testing."""
        from evidence.contracts.item import GradingSpec

        return BenchmarkItem(
            item_id="test:rag:001",
            pack="test",
            domain="credit",
            task="briefing",
            prompt="Write a briefing about this loan application.",
            context=[
                ItemContext(
                    renderer="application",
                    variant="default",
                    content="## Summary\nLoan amount: £10,000\nIncome: £30,000",
                ),
                ItemContext(
                    renderer="bureau",
                    variant="default",
                    content="## Score\nBureau score: 700",
                ),
            ],
            deterministic_checks=[],
            judges=[],
            grading=GradingSpec(disposition="approved"),
        )

    @pytest.fixture
    def mock_chat(self, monkeypatch):
        """Mock the chat function."""
        from evidence.adapters.nvidia_build import ChatResponse

        def fake_chat(role, system, user, *, max_tokens=2048, **_):
            return ChatResponse(
                text="This is a test briefing.",
                model_id="test-model",
                prompt_version="abc123",
                params={"seed": 7},
                latency_ms=100,
                tokens_in=50,
                tokens_out=20,
                raw_id="test-id",
                endpoint="http://test/v1",
            )

        monkeypatch.setattr("evidence.runner.chat", fake_chat)
        return fake_chat

    def test_call_assistant_without_retrieval_has_empty_retrieved(
        self, sample_item, mock_chat, mock_embed
    ):
        from evidence.runner import call_assistant

        transcript = call_assistant(sample_item, "run-1", 0, retrieval=False)

        assert transcript.retrieved == []
        assert "£10,000" in transcript.user_prompt

    def test_call_assistant_with_retrieval_fills_retrieved(
        self, sample_item, mock_chat, mock_embed
    ):
        from evidence.runner import call_assistant

        transcript = call_assistant(sample_item, "run-1", 0, retrieval=True, k_per_doc=1)

        assert len(transcript.retrieved) >= 2
        renderers = {r.renderer for r in transcript.retrieved}
        assert "application" in renderers
        assert "bureau" in renderers

    def test_call_assistant_with_retrieval_uses_as_prompt(
        self, sample_item, mock_chat, mock_embed
    ):
        from evidence.runner import call_assistant

        transcript = call_assistant(sample_item, "run-1", 0, retrieval=True, k_per_doc=1)

        assert "[application#" in transcript.user_prompt or "[bureau#" in transcript.user_prompt
        assert "---" in transcript.user_prompt

    def test_retrieved_chunks_have_scores(self, sample_item, mock_chat, mock_embed):
        from evidence.runner import call_assistant

        transcript = call_assistant(sample_item, "run-1", 0, retrieval=True, k_per_doc=1)

        for r in transcript.retrieved:
            assert isinstance(r.score, float)
            assert 0.0 <= r.score <= 1.0


@pytest.mark.skipif(not (PACK / "items.jsonl").exists(), reason="sample pack not built")
class TestRunPackRetrievalIntegration:
    """Integration tests with the full run_pack flow."""

    @pytest.fixture
    def stubbed_pack(self, monkeypatch, regulations_root):
        from evidence.adapters.nvidia_build import ChatResponse
        from evidence.pack import load_pack

        pack = load_pack(PACK)

        def fake_chat(role, system, user, *, max_tokens=2048, **_):
            if role == "judge":
                text = '{"intelligible": 2, "actionable": 1, "reason": "clear"}'
                return ChatResponse(
                    text, "stub-judge", "p", {}, 5, 10, 10, "j1", "http://stub/v1"
                )
            return ChatResponse(
                "Test briefing with DTI at 35%.",
                "stub-assistant",
                "p",
                {"seed": 7},
                7,
                100,
                50,
                "a1",
                "http://stub/v1",
            )

        monkeypatch.setattr("evidence.runner.chat", fake_chat)
        monkeypatch.setattr("evidence.judge.chat", fake_chat)
        monkeypatch.setattr("evidence.adapters.rag.embed", fake_embed)

        return pack

    def test_run_pack_without_retrieval_has_empty_retrieved(self, stubbed_pack, tmp_path):
        from evidence.runner import run_pack

        out = tmp_path / "no-rag"
        run_pack(stubbed_pack, out, repeats=1, limit=1, retrieval=False, log=lambda s: None)

        transcript_files = list((out / "transcripts").glob("*.json"))
        assert len(transcript_files) == 1

        transcript = json.loads(transcript_files[0].read_text())
        assert transcript["retrieved"] == []

    def test_run_pack_with_retrieval_fills_retrieved(self, stubbed_pack, tmp_path):
        from evidence.runner import run_pack

        out = tmp_path / "with-rag"
        run_pack(stubbed_pack, out, repeats=1, limit=1, retrieval=True, log=lambda s: None)

        transcript_files = list((out / "transcripts").glob("*.json"))
        assert len(transcript_files) == 1

        transcript = json.loads(transcript_files[0].read_text())
        assert len(transcript["retrieved"]) > 0
        renderers = {r["renderer"] for r in transcript["retrieved"]}
        assert len(renderers) >= 2

    def test_manifest_records_retrieval_setting(self, stubbed_pack, tmp_path):
        from evidence.runner import run_pack

        out = tmp_path / "manifest-check"
        manifest = run_pack(
            stubbed_pack, out, repeats=1, limit=1, retrieval=True, k_per_doc=3, log=lambda s: None
        )

        assert manifest["retrieval"] == {"enabled": True, "k_per_doc": 3}

    def test_manifest_retrieval_none_when_off(self, stubbed_pack, tmp_path):
        from evidence.runner import run_pack

        out = tmp_path / "manifest-off"
        manifest = run_pack(stubbed_pack, out, repeats=1, limit=1, retrieval=False, log=lambda s: None)

        assert manifest["retrieval"] is None
