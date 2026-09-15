"""FINOS AI Steel Thread compliance-evidence adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from open_credit_evidence.schemas import PlatformControlEvidence

STEEL_THREAD_REPOSITORY = "https://github.com/finos-hack/ai-steel-thread-demo"
STEEL_THREAD_REVISION = "2782173d47f5074f8767dbdf553fa9165ee1ccd8"
REQUIRED_CONTROLS = ("mi-1", "mi-4", "mi-5", "mi-11")


class PlatformEvidenceError(Exception):
    """Raised when Steel Thread evidence cannot be loaded or understood."""


def _as_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PlatformEvidenceError(f"Steel Thread field {field!r} must be an object")
    return value


def _open_credit_link(payload: dict[str, Any]) -> dict[str, Any] | None:
    direct = payload.get("openCreditEvidence")
    if isinstance(direct, dict):
        return direct
    extensions = payload.get("extensions")
    if isinstance(extensions, dict):
        nested = extensions.get("openCreditEvidence")
        if isinstance(nested, dict):
            return nested
    return None


def normalize_steel_thread_report(
    payload: dict[str, Any],
    case_id: str,
    *,
    source_revision: str = STEEL_THREAD_REVISION,
) -> PlatformControlEvidence:
    """Normalize a per-instance Steel Thread compliance report.

    A report is only marked ``verified`` when its frozen control posture is complete,
    its checks contain no warnings/failures, and it carries an explicit OpenCredit
    link for the same case. A normal unextended demo report is therefore ``linked``.
    """
    controls_payload = _as_mapping(payload.get("controls"), "controls")
    control_keys = {
        "mi-1": "mi1Enabled",
        "mi-4": "mi4Enabled",
        "mi-5": "mi5Enabled",
        "mi-11": "mi11Enabled",
    }
    controls = {
        control_id: bool(controls_payload.get(payload_key))
        for control_id, payload_key in control_keys.items()
    }
    issues: list[str] = []
    business_key = payload.get("businessKey")
    if business_key != case_id:
        issues.append(
            f"Steel Thread businessKey {business_key!r} does not match case_id {case_id!r}"
        )
    instance_snapshot = bool(controls_payload.get("instanceSnapshot"))
    if not instance_snapshot:
        issues.append("Control posture is live fallback, not an instance-start snapshot")
    disabled = [control_id for control_id in REQUIRED_CONTROLS if not controls[control_id]]
    if disabled:
        issues.append(f"Required controls are not enabled: {', '.join(disabled)}")

    raw_checks = payload.get("checks", [])
    if not isinstance(raw_checks, list):
        raise PlatformEvidenceError("Steel Thread field 'checks' must be an array")
    check_statuses: dict[str, str] = {}
    for raw_check in raw_checks:
        if not isinstance(raw_check, dict):
            continue
        check_id = str(raw_check.get("id", ""))
        if check_id:
            check_statuses[check_id] = str(raw_check.get("status", "unknown")).lower()
    non_passing = sorted(
        check_id
        for check_id, status in check_statuses.items()
        if status in {"fail", "warn", "unknown"}
    )
    if non_passing:
        issues.append(f"Platform checks are not passing: {', '.join(non_passing)}")

    overall_status = payload.get("overallStatus")
    if str(overall_status).upper() != "PASS":
        issues.append(f"Platform overallStatus is {overall_status!r}, not 'PASS'")

    raw_calls = payload.get("llmCalls", [])
    if not isinstance(raw_calls, list):
        raise PlatformEvidenceError("Steel Thread field 'llmCalls' must be an array")
    total_tokens = 0
    estimated_cost = 0.0
    for raw_call in raw_calls:
        if not isinstance(raw_call, dict):
            continue
        token_value = raw_call.get("totalTokens")
        cost_value = raw_call.get("estimatedCostUsd")
        if isinstance(token_value, int):
            total_tokens += token_value
        if isinstance(cost_value, (int, float)):
            estimated_cost += float(cost_value)
    if not raw_calls:
        issues.append("No LLM call evidence is attached for mi-4/token accounting")
    elif any(
        not isinstance(raw_call, dict) or not isinstance(raw_call.get("totalTokens"), int)
        for raw_call in raw_calls
    ):
        issues.append("At least one LLM call lacks totalTokens evidence")

    sat_payload = payload.get("sat")
    sat_accepted: bool | None = None
    if isinstance(sat_payload, dict):
        value = sat_payload.get("lastAccepted")
        if isinstance(value, bool):
            sat_accepted = value
    if controls["mi-5"] and sat_accepted is not True:
        issues.append("No accepted mi-5 system-acceptance snapshot is attached")

    link = _open_credit_link(payload)
    if link is None:
        issues.append("No explicit OpenCredit activity/report link is attached")
    elif link.get("caseId") != case_id:
        issues.append("OpenCredit link does not identify the same case")
    elif not link.get("activityId") or not link.get("evidenceReportId"):
        issues.append("OpenCredit link lacks activityId or evidenceReportId")

    process_instance_id = payload.get("processInstanceId")
    if not isinstance(process_instance_id, str) or not process_instance_id:
        raise PlatformEvidenceError("Steel Thread report lacks processInstanceId")

    return PlatformControlEvidence(
        source_repository=STEEL_THREAD_REPOSITORY,
        source_revision=source_revision,
        process_instance_id=process_instance_id,
        business_key=str(business_key) if business_key is not None else None,
        generated_at=(
            str(payload["generatedAt"]) if payload.get("generatedAt") is not None else None
        ),
        overall_status=(
            str(overall_status) if overall_status is not None else None
        ),
        claim_status="verified" if not issues else "linked",
        controls=controls,
        instance_snapshot=instance_snapshot,
        control_posture_captured_at=(
            str(controls_payload["snapshottedAt"])
            if controls_payload.get("snapshottedAt") is not None
            else None
        ),
        check_statuses=check_statuses,
        llm_call_count=len(raw_calls),
        total_tokens=total_tokens,
        estimated_cost_usd=round(estimated_cost, 8),
        sat_accepted=sat_accepted,
        issues=issues,
    )


def load_steel_thread_report(
    report_path: Path,
    case_id: str,
) -> PlatformControlEvidence:
    """Load a previously exported Steel Thread compliance report."""
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlatformEvidenceError(f"Cannot load platform report {report_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PlatformEvidenceError("Steel Thread report must contain a JSON object")
    return normalize_steel_thread_report(payload, case_id)


def fetch_steel_thread_report(
    base_url: str,
    process_instance_id: str,
    case_id: str,
    *,
    timeout: float = 20.0,
) -> PlatformControlEvidence:
    """Fetch the demo's per-instance compliance report endpoint."""
    url = (
        f"{base_url.rstrip('/')}/api/demo/loan-approval/instances/"
        f"{process_instance_id}/compliance-report"
    )
    try:
        response = httpx.get(url, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise PlatformEvidenceError(f"Cannot fetch Steel Thread evidence from {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PlatformEvidenceError("Steel Thread endpoint returned a non-object payload")
    return normalize_steel_thread_report(payload, case_id)
