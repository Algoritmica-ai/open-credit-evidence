# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Jurisdiction overlay records — the facts that select a rule pack, and what it found.

A pack may carry a ``regulatory_context.json`` describing the lender and the
product the assistant serves. The engine evaluates the matching jurisdiction
rule pack (``regulations/<CC>/ruleset.json``) and writes the assessment into
the evidence pack, where it is covered by the checksums like everything else.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RegulatoryContext(BaseModel):
    """Facts used to select jurisdiction-specific rules."""

    model_config = ConfigDict(extra="forbid")

    jurisdiction: str = Field(..., min_length=2, max_length=2)
    product_type: str
    customer_type: str
    lender_type: str
    decision_mode: str
    uses_personal_data: bool = True
    uses_credit_database: bool = False
    uses_private_credit_bureau: bool = False
    uses_central_credit_register: bool = False
    adverse_decision: bool = False
    remote_onboarding: bool = False
    evidence: dict[str, Any] = Field(default_factory=dict)


class RuleFinding(BaseModel):
    """Outcome for one rule in a jurisdiction rule pack."""

    rule_id: str
    title: str
    status: str  # pass | fail | advisory | not_applicable
    obligation_owner: str
    missing_evidence: list[str] = Field(default_factory=list)
    evidence_checked: list[str] = Field(default_factory=list)
    evidence_references: dict[str, Any] = Field(default_factory=dict)
    reason: str


class RegulatoryAssessment(BaseModel):
    """Complete, versioned rule-pack assessment for one run."""

    jurisdiction: str | None
    ruleset_id: str | None
    ruleset_version: str | None
    ruleset_sha256: str | None
    context_sha256: str | None
    status: str  # pass | fail | unscoped | ruleset_not_found
    coverage_complete: bool
    total_rules: int = 0
    applicable_rules: int = 0
    passed_rules: int = 0
    failed_rules: int = 0
    advisory_rules: int = 0
    findings: list[RuleFinding] = Field(default_factory=list)
    note: str
