# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Load a pack from disk: items, manifest, obligations, optional regulatory context."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from evidence.contracts.item import BenchmarkItem
from evidence.contracts.regulatory import RegulatoryContext


@dataclass
class Pack:
    path: Path
    manifest: dict[str, Any]
    items: list[BenchmarkItem]
    obligations: dict[str, Any]
    regulatory_context: RegulatoryContext | None = None
    items_sha256: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def pack_id(self) -> str:
        return str(self.manifest.get("pack_id", self.path.name))

    @property
    def version(self) -> str:
        return str(self.manifest.get("version", "0"))

    def checks_declared(self) -> list[str]:
        names: list[str] = []
        for item in self.items:
            for c in item.deterministic_checks:
                if c not in names:
                    names.append(c)
        return names

    def judges_declared(self) -> list[str]:
        names: list[str] = []
        for item in self.items:
            for j in item.judges:
                if j not in names:
                    names.append(j)
        return names


def load_pack(path: str | Path) -> Pack:
    """Read a pack directory. Raises if items or manifest are missing or malformed."""
    root = Path(path)
    items_path = root / "items.jsonl"
    manifest_path = root / "manifest.json"
    if not items_path.is_file():
        raise FileNotFoundError(f"{items_path} not found")
    if not manifest_path.is_file():
        raise FileNotFoundError(f"{manifest_path} not found")

    raw = items_path.read_bytes()
    items = [
        BenchmarkItem.model_validate_json(line) for line in raw.decode("utf-8").splitlines() if line
    ]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    warnings: list[str] = []
    sha = hashlib.sha256(raw).hexdigest()
    if manifest.get("items_sha256") and manifest["items_sha256"] != sha:
        warnings.append("items.jsonl does not match manifest items_sha256")

    obligations: dict[str, Any] = {}
    obl_path = root / str(manifest.get("obligations_file", "obligations.yaml"))
    if obl_path.is_file():
        obligations = yaml.safe_load(obl_path.read_text(encoding="utf-8")) or {}

    context = None
    ctx_path = root / "regulatory_context.json"
    if ctx_path.is_file():
        context = RegulatoryContext.model_validate_json(ctx_path.read_text(encoding="utf-8"))

    return Pack(
        path=root,
        manifest=manifest,
        items=items,
        obligations=obligations,
        regulatory_context=context,
        items_sha256=sha,
        warnings=warnings,
    )
