# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Re-check a sealed run under the current version of the checks.

When a check changes, the runs scored with its earlier version stay as they were: they
are sealed, and ``evidence verify --recompute`` re-derives them with the versions they
recorded. This module shows what the new version would change on them, without touching
them. It re-scores every memo twice, with the versions the run was scored with and with
the current ones, and writes the difference to a folder of its own, sealed (and anchored
when anchoring is on):

- ``recheck.md``: in plain words, check by check and memo by memo;
- ``recheck.json``: the same, for machines.

It reads an engine run (``runs/…``, from its transcripts) or a capability checker run
(``capabilities/…``, from NeMo Evaluator's credit-memo results).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evidence.checks import check_versions, run_checks
from evidence.contracts.item import BenchmarkItem
from evidence.contracts.transcript import Transcript
from evidence.pack import Pack, load_pack

# (memo, item as the assistant saw it, the memo's text, results as recorded or None)
Memo = tuple[str, BenchmarkItem, str, dict[str, bool] | None]


def _engine_memos(run: Path, pack: Pack | None) -> tuple[list[str], dict[str, int], Iterator[Memo]]:
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    pack = pack or load_pack(Path("packs") / manifest["pack"]["pack_id"])
    items = {i.item_id: i.for_setup(manifest.get("setup") or "as_is") for i in pack.items}
    names = list(manifest.get("checks") or [])
    versions = manifest.get("check_versions") or dict.fromkeys(names, 1)
    recorded: dict[tuple[str, int], dict[str, bool]] = {}
    for line in (run / "results.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line) if line else None
        if r and r["judge"].startswith("check:") and r["passed"] is not None:
            recorded.setdefault((r["item_id"], r["repeat"]), {})[r["check"]] = r["passed"]

    def memos() -> Iterator[Memo]:
        for path in sorted((run / "transcripts").glob("*.json")):
            t = Transcript.model_validate_json(path.read_text(encoding="utf-8"))
            if t.item_id in items:
                yield (f"{t.item_id}#{t.repeat}", items[t.item_id], t.output,
                       recorded.get((t.item_id, t.repeat)))

    return names, versions, memos()


def _capability_memos(run: Path) -> tuple[list[str], dict[str, int], Iterator[Memo]]:
    meta = json.loads((run / "capabilities.json").read_text(encoding="utf-8"))["run"]
    setup = meta.get("setup") or "as_is"
    rows = [json.loads(line) for line in (run / "nel" / "credit-memo" / "results.jsonl")
            .read_text(encoding="utf-8").splitlines() if line]
    names = sorted({k.removeprefix("check_") for r in rows
                    for k in r.get("scoring_details") or {} if k.startswith("check_")})
    versions = meta.get("check_versions") or dict.fromkeys(names, 1)

    def memos() -> Iterator[Memo]:
        for r in sorted(rows, key=lambda r: (r["problem_idx"], r["repeat"])):
            item = BenchmarkItem.model_validate(r["metadata"]["item"]).for_setup(setup)
            sd = r.get("scoring_details") or {}
            yield (f"{item.item_id}#{r['repeat']}", item, r["model_response"] or "",
                   {k.removeprefix("check_"): v for k, v in sd.items()
                    if k.startswith("check_")})

    return names, versions, memos()


def recheck(run: Path, pack: Pack | None = None, *, root: Path = Path("rechecks")) -> Path:
    """Re-score a run under the current checks; returns the sealed folder with the result."""
    run = run.resolve()
    if (run / "capabilities.json").is_file():
        names, before_v, memos = _capability_memos(run)
    else:
        names, before_v, memos = _engine_memos(run, pack)
    now_v = check_versions(names)
    changed = {n: [before_v.get(n, 1), now_v[n]] for n in names if before_v.get(n, 1) != now_v[n]}
    rows: list[dict[str, Any]] = []
    unreproduced = 0
    for key, item, text, recorded in memos:
        before = {c.name: c for c in run_checks(names, output=text, item=item, versions=before_v)}
        after = {c.name: c for c in run_checks(names, output=text, item=item)}
        if recorded is not None and any(recorded.get(n) != before[n].passed for n in recorded):
            unreproduced += 1  # the recorded results do not re-derive: verify says why
        rows.append({
            "memo": key,
            "before": {n: before[n].passed for n in names},
            "after": {n: after[n].passed for n in names},
            "changes": [{"check": n, "was": before[n].passed, "now": after[n].passed,
                         "was_detail": before[n].detail, "now_detail": after[n].detail}
                        for n in names if before[n].passed != after[n].passed],
        })
    summary = _summarise(rows, names)
    result = {"run": str(run), "rechecked_at": datetime.now(UTC).isoformat(timespec="seconds"),
              "versions": {"before": before_v, "now": now_v}, "changed_checks": changed,
              "memos": len(rows), "unreproduced": unreproduced, **summary, "rows": rows}
    out = (root / f"{run.name}-{datetime.now(UTC).strftime('%Y-%m-%dT%H%M%SZ')}").resolve()
    out.mkdir(parents=True)
    (out / "recheck.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (out / "recheck.md").write_text(report(result), encoding="utf-8")
    from evidence import anchor
    from evidence.evidence.writer import seal

    seal(out)
    anchor.anchor(out, "recheck")  # a no-op when anchoring is off
    return out


def _clean(flags: dict[str, bool | None]) -> bool:
    return all(v is not False for v in flags.values())


def _summarise(rows: list[dict[str, Any]], names: list[str]) -> dict[str, Any]:
    def rate(side: str, n: str) -> float:
        judged = [r[side][n] for r in rows if r[side][n] is not None]
        return sum(judged) / len(judged) if judged else 0.0

    return {
        "clean": {"before": sum(_clean(r["before"]) for r in rows),
                  "after": sum(_clean(r["after"]) for r in rows)},
        "now_clean": [r["memo"] for r in rows if _clean(r["after"]) and not _clean(r["before"])],
        "now_flagged": [r["memo"] for r in rows if _clean(r["before"]) and not _clean(r["after"])],
        "checks": {n: {"before": rate("before", n), "after": rate("after", n),
                       "passed_now": sum(1 for r in rows for c in r["changes"]
                                         if c["check"] == n and c["now"]),
                       "failed_now": sum(1 for r in rows for c in r["changes"]
                                         if c["check"] == n and c["now"] is False)}
                   for n in names},
    }


def report(r: dict[str, Any]) -> str:
    n = r["memos"]
    lines = [f"# Re-check: {Path(r['run']).name}", "",
             f"Re-scored {n} memos on {r['rechecked_at']} with the current checks. The run itself "
             "is unchanged and still verifies with the versions it was scored with.", ""]
    if r["changed_checks"]:
        lines.append("Checks that changed since the run: " + ", ".join(
            f"`{c}` (version {a} → {b})" for c, (a, b) in r["changed_checks"].items()) + ".")
    else:
        lines.append("No check has changed since the run: nothing should differ.")
    if r["unreproduced"]:
        lines += ["", f"**{r['unreproduced']} memo(s) did not re-derive as recorded** with the "
                      "run's own versions. Run `evidence verify --recompute` on it."]
    c = r["clean"]
    lines += ["", "| | Before | Now |", "|---|---|---|",
              f"| Memos with no mistake found | {c['before']} of {n} | {c['after']} of {n} |", "",
              "| Check | Passed before | Passed now | Failed before, pass now | "
              "Passed before, fail now |", "|---|---|---|---|---|"]
    for name, s in r["checks"].items():
        lines.append(f"| `{name}` | {s['before']:.1%} | {s['after']:.1%} | {s['passed_now']} | "
                     f"{s['failed_now']} |")
    for title, key in (("Memos now found wrong", "failed"), ("Memos now found right", "passed")):
        changes = [(row["memo"], ch) for row in r["rows"] for ch in row["changes"]
                   if (ch["now"] is False) == (key == "failed")]
        if changes:
            lines += ["", f"## {title} ({len(changes)})", ""]
            for memo, ch in changes:
                lines.append(f"- `{memo}` `{ch['check']}`: was \"{ch['was_detail']}\"; now "
                             f"\"{ch['now_detail']}\"")
    return "\n".join(lines) + "\n"
