# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""The capability checker: what a model can do, measured with NVIDIA NeMo Evaluator.

A credit memo test shows how the assistant does at its job. Before a changed or
fine-tuned assistant replaces the current one, two more questions need an answer: did
the change break anything else, and is the improvement real or noise? This module runs
NVIDIA's open-source NeMo Evaluator (``nel``) over a suite of benchmarks and answers both:

- **Arithmetic** (``gsm8k``), the assistant's main weakness in our tests;
- **Maths in eleven languages, German included** (``mgsm``);
- **Knowledge and reasoning** (``mmlu_pro``);
- **Credit memos** (``evidence/nemo/credit_memo.py``): our six checks decide each memo;
  a judge on another model scores its usefulness beside them, never in their place.

``run`` measures one model and keeps the result in a folder of its own, sealed like a
test and anchored when anchoring is on. ``gate`` sets a candidate against a baseline
with ``nel compare`` (which problems flipped, and whether the change is significant) and
``nel gate`` (GO / NO-GO / INCONCLUSIVE under a release policy).

The model is measured as the engine runs it: temperature 0 and, for Nemotron models,
thinking switched off, which is also what makes the benchmarks' answer extraction work
(with thinking on, Lightning's reasoning precedes the answer without an opening tag, and
the extractors read the reasoning). NeMo Evaluator runs in its own Python environment;
``EVIDENCE_NEL`` names its ``nel`` if it is not on the PATH. Standalone: the engine does
not depend on it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SRC = Path(__file__).resolve().parents[1]  # the directory holding the evidence package
NEMO = Path(__file__).resolve().parent / "nemo"
CREDIT_BENCH = NEMO / "credit_memo.py"
KNOWLEDGE_BENCH = NEMO / "knowledge.py"  # mmlu_pro with a reader that finds the answer

# name -> (what it measures, problems in "standard", in "quick")
BENCHMARKS: dict[str, tuple[str, int, int]] = {
    "gsm8k": ("Arithmetic: grade-school word problems", 100, 20),
    "mgsm": ("Maths in eleven languages, German included", 110, 22),
    "mmlu-pro": ("Knowledge and reasoning across 14 subjects (MMLU-Pro)", 100, 20),
    "credit-memo": ("Credit memos: the six checks decide; a judge scores usefulness", 0, 10),
}
SUITES = {"standard": list(BENCHMARKS), "quick": list(BENCHMARKS),
          "general": ["gsm8k", "mgsm", "mmlu-pro"]}
FILES = {"credit-memo": CREDIT_BENCH, "mmlu-pro": KNOWLEDGE_BENCH}
# Built-in benchmarks left out, and why (NeMo Evaluator 0.3.0).
GAPS = {
    "xstest": "its dataset URL is out of date upstream (the file was renamed), so it fails",
    "lm-eval://ifeval": "needs the langdetect package and NLTK's punkt_tab data, which "
                        "nemo-evaluator[all] does not bring",
}
DEFAULT_POLICY = {
    "version": 1,
    "defaults": {"tier": "supporting", "max_drop": 0.05, "metric": "pass@1"},
    "benchmarks": {"credit-memo": {"tier": "critical", "max_drop": 0.0}},
}


@dataclass
class Target:
    """A model behind an OpenAI-compatible endpoint. The key is named, never stored."""

    url: str  # the base URL, ending in /v1
    model: str
    key_env: str | None = None  # the environment variable holding its API key
    thinking: bool = False

    @classmethod
    def from_role(cls, role: str) -> Target:
        from evidence.adapters.nvidia_build import endpoint_for

        ep = endpoint_for(role)
        return cls(url=ep.base_url.rstrip("/"), model=ep.model_id,
                   key_env="NVIDIA_API_KEY" if ep.is_build else None)


def _service(t: Target, max_tokens: int) -> dict[str, Any]:
    svc: dict[str, Any] = {
        "type": "api", "url": t.url.rstrip("/") + "/chat/completions",
        "protocol": "chat_completions", "model": t.model,
        "generation": {"temperature": 0.0, "max_tokens": max_tokens},
        "proxy": {"request_timeout": 300, "max_retries": 2,
                  "extra_body": {"chat_template_kwargs": {"enable_thinking": t.thinking}}},
    }
    if t.key_env:
        svc["api_key"] = "${" + t.key_env + "}"  # expanded by nel from the environment
    return svc


def config(model: Target, out: Path, *, suite: str = "standard", judge: Target | None = None,
           repeats: int = 2) -> dict[str, Any]:
    """The NeMo Evaluator configuration for one model over a suite."""
    if suite not in SUITES:
        raise ValueError(f"unknown suite {suite!r}; one of {sorted(SUITES)}")
    services = {"model": _service(model, 4096)}
    if judge:
        services["judge"] = _service(judge, 1024)
    benches = []
    for name in SUITES[suite]:
        _, standard, quick = BENCHMARKS[name]
        n = quick if suite == "quick" else standard
        solver: dict[str, Any] = {"type": "simple", "service": "model"}
        b: dict[str, Any] = {"name": str(FILES.get(name, name)), "repeats": repeats,
                             "solver": solver}
        if n:
            b["max_problems"] = n
        if name == "credit-memo" and judge:
            b["scoring"] = {"metrics": [{"type": "judge", "name": "underwriter_usefulness",
                                         "service": "judge"}]}
        benches.append(b)
    return {"services": services, "benchmarks": benches, "output": {"dir": str(out)}}


def _nel(nel: str | None = None) -> str:
    exe = nel or os.environ.get("EVIDENCE_NEL") or shutil.which("nel")
    if not exe:
        raise FileNotFoundError(
            "NeMo Evaluator's nel was not found: pip install 'nemo-evaluator[all]' (in its "
            "own environment) and put nel on the PATH, or set EVIDENCE_NEL to its path")
    return exe


def _env(pack: Path, setup: str, judge: bool) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(SRC), env.get("PYTHONPATH", "")) if p)
    env.update(CREDIT_PACK=str(pack.resolve() / "items.jsonl") if pack.is_dir()
               else str(pack.resolve()), CREDIT_SETUP=setup, CREDIT_JUDGE="on" if judge else "off")
    return env


def run(name: str, model: Target, *, suite: str = "standard", judge: Target | None = None,
        pack: Path = Path("packs/underwriter-de"), setup: str = "as_is", repeats: int = 2,
        root: Path = Path("capabilities"), nel: str | None = None) -> Path:
    """Measure one model; returns the folder holding the result, sealed (and anchored)."""
    exe = _nel(nel)
    out = (root / f"{name}-{datetime.now(UTC).strftime('%Y-%m-%dT%H%M%SZ')}").resolve()
    out.mkdir(parents=True)
    cfg = config(model, out / "nel", suite=suite, judge=judge, repeats=repeats)
    (out / "config.yaml").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    meta = {"name": name, "suite": suite, "model": model.model, "url": model.url,
            "thinking": model.thinking, "judge": judge.model if judge else None,
            "pack": str(pack), "setup": setup, "repeats": repeats,
            "started_at": datetime.now(UTC).isoformat(timespec="seconds")}
    with (out / "nel.log").open("w", encoding="utf-8") as log:
        proc = subprocess.run([exe, "eval", "run", str(out / "config.yaml")], cwd=out,
                              env=_env(pack, setup, judge is not None), stdout=log,
                              stderr=subprocess.STDOUT, check=False)
    meta.update(finished_at=datetime.now(UTC).isoformat(timespec="seconds"),
                nel_exit=proc.returncode)
    summary = summarise(out / "nel") | {"run": meta}
    if proc.returncode != 0:  # what went wrong, from nel's own words
        tail = (out / "nel.log").read_text(encoding="utf-8").splitlines()[-12:]
        summary["error"] = "\n".join(line for line in tail if line.strip())
    (out / "capabilities.json").write_text(json.dumps(summary, indent=2) + "\n",
                                           encoding="utf-8")
    (out / "report.md").write_text(report(summary), encoding="utf-8")
    _seal(out, "capabilities")
    return out


def _seal(out: Path, what: str) -> None:
    from evidence import anchor
    from evidence.evidence.writer import seal

    seal(out)
    anchor.anchor(out, what)  # a no-op when anchoring is off


def _bench_name(d: Path) -> str:
    return d.name


def summarise(nel_out: Path) -> dict[str, Any]:
    """Scores per benchmark from nel's bundles, with the bootstrap 95% interval (the
    normal-approximation interval nel also reports can fall below 0 on small samples)."""
    benches: dict[str, Any] = {}
    for bundle in sorted(nel_out.glob("*/eval-*.json")):
        b = json.loads(bundle.read_text(encoding="utf-8"))["benchmark"]
        p1 = (b.get("scores") or {}).get("pass@1") or {}
        name = _bench_name(bundle.parent)
        row: dict[str, Any] = {
            "measures": BENCHMARKS.get(name, (b["name"],))[0], "samples": b.get("samples"),
            "repeats": b.get("repeats"), "score": p1.get("value"),
            "ci": [p1.get("bootstrap_ci_lower", p1.get("ci_lower")),
                   p1.get("bootstrap_ci_upper", p1.get("ci_upper"))],
        }
        bd = (b.get("scores") or {}).get("breakdowns") or {}
        by = _by_category(bundle.parent / "results.jsonl")
        if by:
            row["by_category"] = by
        checks = {k.removeprefix("check_"): next((g["n"] for g in v if g["group"] == "True"), 0)
                  / max(1, sum(g["n"] for g in v)) for k, v in bd.items()
                  if k.startswith("check_")}
        if checks:
            row["checks"] = checks
        if name == "credit-memo":
            row |= _judged(bundle.parent / "results.jsonl")
        benches[name] = row
    return {"benchmarks": benches, "gaps": GAPS}


def _by_category(results: Path) -> dict[str, Any]:
    """Scores per category (per language for mgsm), from the per-problem results: nel's own
    breakdown leaves categories out when a benchmark is repeated."""
    if not results.is_file():
        return {}
    groups: dict[str, list[float]] = {}
    for line in results.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            cat = (r.get("metadata") or {}).get("category")
            if cat:
                groups.setdefault(str(cat), []).append(float(r["reward"]))
    return {k: {"score": round(sum(v) / len(v), 4), "n": len(v)}
            for k, v in sorted(groups.items())} if len(groups) > 1 else {}


def _judged(results: Path) -> dict[str, Any]:
    """The judge beside the checks: its mean score, and where the two disagree."""
    if not results.is_file():
        return {}
    rows = [json.loads(line) for line in results.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    pairs = [(r["reward"], (r.get("scoring_details") or {}).get("judge", {}).get("score"))
             for r in rows]
    pairs = [(c, j) for c, j in pairs if isinstance(j, int | float)]
    if not pairs:
        return {}
    passed = [j for c, j in pairs if c == 1.0]
    failed = [j for c, j in pairs if c != 1.0]
    return {"judge": {
        "memos": len(pairs), "mean": round(sum(j for _, j in pairs) / len(pairs), 2),
        "mean_when_checks_pass": round(sum(passed) / len(passed), 2) if passed else None,
        "mean_when_checks_fail": round(sum(failed) / len(failed), 2) if failed else None,
        # a memo with a proven mistake the judge rated 4 or 5: the judge was fooled
        "fooled": sum(1 for j in failed if j >= 4),
        # a memo that passed every check the judge rated 1 or 2: for a person to look at
        "doubted": sum(1 for j in passed if j <= 2),
    }}


def gate(baseline: Path, candidate: Path, *, policy: Path | None = None,
         nel: str | None = None) -> dict[str, Any]:
    """Set a candidate against a baseline: ``nel compare`` and ``nel gate``. Writes
    ``gate.json``, ``compare.json`` and ``gate.md`` into the candidate's folder."""
    exe = _nel(nel)
    if policy is None:
        policy = candidate / "gate-policy.yaml"
        policy.write_text(json.dumps(DEFAULT_POLICY, indent=2) + "\n", encoding="utf-8")
    b, c = baseline / "nel", candidate / "nel"
    subprocess.run([exe, "compare", str(b), str(c), "--no-strict", "-o",
                    str(candidate / "compare.json")], capture_output=True, check=False)
    g = subprocess.run([exe, "gate", str(b), str(c), "-p", str(policy), "--format", "json",
                        "--no-strict", "--no-report", "-o", str(candidate / "gate.json")],
                       capture_output=True, text=True, check=False)
    res = json.loads((candidate / "gate.json").read_text(encoding="utf-8")) if (
        candidate / "gate.json").is_file() else {"verdict": "ERROR", "error": g.stderr[-500:]}
    res["baseline"], res["candidate"] = baseline.name, candidate.name
    (candidate / "gate.md").write_text(gate_report(res), encoding="utf-8")
    _seal(candidate, "capability-gate")
    return res


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{100 * v:.1f}%"


def report(s: dict[str, Any]) -> str:
    run_ = s["run"]
    lines = [f"# Capabilities: {run_['model']}", "",
             f"Measured with NVIDIA NeMo Evaluator, {run_['started_at']}. Temperature 0, "
             f"thinking {'on' if run_['thinking'] else 'off'}, {run_['repeats']} repeat(s). "
             f"Credit memos from `{run_['pack']}` ({run_['setup']}).", "",
             "| Capability | What it measures | Score | 95% interval | Problems |",
             "|---|---|---|---|---|"]
    for name, b in s["benchmarks"].items():
        lo, hi = b["ci"]
        lines.append(f"| `{name}` | {b['measures']} | {_pct(b['score'])} | "
                     f"{_pct(lo)} – {_pct(hi)} | {b['samples']} |")
    cm = s["benchmarks"].get("credit-memo")
    if cm and cm.get("checks"):
        lines += ["", "## Credit memos, check by check", "",
                  "| Check | Memos that passed |", "|---|---|"]
        lines += [f"| {k} | {_pct(v)} |" for k, v in cm["checks"].items()]
    if cm and cm.get("judge"):
        j = cm["judge"]
        lines += ["", "## The judge beside the checks", "",
                  f"Usefulness to an underwriter, 1–5, over {j['memos']} memos: mean {j['mean']} "
                  f"({j['mean_when_checks_pass']} where every check passed, "
                  f"{j['mean_when_checks_fail']} where one failed).", "",
                  f"- **{j['fooled']}** memo(s) with a proven mistake the judge rated 4 or 5: "
                  "a judge alone would have passed them.",
                  f"- **{j['doubted']}** memo(s) that passed every check the judge rated 1 or 2: "
                  "for a person to look at.", "",
                  "The checks decide; the judge is reported, never gated."]
    mg = s["benchmarks"].get("mgsm", {}).get("by_category", {})
    if "de" in mg:
        lines += ["", f"German maths alone: {_pct(mg['de']['score'])} of {mg['de']['n']} "
                  "answers."]
    if "mmlu-pro" in s["benchmarks"]:
        lines += ["", "`mmlu-pro` is NeMo Evaluator's MMLU-Pro with an answer reader that also "
                  "takes \"Answer: $D$\": its own reader misses that form and scores right "
                  "answers as wrong."]
    if s.get("error"):
        lines += ["", "## NeMo Evaluator stopped with an error", "", "```", s["error"], "```",
                  "", "The full output is in `nel.log`."]
    lines += ["", "## Not measured", ""] + [f"- `{k}`: {v}." for k, v in s["gaps"].items()]
    return "\n".join(lines) + "\n"


STATUS = {"PASS": "passed", "BREACH": "got worse beyond the limit",
          "INSUFFICIENT_EVIDENCE": "too few problems to tell", "MISSING": "not in both runs"}
VERDICT = {"GO": "GO: the candidate may replace the baseline",
           "NO-GO": "NO-GO: something got worse beyond the policy's limit",
           "INCONCLUSIVE": "INCONCLUSIVE: not enough evidence either way; measure with more "
                           "problems (the standard suite) or more repeats"}


def gate_report(g: dict[str, Any]) -> str:
    lines = [f"# Release gate: {VERDICT.get(g.get('verdict'), g.get('verdict'))}", "",
             f"Baseline `{g.get('baseline')}`, candidate `{g.get('candidate')}`. Measured with "
             "NeMo Evaluator's `nel gate`; the interval is its 95% interval on the change.", "",
             "| Capability | Tier | Before | After | Change | 95% interval | Result |",
             "|---|---|---|---|---|---|---|"]
    rows = g.get("benchmarks") or []
    for b in rows if isinstance(rows, list) else []:
        def pts(v: Any) -> str:
            return f"{100 * v:+.1f} pts" if isinstance(v, int | float) else "—"

        lo, hi = b.get("delta_ci_lower"), b.get("delta_ci_upper")
        lines.append(f"| `{b.get('benchmark')}` | {b.get('tier')} | {_pct(b.get('baseline_score'))}"
                     f" | {_pct(b.get('candidate_score'))} | {pts(b.get('delta'))} | "
                     f"{pts(lo)} to {pts(hi)} | {STATUS.get(b.get('status'), b.get('status'))} |")
    if g.get("error"):
        lines += ["", f"Error: {g['error']}"]
    return "\n".join(lines) + "\n"
