# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""The three-agent judge panel, with a scripted model standing in for the NIM."""

import json

import pytest
from test_run_and_verify import stubbed  # noqa: F401 — the stubbed run fixture

from evidence import panel

CASE = ("| Gross annual income | £52,800 |\n| Proposed instalment | £640 |\n"
        "| Existing commitments | £1,120 |\nPolicy: debt-to-income limit 40%\n")
BUNDLE = {
    "item_id": "p:case_review:APP1:complete", "repeat": 0,
    "briefing": "Debt service exceeds the 40% limit; it represents 33.2% of income.",
    "case_file": CASE,
    "checks": [{"name": "claim_consistency", "passed": False, "value": 0.0,
                "detail": "claims above 40%, states 33.2%", "evidence": "[]"},
               {"name": "numeric_fidelity", "passed": True, "value": 1.0,
                "detail": "all figures grounded", "evidence": "[]"}],
    "passages": [{"passage_id": "ai-act-art-14#4", "citation": "AI Act Article 14(4)",
                  "title": "Human oversight", "text": "…override or reverse the output…"},
                 {"passage_id": "ai-act-art-13#1", "citation": "AI Act Article 13(1)",
                  "title": "Transparency", "text": "…interpret a system's output…"}],
}


def _reply(content=None, tool_calls=None):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {"id": "x", "choices": [{"message": msg}], "usage": {"total_tokens": 10},
            "_latency_ms": 5}


def scripted():
    """A model that plays the three roles; the Challenger makes two tool calls first."""
    seen = []

    def call(model, messages, tools=None, **_):
        seen.append({"system": messages[0]["content"][:20], "tools": tools,
                     "n": len(messages)})
        role = messages[0]["content"].split()[3]  # "You are the Reader/Challenger/Arbiter"
        if role == "Reader":
            return _reply(json.dumps({"intelligible": 2, "actionable": 2, "overridable": 2,
                                      "citations": {"intelligible": "[ai-act-art-13#1]",
                                                    "actionable": "ai-act-art-14#4",
                                                    "overridable": "ai-act-art-14#4"},
                                      "reason": "clear"}))
        if role == "Challenger":
            if not any(m["role"] == "tool" for m in messages):
                return _reply(tool_calls=[
                    {"id": "t1", "type": "function", "function": {
                        "name": "find_in_case_file", "arguments": '{"text": "52800"}'}},
                    {"id": "t2", "type": "function", "function": {
                        "name": "check_result", "arguments": '{"name": "claim_consistency"}'}}])
            return _reply("Checked. " + json.dumps({
                "findings": [{"claim": "exceeds the 40% limit", "problem": "states 33.2%",
                              "evidence": "claim_consistency: claims above 40%, states 33.2%",
                              "source": "check:claim_consistency", "severity": "material"}],
                "checks_confirmed": ["claim_consistency", "affordability_check"],
                "checks_disputed": [],
                "summary": "contradicts itself"}))
        assert "exceeds the 40% limit" in messages[1]["content"]  # saw the findings
        return _reply(json.dumps({"intelligible": 2, "actionable": 1, "overridable": 0,
                                  "citations": {"intelligible": "ai-act-art-13#1",
                                                "actionable": "ai-act-art-14#4",
                                                "overridable": "ai-act-art-99#9"},
                                  "flag_for_review": True,
                                  "flag_reasons": ["limit claimed breached, ratio below it"],
                                  "disagrees_with_reader": ["actionable", "overridable"],
                                  "reason": "reads well, contradicts itself"}))

    return call, seen


def test_tools_read_the_bundle():
    assert "£52,800" in panel.run_tool("find_in_case_file", {"text": "52,800"}, BUNDLE)
    assert "£52,800" in panel.run_tool("find_in_case_file", {"text": "£52800"}, BUNDLE)
    assert "not found" in panel.run_tool("find_in_case_file", {"text": "47.5%"}, BUNDLE)
    assert "claim_consistency: FAIL" in panel.run_tool("list_checks", {}, BUNDLE)
    assert json.loads(panel.run_tool("check_result", {"name": "claim_consistency"},
                                     BUNDLE))["passed"] is False
    assert "no check named" in panel.run_tool("check_result", {"name": "x"}, BUNDLE)
    assert panel.run_tool("read_case_file", {}, BUNDLE) == CASE
    assert panel.run_tool("calculate", {"expression": "(640 + 1,120) / (52800/12) * 100"},
                          BUNDLE) == "40"
    assert "cannot calculate" in panel.run_tool(
        "calculate", {"expression": "__import__('os').system('true')"}, BUNDLE)


def test_panel_record_weighs_the_challenger_and_checks_citations():
    call, seen = scripted()
    rec = panel.run_panel(BUNDLE, call=call, models={r: "m" for r in
                                                      ("reader", "challenger", "arbiter")})
    assert rec["reader_scores"] == {"intelligible": 2, "actionable": 2, "overridable": 2}
    assert rec["scores"] == {"intelligible": 2, "actionable": 1, "overridable": 0}
    assert rec["value"] == 0.5 and rec["flag_for_review"] is True
    assert rec["checks_confirmed"] == ["claim_consistency"] == rec["failing_checks"]
    assert rec["invented_check_names"] == ["affordability_check"]
    assert rec["unread_check_verdicts"] == []  # it read claim_consistency with check_result
    assert rec["citations"]["intelligible"] == {"citation": "ai-act-art-13#1",
                                                "in_passages": True}
    assert rec["citations"]["overridable"]["in_passages"] is False
    ch = rec["agents"]["challenger"]
    assert ch["tool_calls"] == 2
    assert [c["name"] for c in ch["steps"][0]["tool_calls"]] == ["find_in_case_file",
                                                                 "check_result"]
    assert "£52,800" in ch["steps"][0]["tool_calls"][0]["result"]
    # only the Challenger was offered tools
    assert [s["tools"] is not None for s in seen] == [False, True, True, False]
    assert rec["error"] is None


def test_an_agent_that_never_answers_is_recorded_not_raised():
    def call(model, messages, tools=None, **_):
        if tools:
            return _reply(tool_calls=[{"id": "t", "type": "function", "function": {
                "name": "list_checks", "arguments": "{}"}}])
        return _reply("I am not sure.")

    out = panel.run_agent("challenger", panel.CHALLENGER, "B", BUNDLE, call=call, model="m",
                          keys=("findings",))
    assert out["parsed"] is None and "no parseable answer" in out["error"]
    assert out["tool_calls"] == panel.MAX_STEPS - 1  # the last turn is without tools


def test_panel_on_a_run_is_recorded_sealed_and_reported(stubbed, tmp_path, monkeypatch):  # noqa: F811
    from evidence import panel_run
    from evidence.corpus import Corpus
    from evidence.evidence import verify_run, write_evidence
    from evidence.runner import run_pack

    run = tmp_path / "run"
    run_pack(stubbed, run, repeats=1, limit=2, corpus="EU", log=lambda s: None)
    write_evidence(run, stubbed.obligations)
    call, _ = scripted()
    monkeypatch.setattr(panel, "chat", lambda base_url, api_key=None, **kw: call(**kw))
    bundles, facts = panel_run.bundles(run, stubbed, Corpus("EU"), limit=None)
    assert len(bundles) == 2 and bundles[0]["case_file"] and bundles[0]["checks"]
    assert facts["passages_by_field"].keys() == {"intelligible", "actionable", "overridable"}
    records, runtime = panel_run.run_direct(bundles, workers=2, log=lambda s: None)
    m = panel_run.record(run, records, facts, runtime, "2026-09-24T00:00:00+00:00")
    assert m["briefings"] == 2 and m["errors"] == 0 and m["gated"] is False
    write_evidence(run)
    v = verify_run(run, stubbed, recompute=True)
    assert v.ok, v.message
    s = json.loads((run / "evidence" / "panel.json").read_text())
    assert s["answered"] == 2 and s["flagged"] == 2 and s["runtime"]["kind"] == "direct"
    assert s["challenger"]["mean_tool_calls"] == 2.0
    assert "# Judge panel" in (run / "evidence" / "panel.md").read_text()
    # a resumed panel keeps what was finished and replaces failures
    failed = [{"item_id": bundles[0]["item_id"], "repeat": 0, "value": None, "error": "x"}]
    panel_run.record(run, failed, facts, runtime, "2026-09-24T00:00:00+00:00")
    rows = [json.loads(x) for x in (run / "panel" / "records.jsonl").read_text().splitlines()]
    assert len(rows) == 2 and not any(r.get("error") for r in rows)


def test_panel_module_runs_on_the_standard_library_alone():
    import ast
    from pathlib import Path

    tree = ast.parse(Path(panel.__file__).read_text())
    mods = {n.names[0].name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)}
    mods |= {n.module.split(".")[0] for n in ast.walk(tree)
             if isinstance(n, ast.ImportFrom) and n.module}
    import sys

    assert mods - {"__future__"} <= set(sys.stdlib_module_names), mods


@pytest.mark.parametrize("text, keys, ok", [
    ('noise {"findings": [], "summary": {"a": 1}} tail', ("findings",), True),
    ('{"intelligible": 1}', ("intelligible", "actionable"), False),
])
def test_parse_json_takes_nested_objects(text, keys, ok):
    assert (panel.parse_json(text, keys) is not None) is ok


def test_a_verdict_on_a_check_it_did_not_read_is_not_counted():
    def call(model, messages, tools=None, **_):
        role = messages[0]["content"].split()[3]
        if role == "Challenger":
            return _reply(json.dumps({"findings": [], "checks_confirmed": ["claim_consistency"],
                                      "checks_disputed": [{"name": "numeric_fidelity",
                                                           "why": "guess"}]}))
        return _reply(json.dumps({"intelligible": 2, "actionable": 2, "overridable": 2,
                                  "flag_for_review": False}))

    rec = panel.run_panel(BUNDLE, call=call, models={r: "m" for r in
                                                      ("reader", "challenger", "arbiter")})
    assert rec["checks_confirmed"] == [] and rec["checks_disputed"] == []
    assert rec["unread_check_verdicts"] == ["claim_consistency", "numeric_fidelity"]
