# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""One evidence pack, a report for each reader.

``report.md`` holds everything and reads like it. The people who act on a run
ask different questions of it, so each gets a report that answers theirs:

- **business** — can we use it, and what does it take? One page.
- **credit-risk** — is the method sound and the result stable? For the model
  risk team (second line): test design, results with intervals, stability,
  root causes, limitations, how to reproduce.
- **compliance** — what does this evidence, for which article? The obligation
  sections of the full report and the lender's rule pack.
- **operations** — what should underwriters watch for? The failure patterns,
  each with a sentence the assistant actually wrote, and what to do about it.
- **vendor** — what failed and how to reproduce it, for whoever supplies the
  assistant.
- **auditor** — what each file is and how to check that none has changed.

Every report is derived from the run's own files by pure functions, like the
rest of ``evidence/``: ``evidence verify --recompute`` rebuilds them and names
the first line that no longer follows from the results.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any

from evidence.evidence.assess import CAUSES
from evidence.fingerprint import summary as fp_summary

READERS: dict[str, dict[str, str]] = {
    "business": {"title": "Business", "for": "Head of lending, product owner",
                 "question": "Can we use it, and what does it take?"},
    "credit-risk": {"title": "Credit risk", "for": "Model risk, second line",
                    "question": "Is the method sound and the result stable?"},
    "compliance": {"title": "Compliance", "for": "Compliance and legal",
                   "question": "What does this evidence, for which article?"},
    "operations": {"title": "Underwriting operations", "for": "Underwriters and team leads",
                   "question": "What should we watch for in the briefings?"},
    "vendor": {"title": "Vendor", "for": "Whoever supplies the assistant",
               "question": "What failed, and how do we reproduce it?"},
    "auditor": {"title": "Auditor", "for": "Internal audit, a supervisor",
                "question": "Can these numbers be trusted?"},
}

# What a failure of each check means, as the briefing's reader would say it.
PROBLEM = {
    "material_omission": "left out a fact the decision turned on",
    "numeric_fidelity": "stated a figure that is not in, or worked out from, the case file",
    "comparison_fidelity": "compared a figure with a threshold the wrong way round",
    "claim_consistency": "said a limit was breached when its own figure says it was not",
    "decoy_citation": "gave a field with no bearing on the outcome as a reason",
    "flip_accuracy": "did not say correctly what would change the outcome",
}

VERDICT_LINE = {
    "GO": "On cases like these, the assistant meets every threshold your model risk team set.",
    "GO WITH CONDITIONS": "The assistant can be used on cases like these, on the conditions "
                          "below.",
    "NO-GO": "The assistant is not ready to brief underwriters on cases like these without "
             "changes.",
    "INCONCLUSIVE": "This run cannot support a decision; the credit risk report says why.",
}

FIELD_WORDS = {
    "age_band": "age band", "dependants": "dependants", "employer_name": "employer",
    "postcode_district": "postcode", "purpose": "loan purpose", "title": "title",
}

ADVICE = {
    "miscalculated": "Check any ratio or amount the briefing works out against the application "
                     "form before relying on it. The briefing's own arithmetic is where it is "
                     "most often wrong.",
    "misread_threshold": "When a briefing says a figure is above or below a limit, compare the "
                         "two numbers yourself.",
    "decoy_blamed": "Disregard reasoning that rests on {decoys}. The lending policy does not "
                    "use them.",
    "wrong_lever": "If the briefing does not say what would change the outcome, work it out "
                   "from the policy: which limit is breached, and by how much.",
    "skipped": "Read the reason for referral in the file itself. The briefing may leave out "
               "the fact that decides the case.",
    "unclear": "Read the briefing against the file.",
}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _case(item_id: str) -> str:
    parts = item_id.split(":")
    return parts[2] if len(parts) > 2 else item_id


def _transcript_name(item_id: str, repeat: int) -> str:
    return f"{re.sub(r'[^A-Za-z0-9_.-]+', '_', item_id)}-r{repeat}.json"


def _share(n: int, d: int) -> str:
    return f"{round(100 * n / d)}%" if d else "—"


def _gated(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {n: c for n, c in summary["checks"].items() if c.get("gated")}


def _judges(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {n: c for n, c in summary["checks"].items() if not c.get("gated")}


def case_interval(results: list[dict[str, Any]], check: str) -> tuple[float, float, float] | None:
    """Pass rate with a 95% interval computed over cases, not briefings.

    Repeats of one case are not independent — the same file, the same prompt —
    so the interval treats each case's share of passing repeats as one
    observation. It is wider than an interval over briefings, and honest.
    """
    per: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        if r.get("check") == check and r.get("passed") is not None:
            per[r["item_id"]].append(bool(r["passed"]))
    xs = [sum(v) / len(v) for v in per.values()]
    if not xs:
        return None
    mean = sum(xs) / len(xs)
    if len(xs) < 2:
        return mean, mean, mean
    sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / (len(xs) - 1))
    half = 1.96 * sd / math.sqrt(len(xs))
    return mean, max(0.0, mean - half), min(1.0, mean + half)


def _run_line(manifest: dict[str, Any]) -> str:
    sut = manifest["sut"]
    where = "on-prem" if sut.get("on_prem") else "cloud"
    return (
        f"Assistant `{sut['model_id']}` ({where}) · {manifest['transcripts']} briefings: "
        f"{manifest['pack']['items']} referred loan cases × {manifest['repeats']} · "
        f"pack `{manifest['pack']['pack_id']}` v{manifest['pack']['version']} · run "
        f"`{manifest['run_id']}` · model calls {str(manifest.get('started_at', ''))[:10]}"
    )


def _roles(manifest: dict[str, Any]) -> list[str]:
    models = manifest.get("models") or {}
    return [r for r in ("assistant", "judge", "embed")
            if r in models or (r == "assistant") or (r == "judge" and manifest.get("judge"))]


def _fingerprint_lines(manifest: dict[str, Any]) -> list[str]:
    models = manifest.get("models") or {}
    return [f"- {role.capitalize()} model fingerprint: {fp_summary(models.get(role))}"
            + ("; **changed during the run**" if (models.get(role) or {}).get("changed_during_run")
               else "")
            for role in _roles(manifest)]


def _others(current: str) -> list[str]:
    return ["## The other reports", ""] + [
        f"- **{r['title']}** ({r['for']}): `evidence/readers/{name}.md`"
        for name, r in READERS.items() if name != current
    ] + ["- **Everything**, by obligation: `evidence/report.md`", ""]


# --------------------------------------------------------------------------
# business — one page
# --------------------------------------------------------------------------

def business(manifest, summary, decision, recs) -> str:
    total = manifest["transcripts"]
    L = [f"# {manifest['pack']['pack_id']} — the assistant, on one page", "",
         _run_line(manifest), "",
         f"## Verdict: **{decision['verdict']}**", "",
         VERDICT_LINE.get(decision["verdict"], ""), ""]

    rows = []
    go_at = {r["check"]: r["go"] for r in decision["checks"]}
    for name, c in _gated(summary).items():
        if c["failed"]:
            need = f"at most {round((1 - go_at[name]) * 100)}%" if name in go_at else "—"
            rows.append((c["failed"] / (c["passed"] + c["failed"]), name, c, need))
    clean = [n for n, c in _gated(summary).items() if not c["failed"]]
    L += ["## What went wrong, and how often", ""]
    if rows:
        L += ["| In how many briefings the assistant … | briefings | share | allowed for GO |",
              "|---|---|---|---|"]
        for _, name, c, need in sorted(rows, key=lambda x: (-x[0], x[1])):
            n = c["passed"] + c["failed"]
            L.append(f"| {PROBLEM.get(name, name)} | {c['failed']} of {n} | "
                     f"{_share(c['failed'], n)} | {need} |")
        L.append("")
    if clean:
        L += ["No briefing " + ", and none ".join(PROBLEM.get(n, n) for n in clean) + ".", ""]

    L += ["## What to change first", ""]
    if not recs:
        L += ["Nothing: no check failed.", ""]
    for r in recs[:3]:
        who = "the bank" + (", then the vendor if it persists" if r["raise_with_vendor"] else "")
        L.append(f"{r['rank']}. **{r['title']}** — {who}. Addresses "
                 f"{r['addresses'].get('briefings', r['addresses']['results'])} of {total} "
                 "briefings.")
    L += ["", "Make one change, run the pack again, and compare the two runs: a change is "
          "accepted only if it helps and nothing else gets worse.", ""]

    L += ["## What this does not tell you", "",
          "- Whether the lending decisions are right. The underwriter decides; the loan book "
          "shows it, later.",
          "- How the assistant does on real applications. These cases are built so the answer "
          "is known: a failure proves a problem exists, a pass does not prove there is none.",
          "- Fairness across groups of applicants.",
          "- How readable the briefings are. That is a model's opinion, in the credit risk "
          "report, and not part of this verdict.", ""]
    return "\n".join(L + _others("business"))


# --------------------------------------------------------------------------
# credit risk — model risk, second line
# --------------------------------------------------------------------------

def credit_risk(manifest, results, summary, diagnosis, recs, decision, obligations) -> str:
    sut, pack = manifest["sut"], manifest["pack"]
    sdd = pack.get("sdd") or {}
    params = sut.get("params") or {}
    basis = {n: b for ob in obligations.get("obligations", [])
             for n, b in (ob.get("basis") or {}).items()}
    L = [f"# Model risk report — {pack['pack_id']} v{pack['version']} — run {manifest['run_id']}",
         "", _run_line(manifest), ""]

    L += ["## 1. Use and scope", "",
          "An AI assistant writes a briefing for a human underwriter on each loan application "
          "the automated rules referred. The underwriter decides. This run tests the "
          "briefings, not the decisions.", "",
          f"- Assistant under test: `{sut['model_id']}` at `{sut['endpoint']}`, prompt version "
          f"`{sut.get('prompt_version') or '—'}`, temperature {params.get('temperature', '—')}, "
          f"seed {params.get('seed', '—')}, max tokens {sut.get('max_tokens', '—')}.",
          f"- Verdict against the thresholds: **{decision['verdict']}**.",
          *_fingerprint_lines(manifest), ""]

    L += ["## 2. Test design", "",
          f"- **Cases.** Generated by Synthetic Data Designer from `{sdd.get('spec', '—')}` "
          f"(seed {sdd.get('seed', '—')}, {sdd.get('generated', '—')} applications), decided by "
          f"scorecard `{pack.get('scorecard_version')}`, and the {pack['items']} referred cases "
          "closest to a decision line kept. Each case carries a marking key — the facts the "
          "decision turned on, the fields with no bearing on it, what would change it — "
          "computed before any model call.",
          f"- **Repeats.** Each case {manifest['repeats']} times with the same prompt, so "
          "run-to-run variation is measured, not assumed.",
          "- **Checks.** Deterministic: each compares the briefing with the marking key or "
          "with the case file, and needs no model.", ""]
    L += ["| check | what it tests | a briefing fails when it … |", "|---|---|---|"]
    for name in _gated(summary):
        tests = (basis.get(name) or {}).get("tests", "")
        L.append(f"| `{name}` | {tests.replace('|', '/')} | {PROBLEM.get(name, '—')} |")
    L += ["", "- **Thresholds.** Set in `evidence/thresholds.yaml`; they belong to the bank's "
          "model risk team, not to the engine.", ""]
    L += ["| check | GO at | conditional at |", "|---|---|---|"]
    for r in decision["checks"]:
        L.append(f"| `{r['check']}` | {r['go']:.0%} | {r['conditional']:.0%} |")
    L.append("")

    L += ["## 3. Results", "",
          "Pass rate over briefings, with a 95% interval computed over cases: repeats of one "
          "case share a file and a prompt and are not independent observations.", "",
          "| check | passed | pass rate | 95% interval | GO at | status |",
          "|---|---|---|---|---|---|"]
    status = {r["check"]: r for r in decision["checks"]}
    for name, c in _gated(summary).items():
        n = c["passed"] + c["failed"]
        ci = case_interval(results, name)
        interval = f"{ci[1]:.0%} – {ci[2]:.0%}" if ci else "—"
        row = status.get(name)
        L.append(f"| `{name}` | {c['passed']}/{n} | {_share(c['passed'], n)} | {interval} | "
                 f"{row['go']:.0%} | {row['status'].replace('_', '-').upper()} |" if row else
                 f"| `{name}` | {c['passed']}/{n} | {_share(c['passed'], n)} | {interval} | — | "
                 "no threshold |")
    L.append("")
    for name, c in _judges(summary).items():
        cited = (f"; cited a passage it was given in {c['citations']}/{c['results']}"
                 if c.get("citations") is not None else "")
        judge = (manifest.get("judge") or {}).get("model_id", "a model")
        L += [f"Judge `{name}` (`{judge}`): mean {c['mean_value']} on 0–1 over {c['results']} "
              f"briefings{cited}. A model's opinion; reported, never used to pass or fail.", ""]
    if decision["conditions"]:
        L += ["Conditions:", ""] + [f"- {x}" for x in decision["conditions"]] + [""]

    L += ["## 4. Stability", "",
          f"The share of cases whose verdict was the same in all {manifest['repeats']} repeats. "
          "A check a case passes once and fails once is measuring the assistant's run-to-run "
          "variation as much as its quality.", "",
          "| check | stable cases | cases that changed verdict |", "|---|---|---|"]
    for name, a in summary["repeat_agreement"].items():
        L.append(f"| `{name}` | {a['stable']}/{a['items']} | "
                 f"{', '.join(_case(i) for i in a['flipping_items']) or '—'} |")
    L.append("")

    L += ["## 5. Root causes and remediation", "",
          "A cause for every failing result, by fixed rules — no model. One cause on one "
          "briefing can fail more than one check.", ""]
    if diagnosis["causes"]:
        L += ["| cause | briefings | failing results | cases | lever | who acts |",
              "|---|---|---|---|---|---|"]
        for c in diagnosis["causes"]:
            L.append(f"| {c['label']} | {c.get('briefings', '—')} | {c['results']} | {c['items']} "
                     f"| {c['lever']} | {c['owner']} |")
        L.append("")
        for r in recs:
            L.append(f"{r['rank']}. **{r['title']}** ({r['lever']}). {r['action']}")
        L += ["", "Acceptance: re-run the pack with the change and compare the two runs "
              "(`evidence compare <before> <after>`). The rule is in `thresholds.yaml` "
              "(`change_acceptance`).", ""]
    else:
        L += ["No failures.", ""]

    L += ["## 6. Limitations", ""]
    L += [f"- {x['what']}" + (f" {x['why']}" if x.get("why") else "")
          for x in decision["not_tested"]]
    L += [f"- {pack['items']} cases. The intervals in section 3 are wide; a change smaller than "
          "them cannot be told apart from run-to-run variation.", ""]

    L += ["## 7. Reproduce", "",
          f"- Engine `{manifest['engine']['package']}` {manifest['engine']['version']}, commit "
          f"`{manifest['engine'].get('git_commit') or '—'}`; pack items sha256 "
          f"`{pack['items_sha256'][:12]}…`.",
          f"- Model calls {manifest.get('started_at')} to {manifest.get('finished_at')}"
          + (f"; checks scored {manifest['scored_at']}." if manifest.get("scored_at") else "."),
          "- `evidence verify <run> --recompute --pack <pack>` re-derives every check result "
          "and every figure in this report from the transcripts.", ""]
    return "\n".join(L + _others("credit-risk"))


# --------------------------------------------------------------------------
# compliance — the obligation sections of the full report
# --------------------------------------------------------------------------

def compliance(manifest, parts: dict[str, list[str]]) -> str:
    pack = manifest["pack"]
    L = [f"# Compliance — {pack['pack_id']} v{pack['version']} — run {manifest['run_id']}", "",
         _run_line(manifest), "",
         "What this run evidences, contributes to, or does not cover, article by article — "
         "the pack's own claim for each — and the lender's process evidence under the "
         "national rule pack. Each claim is shown with the check results behind it; the "
         "method and intervals are in the credit risk report.", ""]
    for key in ("obligations", "outside_grid", "rule_pack", "non_claims"):
        L += parts.get(key, [])
    return "\n".join(L).rstrip("\n") + "\n\n" + "\n".join(_others("compliance"))


# --------------------------------------------------------------------------
# operations — underwriters and team leads
# --------------------------------------------------------------------------

def _example(cause: str, rec: dict[str, Any], by_key: dict) -> str | None:
    """A sentence the assistant actually wrote, for this cause, if the evidence holds one."""
    r = by_key.get((rec["item_id"], rec["repeat"], rec["check"])) or {}
    ev = r.get("evidence") or []
    if rec["check"] == "comparison_fidelity":
        return next((e["sentence"] for e in ev if e.get("holds") is False), None)
    if rec["check"] == "decoy_citation":
        return next((e["sentence"] for e in ev if e.get("cited")), None)
    if rec["check"] == "numeric_fidelity":
        ctx = next((e for e in ev if e.get("grounded") is False and e.get("context")), None)
        if not ctx:
            return None
        words = ctx["context"].split()[1:-1]  # the window cuts words at both ends
        return f"… {' '.join(words)} …" if words else None
    if rec["check"] == "flip_accuracy":
        return next((e["sentence"] for e in ev if e.get("sentence")), None)
    return None


def operations(manifest, results, diagnosis) -> str:
    total = manifest["transcripts"]
    by_key = {(r["item_id"], r["repeat"], r["check"]): r for r in results}
    L = ["# For underwriters — what to watch for in the assistant's briefings", "",
         _run_line(manifest), "",
         "The briefing is a summary of the file, written by a model. On these cases it went "
         "wrong in the ways below, most frequent first. Each comes with a sentence the "
         "assistant actually wrote and what to do when you see one like it.", ""]
    if not diagnosis["causes"]:
        L += ["No failures on these cases. Keep reading the file for the fact the decision "
              "turns on; a clean run is not a guarantee.", ""]
    for c in diagnosis["causes"]:
        recs = [d for d in diagnosis["records"] if d["cause"] == c["cause"]]
        L += [f"## {c['label']} — {c.get('briefings', c['results'])} of {total} briefings", "",
              c["why"], ""]
        example = next((x for x in (_example(c["cause"], d, by_key) for d in recs) if x), None)
        if example:
            first = next(d for d in recs if _example(c["cause"], d, by_key) == example)
            L += [f"> {example.replace(chr(10), ' ')}", "",
                  f"— case {_case(first['item_id'])}, repeat {first['repeat'] + 1}", ""]
        elif c["cause"] in ("skipped", "miscalculated"):
            detail = by_key.get((recs[0]["item_id"], recs[0]["repeat"], recs[0]["check"]), {})
            if detail.get("detail"):
                L += [f"Case {_case(recs[0]['item_id'])}: {detail['detail']}", ""]
        decoys = sorted({FIELD_WORDS.get(x, x.replace("_", " "))
                         for d in recs for x in d["detail"].get("decoys", [])})
        advice = ADVICE.get(c["cause"], ADVICE["unclear"]).format(
            decoys=", ".join(decoys) or "fields the policy does not use")
        L += [f"**What to do:** {advice}", ""]
    L += ["## Before you rely on a briefing", "",
          "1. Find the reason for referral in the file, and check the briefing states it.",
          "2. Check any ratio or amount the briefing works out against the application form.",
          "3. Where it says a figure is above or below a limit, compare the two numbers.",
          "4. Ignore reasons that rest on age, dependants, postcode, employer, title or loan "
          "purpose.",
          "5. Check it says what would change the outcome, and that this follows from the "
          "policy.", ""]
    return "\n".join(L + _others("operations"))


# --------------------------------------------------------------------------
# vendor — what failed and how to reproduce it
# --------------------------------------------------------------------------

def vendor(manifest, results, summary, recs) -> str:
    sut = manifest["sut"]
    params = sut.get("params") or {}
    L = ["# For the assistant's vendor — what failed, and how to reproduce it", "",
         _run_line(manifest), "",
         "## The system under test", "",
         f"- Model `{sut['model_id']}` at `{sut['endpoint']}`; prompt version "
         f"`{sut.get('prompt_version') or '—'}`; parameters "
         f"{', '.join(f'{k} {v}' for k, v in params.items()) or '—'}; max tokens "
         f"{sut.get('max_tokens', '—')}.",
         *_fingerprint_lines(manifest)[:1],
         "- Every transcript records the exact system prompt, user prompt, parameters, output, "
         "tokens and latency of its call, and the fingerprint of the model that answered.", ""]
    raised = [r for r in recs if r["raise_with_vendor"]]
    L += ["## Raised with you if they persist", ""]
    if raised:
        for r in raised:
            n = r["addresses"].get("briefings", r["addresses"]["results"])
            first = r["action"][:1].lower() + r["action"][1:]
            L.append(f"- **{r['title']}** — {n} briefings. The bank will first {first}")
    else:
        L.append("- None: every cause in this run has a lever the bank controls.")
    L.append("")

    failing = sorted((r for r in results if r.get("passed") is False),
                     key=lambda r: (r["check"], r["item_id"], r["repeat"]))
    L += [f"## Every failing result ({len(failing)})", ""]
    if failing:
        L += ["| case | repeat | check | detail | transcript |", "|---|---|---|---|---|"]
        for r in failing:
            L.append(f"| {_case(r['item_id'])} | {r['repeat'] + 1} | `{r['check']}` | "
                     f"{r['detail'].replace('|', '/')} | `transcripts/"
                     f"{_transcript_name(r['item_id'], r['repeat'])}` |")
        L.append("")
    if manifest["repeats"] > 1:
        L += ["## Run-to-run variation", "",
              f"Each case ran {manifest['repeats']} times with the same prompt"
              + (f", temperature {params['temperature']}" if "temperature" in params else "")
              + (f" and seed {params['seed']}" if "seed" in params else "")
              + ". Cases whose verdict still changed between repeats:", ""]
        for name, a in summary["repeat_agreement"].items():
            if a["flipping_items"]:
                L.append(f"- `{name}`: {len(a['flipping_items'])} of {a['items']} cases — "
                         + ", ".join(_case(i) for i in a["flipping_items"]))
        L.append("")
    L += ["## To reproduce", "",
          "Send the transcript's `system_prompt` and `user_prompt` with its `sut.params` to "
          "the same model and endpoint, then mark the output with the same checks:", "",
          "```",
          f"evidence run packs/{manifest['pack']['pack_id']} --repeats {manifest['repeats']}",
          "evidence verify <run> --recompute --pack packs/"
          f"{manifest['pack']['pack_id']}",
          "```", ""]
    return "\n".join(L + _others("vendor"))


# --------------------------------------------------------------------------
# auditor — what each file is and how to check it
# --------------------------------------------------------------------------

def auditor(manifest, results) -> str:
    pack = manifest["pack"]
    judge = manifest.get("judge") or {}
    corpus = judge.get("corpus") or {}
    reg = manifest.get("regulatory") or {}
    checks = sum(1 for r in results if str(r.get("judge", "")).startswith("check:"))
    opinions = sum(1 for r in results if not str(r.get("judge", "")).startswith("check:"))
    L = ["# For an auditor — how to check this evidence pack", "",
         _run_line(manifest), "",
         "## What is in the run", "",
         "| file | what it is | how it is checked |", "|---|---|---|",
         "| `transcripts/*.json` | one model call each: prompts, parameters, output, tokens, "
         "latency | record — integrity only |",
         f"| `results.jsonl` | {checks} deterministic check results and {opinions} judge "
         "opinions | checks re-derived from the transcripts; judge opinions integrity only |",
         "| `manifest.json` | what ran: pack, models, endpoints, engine commit, times | "
         "record — integrity only |",
         "| `regulations.json` | the lender's rule-pack assessment | integrity only |",
         "| `evidence/obligations.yaml`, `evidence/thresholds.yaml` | the pack's claims and the "
         "bank's thresholds — inputs | integrity only |",
         "| `evidence/*.json`, `evidence/report.md`, `evidence/readers/*.md` | everything "
         "derived from the above | rebuilt byte for byte |",
         "| `checksums.sha256` | a SHA-256 for every file above | — |", "",
         "## How to check it", "",
         "1. `evidence verify runs/<run>` — every file hashes to its recorded value; nothing "
         "is missing and nothing has been added. One changed digit fails this and names the "
         "file.",
         f"2. `evidence verify runs/<run> --recompute --pack packs/{pack['pack_id']}` — runs "
         f"every deterministic check again from the transcripts ({checks} results) and "
         "rebuilds every derived file, naming the first value that differs. Someone who "
         "edits a number *and* re-seals the checksums still fails here.",
         "3. The web UI's tamper demo does step 1 on a copy with one digit changed.", "",
         "## What cannot be re-derived", "",
         "- The transcripts: they are what the model returned. They can be shown unchanged, "
         "not reproduced — serving is not byte-deterministic.",
         "- The judge's opinions: the same, and they never decide pass or fail.", "",
         "## Model fingerprints", "",
         "Which model, exactly, served each role: a SHA-256 over what the server reports about "
         "itself (serving version; for a NIM its build, active profile and every file's "
         "checksum) and what the node recorded (container image digest, serving arguments, "
         "Hugging Face commit and the SHA-256 of every weights file). The components are in "
         "`manifest.json` under `models`; the fingerprint is the SHA-256 of their JSON with "
         "sorted keys.", "",
         "| role | fingerprint | level | pins |", "|---|---|---|---|",
         *[_fp_row(role, (manifest.get("models") or {}).get(role)) for role in _roles(manifest)],
         "",
         "## Identifiers", "",
         f"- Engine commit `{manifest['engine'].get('git_commit') or '—'}`; pack "
         f"`{pack['pack_id']}` v{pack['version']}, items sha256 `{pack['items_sha256']}`.",
         f"- SDD spec hash `{(pack.get('sdd') or {}).get('spec_sha256', '—')}`, seed "
         f"{(pack.get('sdd') or {}).get('seed', '—')}.",
         f"- Regulation corpus sha256 `{corpus.get('corpus_sha256', '—')}`; rule pack "
         f"`{reg.get('ruleset_id', '—')}` sha256 `{reg.get('ruleset_sha256') or '—'}`.",
         f"- Model calls {manifest.get('started_at')} to {manifest.get('finished_at')}"
         + (f"; checks scored {manifest['scored_at']}." if manifest.get("scored_at") else "."),
         ""]
    return "\n".join(L + _others("auditor"))


def _fp_row(role: str, fp: dict[str, Any] | None) -> str:
    if not fp:
        return f"| {role} | not recorded | — | — |"
    pins = fp_summary(fp).split(": ", 1)[-1]
    flag = " **changed during the run**" if fp.get("changed_during_run") else ""
    return (f"| {role} | `{fp.get('fingerprint')}` | {fp.get('level')} | "
            f"{pins.replace('|', '/')}{flag} |")


def build_readers(manifest, results, summary, diagnosis, recs, decision, obligations,
                  parts) -> dict[str, str]:
    """Every reader report, by relative path under the run."""
    out = {
        "business": business(manifest, summary, decision, recs),
        "credit-risk": credit_risk(manifest, results, summary, diagnosis, recs, decision,
                                   obligations),
        "compliance": compliance(manifest, parts),
        "operations": operations(manifest, results, diagnosis),
        "vendor": vendor(manifest, results, summary, recs),
        "auditor": auditor(manifest, results),
    }
    return {f"evidence/readers/{k}.md": v.rstrip("\n") + "\n" for k, v in out.items()}


__all__ = ["CAUSES", "READERS", "build_readers", "case_interval"]
