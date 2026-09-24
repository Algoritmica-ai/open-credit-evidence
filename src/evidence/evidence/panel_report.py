# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""What the judge panel found, set against the deterministic checks and the single judge.

Built from ``panel/records.jsonl``, ``panel/manifest.json`` and ``results.jsonl``
into ``evidence/panel.json`` and ``evidence/panel.md``. The panel is an opinion:
nothing here changes a pass, a fail or the decision.
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any

FIELDS = ("intelligible", "actionable", "overridable")


def _share(n: int, d: int) -> float | None:
    return round(n / d, 3) if d else None


def summarise(run: Path) -> dict[str, Any] | None:
    path = run / "panel" / "records.jsonl"
    if not path.is_file():
        return None
    records = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]
    manifest = json.loads((run / "panel" / "manifest.json").read_text(encoding="utf-8"))
    failing: dict[tuple[str, int], set[str]] = {}
    judge: dict[tuple[str, int], float | None] = {}
    for line in (run / "results.jsonl").read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        r = json.loads(line)
        key = (r["item_id"], r["repeat"])
        if r.get("check") == "readability":
            judge[key] = r.get("value")
        elif r.get("passed") is False:
            failing.setdefault(key, set()).add(r["check"])
    ok = [r for r in records if not r.get("error") and r.get("value") is not None]
    keyed = {(r["item_id"], r["repeat"]): r for r in ok}
    bad = [k for k in keyed if failing.get(k)]
    clean = [k for k in keyed if not failing.get(k)]
    flagged = [k for k, r in keyed.items() if r.get("flag_for_review")]
    confirmed = sum(len(set(keyed[k].get("checks_confirmed") or []) & failing[k]) for k in bad)
    failures = sum(len(failing[k]) for k in bad)
    disputed: dict[str, int] = {}
    for r in ok:
        for d in r.get("checks_disputed") or []:
            disputed[str(d.get("name"))] = disputed.get(str(d.get("name")), 0) + 1
    agree = {f: _share(sum(1 for r in ok if f in r.get("scores", {})
                           and r["scores"].get(f) == r.get("reader_scores", {}).get(f)),
                       sum(1 for r in ok if f in r.get("scores", {}))) for f in FIELDS}
    cites = [r for r in ok if r.get("citations")]
    cites_ok = sum(1 for r in cites if all(c.get("in_passages") for c in r["citations"].values()
                                          if c.get("citation")))
    missed = sorted(k for k in bad if judge.get(k) == 1.0 and keyed[k].get("flag_for_review"))
    examples = []
    for k in missed[:3]:
        r = keyed[k]
        f = next((x for x in r.get("findings") or [] if x.get("severity") == "material"),
                 (r.get("findings") or [{}])[0])
        examples.append({"item_id": k[0], "repeat": k[1], "failing_checks": sorted(failing[k]),
                         "panel_value": r["value"], "flag_reason": (r.get("flag_reasons")
                                                                    or [None])[0],
                         "finding": {x: f.get(x) for x in ("claim", "problem", "evidence")}
                         if f else None})
    judge_vals = [judge[k] for k in keyed if judge.get(k) is not None]
    return {
        "panel": manifest.get("panel"),
        "runtime": manifest.get("runtime"),
        "briefings": len(records), "answered": len(ok),
        "errors": len(records) - len(ok),
        "mean_value": round(mean(r["value"] for r in ok), 3) if ok else None,
        "judge_mean_value": round(mean(judge_vals), 3) if judge_vals else None,
        "flagged": len(flagged),
        "with_failing_checks": {
            "briefings": len(bad),
            "flagged": sum(1 for k in bad if keyed[k].get("flag_for_review")),
            "judge_full_marks": sum(1 for k in bad if judge.get(k) == 1.0),
            "panel_full_marks": sum(1 for k in bad if keyed[k]["value"] == 1.0),
            "judge_full_marks_panel_flagged": len(missed),
        },
        "without_failing_checks": {
            "briefings": len(clean),
            "flagged": sum(1 for k in clean if keyed[k].get("flag_for_review")),
        },
        "challenger": {
            "findings": sum(len(r.get("findings") or []) for r in ok),
            "material_findings": sum(1 for r in ok for f in r.get("findings") or []
                                     if f.get("severity") == "material"),
            "failing_checks_confirmed": confirmed, "failing_checks": failures,
            "checks_disputed": dict(sorted(disputed.items())),
            "invented_check_names": sum(len(r.get("invented_check_names") or []) for r in ok),
            "unread_check_verdicts": sum(len(r.get("unread_check_verdicts") or []) for r in ok),
            "mean_tool_calls": round(mean((r.get("agents") or {}).get("challenger", {}).get(
                "tool_calls", 0) for r in ok), 1) if ok else None,
        },
        "reader_arbiter_agreement": agree,
        "citations_all_given": {"records": len(cites), "ok": cites_ok},
        "examples": examples,
        "gated": False,
    }


def lines(s: dict[str, Any]) -> list[str]:
    """The panel section of the evidence, in markdown."""
    rt = s.get("runtime") or {}
    where = ("inside the NemoClaw sandbox `{}` on {} (OpenShell {}, network policies: {}), "
             "model route {} / {}".format(
                 rt.get("sandbox"), rt.get("node"), rt.get("openshell"),
                 ", ".join(rt.get("network_policies") or []) or "—",
                 (rt.get("inference_route") or {}).get("provider"),
                 (rt.get("inference_route") or {}).get("model"))
             if rt.get("kind") == "nemoclaw" else f"in the engine, against `{rt.get('endpoint')}`")
    models = rt.get("models") or {}
    w, c, ch = s["with_failing_checks"], s["without_failing_checks"], s["challenger"]
    L = ["# Judge panel", "",
         "Three agents reviewed each briefing: a **Reader** scored it as the underwriter would, "
         "a **Challenger** checked it against the case file and the deterministic checks with "
         "tools, and an **Arbiter** gave the final scores and said whether a person should "
         "review it. An opinion, reported and never used to pass or fail.", "",
         f"- Ran {where}. Models: reader `{models.get('reader')}`, challenger "
         f"`{models.get('challenger')}`, arbiter `{models.get('arbiter')}`.",
         f"- {s['answered']}/{s['briefings']} briefings answered"
         + (f"; {s['errors']} failed and are left out" if s["errors"] else "") + ".",
         f"- Mean score {s['mean_value']} on 0–1 (the single judge: {s['judge_mean_value']}). "
         f"Flagged for review: {s['flagged']}.", "",
         "## Against the deterministic checks", "",
         "| | briefings | panel flagged | single judge full marks | panel full marks |",
         "|---|---|---|---|---|",
         f"| failing at least one check | {w['briefings']} | {w['flagged']} | "
         f"{w['judge_full_marks']} | {w['panel_full_marks']} |",
         f"| failing none | {c['briefings']} | {c['flagged']} | — | — |", "",
         f"Of the briefings the single judge gave full marks despite a failing check, the panel "
         f"flagged {w['judge_full_marks_panel_flagged']}.", "",
         f"The Challenger made {ch['findings']} findings ({ch['material_findings']} material), "
         f"with {ch['mean_tool_calls']} tool calls per briefing on average, and confirmed "
         f"{ch['failing_checks_confirmed']} of the {ch['failing_checks']} failing check results "
         "from what it saw itself."]
    if ch["checks_disputed"]:
        L.append("It disputed checks it thought wrong — worth an auditor's look: "
                 + ", ".join(f"`{k}` {v}×" for k, v in ch["checks_disputed"].items()) + ".")
    if ch.get("invented_check_names"):
        L.append(f"It named checks that were not run {ch['invented_check_names']} times; those "
                 "names are left out of the counts above.")
    if ch.get("unread_check_verdicts"):
        L.append(f"It confirmed or disputed a check without reading its evidence "
                 f"{ch['unread_check_verdicts']} times; those verdicts are not counted.")
    ag = s["reader_arbiter_agreement"]
    L += ["", "## Within the panel", "",
          "Reader and Arbiter gave the same score on "
          + ", ".join(f"{f} {'—' if v is None else f'{v:.0%}'}" for f, v in ag.items())
          + " of briefings; where they differ, the Arbiter weighed the Challenger's findings.",
          f"Every citation was a passage the panel was given in "
          f"{s['citations_all_given']['ok']}/{s['citations_all_given']['records']} records."]
    if s["examples"]:
        L += ["", "## Examples: full marks from the single judge, flagged by the panel", ""]
        for e in s["examples"]:
            f = e.get("finding") or {}
            L.append(f"- `{e['item_id'].split(':')[2]}` r{e['repeat']} (failing: "
                     f"{', '.join(e['failing_checks'])}): {e.get('flag_reason') or '—'}"
                     + (f" — *{f.get('claim')}*: {f.get('problem')}" if f.get("claim") else ""))
    L += ["", "Every agent's replies, tool calls and tool results are in `panel/records.jsonl`; "
          "what ran and where, in `panel/manifest.json`.", ""]
    return L
