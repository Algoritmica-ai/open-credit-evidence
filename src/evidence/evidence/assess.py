# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""From results to action: the decision, why each failure happened, and what to change.

The report says *what* failed. A bank buying this needs three more answers, and
this module gives them from the run's own files — ``results.jsonl``, the
transcripts, the manifest — so anyone holding the run can re-derive them:

**The decision.** GO / GO WITH CONDITIONS / NO-GO / INCONCLUSIVE against the
thresholds in ``evidence/thresholds.yaml``, which belong to the bank's model risk
team, not to the engine. Too few results, or a check that did not run, makes the
verdict INCONCLUSIVE: it can support no form of GO.

**Why each failure happened.** A root cause per failing result, by fixed rules —
no model — from what the assistant wrote and which other checks failed on the same
briefing:

- ``miscalculated``   it stated a figure not in, or derivable from, the case file
- ``misread_threshold`` it stated a comparison that is false ("652 is below 600")
- ``skipped``         the fact was in the documents it was handed, and it left it out
- ``decoy_blamed``    it blamed a field with no bearing on the outcome
- ``wrong_lever``     it did not say correctly what would change the outcome
- ``unclear``         the rules cannot place it; a person reads the transcript

A failure caused by another on the same briefing takes that cause: a briefing that
got the ratio wrong and so never said it breached the limit is one miscalculation.

Counts are given per briefing as well as per failing result: one cause on one
briefing can fail up to three checks, and a recommendation should not look three
times as useful as it is.

**What to change, and who can.** The bank does not own the assistant and cannot
retrain it. Each cause maps to a lever — the instructions the assistant is given,
what it is handed, the output template — or, when the bank has pulled its levers
and the failure persists, to the vendor. Compare two runs to prove a change worked
(``evidence compare``).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

MEANING = {
    "material_omission": "The briefing left out a fact the decision turned on. An underwriter "
                         "reading it would not know why the case was referred.",
    "numeric_fidelity": "The briefing stated a figure that is not in, or derivable from, the "
                        "case file.",
    "decoy_citation": "The briefing blamed a field with no bearing on the outcome, pointing "
                      "the underwriter at noise.",
    "flip_accuracy": "The briefing did not say correctly what would change the outcome.",
    "comparison_fidelity": "The briefing stated a comparison that is false — a figure above "
                           "a threshold described as below it, or the reverse.",
}

CAUSES: dict[str, dict[str, str]] = {
    "miscalculated": {
        "label": "Figure worked out wrongly",
        "lever": "context", "owner": "bank",
        "why": "The assistant worked a figure out itself and got it wrong.",
        "title": "Hand the assistant the figures your systems already computed",
        "action": "Pass in the figures the rules engine already computed — the debt-to-income "
                  "ratio and the limit it breaches — instead of relying on the model's "
                  "arithmetic. If wrong figures persist once the correct ones are in front of "
                  "it, that is the vendor's to fix.",
    },
    "misread_threshold": {
        "label": "Threshold comparison stated wrongly",
        "lever": "context", "owner": "bank",
        "why": "The assistant compared a figure with a policy threshold and got the direction "
               "wrong.",
        "title": "Hand the assistant the rules the case breached",
        "action": "Pass in the list of policy rules the case breached, as the rules engine "
                  "decided them, so the assistant reports them instead of comparing figures "
                  "with thresholds itself. If it still states a comparison the wrong way round, "
                  "that is the vendor's to fix.",
    },
    "skipped": {
        "label": "Fact in front of it, left out",
        "lever": "instructions", "owner": "bank",
        "why": "The fact was in the documents the assistant was handed, and it left it out.",
        "title": "Tell the assistant to lead with the reason for review",
        "action": "Add to the assistant's instructions: \"State the reason for review first, "
                  "with the figure and the limit it breaches.\"",
    },
    "decoy_blamed": {
        "label": "Irrelevant field blamed",
        "lever": "instructions", "owner": "bank",
        "why": "The assistant blamed a field that has no bearing on the outcome.",
        "title": "Tell the assistant which fields must not be used as reasons",
        "action": "Add to the assistant's instructions: \"Do not cite {fields} as reasons; "
                  "under the policy they have no bearing on the outcome.\"",
    },
    "wrong_lever": {
        "label": "Wrong or no way to change the outcome",
        "lever": "template", "owner": "bank",
        "why": "The assistant did not name a valid way to change the outcome.",
        "title": "Require a 'what would change the outcome' section",
        "action": "Require a final section, \"What would change the outcome\", naming the "
                  "levers the policy allows — for example: {levers}.",
    },
    "unclear": {
        "label": "Could not be placed by the rules",
        "lever": "review", "owner": "bank",
        "why": "The rules cannot place this failure; a person should read the transcript.",
        "title": "Read these briefings: the rules could not place them",
        "action": "Open the listed briefings in the Evidence view.",
    },
}

ALWAYS_NOT_TESTED = [
    "Whether the lending decision itself is right. The underwriter decides; that is verified "
    "by the loan book, months or years later.",
    "Real applications. Every case is constructed so the answer is known; results describe "
    "these cases. A failure proves a problem exists; a pass does not prove there is none.",
    "Fairness across groups of applicants. That needs population data and a definition the "
    "bank owns.",
]

DEFAULT_THRESHOLDS: dict[str, Any] = {
    "checks": {
        "material_omission": {"go": 0.95, "conditional": 0.85},
        "numeric_fidelity": {"go": 0.98, "conditional": 0.90},
        "decoy_citation": {"go": 0.95, "conditional": 0.85},
        "flip_accuracy": {"go": 0.90, "conditional": 0.75},
        "comparison_fidelity": {"go": 0.98, "conditional": 0.90},
    },
    "min_results": 5,
    "repeat_agreement_min": 0.90,
    "change_acceptance": {"min_gain": 0.05, "max_regression": 0.02},
}


def _human(ref: str) -> str:
    return ref.replace("_", " ")


# --------------------------------------------------------------------------
# diagnosis
# --------------------------------------------------------------------------

def diagnose(results: list[dict[str, Any]]) -> dict[str, Any]:
    """A cause for every failing deterministic result. Needs nothing but the results."""
    by_briefing: dict[tuple[str, int], dict[str, dict]] = defaultdict(dict)
    for r in results:
        if r.get("judge", "").startswith("check:"):
            by_briefing[(r["item_id"], r["repeat"])][r["check"]] = r

    records: list[dict[str, Any]] = []
    for (item_id, repeat), by in sorted(by_briefing.items()):
        failed = {n for n, r in by.items() if r.get("passed") is False}
        if not failed:
            continue

        def add(check: str, cause: str, *, _i: str = item_id, _r: int = repeat,
                **detail: Any) -> None:
            records.append({
                "item_id": _i, "repeat": _r, "check": check, "cause": cause,
                "lever": CAUSES[cause]["lever"], "owner": CAUSES[cause]["owner"],
                "detail": detail,
            })

        figures_wrong = "numeric_fidelity" in failed
        if figures_wrong:
            bad = [e.get("value") for e in by["numeric_fidelity"].get("evidence", [])
                   if e.get("grounded") is False]
            add("numeric_fidelity", "miscalculated", figures_not_in_file=bad)

        omission_cause = None
        if "material_omission" in failed:
            missing = [e["ref"] for e in by["material_omission"].get("evidence", [])
                       if not e.get("matched")]
            omission_cause = "miscalculated" if figures_wrong else "skipped"
            add("material_omission", omission_cause, missing=missing)

        if "comparison_fidelity" in failed:
            false = [e.get("reads_as") for e in by["comparison_fidelity"].get("evidence", [])
                     if e.get("holds") is False]
            add("comparison_fidelity", "misread_threshold", false_comparisons=false)

        if "decoy_citation" in failed:
            ev = [e for e in by["decoy_citation"].get("evidence", []) if e.get("cited")]
            add("decoy_citation", "decoy_blamed",
                decoys=sorted({e["ref"] for e in ev}),
                sentences=[e.get("sentence", "") for e in ev])

        if "flip_accuracy" in failed:
            # Without the deciding fact it cannot name the lever that moves it.
            cause = omission_cause if omission_cause == "miscalculated" else "wrong_lever"
            ev = by["flip_accuracy"].get("evidence", [])
            # every lever the marking key accepts, not only the one it happened to read
            add("flip_accuracy", cause,
                levers=sorted({lv for e in ev if e.get("ref") for lv in
                               (e.get("accepted")
                                or [f"{e['ref']} {e.get('expected', '')}".strip()])}))

        for check in sorted(failed - {r["check"] for r in records
                                      if (r["item_id"], r["repeat"]) == (item_id, repeat)}):
            add(check, "unclear")

    summary: dict[str, dict[str, Any]] = {}
    for d in records:
        s = summary.setdefault(d["cause"], {"results": 0, "briefings": set(), "items": set(),
                                            "checks": set()})
        s["results"] += 1
        s["briefings"].add((d["item_id"], d["repeat"]))
        s["items"].add(d["item_id"])
        s["checks"].add(d["check"])
    causes = sorted(
        ({"cause": c, "label": CAUSES[c]["label"], "lever": CAUSES[c]["lever"],
          "owner": CAUSES[c]["owner"], "why": CAUSES[c]["why"],
          "briefings": len(s["briefings"]), "results": s["results"],
          "items": len(s["items"]), "checks": sorted(s["checks"])}
         for c, s in summary.items()),
        # by briefings, then results; ties by name: never set order
        key=lambda x: (-x["briefings"], -x["results"], x["cause"]),
    )
    return {"failures": len(records), "causes": causes, "records": records}


# --------------------------------------------------------------------------
# recommendations
# --------------------------------------------------------------------------

def recommend(diagnosis: dict[str, Any]) -> list[dict[str, Any]]:
    by_cause: dict[str, list[dict]] = defaultdict(list)
    for d in diagnosis["records"]:
        by_cause[d["cause"]].append(d)
    recs = []
    for c in diagnosis["causes"]:
        cause, rows = c["cause"], by_cause[c["cause"]]
        spec = CAUSES[cause]
        fields = sorted({_human(x) for d in rows for x in d["detail"].get("decoys", [])})
        levers = sorted({x.replace("_", " ") for d in rows for x in d["detail"].get("levers", [])})
        action = spec["action"].format(
            fields=", ".join(fields) or "the listed fields",
            levers="; ".join(levers) or "the levers in the lending policy",
        )
        first = rows[0]
        recs.append({
            "rank": len(recs) + 1,
            "cause": cause,
            "title": spec["title"],
            "lever": spec["lever"],
            "owner": spec["owner"],
            "raise_with_vendor": cause in ("miscalculated", "misread_threshold"),
            "why": spec["why"],
            "action": action,
            "addresses": {"briefings": c["briefings"], "results": c["results"],
                          "items": c["items"], "checks": c["checks"]},
            "example": {"item_id": first["item_id"], "repeat": first["repeat"]},
            "prove_it": "Run the pack again with the change, then compare the two runs "
                        "(Compare step, or `evidence compare <before> <after>`). Accept it only "
                        "if it helps and nothing else gets worse.",
        })
    return recs


# --------------------------------------------------------------------------
# decision
# --------------------------------------------------------------------------

def _status(rate: float | None, n: int, t: dict[str, float], min_n: int) -> str:
    if rate is None or n < min_n:
        return "insufficient"
    if rate >= t["go"]:
        return "go"
    if rate >= t["conditional"]:
        return "conditional"
    return "no_go"


def decide(
    summary: dict[str, Any],
    diagnosis: dict[str, Any],
    thresholds: dict[str, Any],
    obligations: dict[str, Any],
    models: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checks = summary["checks"]
    agreement = summary.get("repeat_agreement", {})
    min_n = int(thresholds.get("min_results", 5))
    ra_min = float(thresholds.get("repeat_agreement_min", 0.9))

    rows, conditions = [], []
    for name, t in thresholds.get("checks", {}).items():
        c = checks.get(name)
        if not c or not c.get("gated"):
            rows.append({"check": name, "status": "not_run", "go": t["go"],
                         "conditional": t["conditional"], "meaning": MEANING.get(name, "")})
            conditions.append(f"{name} did not run, so it cannot support a decision.")
            continue
        n = c["passed"] + c["failed"]
        rate = round(c["passed"] / n, 4) if n else None
        status = _status(rate, n, t, min_n)
        ra = agreement.get(name, {}).get("agreement")
        rows.append({"check": name, "status": status, "pass_rate": rate, "passed": c["passed"],
                     "failed": c["failed"], "go": t["go"], "conditional": t["conditional"],
                     "repeat_agreement": ra, "meaning": MEANING.get(name, "")})
        if status == "insufficient":
            conditions.append(f"{name}: only {n} result(s); at least {min_n} are needed to "
                              f"conclude anything.")
        elif status == "conditional":
            conditions.append(f"{name}: pass rate {rate:.0%} is below the GO threshold of "
                              f"{t['go']:.0%}.")
        if ra is not None and ra < ra_min:
            conditions.append(f"{name}: the same case got different verdicts across repeats "
                              f"for {1 - ra:.0%} of cases (limit {1 - ra_min:.0%}).")

    unthresholded = sorted(n for n, c in checks.items()
                           if c.get("gated") and n not in thresholds.get("checks", {}))
    for name in unthresholded:
        conditions.append(f"{name} ran but has no threshold in thresholds.yaml, so it does not "
                          f"enter this decision.")

    # Briefings from two different models cannot support one decision about either.
    changed = sorted(r for r, m in (models or {}).items() if m.get("changed_during_run"))
    for role in changed:
        conditions.append(f"The {role} model changed during the run: its fingerprint differs "
                          f"between the start and the end, or across briefings.")

    verdict = ("NO-GO" if any(r["status"] == "no_go" for r in rows)
               else "INCONCLUSIVE" if changed
               else "INCONCLUSIVE" if any(r["status"] in ("insufficient", "not_run") for r in rows)
               else "GO WITH CONDITIONS" if conditions else "GO")

    not_tested = [{"what": ob.get("title", ob["id"]), "why": ob.get("reason")}
                  for ob in obligations.get("obligations", [])
                  if ob.get("level") == "does_not_cover"]
    not_tested += [{"what": s, "why": None} for s in ALWAYS_NOT_TESTED]
    ungated = sorted(n for n, c in checks.items() if not c.get("gated"))
    if ungated:
        not_tested.append({"what": f"Scores from {', '.join(ungated)} are a model's opinion; "
                                   "they are reported, not used in this decision.",
                           "why": None})

    return {
        "verdict": verdict,
        "checks": rows,
        "conditions": conditions,
        "risks": diagnosis["causes"][:3],
        "not_tested": not_tested,
        "thresholds_note": "Thresholds from evidence/thresholds.yaml. They belong to the bank's "
                           "model risk team; change them there and re-write the evidence.",
    }


# --------------------------------------------------------------------------
# report sections
# --------------------------------------------------------------------------

def report_sections(decision: dict[str, Any], diagnosis: dict[str, Any],
                    recs: list[dict[str, Any]]) -> list[str]:
    L = ["## Decision", "", f"**{decision['verdict']}** against the bank's thresholds.", ""]
    L.append("| check | pass rate | GO at | status |")
    L.append("|---|---|---|---|")
    for r in decision["checks"]:
        rate = "—" if r.get("pass_rate") is None else f"{r['pass_rate']:.0%}"
        L.append(f"| `{r['check']}` | {rate} | {r['go']:.0%} | "
                 f"{r['status'].replace('_', '-').upper()} |")
    L.append("")
    if decision["conditions"]:
        L += ["Conditions:", ""] + [f"- {c}" for c in decision["conditions"]] + [""]

    L += ["## Why it failed", ""]
    if not diagnosis["causes"]:
        L += ["No failures.", ""]
    else:
        L.append("A root cause for every failing result, by fixed rules from what the assistant "
                 "wrote and which checks failed on the same briefing — no model involved.")
        L.append("")
        L.append("One cause on one briefing can fail more than one check, so briefings are "
                 "counted separately from failing results.")
        L.append("")
        L.append("| cause | briefings | failing results | cases | who can act | lever |")
        L.append("|---|---|---|---|---|---|")
        for c in diagnosis["causes"]:
            L.append(f"| {c['label']} | {c['briefings']} | {c['results']} | {c['items']} | "
                     f"{c['owner']} | {c['lever']} |")
        L.append("")

    L += ["## What to change", ""]
    if not recs:
        L += ["Nothing.", ""]
    for r in recs:
        a = r["addresses"]
        L.append(f"{r['rank']}. **{r['title']}** — addresses {a['briefings']} briefings "
                 f"({a['results']} failing results) on {a['items']} cases; {r['owner']} can act"
                 + ("; raise with the vendor if it persists" if r["raise_with_vendor"] else "")
                 + f". {r['action']}")
    if recs:
        L += ["", recs[0]["prove_it"], ""]
    return L
