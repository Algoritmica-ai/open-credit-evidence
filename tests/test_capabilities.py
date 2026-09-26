# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""The capability checker, with a fake ``nel`` that writes bundles shaped like NeMo
Evaluator 0.3.0's: no model and no NeMo Evaluator needed."""

import json
import stat
import sys
from pathlib import Path

import pytest

from evidence import capabilities as cap
from evidence.evidence.verify import verify_run
from evidence.nemo.answers import letter

FAKE_NEL = r'''
import json, sys
from pathlib import Path

args = sys.argv[1:]
if args[:2] == ["eval", "run"]:
    cfg = json.loads(Path(args[2]).read_text())
    out = Path(cfg["output"]["dir"])
    for b in cfg["benchmarks"]:
        name = Path(b["name"]).stem.replace("_", "-") if b["name"].endswith(".py") else b["name"]
        name = {"credit-memo": "credit-memo", "knowledge": "mmlu-pro"}.get(name, name)
        d = out / name
        d.mkdir(parents=True)
        bd = {"correct": [{"group": "True", "n": 3, "mean_reward": 1.0}]}
        rows = []
        if name == "credit-memo":
            bd["check_numeric_fidelity"] = [{"group": "True", "n": 1}, {"group": "False", "n": 3}]
            for reward, judge in ((1.0, 5), (0.0, 5), (0.0, 4), (0.0, 2), (1.0, 1)):
                rows.append({"reward": reward, "metadata": {"category": "near_boundary"},
                             "scoring_details": {"judge": {"score": judge}}})
        if name == "mgsm":
            for lang, reward in (("de", 1.0), ("de", 0.0), ("en", 1.0)):
                rows.append({"reward": reward, "metadata": {"category": lang}})
        (d / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        (d / "eval-1.json").write_text(json.dumps({"benchmark": {
            "name": name, "samples": 10, "repeats": b["repeats"],
            "scores": {"pass@1": {"value": 0.4, "ci_lower": -0.08, "ci_upper": 0.9,
                                  "bootstrap_ci_lower": 0.1, "bootstrap_ci_upper": 0.7},
                       "breakdowns": bd}}}))
elif args[0] == "gate":
    o = Path(args[args.index("-o") + 1])
    o.write_text(json.dumps({"verdict": "INCONCLUSIVE", "benchmarks": [
        {"benchmark": "credit-memo", "tier": "critical", "status": "PASS",
         "baseline_score": 0.2, "candidate_score": 0.75, "delta": 0.55,
         "delta_ci_lower": 0.02, "delta_ci_upper": 1.08},
        {"benchmark": "gsm8k", "tier": "supporting", "status": "INSUFFICIENT_EVIDENCE",
         "baseline_score": 0.9, "candidate_score": 0.85, "delta": -0.05,
         "delta_ci_lower": -0.12, "delta_ci_upper": 0.02}]}))
elif args[0] == "compare":
    Path(args[args.index("-o") + 1]).write_text("{}")
'''


@pytest.fixture
def nel(tmp_path):
    exe = tmp_path / "nel"
    exe.write_text(f"#!{sys.executable}\n{FAKE_NEL}")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return str(exe)


def test_the_config_measures_the_model_as_the_engine_runs_it(tmp_path):
    model = cap.Target(url="https://integrate.api.nvidia.com/v1", model="lightning",
                       key_env="NVIDIA_API_KEY")
    cfg = cap.config(model, tmp_path, suite="quick",
                     judge=cap.Target(url="http://node:8204/v1", model="super"))
    m = cfg["services"]["model"]
    assert m["url"].endswith("/v1/chat/completions") and m["api_key"] == "${NVIDIA_API_KEY}"
    assert m["generation"]["temperature"] == 0.0
    assert m["proxy"]["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False
    assert "judge" in cfg["services"]
    names = [b["name"] for b in cfg["benchmarks"]]
    assert names[:2] == ["gsm8k", "mgsm"] and names[2].endswith("knowledge.py")
    credit = next(b for b in cfg["benchmarks"] if b["name"].endswith("credit_memo.py"))
    assert credit["scoring"]["metrics"][0]["type"] == "judge" and credit["max_problems"] == 10
    no_judge = cap.config(model, tmp_path, suite="general")
    assert "judge" not in no_judge["services"] and len(no_judge["benchmarks"]) == 3
    with pytest.raises(ValueError):
        cap.config(model, tmp_path, suite="everything")


def test_a_run_is_summarised_sealed_and_says_where_the_judge_was_fooled(tmp_path, nel):
    out = cap.run("lightning", cap.Target(url="http://node:8200/v1", model="lightning"),
                  suite="quick", judge=cap.Target(url="http://node:8204/v1", model="super"),
                  pack=Path("packs/underwriter-de"), root=tmp_path, nel=nel)
    s = json.loads((out / "capabilities.json").read_text())
    cm = s["benchmarks"]["credit-memo"]
    assert cm["ci"] == [0.1, 0.7]  # the bootstrap interval, not the one below 0
    assert cm["checks"]["numeric_fidelity"] == 0.25
    j = cm["judge"]
    assert (j["fooled"], j["doubted"], j["memos"]) == (2, 1, 5)
    assert s["benchmarks"]["mgsm"]["by_category"]["de"] == {"score": 0.5, "n": 2}
    text = (out / "report.md").read_text()
    assert "a judge alone would have passed them" in text and "German maths alone: 50.0%" in text
    assert "`xstest`" in text  # what is not measured, and why
    assert verify_run(out).ok and s["run"]["nel_exit"] == 0


def test_a_gate_is_written_in_plain_words_and_sealed(tmp_path, nel):
    base, cand = tmp_path / "base", tmp_path / "cand"
    for d in (base, cand):
        (d / "nel").mkdir(parents=True)
    g = cap.gate(base, cand, nel=nel)
    assert g["verdict"] == "INCONCLUSIVE" and (cand / "gate-policy.yaml").is_file()
    md = (cand / "gate.md").read_text()
    assert "+55.0 pts" in md and "too few problems to tell" in md and "passed" in md
    policy = json.loads((cand / "gate-policy.yaml").read_text())
    assert policy["benchmarks"]["credit-memo"] == {"tier": "critical", "max_drop": 0.0}
    assert verify_run(cand).ok


def test_without_nel_the_message_says_how_to_get_it(monkeypatch):
    monkeypatch.delenv("EVIDENCE_NEL", raising=False)
    monkeypatch.setenv("PATH", "/nonexistent")
    with pytest.raises(FileNotFoundError, match="nemo-evaluator"):
        cap._nel()


@pytest.mark.parametrize("reply,expected", [
    ("so it is D.\n\nAnswer: D", "D"),
    ("This corresponds to option D.\n\nAnswer: $D$", "D"),
    ("Answer: (b)", "B"),
    ("Answer: **H**", "H"),
    ("Answer: \\boxed{F}", "F"),
    ("First I thought Answer: A, but no.\nAnswer: C", "C"),
    ("G) Strategy and implementation", None),
])
def test_the_answer_reader_takes_the_forms_models_write(reply, expected):
    assert letter(reply) == expected
