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
      obligations.yaml   the pack's claims, copied verbatim
    checksums.sha256     every file above; ``evidence verify`` recomputes and compares

The report says, for each obligation, whether the run *evidences* it,
*contributes* to it, or *does not cover* it — the pack's own claim levels —
and gives the numbers only for checks that actually ran.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from evidence.aggregate import by_obligation, items_failing_any, repeat_agreement, summarise_checks

CHECKSUMS = "checksums.sha256"


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
) -> str:
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
                line += f"; {c['needs_audit']} result(s) resolved by similarity, flagged for audit"
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

    for ob in by_obligation(pack_obligations, checks):
        level = (ob["level"] or "").upper().replace("_", " ")
        L.append(f"## {ob['title']} ({ob['id']}) — {level}")
        L.append("")
        if ob["level"] == "does_not_cover":
            L.append(f"Not covered. {ob['reason']}")
        elif not ob["checks"]:
            L.append("No check that evidences this obligation ran in this pack.")
        else:
            for name in ob["checks"]:
                L.extend(check_lines(name))
        if ob["not_run"] and ob["level"] != "does_not_cover":
            L.append(f"- Declared in the grid, not run: {', '.join(ob['not_run'])}")
        L.append("")

    extra = [
        n
        for n in checks
        if not any(n in ob["checks"] for ob in by_obligation(pack_obligations, checks))
    ]
    if extra:
        L.append("## Reported outside the obligation grid")
        L.append("")
        for name in extra:
            L.extend(check_lines(name))
        L.append("")

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
        + f". Started {manifest['started_at']}, finished {manifest['finished_at']}."
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
    L.append("## What this pack does not claim")
    L.append("")
    L.append(
        "It does not make or score the credit decision, does not grade regulatory compliance, "
        "and does not measure fairness across a population. The judge's scores are a model "
        "opinion about readability and are reported, not gated."
    )
    return "\n".join(L) + "\n"


def write_evidence(run: Path, pack_obligations: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build evidence/ from manifest + results, copy obligations, then seal the run."""
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    results = _read_results(run)
    regulatory = (
        json.loads((run / "regulations.json").read_text(encoding="utf-8"))
        if (run / "regulations.json").is_file()
        else {"status": "unscoped", "note": "no assessment"}
    )
    ev = run / "evidence"
    ev.mkdir(exist_ok=True)
    obligations = pack_obligations or {}
    if pack_obligations is not None:
        import yaml

        (ev / "obligations.yaml").write_text(
            yaml.safe_dump(pack_obligations, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
    elif (ev / "obligations.yaml").is_file():
        import yaml

        obligations = yaml.safe_load((ev / "obligations.yaml").read_text(encoding="utf-8")) or {}

    summary = {
        "checks": summarise_checks(results),
        "repeat_agreement": repeat_agreement(results),
        "failing": items_failing_any(results),
        "obligations": by_obligation(obligations, summarise_checks(results)),
    }
    (ev / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (ev / "report.md").write_text(
        _report(manifest, summary, obligations, regulatory), encoding="utf-8"
    )
    n = seal(run)
    return {"files_sealed": n, "summary": summary}


def copy_pack_obligations(pack_dir: Path, run: Path) -> None:
    src = pack_dir / "obligations.yaml"
    if src.is_file():
        (run / "evidence").mkdir(exist_ok=True)
        shutil.copy(src, run / "evidence" / "obligations.yaml")
