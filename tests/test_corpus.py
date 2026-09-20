# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""The regulation corpus: chunking, building, hashing and retrieval — with a fake embedder."""

import json
from pathlib import Path

import pytest

from evidence.corpus import Corpus, build_corpus, list_corpora, load_corpus_spec, split_passages
from evidence.judge import parse_scores, passages_block

pytest.importorskip("pymilvus", reason="Milvus Lite is needed for the corpus index")

ROOT = Path(__file__).resolve().parents[1]


from conftest import fake_embed  # noqa: E402


def test_split_one_passage_per_paragraph():
    src = {"id": "x", "citation": "Art X", "title": "T"}
    text = "# Article X\n\nintro\n\n## 1.\n\nfirst para\n\n## 2.\n\nsecond (a) and (b)\n"
    ps = split_passages(src, text)
    assert [p.passage_id for p in ps] == ["x#1", "x#2"]
    assert ps[1].citation == "Art X(2)" and ps[1].text == "second (a) and (b)"


def test_eu_sources_chunk_and_manifest_is_reproducible(tmp_path):
    # copy the EU corpus into a scratch root and build it twice with the fake embedder
    import shutil

    shutil.copytree(
        ROOT / "regulations" / "EU", tmp_path / "EU", ignore=shutil.ignore_patterns("index")
    )
    m1 = build_corpus("EU", tmp_path, embedder=fake_embed, embed_model="fake")
    m2 = build_corpus("EU", tmp_path, embedder=fake_embed, embed_model="fake")
    assert m1["passages"] >= 20 and m1["corpus_sha256"] == m2["corpus_sha256"]
    base, spec = load_corpus_spec("EU", tmp_path)
    assert {s["id"] for s in spec["sources"]} == {s["id"] for s in m1["sources"]}
    assert (tmp_path / "EU" / "index" / "passages.db").exists()
    lines = (tmp_path / "EU" / "index" / "passages.jsonl").read_text().splitlines()
    assert len(lines) == m1["passages"] and all(json.loads(x)["passage_id"] for x in lines)
    assert list_corpora(tmp_path)[0]["built"]


def test_retrieval_returns_passages_the_judge_can_cite(tmp_path):
    import shutil

    shutil.copytree(
        ROOT / "regulations" / "EU", tmp_path / "EU", ignore=shutil.ignore_patterns("index")
    )
    build_corpus("EU", tmp_path, embedder=fake_embed, embed_model="fake")
    c = Corpus("EU", tmp_path, embedder=fake_embed)
    hits = c.retrieve("override or reverse the output of the high-risk AI system", k=2)
    assert len(hits) == 2 and all(p.passage_id in c.passages for p, _ in hits)
    block = passages_block([p for p, _ in hits])
    assert all(f"[{p.passage_id}]" in block for p, _ in hits)
    c.close()


def test_unbuilt_corpus_is_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="corpus build"):
        Corpus("ZZ", tmp_path)


def test_parse_scores_with_citation_and_truncation():
    full = parse_scores(
        '{"intelligible": 2, "actionable": 1, "overridable": 2, '
        '"citation": "ai-act-art-14#4", "reason": "r"}'
    )
    assert full["overridable"] == 2 and full["citation"] == "ai-act-art-14#4"
    cut = parse_scores('{"intelligible": 2, "actionable": 1, "overridable": 0, "cit')
    assert cut["overridable"] == 0 and "truncated" in cut["reason"]
    assert parse_scores("no json here") is None
