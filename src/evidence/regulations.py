# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Jurisdiction rule packs: load, fingerprint, and check evidence presence.

Rule packs live under ``regulations/<CC>/ruleset.json`` and are written by the
regulatory workstream, not the engine. A rule is *applicable* when the pack's
regulatory context matches its applicability conditions; an applicable rule
*passes* when every evidence key it requires is populated in the context.

This is an evidence-presence check. It does not determine legal applicability,
interpret law, or certify compliance; the evidence pack says so.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from evidence.contracts.regulatory import RegulatoryAssessment, RegulatoryContext, RuleFinding


class RulesetError(Exception):
    """A jurisdiction rule pack is missing or malformed."""


def default_rules_root() -> Path:
    configured = os.getenv("EVIDENCE_RULESETS_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "regulations"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_ruleset(jurisdiction: str, rules_root: Path | None = None) -> tuple[dict[str, Any], str]:
    """Load one rule pack and return it with the sha256 of its canonical form."""
    root = rules_root or default_rules_root()
    path = root / jurisdiction.upper() / "ruleset.json"
    if not path.is_file():
        raise RulesetError(f"no ruleset for jurisdiction {jurisdiction.upper()}: {path}")
    try:
        ruleset: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RulesetError(f"cannot load ruleset {path}: {exc}") from exc

    missing = sorted({"ruleset_id", "version", "jurisdiction", "rules"} - ruleset.keys())
    if missing:
        raise RulesetError(f"ruleset {path} is missing fields: {', '.join(missing)}")
    if ruleset["jurisdiction"] != jurisdiction.upper():
        raise RulesetError(
            f"ruleset jurisdiction {ruleset['jurisdiction']!r} != {jurisdiction.upper()!r}"
        )
    rules = ruleset["rules"]
    if not isinstance(rules, list) or not rules:
        raise RulesetError(f"ruleset {path} must contain at least one rule")
    ids = [str(r.get("id", "")) for r in rules if isinstance(r, dict)]
    if len(ids) != len(rules) or not all(ids):
        raise RulesetError(f"every rule in {path} must have an id")
    if len(ids) != len(set(ids)):
        raise RulesetError(f"rule ids in {path} must be unique")
    return ruleset, _sha256(_canonical(ruleset))


def _applicable(rule: dict[str, Any], context: RegulatoryContext) -> bool:
    values = context.model_dump(mode="json")
    conditions = rule.get("applicability", {})
    if not isinstance(conditions, dict):
        raise RulesetError(f"rule {rule.get('id')} has invalid applicability")
    for field, expected in conditions.items():
        actual = values.get(field)
        if isinstance(expected, list):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def _present(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _evaluate(rule: dict[str, Any], context: RegulatoryContext) -> RuleFinding:
    rule_id = str(rule["id"])
    title = str(rule.get("title", rule_id))
    owner = str(rule.get("obligation_owner", "lender"))
    if not _applicable(rule, context):
        return RuleFinding(
            rule_id=rule_id,
            title=title,
            status="not_applicable",
            obligation_owner=owner,
            reason="case facts do not meet this rule's applicability conditions",
        )
    requirements = rule.get("evidence_requirements", [])
    if not isinstance(requirements, list):
        raise RulesetError(f"rule {rule_id} has invalid evidence_requirements")
    keys = [str(r["key"]) for r in requirements]
    missing = [k for k in keys if not _present(context.evidence.get(k))]
    refs = {k: context.evidence[k] for k in keys if _present(context.evidence.get(k))}
    common = dict(
        rule_id=rule_id,
        title=title,
        obligation_owner=owner,
        missing_evidence=missing,
        evidence_checked=keys,
        evidence_references=refs,
    )
    if str(rule.get("enforcement", "required")) != "required":
        return RuleFinding(
            status="advisory",
            reason=str(rule.get("transition_note", "tracked as a non-blocking reference")),
            **common,
        )
    if missing:
        return RuleFinding(status="fail", reason="required evidence is missing", **common)
    return RuleFinding(
        status="pass", reason="all required evidence references are present", **common
    )


def assess(
    context: RegulatoryContext | None, rules_root: Path | None = None
) -> RegulatoryAssessment:
    """Evaluate every rule in the jurisdiction pack selected by ``context``."""
    note_scope = (
        "evidence-presence assessment only; legal applicability and substantive "
        "compliance require lender and legal review"
    )
    if context is None:
        return RegulatoryAssessment(
            jurisdiction=None,
            ruleset_id=None,
            ruleset_version=None,
            ruleset_sha256=None,
            context_sha256=None,
            status="unscoped",
            coverage_complete=False,
            note="no regulatory_context supplied; no jurisdiction rule pack was selected",
        )
    jurisdiction = context.jurisdiction.upper()
    context_sha = _sha256(_canonical(context.model_dump(mode="json")))
    try:
        ruleset, ruleset_sha = load_ruleset(jurisdiction, rules_root)
    except RulesetError as exc:
        return RegulatoryAssessment(
            jurisdiction=jurisdiction,
            ruleset_id=None,
            ruleset_version=None,
            ruleset_sha256=None,
            context_sha256=context_sha,
            status="ruleset_not_found",
            coverage_complete=False,
            note=str(exc),
        )
    findings = [_evaluate(rule, context) for rule in ruleset["rules"]]
    count = lambda s: sum(f.status == s for f in findings)  # noqa: E731
    return RegulatoryAssessment(
        jurisdiction=jurisdiction,
        ruleset_id=str(ruleset["ruleset_id"]),
        ruleset_version=str(ruleset["version"]),
        ruleset_sha256=ruleset_sha,
        context_sha256=context_sha,
        status="fail" if count("fail") else "pass",
        coverage_complete=len(findings) == len(ruleset["rules"]),
        total_rules=len(ruleset["rules"]),
        applicable_rules=sum(f.status != "not_applicable" for f in findings),
        passed_rules=count("pass"),
        failed_rules=count("fail"),
        advisory_rules=count("advisory"),
        findings=findings,
        note=note_scope,
    )
