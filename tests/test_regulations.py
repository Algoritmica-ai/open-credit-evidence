# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Jurisdiction rule packs: structure of the registries and behaviour of the checker."""

import json
import re
from pathlib import Path

import pytest

from evidence.contracts.regulatory import RegulatoryContext
from evidence.regulations import RulesetError, assess, load_ruleset

ROOT = Path(__file__).resolve().parents[1] / "regulations"
ID = re.compile(r"^[A-Z]{2}-[A-Z0-9]+(?:-[A-Z0-9]+)*$")


def test_registries_have_unique_ids_prefixed_by_country():
    seen: set[str] = set()
    paths = sorted(ROOT.glob("*/registry.json"))
    assert paths
    for path in paths:
        reg = json.loads(path.read_text(encoding="utf-8"))
        country = reg["jurisdiction"]["code"]
        assert path.parent.name == country
        for entry in reg["entries"]:
            assert ID.fullmatch(entry["id"]) and entry["id"].startswith(f"{country}-")
            assert entry["id"] not in seen
            seen.add(entry["id"])
            assert entry["status"] in {"in_force", "transition", "conditional", "deprecated"}
            assert entry["official_sources"]


def test_rulesets_load_and_fingerprint():
    for path in sorted(ROOT.glob("*/ruleset.json")):
        ruleset, sha = load_ruleset(path.parent.name)
        assert ruleset["jurisdiction"] == path.parent.name
        assert len(sha) == 64
        ids = [r["id"] for r in ruleset["rules"]]
        assert len(ids) == len(set(ids))


def test_example_context_passes_its_ruleset():
    ctx = RegulatoryContext.model_validate_json(
        (ROOT / "IT" / "case-context.example.json").read_text(encoding="utf-8")
    )
    a = assess(ctx)
    assert a.status == "pass" and a.coverage_complete
    assert a.failed_rules == 0 and a.applicable_rules > 0
    assert {f.status for f in a.findings} <= {"pass", "advisory", "not_applicable"}


def test_missing_evidence_fails_and_is_named():
    ctx = RegulatoryContext.model_validate_json(
        (ROOT / "IT" / "case-context.example.json").read_text(encoding="utf-8")
    )
    ctx.evidence.pop("creditworthiness_assessment")
    a = assess(ctx)
    assert a.status == "fail"
    failed = [f for f in a.findings if f.status == "fail"]
    assert failed and all("creditworthiness_assessment" in f.missing_evidence for f in failed)


def test_no_context_is_unscoped_and_unknown_jurisdiction_is_reported():
    assert assess(None).status == "unscoped"
    ctx = RegulatoryContext(
        jurisdiction="ZZ",
        product_type="consumer_credit",
        customer_type="consumer",
        lender_type="bank",
        decision_mode="assisted",
    )
    assert assess(ctx).status == "ruleset_not_found"


def test_malformed_ruleset_is_rejected(tmp_path):
    (tmp_path / "XX").mkdir()
    (tmp_path / "XX" / "ruleset.json").write_text(
        '{"ruleset_id": "x", "version": "1", "jurisdiction": "XX", "rules": []}'
    )
    with pytest.raises(RulesetError):
        load_ruleset("XX", tmp_path)
