# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""The readability judge — a model asked two things a formula cannot answer.

The judge is asked whether an underwriter could understand the briefing and
whether they could tell what would need to change. It is **not** asked whether
the briefing is complete or correct; the deterministic checks own that, and a
judge that also graded completeness would be a model marking a model.

Which model answers is a deployment decision (``EVIDENCE_JUDGE_BASE_URL`` /
``EVIDENCE_JUDGE_MODEL``): Nemotron 3 Ultra on NVIDIA Build, or a distilled
Nano served on-prem. The score record names the model and the endpoint.
"""

from __future__ import annotations

import json
import re
from typing import Any

from evidence.adapters.nvidia_build import chat
from evidence.contracts.item import BenchmarkItem

RUBRIC = (
    "You are grading an underwriter briefing for readability only. Answer with a JSON "
    'object {"intelligible": 0-2, "actionable": 0-2, "reason": "..."} and nothing else. '
    "intelligible: could an underwriter understand it without re-reading the file "
    "(0 no, 1 partly, 2 yes). "
    "actionable: can they tell what would need to change for a different outcome "
    "(0 no, 1 partly, 2 yes). "
    "Do not grade whether the briefing is complete or correct; that is checked elsewhere."
)
MAX_PER_FIELD = 2
# Thinking tokens count against max_tokens on a reasoning model; leave room.
JUDGE_MAX_TOKENS = 2500
_JSON = re.compile(r"\{.*?\}", re.S)
_FIELDS = re.compile(r'"intelligible"\s*:\s*(\d)\D+"actionable"\s*:\s*(\d)', re.S)


def parse_scores(text: str) -> dict[str, Any] | None:
    """First JSON object in the reply with the two integer fields, else None."""
    for m in _JSON.finditer(text):
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
        if {"intelligible", "actionable"} <= obj.keys():
            try:
                obj["intelligible"] = int(obj["intelligible"])
                obj["actionable"] = int(obj["actionable"])
            except (TypeError, ValueError):
                continue
            return obj
    # A truncated reply may still carry both scores before the cut.
    m = _FIELDS.search(text)
    if m:
        return {
            "intelligible": int(m.group(1)),
            "actionable": int(m.group(2)),
            "reason": "(reply truncated; scores recovered)",
        }
    return None


def judge_readability(
    *, output: str, item: BenchmarkItem, max_tokens: int = JUDGE_MAX_TOKENS
) -> dict[str, Any]:
    """One judge call, returned in the same record shape as a check score."""
    r = chat("judge", system=RUBRIC, user=f"BRIEFING:\n{output}", max_tokens=max_tokens)
    scores = parse_scores(r.text)
    base: dict[str, Any] = {
        "judge": f"model:{r.model_id}",
        "judge_trace_id": r.raw_id,
        "endpoint": r.endpoint,
        "prompt_version": r.prompt_version,
        "latency_ms": r.latency_ms,
        "needs_audit": True,  # a model opinion is always auditable
    }
    if scores is None:
        return base | {
            "value": None,
            "passed": None,
            "detail": "judge reply was not parseable JSON",
            "evidence": [{"raw": r.text[:500]}],
        }
    total = scores["intelligible"] + scores["actionable"]
    return (
        base
        | {
            "value": round(total / (2 * MAX_PER_FIELD), 3),
            "passed": None,  # readability is reported, not gated
            "detail": str(scores.get("reason", ""))[:400],
            "evidence": [
                {"intelligible": scores["intelligible"], "actionable": scores["actionable"]}
            ],
        }
    )
