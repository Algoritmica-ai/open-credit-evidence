# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Did a change help? Two runs of the same pack, compared case by case.

    evidence compare runs/before runs/after

The bank changes something it controls — the assistant's instructions, what it
is handed, the model version it chose — and runs the pack again. This says
whether that helped, per check, without pooling away the pairing:

- For each case, the share of repeats that passed, before and after. The change
  *helped* the case if that went up, *hurt* it if it went down.
- The mean change across cases gets a 95% interval from the spread of per-case
  changes, so a gain smaller than the assistant's own run-to-run wobble is not
  mistaken for an improvement.

**The rule** (``change_acceptance`` in the *after* run's ``evidence/thresholds.yaml``,
owned by the bank). Per check:

- *improved* — up by at least ``min_gain``, whole interval above zero
- *regressed* — down by more than ``max_regression``, whole interval below zero
- *possibly worse* — down by more than ``max_regression``, but the interval
  reaches zero: it could be run-to-run noise, and it could be real
- otherwise *no clear change*

Verdict: REJECT if any check regressed; INCONCLUSIVE if any is possibly worse
(run more repeats to settle it); ACCEPT if at least one improved; else NO EFFECT.

What changed between the runs is read from the two manifests — model, endpoint,
prompt version, parameters, repeats, engine commit — so the comparison names
the lever it is evidence for. Pure: the same two runs always give the same answer.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from evidence.evidence.assess import CAUSES, DEFAULT_THRESHOLDS, diagnose

WATCHED = [
    ("assistant model", ("sut", "model_id")),
    ("assistant endpoint", ("sut", "endpoint")),
    ("assistant prompt version", ("sut", "prompt_version")),
    ("assistant parameters", ("sut", "params")),
    ("judge model", ("judge", "model_id")),
    ("repeats", ("repeats",)),
    ("pack", ("pack", "items_sha256")),
    ("engine commit", ("engine", "git_commit")),
]


def _get(d: Any, path: tuple[str, ...]) -> Any:
    for k in path:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _results(run: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in (run / "results.jsonl").read_text(encoding="utf-8").splitlines()
            if x]


def _per_case(results: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    acc: dict[str, dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))
    for r in results:
        if r.get("judge", "").startswith("check:") and r.get("passed") is not None:
            acc[r["check"]][r["item_id"]].append(bool(r["passed"]))
    return {c: {i: sum(v) / len(v) for i, v in items.items()} for c, items in acc.items()}


def _rate(results: list[dict[str, Any]], check: str) -> float | None:
    rows = [r for r in results if r.get("check") == check and r.get("passed") is not None]
    return round(sum(r["passed"] for r in rows) / len(rows), 4) if rows else None


def _interval(deltas: list[float]) -> tuple[float, float, float]:
    n = len(deltas)
    mean = sum(deltas) / n
    if n < 2:
        return mean, mean, mean
    sd = math.sqrt(sum((d - mean) ** 2 for d in deltas) / (n - 1))
    half = 1.96 * sd / math.sqrt(n)
    return mean, mean - half, mean + half


def _thresholds(run: Path) -> dict[str, Any]:
    p = run / "evidence" / "thresholds.yaml"
    if not p.is_file():
        return DEFAULT_THRESHOLDS
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def compare_runs(before: Path, after: Path) -> dict[str, Any]:
    ma = json.loads((before / "manifest.json").read_text(encoding="utf-8"))
    mb = json.loads((after / "manifest.json").read_text(encoding="utf-8"))
    ra, rb = _results(before), _results(after)
    rule = {**DEFAULT_THRESHOLDS["change_acceptance"],
            **(_thresholds(after).get("change_acceptance") or {})}

    warnings = []
    if _get(ma, ("pack", "items_sha256")) != _get(mb, ("pack", "items_sha256")):
        warnings.append("The two runs used different packs, so cases are only paired where "
                        "their ids match.")
    for label, m in (("before", ma), ("after", mb)):
        if m.get("cancelled"):
            warnings.append(f"The {label} run was cancelled before it finished.")

    pa, pb = _per_case(ra), _per_case(rb)
    checks = []
    for name in sorted(set(pa) | set(pb)):
        common = sorted(set(pa.get(name, {})) & set(pb.get(name, {})))
        if not common:
            checks.append({"check": name, "cases": 0, "status": "not_comparable"})
            continue
        deltas = [pb[name][i] - pa[name][i] for i in common]
        mean, lo, hi = _interval(deltas)
        improved = mean >= rule["min_gain"] and lo > 0
        down = mean <= -rule["max_regression"]
        status = ("improved" if improved else "regressed" if down and hi < 0
                  else "possibly_worse" if down else "no_clear_change")
        checks.append({
            "check": name, "cases": len(common),
            "before": _rate(ra, name), "after": _rate(rb, name),
            "change": round(mean, 4), "interval": [round(lo, 4), round(hi, 4)],
            "helped": sum(d > 0 for d in deltas), "hurt": sum(d < 0 for d in deltas),
            "unchanged": sum(d == 0 for d in deltas),
            "status": status,
            "helped_cases": [i for i, d in zip(common, deltas, strict=True) if d > 0],
            "hurt_cases": [i for i, d in zip(common, deltas, strict=True) if d < 0],
        })

    statuses = {c["status"] for c in checks}
    verdict = ("REJECT" if "regressed" in statuses
               else "INCONCLUSIVE" if "possibly_worse" in statuses
               else "ACCEPT" if "improved" in statuses else "NO EFFECT")

    changed = [{"what": label, "before": _get(ma, path), "after": _get(mb, path)}
               for label, path in WATCHED if _get(ma, path) != _get(mb, path)]

    ca = {c["cause"]: c["results"] for c in diagnose(ra)["causes"]}
    cb = {c["cause"]: c["results"] for c in diagnose(rb)["causes"]}
    causes = [{"cause": c, "label": CAUSES[c]["label"], "lever": CAUSES[c]["lever"],
               "before": ca.get(c, 0), "after": cb.get(c, 0)}
              for c in sorted(set(ca) | set(cb), key=lambda c: (-ca.get(c, 0), c))]

    return {
        "before": {"run_id": ma["run_id"], "sut": _get(ma, ("sut", "model_id")),
                   "finished_at": ma.get("finished_at")},
        "after": {"run_id": mb["run_id"], "sut": _get(mb, ("sut", "model_id")),
                  "finished_at": mb.get("finished_at")},
        "rule": rule,
        "verdict": verdict,
        "changed": changed,
        "checks": checks,
        "causes": causes,
        "warnings": warnings,
    }
