# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Which model, exactly, answered: a fingerprint per role for the evidence.

A model's name is a label. ``nano-judge`` is our alias; the same name can serve
different weights after a restart, and a moving container tag can change the
serving stack under it. The fingerprint names what actually ran, from two
sources:

- **the server**, asked over HTTP at run time: its serving version and, for a
  NIM, the model build, the active profile and the checksum of every file in
  that profile (``/v1/metadata``, ``/v1/manifest``)
- **the node**, recorded by ``scripts/cluster/fingerprint_models.py`` in
  ``models.json`` (``EVIDENCE_MODELS_FILE``, default ``./models.json``): the
  container image digest, the serving arguments that change output, and for a
  vLLM server the Hugging Face commit and SHA-256 of every weights file

The components are hashed into one SHA-256 per role. Where it ran (host, port)
and what we call it are recorded but left out of the hash: a model moved to
another node, or renamed, is the same model.

``level`` says how much the fingerprint pins: ``weights`` (file hashes of what
was loaded), ``server`` (what the server reports about itself, no file hashes),
or ``name`` (a hosted endpoint, where only the model name is visible).
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from evidence.adapters.nvidia_build import endpoint_for

TIMEOUT = 8


def _get(url: str) -> Any:
    """GET JSON from a self-hosted server, never through a proxy."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _models_file() -> dict[str, Any]:
    path = Path(os.environ.get("EVIDENCE_MODELS_FILE") or "models.json")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _node_facts(address: str) -> dict[str, Any] | None:
    """The models.json entry for the server at host:port, if the node published one."""
    doc = _models_file()
    for server in (doc.get("servers") or {}).values():
        if server.get("address") == address:
            return server | {"recorded_at": doc.get("written_at"), "node": doc.get("node")}
    return None


def _nim_profile_files(manifest: dict[str, Any] | None, profile_id: str | None) -> dict[str, str]:
    """The checksum of every file in the NIM's active profile, from its manifest."""
    if not manifest or not profile_id:
        return {}
    try:
        doc = yaml.safe_load(manifest.get("manifest_file", "")) or {}
    except yaml.YAMLError:
        return {}
    for p in doc.get("profiles") or []:
        if p.get("id") == profile_id:
            files = ((p.get("workspace") or {}).get("files")) or {}
            return {name: str(f.get("checksum")) for name, f in sorted(files.items())
                    if isinstance(f, dict)}
    return {}


def _hash(components: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(components, sort_keys=True).encode("utf-8")).hexdigest()


def model_fingerprint(role: str) -> dict[str, Any]:
    """The fingerprint of the model serving ``role`` right now."""
    ep = endpoint_for(role)
    if ep.is_build:
        components = {"served_model": ep.model_id, "provider": "NVIDIA Build"}
        return {"role": role, "level": "name", "served_as": ep.model_id, "endpoint": ep.base_url,
                "components": components, "fingerprint": _hash(components),
                "note": "hosted endpoint: only the model name is visible"}

    base = ep.base_url
    root = base.removesuffix("/v1")
    served = _get(f"{base}/models") or {}
    entry = next((m for m in served.get("data", []) if m.get("id") == ep.model_id),
                 (served.get("data") or [{}])[0])
    server: dict[str, Any] = {
        "engine_version": (_get(f"{root}/version") or {}).get("version"),
        "max_model_len": entry.get("max_model_len"),
    }
    weights: dict[str, Any] = {}
    meta = _get(f"{base}/metadata")
    if meta:  # a NIM describes its own build and profile
        server |= {"nim_release": meta.get("version"),
                   "model_build": [m.get("modelUrl") for m in meta.get("modelInfo", [])],
                   "profile_id": meta.get("profile_id"),
                   "profile_name": meta.get("profile_name")}
        files = _nim_profile_files(_get(f"{base}/manifest"), meta.get("profile_id"))
        if files:
            weights = {"source": "NIM manifest, active profile", "files": files}

    host = urlparse(base).netloc
    node = _node_facts(host)
    container: dict[str, Any] = {}
    if node:
        container = {"image": node.get("image"), "image_id": node.get("image_id"),
                     "repo_digests": node.get("repo_digests"), "args": {
                         k: v for k, v in (node.get("args") or {}).items()
                         if k != "--served-model-name"}}
        w = node.get("weights") or {}
        if w.get("files") and not weights:
            weights = {"source": "Hugging Face download on the node",
                       "hf_commit": w.get("hf_commit"), "files": w.get("files")}

    components = {"server": server, "weights": weights, "container": container}
    level = "weights" if weights.get("files") else "server"
    return {"role": role, "level": level, "served_as": ep.model_id, "endpoint": base,
            "node": (node or {}).get("node"), "node_recorded_at": (node or {}).get("recorded_at"),
            "components": components, "fingerprint": _hash(components),
            "note": None if node else "no models.json entry for this server: container and "
                                      "node-side weights not recorded"}


def summary(fp: dict[str, Any] | None) -> str:
    """One line for a report: what the fingerprint pins."""
    if not fp:
        return "not recorded"
    c = fp.get("components") or {}
    s, w, k = c.get("server") or {}, c.get("weights") or {}, c.get("container") or {}
    parts = []
    if s.get("nim_release"):
        parts.append(f"NIM {s['nim_release']}")
    if s.get("model_build"):
        parts.append("build " + ", ".join(b.rsplit(":", 1)[-1] for b in s["model_build"] if b))
    if s.get("profile_name"):
        parts.append(f"profile {s['profile_name']}")
    if w.get("hf_commit"):
        parts.append(f"HF commit {str(w['hf_commit'])[:10]}")
    if w.get("files"):
        parts.append(f"{len(w['files'])} weight files hashed")
    if s.get("engine_version"):
        parts.append(f"engine {s['engine_version']}")
    if k.get("image_id"):
        parts.append(f"image {k['image_id'][:19]}…")
    return f"`{fp['fingerprint'][:16]}…` ({fp['level']}): " + ("; ".join(parts) or fp.get("note")
                                                                  or "")
