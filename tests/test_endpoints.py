# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Where each role runs is a .env decision; the adapter must honour it without a network."""

import os

import pytest

from evidence.adapters import nvidia_build as nb


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # The developer's .env may point roles at the cluster; these tests must not see it.
    monkeypatch.setattr(nb, "_load_env", lambda: None)
    for k in list(os.environ):
        if k.startswith("EVIDENCE_") or k == "NO_PROXY" or k == "no_proxy":
            monkeypatch.delenv(k, raising=False)


def test_defaults_to_build():
    ep = nb.endpoint_for("assistant")
    assert ep.base_url == nb.BASE_URL
    assert ep.model_id == nb.MODELS["assistant"]
    assert ep.is_build


def test_role_override_points_at_nim(monkeypatch):
    monkeypatch.setenv("EVIDENCE_ASSISTANT_BASE_URL", "http://rtx-3se-05-36:8000/v1/")
    monkeypatch.setenv("EVIDENCE_ASSISTANT_MODEL", "nvidia/nemotron-3.5-lightning")
    ep = nb.endpoint_for("assistant")
    assert ep.base_url == "http://rtx-3se-05-36:8000/v1"
    assert ep.model_id == "nvidia/nemotron-3.5-lightning"
    assert not ep.is_build
    # other roles untouched
    assert nb.endpoint_for("judge").is_build


def test_deprecated_model_refused_even_when_overridden(monkeypatch):
    monkeypatch.setenv("EVIDENCE_JUDGE_MODEL", "nvidia/nemotron-3-super-120b-a12b")
    with pytest.raises(ValueError, match="deprecated"):
        nb.endpoint_for("judge")


def test_unknown_role():
    with pytest.raises(KeyError):
        nb.endpoint_for("retriever")


def test_local_host_is_added_to_no_proxy(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1")
    nb._bypass_proxy("http://rtx-3se-05-36:8000/v1")
    assert os.environ["NO_PROXY"] == "localhost,127.0.0.1,rtx-3se-05-36"
    nb._bypass_proxy("http://rtx-3se-05-36:8000/v1")  # idempotent
    assert os.environ["NO_PROXY"].count("rtx-3se-05-36") == 1


def test_build_host_never_touches_proxy(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "localhost")
    nb._bypass_proxy(nb.BASE_URL)
    assert os.environ["NO_PROXY"] == "localhost"


class _FakeEmbeddings:
    def __init__(self):
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)

        class _D:
            embedding = [1.0, 0.0]

        class _R:
            data = [_D() for _ in kw["input"]]

        return _R()


def _embed_with(monkeypatch, **env):
    fake = _FakeEmbeddings()

    class _Client:
        embeddings = fake

    monkeypatch.setattr(nb, "_client", lambda ep: _Client())
    monkeypatch.setenv("EVIDENCE_EMBED_BASE_URL", "http://rtx-3se-06-04:8202/v1")
    monkeypatch.setenv("EVIDENCE_EMBED_MODEL", "nvidia/nemotron-3-embed-1b")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    nb.embed(["human oversight"], input_type="query")
    return fake.calls[0]


def test_an_embedding_nim_takes_the_role_as_a_parameter(monkeypatch):
    call = _embed_with(monkeypatch)
    assert call["input"] == ["human oversight"]
    assert call["extra_body"]["input_type"] == "query"


def test_a_raw_vllm_checkpoint_takes_the_role_as_a_prefix(monkeypatch):
    call = _embed_with(monkeypatch, EVIDENCE_EMBED_ROLE_STYLE="prefix")
    assert call["input"] == ["query: human oversight"] and "extra_body" not in call
