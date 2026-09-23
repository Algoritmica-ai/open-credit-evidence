# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Decision, root causes, recommendations, compare — and that every one re-derives.

Unit tests on hand-built results, then the committed runs: their evidence must
rebuild byte for byte, a hand-edited number must be named even after re-sealing,
and the answer must not depend on Python's hash seed. No network.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from evidence.evidence import verify_run
from evidence.evidence.assess import DEFAULT_THRESHOLDS, decide, diagnose, recommend
from evidence.evidence.compare import compare_runs
from evidence.evidence.writer import build_evidence, seal
from evidence.pack import load_pack

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
PACK = ROOT / "packs" / "underwriter-sample"
committed = pytest.mark.skipif(not (RUNS / "2026-09-20-onprem").is_dir(), reason="no committed run")


def res(item: str, check: str, passed: bool, repeat: int = 0, **evidence) -> dict:
    return {"item_id": f"p:case_review:{item}:complete", "repeat": repeat, "check": check,
            "judge": f"check:{check}", "passed": passed, "value": 1.0 if passed else 0.0,
            "detail": "", "evidence": [evidence] if evidence else [], "needs_audit": False}


# --------------------------------------------------------------- diagnosis

def test_wrong_figure_explains_the_omission_and_the_lever():
    r = [res("A", "numeric_fidelity", False, value="38.2%", grounded=False),
         res("A", "material_omission", False, ref="dti_ratio", matched=False),
         res("A", "flip_accuracy", False, ref="gross_annual", expected="increase")]
    d = diagnose(r)
    assert {x["cause"] for x in d["records"]} == {"miscalculated"}
    assert d["records"][0]["detail"]["figures_not_in_file"] == ["38.2%"]


def test_fact_left_out_with_correct_figures_is_skipped():
    d = diagnose([res("A", "material_omission", False, ref="dti_ratio", matched=False),
                  res("A", "numeric_fidelity", True)])
    assert [x["cause"] for x in d["records"]] == ["skipped"]


def test_decoy_and_lever_causes_and_their_wording():
    d = diagnose([
        res("A", "decoy_citation", False, ref="age_band", cited=True, sentence="Age is a risk."),
        res("B", "flip_accuracy", False, ref="gross_annual", expected="increase"),
    ])
    causes = {x["cause"] for x in d["records"]}
    assert causes == {"decoy_blamed", "wrong_lever"}
    recs = {r["cause"]: r for r in recommend(d)}
    assert "age band" in recs["decoy_blamed"]["action"]
    assert "gross annual increase" in recs["wrong_lever"]["action"]


def test_passing_briefings_have_no_diagnosis():
    assert diagnose([res("A", "material_omission", True)])["failures"] == 0


def test_cause_ties_break_by_name():
    d = diagnose([res("A", "decoy_citation", False, ref="x", cited=True),
                  res("B", "flip_accuracy", False, ref="y", expected="increase")])
    assert [c["cause"] for c in d["causes"]] == ["decoy_blamed", "wrong_lever"]


# ---------------------------------------------------------------- decision

def _summary(passed: int, failed: int, agreement: float = 1.0) -> dict:
    checks = {n: {"passed": passed, "failed": failed, "gated": True}
              for n in DEFAULT_THRESHOLDS["checks"]}
    return {"checks": checks,
            "repeat_agreement": {n: {"agreement": agreement} for n in checks}}


def test_all_passing_is_go():
    d = decide(_summary(20, 0), {"causes": []}, DEFAULT_THRESHOLDS, {})
    assert d["verdict"] == "GO"


def test_a_check_below_conditional_is_no_go():
    d = decide(_summary(10, 10), {"causes": []}, DEFAULT_THRESHOLDS, {})
    assert d["verdict"] == "NO-GO"


def test_too_few_results_is_inconclusive_not_go():
    d = decide(_summary(3, 0), {"causes": []}, DEFAULT_THRESHOLDS, {})
    assert d["verdict"] == "INCONCLUSIVE"


def test_unstable_repeats_add_a_condition():
    d = decide(_summary(20, 0, agreement=0.5), {"causes": []}, DEFAULT_THRESHOLDS, {})
    assert d["verdict"] == "GO WITH CONDITIONS"
    assert any("across repeats" in c for c in d["conditions"])


def test_the_banks_thresholds_decide():
    lenient = {**DEFAULT_THRESHOLDS,
               "checks": {n: {"go": 0.4, "conditional": 0.1} for n in DEFAULT_THRESHOLDS["checks"]}}
    assert decide(_summary(10, 10), {"causes": []}, lenient, {})["verdict"] == "GO"


# ------------------------------------------------------------------ compare

def _run(tmp: Path, name: str, verdicts: dict[str, list[bool]], model: str = "m") -> Path:
    run = tmp / name
    run.mkdir()
    (run / "manifest.json").write_text(json.dumps({
        "run_id": name, "pack": {"items_sha256": "x"}, "repeats": 2,
        "sut": {"model_id": model, "endpoint": "e", "prompt_version": "p", "params": {}}}))
    lines = []
    for i in range(20):
        for check, per_item in verdicts.items():
            for rep in range(2):
                lines.append(json.dumps(res(f"C{i}", check, per_item[i], rep)))
    (run / "results.jsonl").write_text("\n".join(lines) + "\n")
    return run


def test_a_clear_gain_is_accepted(tmp_path):
    a = _run(tmp_path, "a", {"numeric_fidelity": [i < 8 for i in range(20)]})
    b = _run(tmp_path, "b", {"numeric_fidelity": [i < 18 for i in range(20)]}, model="m2")
    c = compare_runs(a, b)
    assert c["verdict"] == "ACCEPT"
    assert c["checks"][0]["helped"] == 10 and c["checks"][0]["hurt"] == 0
    assert c["changed"] == [{"what": "assistant model", "before": "m", "after": "m2"}]


def test_a_clear_loss_is_rejected(tmp_path):
    a = _run(tmp_path, "a", {"numeric_fidelity": [i < 18 for i in range(20)]})
    b = _run(tmp_path, "b", {"numeric_fidelity": [i < 8 for i in range(20)]})
    assert compare_runs(a, b)["verdict"] == "REJECT"


def test_a_loss_inside_the_noise_is_inconclusive(tmp_path):
    before = [True] * 20
    after = [True] * 19 + [False]
    a = _run(tmp_path, "a", {"material_omission": before})
    b = _run(tmp_path, "b", {"material_omission": after})
    c = compare_runs(a, b)
    assert c["checks"][0]["status"] == "possibly_worse"
    assert c["verdict"] == "INCONCLUSIVE"


def test_identical_runs_have_no_effect(tmp_path):
    a = _run(tmp_path, "a", {"material_omission": [True] * 20})
    b = _run(tmp_path, "b", {"material_omission": [True] * 20})
    c = compare_runs(a, b)
    assert c["verdict"] == "NO EFFECT" and c["changed"] == []


# ---------------------------------------------------------- committed runs

@committed
@pytest.mark.parametrize("name", sorted(p.name for p in RUNS.iterdir() if p.is_dir())
                         if RUNS.is_dir() else [])
def test_committed_runs_verify_and_rederive(name):
    v = verify_run(RUNS / name, load_pack(PACK), recompute=True)
    assert v.ok, v.message
    assert "evidence files rebuilt from the results and match" in v.message


@committed
def test_an_edited_number_is_named_even_after_resealing(tmp_path):
    run = tmp_path / "run"
    shutil.copytree(RUNS / "2026-09-20-onprem", run)
    p = run / "evidence" / "decision.json"
    d = json.loads(p.read_text())
    d["checks"][1]["pass_rate"] = 0.99
    p.write_text(json.dumps(d, indent=2) + "\n")
    seal(run)
    v = verify_run(run, load_pack(PACK), recompute=True)
    assert not v.ok
    assert "evidence/decision.json: checks[1].pass_rate recorded 0.99" in v.message


@committed
def test_evidence_does_not_depend_on_hash_seed():
    code = ("import sys, hashlib, pathlib; from evidence.evidence.writer import build_evidence; "
            "out = build_evidence(pathlib.Path(sys.argv[1])); "
            "print(hashlib.sha256(''.join(k + v for k, v in sorted(out.items())).encode())"
            ".hexdigest())")
    digests = {subprocess.run([sys.executable, "-c", code, str(RUNS / "2026-09-20-onprem")],
                              env={**os.environ, "PYTHONHASHSEED": s}, capture_output=True,
                              text=True, check=True).stdout
               for s in ("0", "1", "7", "12345")}
    assert len(digests) == 1


@committed
def test_build_evidence_matches_what_is_committed():
    for rel, body in build_evidence(RUNS / "2026-09-20-build").items():
        assert (RUNS / "2026-09-20-build" / rel).read_text(encoding="utf-8") == body, rel
