# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Turn results.jsonl into the numbers the evidence pack reports.

Per check: how many (item, repeat) results passed, failed, and needed audit.
Per item: whether its verdict was the same across repeats — the reproducibility
figure. Per obligation: the checks that evidence it, taken from the pack's
``obligations.yaml`` grid, restricted to checks that actually ran.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any


def _by_check(results: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in results:
        out[r["check"]].append(r)
    return out


def summarise_checks(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for name, rows in _by_check(results).items():
        gated = [r for r in rows if r.get("passed") is not None]
        values = [r["value"] for r in rows if isinstance(r.get("value"), (int, float))]
        items = sorted({r["item_id"] for r in rows})
        failing = sorted({r["item_id"] for r in gated if not r["passed"]})
        summary[name] = {
            "results": len(rows),
            "items": len(items),
            "passed": sum(1 for r in gated if r["passed"]),
            "failed": sum(1 for r in gated if not r["passed"]),
            "needs_audit": sum(1 for r in rows if r.get("needs_audit")),
            "mean_value": round(mean(values), 3) if values else None,
            "failing_items": failing,
            "gated": bool(gated),
        }
    return summary


def repeat_agreement(results: list[dict[str, Any]]) -> dict[str, Any]:
    """For each check, the share of items whose pass/fail verdict was identical across repeats."""
    per_check: dict[str, Any] = {}
    for name, rows in _by_check(results).items():
        verdicts: dict[str, set[bool]] = defaultdict(set)
        for r in rows:
            if r.get("passed") is not None:
                verdicts[r["item_id"]].add(bool(r["passed"]))
        if not verdicts:
            continue
        stable = sum(1 for v in verdicts.values() if len(v) == 1)
        per_check[name] = {
            "items": len(verdicts),
            "stable": stable,
            "agreement": round(stable / len(verdicts), 3),
            "flipping_items": sorted(k for k, v in verdicts.items() if len(v) > 1),
        }
    return per_check


def items_failing_any(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per (item, check) that failed in at least one repeat, with the detail."""
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for r in results:
        if r.get("passed") is False:
            key = (r["item_id"], r["check"])
            rows.setdefault(
                key,
                {
                    "item_id": r["item_id"],
                    "check": r["check"],
                    "repeats_failed": 0,
                    "detail": r["detail"],
                },
            )
            rows[key]["repeats_failed"] += 1
    return sorted(rows.values(), key=lambda x: (x["check"], x["item_id"]))


def by_obligation(
    obligations: dict[str, Any], check_summary: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Attach ran checks to each obligation in the pack's grid, in the pack's order."""
    out: list[dict[str, Any]] = []
    for ob in obligations.get("obligations", []):
        grid = [c for c in ob.get("grid", []) if c in check_summary]
        not_run = [c for c in ob.get("grid", []) if c not in check_summary]
        out.append(
            {
                "id": ob["id"],
                "title": ob.get("title", ob["id"]),
                "level": ob.get("level"),
                "reason": ob.get("reason"),
                "checks": grid,
                "not_run": not_run,
            }
        )
    return out
