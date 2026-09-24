# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Write the evidence pack for a run and seal it with checksums.

Layout inside a run directory::

    manifest.json        what ran: pack, model, endpoint, prompt hash, seeds, git commit
    results.jsonl        one record per (item, repeat, check)
    transcripts/         one file per (item, repeat)
    regulations.json     jurisdiction rule-pack assessment
    evidence/
      report.md          the pack, by obligation — for a validator or supervisor
      summary.json       the numbers behind the report
      decision.json      GO / GO WITH CONDITIONS / NO-GO / INCONCLUSIVE, against thresholds.yaml
      diagnosis.json     a root cause for every failing result
      recommendations.json  what to change, and who can
      thresholds.yaml    the bank's go / no-go thresholds (defaults if none given)
      readers/           the same evidence as a report per reader: business (one page),
                         credit-risk, compliance, operations, vendor, auditor
      obligations.yaml   the pack's claims, copied verbatim
    checksums.sha256     every file above; ``evidence verify`` recomputes and compares

The report says, for each obligation, whether the run *evidences* it,
*contributes* to it, or *does not cover* it — the pack's own claim levels —
and gives the numbers only for checks that actually ran. It opens with the
decision, the root cause of each failure and what to change
(``evidence.evidence.assess``).

Everything under ``evidence/`` except the two inputs (``obligations.yaml``,
``thresholds.yaml``) is derived from the run by one pure function,
``build_evidence``. The writer calls it; ``evidence verify --recompute`` calls it
again and names the first number that no longer follows from the results.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from evidence.aggregate import by_obligation, items_failing_any, repeat_agreement, summarise_checks
from evidence.evidence.assess import (
    DEFAULT_THRESHOLDS,
    decide,
    diagnose,
    recommend,
    report_sections,
)
from evidence.evidence.readers import build_readers

CHECKSUMS = "checksums.sha256"

# What ``needs_audit`` means differs by check; the report must say which.
AUDIT_REASON = {
    "material_omission": "resolved by similarity",
    "decoy_citation": "mentioned a decoy field without giving it as a reason",
}


def _read_results(run: Path) -> list[dict[str, Any]]:
    path = run / "results.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def seal(run: Path) -> int:
    """Write checksums.sha256 over every file in the run (except itself). Returns the count."""
    lines = []
    for path in sorted(p for p in run.rglob("*") if p.is_file() and p.name != CHECKSUMS):
        lines.append(f"{_sha256_file(path)}  {path.relative_to(run).as_posix()}")
    (run / CHECKSUMS).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


def _pct(n: int, d: int) -> str:
    return f"{n}/{d}" if d else "—"


def _report(
    manifest: dict[str, Any],
    summary: dict[str, Any],
    pack_obligations: dict[str, Any],
    regulatory: dict[str, Any],
    lead: list[str] | None = None,
) -> str:
    lines, _ = _report_lines(manifest, summary, pack_obligations, regulatory, lead)
    return "\n".join(lines) + "\n"


def report_parts(
    manifest: dict[str, Any],
    summary: dict[str, Any],
    pack_obligations: dict[str, Any],
    regulatory: dict[str, Any],
) -> dict[str, list[str]]:
    """The full report's sections by name, for the reader reports that reuse them."""
    lines, marks = _report_lines(manifest, summary, pack_obligations, regulatory, None)
    order = sorted(marks.items(), key=lambda kv: kv[1])
    return {name: lines[start:(order[i + 1][1] if i + 1 < len(order) else len(lines))]
            for i, (name, start) in enumerate(order)}


def _report_lines(
    manifest: dict[str, Any],
    summary: dict[str, Any],
    pack_obligations: dict[str, Any],
    regulatory: dict[str, Any],
    lead: list[str] | None,
) -> tuple[list[str], dict[str, int]]:
    marks: dict[str, int] = {"header": 0}
    checks = summary["checks"]
    agreement = summary["repeat_agreement"]
    sut = manifest["sut"]
    judge = manifest.get("judge")
    L: list[str] = []
    L.append(
        f"# Evidence pack — {manifest['pack']['pack_id']} v{manifest['pack']['version']} "
        f"— run {manifest['run_id']}"
    )
    L.append("")
    judge_line = "No judge."
    if judge:
        judge_line = (
            f"Judge: `{judge['model_id']}` ({'on-prem' if judge['on_prem'] else 'cloud'}), "
            "readability and oversight only"
        )
        corpus = judge.get("corpus")
        judge_line += (
            f", citing regulation corpus {corpus['jurisdiction']} "
            f"(sha256 `{corpus['corpus_sha256'][:12]}…`, {corpus['passages']} passages)."
            if corpus
            else ", no regulation corpus."
        )
    L.append(
        f"Assistant under test: `{sut['model_id']}` at `{sut['endpoint']}` "
        f"({'on-prem' if sut['on_prem'] else 'cloud'}). "
        f"{manifest['pack']['items']} items × {manifest['repeats']} repeat(s) = "
        f"{manifest['transcripts']} briefings. " + judge_line
    )
    L.append("")
    L.append(
        "Every figure below is computed from `results.jsonl`; every result points to a "
        "transcript in `transcripts/`; `checksums.sha256` covers all of them."
    )
    L.append("")
    marks["lead"] = len(L)
    L.extend(lead or [])

    def check_lines(name: str) -> list[str]:
        c = checks.get(name)
        if not c:
            return [f"- `{name}` — not run"]
        if c["gated"]:
            line = (
                f"- `{name}` — **{_pct(c['passed'], c['passed'] + c['failed'])} pass** "
                f"(mean score {c['mean_value']})"
            )
            if c["needs_audit"]:
                why = AUDIT_REASON.get(name, "needed a person's judgement")
                line += f"; {c['needs_audit']} result(s) {why}, flagged for audit"
            a = agreement.get(name)
            if a and manifest["repeats"] > 1:
                line += f"; verdict stable across repeats for {_pct(a['stable'], a['items'])} items"
            out = [line]
            if c["failing_items"]:
                out.append("  - failing: " + ", ".join(i.split(":")[2] for i in c["failing_items"]))
            return out
        line = (
            f"- `{name}` — mean {c['mean_value']} (0–1), reported not gated; "
            f"{c['results']} judge calls, all auditable"
        )
        if c.get("citations") is not None:
            line += (
                f"; cited a passage it was given in {c['citations']}/{c['results']}"
                f" ({', '.join(c['cited'])})"
                if c["cited"]
                else ""
            )
        return [line]

    marks["obligations"] = len(L)
    for ob in by_obligation(pack_obligations, checks):
        level = (ob["level"] or "").upper().replace("_", " ")
        L.append(f"## {ob['title']} ({ob['id']}) — {level}")
        L.append("")
        if ob["level"] == "does_not_cover":
            L.append(f"Not covered. {ob['reason']}")
            L.append("")
            continue
        if ob.get("requires"):
            L.append(f"*What the Act requires:* {ob['requires']}")
            if ob.get("passages"):
                L.append(f"*Text:* {', '.join(ob['passages'])} in the regulation corpus.")
            L.append("")
        for c in ob["check_basis"]:
            if c["ran"]:
                lines = check_lines(c["name"])
                if c.get("tests"):
                    lines[0] += f" — *{c['ref']}:* {c['tests']}"
                L.extend(lines)
            else:
                state = "planned, not yet built" if not c["registered"] else "not run in this pack"
                L.append(
                    f"- `{c['name']}` — {state}"
                    + (f" — *{c['ref']}:* {c['tests']}" if c.get("tests") else "")
                )
        if ob.get("judge"):
            j = ob["judge"]
            r = j.get("result")
            L.append(
                f"- judge `{j['name']}` — "
                + (f"mean {r['mean_value']} (0–1), reported not gated" if r else "not run")
                + f" — *{j['ref']}:* {j['tests']}"
            )
        if ob.get("metrics"):
            for name, m in ob["metrics"].items():
                a = agreement
                if name == "repeat_agreement" and a and manifest["repeats"] > 1:
                    worst = min(a.values(), key=lambda x: x["agreement"])
                    L.append(
                        f"- `repeat_agreement` — lowest across checks "
                        f"{_pct(worst['stable'], worst['items'])} — *{m['ref']}:* {m['tests']}"
                    )
                else:
                    L.append(
                        f"- `{name}` — needs more than one repeat — *{m['ref']}:* {m['tests']}"
                    )
        if ob.get("process"):
            pr = ob["process"]
            L.append(
                f"- lender's process (jurisdiction rule pack) — "
                f"**{regulatory.get('status', '—')}** — *{pr['ref']}:* {pr['tests']}"
            )
        if not ob["check_basis"] and not ob.get("judge") and not ob.get("process"):
            L.append("No check that evidences this obligation ran in this pack.")
        L.append("")

    marks["outside_grid"] = len(L)
    placed = {n for ob in by_obligation(pack_obligations, checks) for n in ob["checks"]}
    placed |= {
        ob["judge"]["name"] for ob in by_obligation(pack_obligations, checks) if ob.get("judge")
    }
    extra = [n for n in checks if n not in placed]
    if extra:
        L.append("## Reported outside the obligation grid")
        L.append("")
        for name in extra:
            L.extend(check_lines(name))
        L.append("")

    marks["reproducibility"] = len(L)
    if manifest["repeats"] > 1:
        L.append("## Reproducibility")
        L.append("")
        L.append(
            f"Each item was run {manifest['repeats']} times with the same prompt, "
            "temperature 0 and a fixed seed. Serving stacks are not byte-deterministic; "
            "reproducibility is therefore reported as the share of items whose verdict "
            "was identical across repeats, per check:"
        )
        L.append("")
        for name, a in agreement.items():
            flips = (
                f" — flipping: {', '.join(i.split(':')[2] for i in a['flipping_items'])}"
                if a["flipping_items"]
                else ""
            )
            L.append(f"- `{name}`: {_pct(a['stable'], a['items'])} ({a['agreement']}){flips}")
        L.append("")

    marks["rule_pack"] = len(L)
    juris = regulatory.get("jurisdiction") or "—"
    L.append(f"## Lender's process evidence — jurisdiction rule pack ({juris})")
    L.append("")
    L.append(
        "Separate from the obligations above, which concern the assistant's briefings. "
        "This section evaluates the *deploying lender's* process against the national rule "
        "pack selected by the pack's `regulatory_context.json`: for each rule that applies to "
        "this lender and product, is every required evidence reference present? It does not "
        "read the referenced artefacts or interpret the law."
    )
    L.append("")
    if regulatory.get("status") in ("unscoped", "ruleset_not_found"):
        L.append(f"{regulatory['status']}: {regulatory.get('note')}")
    else:
        L.append(
            f"`{regulatory['ruleset_id']}` v{regulatory['ruleset_version']} "
            f"(sha256 `{regulatory['ruleset_sha256'][:12]}…`), jurisdiction "
            f"{regulatory['jurisdiction']}: **{regulatory['status']}** — "
            f"{regulatory['applicable_rules']} applicable rule(s), "
            f"{regulatory['passed_rules']} pass, {regulatory['failed_rules']} fail, "
            f"{regulatory['advisory_rules']} advisory. {regulatory['note']}. "
            "Findings per rule in `regulations.json`."
        )
    L.append("")

    marks["failures"] = len(L)
    L.append("## Failures, by item")
    L.append("")
    failing = summary["failing"]
    if not failing:
        L.append("None.")
    else:
        L.append("| item | check | repeats failed | detail |")
        L.append("|---|---|---|---|")
        for f in failing:
            L.append(
                f"| {f['item_id'].split(':')[2]} | `{f['check']}` | {f['repeats_failed']} | "
                f"{f['detail'].replace('|', '/')} |"
            )
    L.append("")

    marks["produced"] = len(L)
    L.append("## How this was produced")
    L.append("")
    sdd = manifest["pack"].get("sdd") or {}
    L.append(
        f"- Pack `{manifest['pack']['pack_id']}` v{manifest['pack']['version']}, "
        f"items sha256 `{manifest['pack']['items_sha256'][:12]}…`, "
        f"generated by Synthetic Data Designer from `{sdd.get('spec', '?')}` "
        f"(seed {sdd.get('seed', '?')}), scorecard `{manifest['pack'].get('scorecard_version')}`. "
        "Ground truth was computed before any model call."
    )
    L.append(
        f"- Engine `{manifest['engine']['package']}` {manifest['engine']['version']}"
        + (
            f", commit `{manifest['engine']['git_commit']}`"
            if manifest["engine"].get("git_commit")
            else ""
        )
        + f". Model calls from {manifest['started_at']} to {manifest['finished_at']}"
        + (f"; checks scored {manifest['scored_at']}." if manifest.get("scored_at") else ".")
    )
    L.append(
        f"- Assistant parameters: max_tokens {sut['max_tokens']}; per-call temperature, seed "
        "and prompt hash are in each transcript."
    )
    L.append(
        "- Integrity: `checksums.sha256`. Re-check with `evidence verify <run>`; "
        "re-derive every check result from the transcripts with "
        "`evidence verify <run> --recompute`."
    )
    L.append("")
    marks["non_claims"] = len(L)
    L.append("## What this pack does not claim")
    L.append("")
    L.append(
        "It does not make or score the credit decision, does not grade regulatory compliance, "
        "and does not measure fairness across a population. The judge's scores are a model "
        "opinion about readability and are reported, not gated."
    )
    return L, marks


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2) + "\n"


def build_evidence(run: Path) -> dict[str, str]:
    """Every derived file under evidence/, from the run's own files. Pure: same run, same bytes.

    Reads manifest.json, results.jsonl, regulations.json and the two inputs in
    evidence/ (obligations.yaml, thresholds.yaml). Returns {relative path: content}.
    """
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    results = _read_results(run)
    regulatory = (
        json.loads((run / "regulations.json").read_text(encoding="utf-8"))
        if (run / "regulations.json").is_file()
        else {"status": "unscoped", "note": "no assessment"}
    )
    ev = run / "evidence"
    obligations = (
        yaml.safe_load((ev / "obligations.yaml").read_text(encoding="utf-8")) or {}
        if (ev / "obligations.yaml").is_file()
        else {}
    )
    thresholds = (
        yaml.safe_load((ev / "thresholds.yaml").read_text(encoding="utf-8")) or {}
        if (ev / "thresholds.yaml").is_file()
        else DEFAULT_THRESHOLDS
    )
    checks = summarise_checks(results)
    summary = {
        "checks": checks,
        "repeat_agreement": repeat_agreement(results),
        "failing": items_failing_any(results),
        "obligations": by_obligation(obligations, checks),
    }
    diagnosis = diagnose(results)
    recs = recommend(diagnosis)
    decision = decide(summary, diagnosis, thresholds, obligations)
    readers = build_readers(manifest, results, summary, diagnosis, recs, decision, obligations,
                            report_parts(manifest, summary, obligations, regulatory))
    return {
        "evidence/summary.json": json.dumps(summary, indent=2),
        "evidence/diagnosis.json": _dump(diagnosis),
        "evidence/recommendations.json": _dump(recs),
        "evidence/decision.json": _dump(decision),
        "evidence/report.md": _report(manifest, summary, obligations, regulatory,
                                      lead=report_sections(decision, diagnosis, recs)),
        **readers,
    }


def write_evidence(
    run: Path,
    pack_obligations: dict[str, Any] | None = None,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write evidence/ from manifest + results, then seal the run.

    ``pack_obligations`` and ``thresholds`` are written into evidence/ first when
    given; otherwise what is already there is kept, and thresholds default to the
    engine's.
    """
    ev = run / "evidence"
    ev.mkdir(exist_ok=True)
    if pack_obligations is not None:
        (ev / "obligations.yaml").write_text(
            yaml.safe_dump(pack_obligations, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
    if thresholds is not None or not (ev / "thresholds.yaml").is_file():
        (ev / "thresholds.yaml").write_text(
            "# Go / no-go thresholds. They belong to the bank's model risk team.\n"
            + yaml.safe_dump(thresholds or DEFAULT_THRESHOLDS, sort_keys=False),
            encoding="utf-8",
        )
    files = build_evidence(run)
    (ev / "readers").mkdir(exist_ok=True)
    for rel, body in files.items():
        (run / rel).write_text(body, encoding="utf-8")
    n = seal(run)
    return {"files_sealed": n, "summary": json.loads(files["evidence/summary.json"]),
            "decision": json.loads(files["evidence/decision.json"])}


def copy_pack_obligations(pack_dir: Path, run: Path) -> None:
    src = pack_dir / "obligations.yaml"
    if src.is_file():
        (run / "evidence").mkdir(exist_ok=True)
        shutil.copy(src, run / "evidence" / "obligations.yaml")
