# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Re-check an evidence pack.

Level 1 — integrity: every file listed in ``checksums.sha256`` still hashes to
the recorded value, nothing listed is missing, nothing unlisted has appeared.
A single edited digit fails this, and the failure names the file.

Level 2 — re-derivation (``recompute=True``): run every deterministic check
again from the transcripts and the pack, and compare with ``results.jsonl``.
Then rebuild everything under ``evidence/`` — summary, decision, diagnosis,
recommendations, report — from the results and compare byte for byte, naming
the first value that differs. This is what makes the numbers in the report
evidence rather than assertion: anyone with the pack and the run can reproduce
them, and someone who edits a number *and* re-seals the checksums still fails.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evidence.checks import run_checks
from evidence.contracts.transcript import Transcript
from evidence.evidence.writer import CHECKSUMS, _sha256_file, build_evidence, sealed_files
from evidence.pack import Pack


@dataclass
class Verification:
    ok: bool
    files_checked: int = 0
    mismatched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    unlisted: list[str] = field(default_factory=list)
    recomputed: int = 0
    disagreements: list[dict[str, Any]] = field(default_factory=list)
    # evidence/ files that do not rebuild from the results — kept apart from check-result
    # disagreements: an edited results.jsonl shows up in both, the first being the cause
    derived: list[dict[str, Any]] = field(default_factory=list)
    message: str = ""


def verify_integrity(run: Path) -> Verification:
    sums = run / CHECKSUMS
    if not sums.is_file():
        return Verification(ok=False, message=f"{CHECKSUMS} not found — run was never sealed")
    expected: dict[str, str] = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, name = line.split("  ", 1)
            expected[name] = digest
    v = Verification(ok=True, files_checked=len(expected))
    for name, digest in expected.items():
        path = run / name
        if not path.is_file():
            v.missing.append(name)
        elif _sha256_file(path) != digest:
            v.mismatched.append(name)
    present = {p.relative_to(run).as_posix() for p in sealed_files(run)}
    v.unlisted = sorted(present - expected.keys())
    v.ok = not (v.mismatched or v.missing or v.unlisted)
    if v.ok:
        v.message = f"{v.files_checked} files: all checksums match"
    else:
        parts = []
        if v.mismatched:
            parts.append("checksum mismatch: " + ", ".join(v.mismatched))
        if v.missing:
            parts.append("missing: " + ", ".join(v.missing))
        if v.unlisted:
            parts.append("not in checksums: " + ", ".join(v.unlisted))
        v.message = "; ".join(parts)
    return v


def verify_recompute(run: Path, pack: Pack, v: Verification | None = None) -> Verification:
    """Re-run every deterministic check from the transcripts and compare with results.jsonl."""
    v = v or Verification(ok=True)
    # each memo is checked against what the assistant was given under the run's setup
    setup = json.loads((run / "manifest.json").read_text(encoding="utf-8")).get("setup", "as_is")
    items = {i.item_id: i.for_setup(setup) for i in pack.items}
    recorded: dict[tuple[str, int, str], dict[str, Any]] = {}
    for line in (run / "results.jsonl").read_text(encoding="utf-8").splitlines():
        if line:
            r = json.loads(line)
            if r["judge"].startswith("check:"):
                recorded[(r["item_id"], r["repeat"], r["check"])] = r
    for path in sorted((run / "transcripts").glob("*.json")):
        t = Transcript.model_validate_json(path.read_text(encoding="utf-8"))
        item = items.get(t.item_id)
        if item is None:
            v.disagreements.append({"item_id": t.item_id, "reason": "item not in pack"})
            continue
        names = sorted({c for (i, rep, c) in recorded if i == t.item_id and rep == t.repeat})
        for c in run_checks(names, output=t.output, item=item):
            v.recomputed += 1
            old = recorded[(t.item_id, t.repeat, c.name)]
            new = c.to_score()
            if (old["passed"], round(old["value"], 6)) != (new["passed"], round(new["value"], 6)):
                v.disagreements.append(
                    {
                        "item_id": t.item_id,
                        "repeat": t.repeat,
                        "check": c.name,
                        "recorded": {"passed": old["passed"], "value": old["value"]},
                        "recomputed": {"passed": new["passed"], "value": new["value"]},
                    }
                )
    if v.disagreements:
        v.ok = False
        v.message += f"; {len(v.disagreements)} check result(s) do not re-derive"
    else:
        v.message += f"; {v.recomputed} check results re-derived from transcripts"
    return v


def _first_difference(a: Any, b: Any, path: str = "") -> tuple[str, Any, Any] | None:
    if type(a) is not type(b):
        return path or "(root)", a, b
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                return f"{path}.{k}".lstrip("."), a.get(k, "<missing>"), b.get(k, "<missing>")
            d = _first_difference(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path} (length)".lstrip("."), len(a), len(b)
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            d = _first_difference(x, y, f"{path}[{i}]")
            if d:
                return d
        return None
    return None if a == b else (path.lstrip("."), a, b)


def verify_derived(run: Path, v: Verification | None = None) -> Verification:
    """Rebuild every derived file under evidence/ from the run and compare with what is there."""
    v = v or Verification(ok=True)
    rebuilt = 0
    for rel, fresh in build_evidence(run).items():
        path = run / rel
        if not path.is_file():
            v.derived.append({"file": rel, "reason": "missing — written by an older engine; "
                                                     "re-write with `evidence report --rewrite`"})
            continue
        stored = path.read_text(encoding="utf-8")
        rebuilt += 1
        if stored == fresh:
            continue
        where: dict[str, Any] = {"file": rel}
        d = (_first_difference(json.loads(stored), json.loads(fresh))
             if rel.endswith(".json") else None)
        if d:
            where.update(value=d[0], recorded=d[1], recomputed=d[2])
        else:
            where["reason"] = "does not match what the results produce"
        v.derived.append(where)
    if v.derived:
        v.ok = False
        first = v.derived[0]
        v.message += (f"; {first['file']}: {first['value']} recorded {first['recorded']!r}, "
                      f"recomputed {first['recomputed']!r}" if "value" in first
                      else f"; {first['file']}: {first['reason']}")
    else:
        v.message += f"; {rebuilt} evidence files rebuilt from the results and match"
    return v


def verify_run(run: Path, pack: Pack | None = None, *, recompute: bool = False) -> Verification:
    v = verify_integrity(run)
    if recompute and v.files_checked:
        if pack is None:
            raise ValueError("recompute needs the pack")
        v = verify_recompute(run, pack, v)
        v = verify_derived(run, v)
    return v
