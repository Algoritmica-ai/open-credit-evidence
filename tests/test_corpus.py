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
    # the same passages under the same model name, embedded differently, are a new version
    m3 = build_corpus("EU", tmp_path, embedder=lambda texts, kind: [
        list(reversed(v)) for v in fake_embed(texts, kind)], embed_model="fake")
    assert m3["passages_sha256"] == m1["passages_sha256"]
    assert m3["vectors_sha256"] != m1["vectors_sha256"]
    assert m3["corpus_sha256"] != m1["corpus_sha256"]
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


def test_cosine_fallback_matches_milvus_ranking(tmp_path):
    import shutil

    shutil.copytree(
        ROOT / "regulations" / "EU", tmp_path / "EU", ignore=shutil.ignore_patterns("index")
    )
    build_corpus("EU", tmp_path, embedder=fake_embed, embed_model="fake")
    q = "override or reverse the output of the high-risk AI system"
    c = Corpus("EU", tmp_path, embedder=fake_embed)
    milvus = [p.passage_id for p, _ in c.retrieve(q, k=3)]
    c.close()
    shutil.rmtree(tmp_path / "EU" / "index" / "passages.db", ignore_errors=True)
    if (tmp_path / "EU" / "index" / "passages.db").exists():
        (tmp_path / "EU" / "index" / "passages.db").unlink()
    c2 = Corpus("EU", tmp_path, embedder=fake_embed)
    assert c2.backend == "cosine"
    assert [p.passage_id for p, _ in c2.retrieve(q, k=3)] == milvus


def test_split_drops_the_file_note_and_refuses_unheaded_or_overrunning_text():
    src = {"id": "ax", "citation": "Annex X", "title": "T",
           "paragraph_citation": "{citation}, point {para}"}
    note = "# Annex X\n\nRegulation ..., consolidated text.\nSource: https://example\n\n\n"
    ps = split_passages(src, note + "## 5.\n\nAccess to services:\n\n(b) credit scoring;\n")
    assert [p.passage_id for p in ps] == ["ax#5"]
    assert ps[0].citation == "Annex X, point 5" and ps[0].text.startswith("Access to services")
    with pytest.raises(ValueError, match="no '## <paragraph>' sections"):
        split_passages(src, note + "Access to services: (b) credit scoring;\n")
    with pytest.raises(ValueError, match="'SECTION 3'"):
        split_passages(src, "## 5.\n\nmodel flaws.\n\nSECTION 3\n\nObligations of providers\n")
    with pytest.raises(ValueError, match="'Article 16'"):
        split_passages(src, "## 5.\n\nmodel flaws.\n\nArticle 16\n\nObligations\n")


def test_eu_passages_carry_no_file_note_or_structural_heading():
    base, spec = load_corpus_spec("EU")
    for s in spec["sources"]:
        for p in split_passages(s, (base / s["file"]).read_text(encoding="utf-8")):
            assert "Source: http" not in p.text and "consolidated text as of" not in p.text
    # the repository's index is built from the sources as they are now
    built = [(r["passage_id"], r["text"]) for r in map(json.loads, (
        base / "index" / "passages.jsonl").read_text(encoding="utf-8").splitlines())]
    fresh = [(p.passage_id, p.text) for s in spec["sources"]
             for p in split_passages(s, (base / s["file"]).read_text(encoding="utf-8"))]
    assert built == fresh


def test_embedder_check_passes_for_the_builder_and_fails_for_another(regulations_root):
    c = Corpus("EU", regulations_root, embedder=fake_embed)
    ok = c.check_embedder()
    assert ok["ok"] and ok["cosine"] >= 0.999 and ok["probe"] in c.passages
    other = Corpus("EU", regulations_root, embedder=lambda texts, kind: [
        list(reversed(v)) for v in fake_embed(texts, kind)])
    bad = other.check_embedder()
    assert not bad["ok"] and bad["index_embed_model"] == "fake"
    wider = Corpus("EU", regulations_root, embedder=lambda texts, kind: [
        v + [0.0] for v in fake_embed(texts, kind)])
    assert wider.check_embedder()["cosine"] == 0.0  # another dimension is another embedder


def test_verify_sources_finds_passages_and_says_where_one_diverges(regulations_root):
    from evidence.corpus import source_check_status, verify_sources

    rows = [json.loads(x) for x in (regulations_root / "EU" / "index" / "passages.jsonl")
            .read_text().splitlines() if x]
    # an official text with every passage, typeset differently, and one word changed in one
    texts = [r["text"].replace("’", "'").replace("\n\n", "\n") for r in rows]
    changed = rows[3]["passage_id"]
    texts[3] = texts[3][:150] + " altered " + texts[3][159:]
    official = "\n\n".join(texts)
    rec = verify_sources("EU", official, official={"id": "CELEX:TEST"}, root=regulations_root)
    assert rec["found"] == rec["passages"] - 1
    miss = next(r for r in rec["results"] if not r["found"])
    assert miss["passage_id"] == changed and 0 < miss["matches_up_to"] < miss["of"]
    c = Corpus("EU", regulations_root, embedder=fake_embed)
    status = c.source_check()
    assert status["official"] == "CELEX:TEST" and status["unchecked"] == [changed]
    # a passage edited after the check is unchecked again
    p0 = next(iter(c.passages.values()))
    edited = [p if p is not p0 else p.__class__(**(p.__dict__ | {"text": p.text + " x"}))
              for p in c.passages.values()]
    assert p0.passage_id in source_check_status("EU", edited, regulations_root)["unchecked"]


def test_repository_source_check_covers_every_passage():
    from evidence.corpus import list_corpora

    eu = next(c for c in list_corpora() if c["jurisdiction"] == "EU")
    sc = eu["source_check"]
    assert sc is not None, "run evidence corpus verify-sources EU"
    assert sc["found"] == sc["passages"] == eu["passages"] and not sc["unchecked"]


def test_parse_scores_reads_nested_per_question_citations():
    from evidence.judge import citations

    s = parse_scores('thinking… {"intelligible": 2, "actionable": 1, "overridable": 2, '
                     '"citations": {"intelligible": "[ai-act-art-13#1]", "actionable": '
                     '"ai-act-art-13#3", "overridable": "\'ai-act-art-14#4\'"}, "reason": "r"}')
    assert s["overridable"] == 2 and "truncated" not in s["reason"]
    assert citations(s) == {"intelligible": "ai-act-art-13#1", "actionable": "ai-act-art-13#3",
                            "overridable": "ai-act-art-14#4"}
    one = citations({"citation": " [ai-act-art-14#4] "})
    assert set(one.values()) == {"ai-act-art-14#4"} and len(one) == 3


def test_judge_retrieves_per_question_and_checks_each_citation(regulations_root, monkeypatch):
    from evidence.adapters.nvidia_build import ChatResponse
    from evidence.judge import FIELD_QUERIES, judge_readability

    c = Corpus("EU", regulations_root, embedder=fake_embed)
    seen = {}

    def chat(role, system, user, **_):
        seen["system"] = system
        ids = [line[1:line.index("]")] for line in system.splitlines() if line.startswith("[")]
        text = json.dumps({"intelligible": 2, "actionable": 1, "overridable": 2,
                           "citations": {"intelligible": f"[{ids[0]}]",
                                         "actionable": f"{ids[-1]}, {ids[0]}",
                                         "overridable": "ai-act-art-99#1"}, "reason": "r"})
        return ChatResponse(text, "stub-judge", "p", {}, 5, 10, 10, "j1", "http://stub/v1")

    monkeypatch.setattr("evidence.judge.chat", chat)
    rec = judge_readability(output="a briefing", item=None, corpus=c)
    assert set(rec["passages_by_field"]) == set(FIELD_QUERIES)
    assert set(rec["passages"]) == {pid for ids in rec["passages_by_field"].values() for pid in ids}
    per = rec["evidence"][0]["citations"]
    assert per["intelligible"]["in_passages"] and per["actionable"]["in_passages"]
    assert per["actionable"]["citation"].count(",") == 1  # two given passages both count
    assert per["overridable"] == {"citation": "ai-act-art-99#1", "in_passages": False}
    assert rec["evidence"][0]["citation_in_passages"] is False
