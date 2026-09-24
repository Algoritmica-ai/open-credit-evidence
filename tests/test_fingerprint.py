# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Which model, exactly, answered — pinned from the server and the node, and kept honest."""

import json

import pytest

from evidence import fingerprint as fpm
from evidence.evidence.assess import DEFAULT_THRESHOLDS, decide

MANIFEST = """profiles:
- id: other
  workspace: {files: {a.safetensors: {checksum: 'blake3:111'}}}
- id: active
  workspace: {files: {b.safetensors: {checksum: 'blake3:222'}, c.json: {checksum: 'blake3:333'}}}
"""


def _server(nim: bool):
    def get(url):
        if url.endswith("/v1/models"):
            return {"data": [{"id": "m", "max_model_len": 8192}]}
        if url.endswith("/version"):
            return {"version": "0.29.1"}
        if nim and url.endswith("/v1/metadata"):
            return {"version": "2.0.9", "modelInfo": [{"modelUrl": "ngc://nim/x:hf-abc"}],
                    "profile_id": "active", "profile_name": "vllm-int4-tp1"}
        if nim and url.endswith("/v1/manifest"):
            return {"manifest_file": MANIFEST}
        return None
    return get


@pytest.fixture
def on_prem(monkeypatch, tmp_path):
    def setup(nim, address="10.0.0.5:8201", node=True):
        monkeypatch.setenv("EVIDENCE_JUDGE_BASE_URL", f"http://{address}/v1")
        monkeypatch.setenv("EVIDENCE_JUDGE_MODEL", "m")
        monkeypatch.setattr(fpm, "_get", _server(nim))
        doc = {"written_at": "t", "node": "n", "servers": {"judge": {
            "address": address, "image": "vllm:nightly", "image_id": "sha256:img",
            "repo_digests": ["vllm@sha256:img"], "args": {"--dtype": "bfloat16",
                                                          "--served-model-name": "m"},
            "weights": {"hf_commit": "6533e8de", "files": {"w.safetensors": "fca4"}}}}}
        path = tmp_path / "models.json"
        path.write_text(json.dumps(doc) if node else "{}")
        monkeypatch.setenv("EVIDENCE_MODELS_FILE", str(path))
        return fpm.model_fingerprint("judge")
    return setup


def test_vllm_is_pinned_by_the_weights_the_node_hashed(on_prem):
    fp = on_prem(nim=False)
    assert fp["level"] == "weights"
    assert fp["components"]["weights"]["hf_commit"] == "6533e8de"
    assert fp["components"]["container"]["image_id"] == "sha256:img"
    assert "--served-model-name" not in fp["components"]["container"]["args"]


def test_a_nim_is_pinned_by_its_active_profile(on_prem):
    fp = on_prem(nim=True)
    files = fp["components"]["weights"]["files"]
    assert files == {"b.safetensors": "blake3:222", "c.json": "blake3:333"}
    assert fp["components"]["server"]["profile_name"] == "vllm-int4-tp1"


def test_the_same_model_elsewhere_has_the_same_fingerprint(on_prem, monkeypatch, tmp_path):
    a = on_prem(nim=False, address="10.0.0.5:8201")["fingerprint"]
    b = on_prem(nim=False, address="10.0.0.9:8301")["fingerprint"]
    assert a == b


def test_without_the_node_file_it_says_so(on_prem):
    fp = on_prem(nim=False, node=False)
    assert fp["level"] == "server" and "models.json" in fp["note"]


def test_a_hosted_model_is_pinned_by_name_only(monkeypatch):
    monkeypatch.delenv("EVIDENCE_ASSISTANT_BASE_URL", raising=False)
    monkeypatch.setenv("EVIDENCE_ASSISTANT_BASE_URL", "https://integrate.api.nvidia.com/v1")
    fp = fpm.model_fingerprint("assistant")
    assert fp["level"] == "name" and "only the model name" in fp["note"]


def test_a_model_that_changed_during_the_run_cannot_support_a_decision():
    checks = {n: {"passed": 60, "failed": 0, "gated": True} for n in DEFAULT_THRESHOLDS["checks"]}
    summary = {"checks": checks, "repeat_agreement": {}}
    ok = decide(summary, {"causes": []}, DEFAULT_THRESHOLDS, {}, {"assistant": {}})
    assert ok["verdict"] == "GO"
    changed = decide(summary, {"causes": []}, DEFAULT_THRESHOLDS, {},
                     {"assistant": {"changed_during_run": True}})
    assert changed["verdict"] == "INCONCLUSIVE"
    assert any("assistant model changed" in c for c in changed["conditions"])
