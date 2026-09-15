"""Jurisdiction ruleset loading and deterministic evidence checks."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from open_credit_evidence.loader import compute_fingerprint
from open_credit_evidence.schemas import (
    Case,
    RegulatoryAssessment,
    RegulatoryContext,
    RegulatoryRuleFinding,
)


class RulesetError(Exception):
    """Raised when a jurisdiction ruleset is missing or malformed."""


def default_rules_root() -> Path:
    """Resolve the repository rules directory, with an install-time override."""
    configured = os.getenv("OCE_RULESETS_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "regulations"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def load_ruleset(
    jurisdiction: str,
    rules_root: Path | None = None,
) -> tuple[dict[str, Any], str]:
    """Load and fingerprint one jurisdiction ruleset."""
    root = rules_root or default_rules_root()
    path = root / jurisdiction.upper() / "ruleset.json"
    if not path.is_file():
        raise RulesetError(f"No ruleset found for jurisdiction {jurisdiction.upper()}: {path}")
    try:
        ruleset: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RulesetError(f"Cannot load ruleset {path}: {exc}") from exc

    required = {"ruleset_id", "version", "jurisdiction", "rules"}
    missing = sorted(required - ruleset.keys())
    if missing:
        raise RulesetError(f"Ruleset {path} is missing fields: {', '.join(missing)}")
    if ruleset["jurisdiction"] != jurisdiction.upper():
        raise RulesetError(
            f"Ruleset jurisdiction {ruleset['jurisdiction']!r} does not match "
            f"{jurisdiction.upper()!r}"
        )
    rules = ruleset["rules"]
    if not isinstance(rules, list) or not rules:
        raise RulesetError(f"Ruleset {path} must contain at least one rule")
    ids = [str(rule.get("id", "")) for rule in rules if isinstance(rule, dict)]
    if len(ids) != len(rules) or any(not rule_id for rule_id in ids):
        raise RulesetError(f"Every rule in {path} must have an ID")
    if len(ids) != len(set(ids)):
        raise RulesetError(f"Rule IDs in {path} must be unique")

    return ruleset, compute_fingerprint(_canonical_json(ruleset))


def _is_applicable(rule: dict[str, Any], context: RegulatoryContext) -> bool:
    values = context.model_dump(mode="json")
    applicability = rule.get("applicability", {})
    if not isinstance(applicability, dict):
        raise RulesetError(f"Rule {rule.get('id')} has invalid applicability")
    for field, expected in applicability.items():
        actual = values.get(field)
        if isinstance(expected, list):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def _has_evidence(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _evaluate_rule(
    rule: dict[str, Any],
    context: RegulatoryContext,
) -> RegulatoryRuleFinding:
    rule_id = str(rule["id"])
    title = str(rule.get("title", rule_id))
    owner = str(rule.get("obligation_owner", "lender"))
    if not _is_applicable(rule, context):
        return RegulatoryRuleFinding(
            rule_id=rule_id,
            title=title,
            status="not_applicable",
            obligation_owner=owner,
            reason="Case facts do not meet this rule's applicability conditions",
        )

    requirements = rule.get("evidence_requirements", [])
    if not isinstance(requirements, list):
        raise RulesetError(f"Rule {rule_id} has invalid evidence_requirements")
    evidence_keys = [str(requirement["key"]) for requirement in requirements]
    missing = [key for key in evidence_keys if not _has_evidence(context.evidence.get(key))]
    references = {
        key: context.evidence[key]
        for key in evidence_keys
        if _has_evidence(context.evidence.get(key))
    }

    enforcement = str(rule.get("enforcement", "required"))
    if enforcement != "required":
        return RegulatoryRuleFinding(
            rule_id=rule_id,
            title=title,
            status="advisory",
            obligation_owner=owner,
            missing_evidence=missing,
            evidence_checked=evidence_keys,
            evidence_references=references,
            reason=str(rule.get("transition_note", "Tracked as a non-blocking reference")),
        )
    if missing:
        return RegulatoryRuleFinding(
            rule_id=rule_id,
            title=title,
            status="fail",
            obligation_owner=owner,
            missing_evidence=missing,
            evidence_checked=evidence_keys,
            evidence_references=references,
            reason="Required evidence is missing",
        )
    return RegulatoryRuleFinding(
        rule_id=rule_id,
        title=title,
        status="pass",
        obligation_owner=owner,
        evidence_checked=evidence_keys,
        evidence_references=references,
        reason="All required evidence references are present",
    )


def evaluate_case_regulations(
    case: Case,
    rules_root: Path | None = None,
) -> RegulatoryAssessment:
    """Evaluate every rule in the selected jurisdiction ruleset for one case."""
    context = case.metadata.regulatory_context
    if context is None:
        return RegulatoryAssessment(
            case_id=case.metadata.case_id,
            jurisdiction=None,
            ruleset_id=None,
            ruleset_version=None,
            ruleset_fingerprint=None,
            context_fingerprint=None,
            status="unscoped",
            coverage_complete=False,
            note=(
                "No regulatory_context was supplied. The case was checked, but no "
                "jurisdiction ruleset could be selected."
            ),
        )

    jurisdiction = context.jurisdiction.upper()
    context_fingerprint = compute_fingerprint(_canonical_json(context.model_dump(mode="json")))
    try:
        ruleset, fingerprint = load_ruleset(jurisdiction, rules_root)
    except RulesetError as exc:
        return RegulatoryAssessment(
            case_id=case.metadata.case_id,
            jurisdiction=jurisdiction,
            ruleset_id=None,
            ruleset_version=None,
            ruleset_fingerprint=None,
            context_fingerprint=context_fingerprint,
            status="ruleset_not_found",
            coverage_complete=False,
            note=str(exc),
        )

    findings = [_evaluate_rule(rule, context) for rule in ruleset["rules"]]
    failed = sum(finding.status == "fail" for finding in findings)
    passed = sum(finding.status == "pass" for finding in findings)
    advisory = sum(finding.status == "advisory" for finding in findings)
    applicable = sum(finding.status != "not_applicable" for finding in findings)
    evaluated_ids = [finding.rule_id for finding in findings]
    total_rules = len(ruleset["rules"])
    coverage_complete = len(evaluated_ids) == total_rules

    return RegulatoryAssessment(
        case_id=case.metadata.case_id,
        jurisdiction=jurisdiction,
        ruleset_id=str(ruleset["ruleset_id"]),
        ruleset_version=str(ruleset["version"]),
        ruleset_fingerprint=fingerprint,
        context_fingerprint=context_fingerprint,
        status="fail" if failed else "pass",
        coverage_complete=coverage_complete,
        total_rules=total_rules,
        applicable_rules=applicable,
        passed_rules=passed,
        failed_rules=failed,
        advisory_rules=advisory,
        evaluated_rule_ids=evaluated_ids,
        findings=findings,
        checked_at=datetime.now(UTC),
        note=(
            "Evidence-presence assessment only; legal applicability and substantive "
            "compliance require lender and legal review."
        ),
    )
