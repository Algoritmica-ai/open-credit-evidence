# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Shared fixtures: a scratch copy of regulations/ with the EU corpus built by a fake embedder.

Tests never call the embedding endpoint. The fake embedder is deterministic and
4-dimensional; the scratch root keeps the repository's own index untouched.
"""

import hashlib
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def fake_embed(texts, input_type):
    out = []
    for t in texts:
        v = [0.0] * 4
        for w in t.lower().split():
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 4] += 1.0
        n = sum(x * x for x in v) ** 0.5 or 1.0
        out.append([x / n for x in v])
    return out


@pytest.fixture
def regulations_root(tmp_path, monkeypatch):
    """regulations/ copied to tmp, EU index built with the fake embedder, env pointed at it."""
    pytest.importorskip("pymilvus")
    from evidence.corpus import build_corpus

    root = tmp_path / "regulations"
    shutil.copytree(ROOT / "regulations", root, ignore=shutil.ignore_patterns("index"))
    monkeypatch.setenv("EVIDENCE_RULESETS_DIR", str(root))
    monkeypatch.setattr("evidence.corpus.embed", fake_embed)
    build_corpus("EU", root, embedder=fake_embed, embed_model="fake")
    return root
