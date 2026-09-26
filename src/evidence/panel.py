# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""The judge panel: three agents reason about a briefing before an opinion is recorded.

The single readability judge reads a briefing once and gives three scores. It
cannot check a number, and it has given full marks to briefings whose own
figures contradict the limit they claim was breached. The panel splits the job:

- **Reader** reads the briefing as the underwriter would, without the case
  file, and scores it: intelligible, actionable, overridable (0-2 each), with
  the passage of regulation it applied for each.
- **Challenger** looks for what is wrong with it. It has tools: the case file,
  a search over it, and the verdict and evidence of every deterministic check
  run on this briefing. It must back each finding with what a tool returned,
  and may dispute a check it thinks is wrong.
- **Arbiter** reads the briefing, the Reader's scores and the Challenger's
  findings, gives the final scores and citations, and says whether a person
  should look at the briefing and why.

The panel is an opinion, like the judge: it is reported and flags briefings
for review; it never passes or fails one. Every agent's replies, tool calls and
tool results are recorded.

This module is the whole panel and uses the Python standard library only, so
the same file runs in the engine (``evidence panel <run>``) and, copied into a
NemoClaw sandbox, against the sandbox's managed inference route
(``python3 panel.py --in bundles.jsonl --out records.jsonl --base-url
https://inference.local/v1``). The tools read a bundle prepared by the engine:
the case file, the briefing, the check results and the regulation passages.
The checks are deterministic, so their recorded verdicts are what calling
them again would return.
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import json
import operator
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

PANEL_VERSION = "panel-v2"
# v3: the Challenger gets the case file and every check's evidence in its first message
# instead of fetching them one tool call at a time; it keeps the calculator and a search.
PANEL_VERSION_UP_FRONT = "panel-v3"
# v4: v3 plus reference figures the engine computed exactly from the case file (the ratio,
# the limits, the score, the file's age), so the Challenger compares instead of computing.
PANEL_VERSION_FIGURES = "panel-v4"
FIGURES_NOTE = (
    "\n\nREFERENCE FIGURES are given below the case file: the engine computed them exactly "
    "from the case file, and they are correct. Compare every figure and every claim about a "
    "limit, the score, the file's age or missed payments with them. Use calculate only for "
    "a figure they do not cover.")
FIELDS = ("intelligible", "actionable", "overridable")
MAX_PER_FIELD = 2
# Model turns per agent, tool rounds included. The Challenger checks figures one
# tool call at a time: a thorough one makes six or seven before it answers.
MAX_STEPS = {"reader": 4, "challenger": 14, "arbiter": 4}
MAX_TOKENS = 8000  # per turn; a reasoning model can spend thousands of tokens thinking
TOOL_RESULT_CHARS = 4000
TIMEOUT = 600

READER = (
    "You are the Reader on a panel reviewing a credit-referral briefing written by an AI "
    "assistant for a human underwriter. Read it as the underwriter would, without the case "
    "file. The regulation passages below set the standard: the underwriter must be able to "
    "understand the output, see what drives it, and disagree with or override it.\n\n"
    "Score each 0 (no), 1 (partly) or 2 (yes):\n"
    "intelligible: can the underwriter understand the briefing without re-reading the file?\n"
    "actionable: can they tell what would need to change for a different outcome?\n"
    "overridable: does it give them the reasons and the facts they rest on, enough to "
    "disagree with it or reverse it?\n"
    "For each, cite the one passage whose standard you applied: its id exactly as written "
    "in square brackets below, without the brackets.\n\n"
    'Answer with one JSON object and nothing else: {"intelligible": 0-2, "actionable": 0-2, '
    '"overridable": 0-2, "citations": {"intelligible": "<id>", "actionable": "<id>", '
    '"overridable": "<id>"}, "unclear": ["what an underwriter would struggle with"], '
    '"reason": "one or two sentences"}'
)
CHALLENGER = (
    "You are the Challenger on a panel reviewing a credit-referral briefing written by an AI "
    "assistant for a human underwriter. Your job is to find what is wrong with it: figures "
    "that are not in the case file or are computed wrongly, claims that contradict the "
    "briefing's own figures (for example a limit said to be breached when the stated ratio "
    "is below it), factors given the wrong way round, material facts left out, and reasons "
    "that are not real factors.\n\n"
    "Use the tools. Look up every figure you doubt in the case file. A figure the briefing "
    "derives (monthly from annual, a sum, a ratio) is correct if the arithmetic from "
    "case-file figures gives it: work it out with the calculate tool, never in your head, "
    "and report it only if the result differs. A difference that rounding explains (under "
    "half a percentage point, or a few pounds on a figure the briefing rounds) is not an "
    "error. Monthly figures come from annual ones divided by 12.\n"
    "The verdicts of the deterministic checks run on this briefing are listed with it: "
    "they are exact but narrow. Before you confirm or dispute a check, read its evidence "
    "with check_result: a confirmation or dispute of a check you did not read is not "
    "counted. Confirm it only if you can see the problem yourself; dispute it only if the "
    "case file shows it is wrong, and say why. Use only the check names listed. Do not "
    "report anything you have not verified with a tool.\n\n"
    "When you are done, answer with one JSON object and nothing else: "
    '{"findings": [{"claim": "what the briefing says", "problem": "what is wrong", '
    '"evidence": "what the tool showed", "source": "case_file or check:<name>", '
    '"severity": "material or minor"}], "checks_confirmed": ["<check name>"], '
    '"checks_disputed": [{"name": "<check name>", "why": "..."}], '
    '"summary": "one or two sentences"}'
)
ARBITER = (
    "You are the Arbiter on a panel reviewing a credit-referral briefing written by an AI "
    "assistant for a human underwriter. The Reader scored how usable the briefing is; the "
    "Challenger checked it against the case file and the deterministic checks. Weigh both. "
    "A briefing that reads well but misstates a figure, contradicts itself, or leaves out a "
    "material fact does not give the underwriter what they need to disagree with it: that "
    "lowers overridable, and usually actionable. Findings the Challenger did not back with "
    "evidence count for nothing. Flag the briefing for review when there is at least one "
    "material finding backed by evidence, or a failing deterministic check you have no "
    "reason to doubt; not for rounding or style.\n\n"
    "Score each 0 (no), 1 (partly) or 2 (yes): intelligible, actionable, overridable, as "
    "the Reader was asked. Cite for each the one passage whose standard you applied, its id "
    "exactly as written in square brackets below, without the brackets. Say whether a "
    "person should review this briefing before it is relied on.\n\n"
    'Answer with one JSON object and nothing else: {"intelligible": 0-2, "actionable": 0-2, '
    '"overridable": 0-2, "citations": {"intelligible": "<id>", "actionable": "<id>", '
    '"overridable": "<id>"}, "flag_for_review": true or false, "flag_reasons": ["..."], '
    '"disagrees_with_reader": ["<field>"], "reason": "two or three sentences"}'
)

TOOLS = {
    "read_case_file": {
        "description": "The full case file the assistant was given: applicant, income, "
                       "commitments, bureau data, the lender's policy.",
        "parameters": {"type": "object", "properties": {}},
    },
    "find_in_case_file": {
        "description": "Lines of the case file containing a text or number. Numbers match "
                       "without currency signs, thousands separators or percent signs.",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}},
                       "required": ["text"]},
    },
    "list_checks": {
        "description": "Every deterministic check run on this briefing, with its verdict and "
                       "a one-line detail.",
        "parameters": {"type": "object", "properties": {}},
    },
    "calculate": {
        "description": "Evaluate arithmetic exactly: numbers, + - * / and parentheses, e.g. "
                       "'(640 + 1120) / (52800 / 12) * 100'.",
        "parameters": {"type": "object", "properties": {"expression": {"type": "string"}},
                       "required": ["expression"]},
    },
    "check_result": {
        "description": "One deterministic check's verdict, detail and evidence for this "
                       "briefing.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}},
                       "required": ["name"]},
    },
}
ROLE_TOOLS = {"reader": [], "challenger": list(TOOLS), "arbiter": []}
UP_FRONT_TOOLS = ["calculate", "find_in_case_file"]
UP_FRONT_STEPS = 10
THINK_LAST_STEPS = 7  # without reasoning a model can loop on tools: six rounds, then answer

CHALLENGER_UP_FRONT = (
    "You are the Challenger on a panel reviewing a credit-referral briefing written by an AI "
    "assistant for a human underwriter. Your job is to find what is wrong with it: figures "
    "that are not in the case file or are computed wrongly, claims that contradict the "
    "briefing's own figures (for example a limit said to be breached when the stated ratio "
    "is below it), factors given the wrong way round, material facts left out, and reasons "
    "that are not real factors.\n\n"
    "The case file and the verdict and evidence of every deterministic check run on this "
    "briefing are given below. A figure the briefing derives (monthly from annual, a sum, a "
    "ratio) is correct if the arithmetic from case-file figures gives it: work it out with "
    "the calculate tool, never in your head, and report it only if the result differs. A "
    "difference that rounding explains (under half a percentage point, or a few units on a "
    "figure the briefing rounds) is not an error. Monthly figures come from annual ones "
    "divided by 12. Use find_in_case_file if you need a line of the case file again.\n"
    "The checks are exact but narrow. Confirm a check only if you can see the problem "
    "yourself; dispute it only if the case file shows it is wrong, and say why. Use only "
    "the check names given. Do not report a figure you have not verified with a tool.\n\n"
    "When you are done, answer with one JSON object and nothing else: "
    '{"findings": [{"claim": "what the briefing says", "problem": "what is wrong", '
    '"evidence": "what the case file or the calculation shows", "source": "case_file or '
    'check:<name>", "severity": "material or minor"}], "checks_confirmed": ["<check name>"], '
    '"checks_disputed": [{"name": "<check name>", "why": "..."}], '
    '"summary": "one or two sentences"}'
)


# --------------------------------------------------------------------------- tools

def _plain(s: str) -> str:
    return re.sub(r"[£$€,%]", "", s).lower()


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.USub: operator.neg, ast.UAdd: operator.pos}


def calculate(expression: str) -> float:
    """Arithmetic only: numbers, + - * / and parentheses. Nothing else is evaluated."""
    def ev(n: ast.AST) -> float:
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        raise ValueError("only numbers, + - * / and parentheses")
    return ev(ast.parse(re.sub(r"[£$€,%\s]", "", expression), mode="eval"))


def run_tool(name: str, args: dict[str, Any], bundle: dict[str, Any]) -> str:
    """A tool's answer, as text for the model. Reads the bundle only."""
    checks = bundle.get("checks") or []
    if name == "read_case_file":
        return bundle.get("case_file", "")
    if name == "find_in_case_file":
        want = _plain(str(args.get("text", ""))).strip()
        if not want:
            return "give a text or number to look for"
        hits = [ln for ln in bundle.get("case_file", "").splitlines() if want in _plain(ln)]
        return "\n".join(hits[:20]) if hits else f"not found in the case file: {args['text']!r}"
    if name == "list_checks":
        return "\n".join(f"{c['name']}: {'pass' if c['passed'] else 'FAIL'} — {c['detail']}"
                         for c in checks) or "no checks were run"
    if name == "calculate":
        try:
            return f"{calculate(str(args.get('expression', ''))):.6g}"
        except (ValueError, SyntaxError, ZeroDivisionError) as e:
            return f"cannot calculate {args.get('expression')!r}: {e}"
    if name == "check_result":
        c = next((c for c in checks if c["name"] == args.get("name")), None)
        if c is None:
            return f"no check named {args.get('name')!r}; checks: " + ", ".join(
                x["name"] for x in checks)
        return json.dumps(c, ensure_ascii=False)
    return f"unknown tool {name!r}"


# --------------------------------------------------------------------------- model

def chat(base_url: str, model: str, messages: list[dict[str, Any]],
         tools: list[str] | None = None, api_key: str | None = None,
         max_tokens: int = MAX_TOKENS, use_env_proxy: bool = False,
         json_only: bool = False, thinking: bool = True) -> dict[str, Any]:
    """One unstreamed chat completion from an OpenAI-compatible server.

    A self-hosted server is called directly, never through a proxy. Inside a
    NemoClaw sandbox every connection goes through the sandbox's own proxy,
    which enforces its network policy: ``use_env_proxy`` takes it from the
    environment. ``json_only`` has the server constrain the answer to valid JSON
    (after any reasoning).
    """
    body: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": max_tokens,
                            "temperature": 0}
    if tools:
        body["tools"] = [{"type": "function", "function": {"name": n, **TOOLS[n]}}
                         for n in tools]
    if json_only:
        body["response_format"] = {"type": "json_object"}
    if not thinking:  # Nemotron reasoning off for this call (the chat template's switch)
        body["chat_template_kwargs"] = {"enable_thinking": False}
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions",
                                 data=json.dumps(body).encode(), headers=headers, method="POST")
    opener = (urllib.request.build_opener() if use_env_proxy
              else urllib.request.build_opener(urllib.request.ProxyHandler({})))
    t0 = time.time()
    with opener.open(req, timeout=TIMEOUT) as r:
        reply = json.loads(r.read())
    reply["_latency_ms"] = int((time.time() - t0) * 1000)
    return reply


Chat = Callable[..., dict[str, Any]]


class Stopped(Exception):
    """Someone stopped the panel: the briefing in progress is dropped at its next turn."""

_OPEN = re.compile(r"\{")


def parse_json(text: str, keys: tuple[str, ...]) -> dict[str, Any] | None:
    """The first JSON object in the text that has all of ``keys``."""
    decoder = json.JSONDecoder()
    for m in _OPEN.finditer(text or ""):
        try:
            obj, _ = decoder.raw_decode(text, m.start())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and set(keys) <= obj.keys():
            return obj
    return None


def run_agent(role: str, system: str, user: str, bundle: dict[str, Any], *, call: Chat,
              model: str, keys: tuple[str, ...], tools: list[str] | None = None,
              steps_max: int | None = None, thinking: bool = True,
              think_last: bool = False) -> dict[str, Any]:
    """One agent: model turns and tool rounds until it answers, recorded step by step.

    An answer that is empty (the turn's tokens went on reasoning) or not the JSON
    asked for is followed by one more turn, without tools, in which the server
    constrains the reply to valid JSON. So is the last turn, if the agent is
    still calling tools when its turns run out.
    """
    tools = ROLE_TOOLS[role] if tools is None else tools
    steps_max = steps_max or MAX_STEPS[role]
    if think_last and thinking:
        steps_max = min(steps_max, THINK_LAST_STEPS)
    # think_last: the turns that only fetch or compute run without reasoning; the agent then
    # thinks once, over everything it has, for its final answer
    final = False
    messages: list[dict[str, Any]] = [{"role": "system", "content": system},
                                      {"role": "user", "content": user}]
    steps: list[dict[str, Any]] = []
    closing = False  # the next turn is the JSON-only answer
    for n in range(steps_max):
        if n == steps_max - 1 and not closing:
            closing = True
            messages.append({"role": "user", "content": "Stop using tools. Give your final "
                             "answer now, as the JSON object asked for."})
        think = thinking and (not think_last or final or closing)
        reply = call(model=model, messages=messages,
                     tools=None if closing else (tools or None), json_only=closing,
                     **({} if think else {"thinking": False}))
        msg = (reply.get("choices") or [{}])[0].get("message") or {}
        calls = msg.get("tool_calls") or []
        step: dict[str, Any] = {"latency_ms": reply.get("_latency_ms"), "usage": reply.get(
            "usage"), "id": reply.get("id"), "json_only": closing}
        if calls and not closing:
            messages.append({"role": "assistant", "content": msg.get("content") or "",
                             "tool_calls": calls})
            step["tool_calls"] = []
            for c in calls:
                fn = c.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                out = run_tool(fn.get("name", ""), args if isinstance(args, dict) else {},
                               bundle)
                messages.append({"role": "tool", "tool_call_id": c.get("id"),
                                 "content": out[:TOOL_RESULT_CHARS]})
                step["tool_calls"].append({"name": fn.get("name"), "arguments": args,
                                           "result": out[:600], "result_chars": len(out)})
            steps.append(step)
            continue
        text = msg.get("content") or ""
        step["reply"] = text[:6000]
        step["thinking"] = think
        steps.append(step)
        if think_last and thinking and not (final or closing):  # now the one thinking turn
            if text:
                messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user", "content": "Check each finding once more against "
                             "the reference figures and the case file: drop what does not hold, "
                             "add what is missing. Give your final answer: the JSON object "
                             "asked for, and nothing else."})
            final = closing = True
            continue
        parsed = parse_json(text, keys)
        if parsed is None and closing and think_last and think:
            # the reasoning turn ended without an answer: ask once more, answer only
            messages.append({"role": "user", "content": "Give your final answer now: the "
                             "JSON object asked for, and nothing else."})
            again = call(model=model, messages=messages, tools=None, json_only=True,
                         thinking=False)
            amsg = (again.get("choices") or [{}])[0].get("message") or {}
            text = amsg.get("content") or ""
            steps.append({"latency_ms": again.get("_latency_ms"), "usage": again.get("usage"),
                          "id": again.get("id"), "json_only": True, "thinking": False,
                          "reply": text[:6000], "fallback": True})
            parsed = parse_json(text, keys)
        if parsed is None and not closing:  # empty or malformed: one constrained turn
            if text:
                messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user", "content": "Give your final answer now: the "
                             "JSON object asked for, and nothing else."})
            closing = True
            continue
        out = {"role": role, "model": model, "steps": steps, "parsed": parsed,
               "tool_calls": sum(len(s.get("tool_calls", [])) for s in steps)}
        if parsed is None:
            out["error"] = "no parseable answer, even constrained to JSON"
        return out
    return {"role": role, "model": model, "steps": steps, "parsed": None,
            "tool_calls": sum(len(s.get("tool_calls", [])) for s in steps),
            "error": f"no answer in {steps_max} turns"}


# --------------------------------------------------------------------------- panel

def _clean(value: Any) -> str:
    return str(value or "").strip().strip("[]()'\"` ").strip()


def _scores(obj: dict[str, Any] | None) -> dict[str, int]:
    out = {}
    for f in FIELDS:
        try:
            out[f] = max(0, min(MAX_PER_FIELD, int((obj or {})[f])))
        except (KeyError, TypeError, ValueError):
            pass
    return out


def _citations(obj: dict[str, Any] | None, given: set[str]) -> dict[str, dict[str, Any]]:
    per = (obj or {}).get("citations") if isinstance((obj or {}).get("citations"), dict) else {}
    out = {}
    for f in FIELDS:
        ids = [_clean(x) for x in re.split(r",|;|\band\b", str(per.get(f) or "")) if _clean(x)]
        out[f] = {"citation": ", ".join(ids) or None,
                  "in_passages": all(i in given for i in ids) if ids else None}
    return out


def passages_block(passages: list[dict[str, Any]]) -> str:
    return "\n\n".join(f"[{p['passage_id']}] {p['citation']} — {p.get('title', '')}\n{p['text']}"
                       for p in passages)


def checks_block(bundle: dict[str, Any]) -> str:
    """Every check's verdict, detail and evidence, as check_result gives them one by one."""
    return "\n\n".join(run_tool("check_result", {"name": c["name"]}, bundle)[:TOOL_RESULT_CHARS]
                         for c in bundle.get("checks") or []) or "no checks were run"


def run_panel(bundle: dict[str, Any], *, call: Chat, models: dict[str, str],
              up_front: bool = False, thinking: dict[str, bool] | None = None,
              figures: bool = False, think_last: bool = False) -> dict[str, Any]:
    """The three agents on one briefing, and the panel's record. ``up_front`` gives the
    Challenger the case file and the checks' evidence at the start (panel-v3); ``thinking``
    turns a role's model reasoning off where it says False."""
    think = {"reader": True, "challenger": True, "arbiter": True} | (thinking or {})
    passages = bundle.get("passages") or []
    given = {p["passage_id"] for p in passages}
    regulation = "\n\nREGULATION PASSAGES:\n\n" + passages_block(passages) if passages else ""
    briefing = f"BRIEFING:\n{bundle['briefing']}"
    t0 = time.time()
    listed = run_tool("list_checks", {}, bundle)
    # The Reader and the Challenger do not see each other's work: run them at once.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as both:
        reading = both.submit(run_agent, "reader", READER + regulation, briefing, bundle,
                              call=call, model=models["reader"],
                              keys=("intelligible", "actionable"), thinking=think["reader"])
        figs = bundle.get("figures") if figures else None
        if up_front or figs:
            challenging = both.submit(
                run_agent, "challenger", CHALLENGER_UP_FRONT + (FIGURES_NOTE if figs else ""),
                f"{briefing}\n\nCASE FILE:\n{bundle.get('case_file', '')}\n\n"
                + (f"REFERENCE FIGURES:\n{figs}\n\n" if figs else "")
                + f"DETERMINISTIC CHECKS (verdict, detail, evidence):\n{checks_block(bundle)}",
                bundle, call=call, model=models["challenger"], keys=("findings",),
                tools=UP_FRONT_TOOLS, steps_max=UP_FRONT_STEPS, thinking=think["challenger"],
                think_last=think_last)
        else:
            challenging = both.submit(run_agent, "challenger", CHALLENGER,
                                      f"{briefing}\n\nCHECKS RUN ON THIS BRIEFING:\n{listed}",
                                      bundle, call=call, model=models["challenger"],
                                      keys=("findings",), thinking=think["challenger"])
        reader, challenger = reading.result(), challenging.result()
    brief = {
        "reader": reader["parsed"] or {"error": reader.get("error")},
        "challenger": challenger["parsed"] or {"error": challenger.get("error")},
    }
    arbiter = run_agent(
        "arbiter", ARBITER + regulation,
        f"{briefing}\n\nREADER:\n{json.dumps(brief['reader'], ensure_ascii=False)}\n\n"
        f"CHALLENGER:\n{json.dumps(brief['challenger'], ensure_ascii=False)}",
        bundle, call=call, model=models["arbiter"], keys=("intelligible", "actionable"),
        thinking=think["arbiter"])

    final = arbiter["parsed"]
    scores, reader_scores = _scores(final), _scores(reader["parsed"])
    ch = challenger["parsed"] or {}
    failing = sorted(c["name"] for c in bundle.get("checks", []) if c["passed"] is False)
    names = {c["name"] for c in bundle.get("checks", [])}
    said = [str(x) for x in ch.get("checks_confirmed") or []]
    disputed_all = [d for d in ch.get("checks_disputed") or [] if isinstance(d, dict)]
    # a verdict on a check counts only if the Challenger read that check's evidence: in v3
    # every check's evidence is in its first message
    read = set(names) if (up_front or figs) else {
        str((c.get("arguments") or {}).get("name")) for s in challenger["steps"]
        for c in s.get("tool_calls", []) if c.get("name") == "check_result"}
    confirmed = sorted({x for x in said if x in names and x in read})
    disputed = [d for d in disputed_all if d.get("name") in names and d.get("name") in read]
    unread = sorted({x for x in said if x in names and x not in read}
                    | {str(d.get("name")) for d in disputed_all
                       if d.get("name") in names and d.get("name") not in read})
    invented = sorted({x for x in said if x not in names}
                      | {str(d.get("name")) for d in disputed_all if d.get("name") not in names})
    return {
        "item_id": bundle["item_id"], "repeat": bundle["repeat"],
        "panel": (PANEL_VERSION_FIGURES if figs else PANEL_VERSION_UP_FRONT if up_front
                  else PANEL_VERSION),
        **({"think_last": True} if think_last else {}),
        **({"thinking_off": sorted(r for r, on in think.items() if not on)}
           if not all(think.values()) else {}),
        "value": (round(sum(scores.values()) / (MAX_PER_FIELD * len(scores)), 3)
                  if scores else None),
        "scores": scores, "reader_scores": reader_scores,
        "citations": _citations(final, given) if passages else None,
        "flag_for_review": bool((final or {}).get("flag_for_review")) if final else None,
        "flag_reasons": [str(x) for x in (final or {}).get("flag_reasons") or []][:5],
        "reason": str((final or {}).get("reason", ""))[:600],
        "findings": [f for f in ch.get("findings") or [] if isinstance(f, dict)][:12],
        "failing_checks": failing, "checks_confirmed": confirmed,
        "checks_disputed": disputed[:6], "invented_check_names": invented,
        "unread_check_verdicts": unread,
        "passages": sorted(given), "latency_ms": int((time.time() - t0) * 1000),
        "agents": {"reader": reader, "challenger": challenger, "arbiter": arbiter},
        "error": next((a["error"] for a in (reader, challenger, arbiter) if a.get("error")),
                      None),
    }


def run_many(bundles: list[dict[str, Any]], *, call: Chat, models: dict[str, str],
             workers: int = 4, done: set[tuple[str, int]] | None = None,
             write: Callable[[dict[str, Any]], None] = lambda r: None,
             log: Callable[[str], None] = print,
             should_stop: Callable[[], bool] | None = None, up_front: bool = False,
             thinking: dict[str, bool] | None = None, figures: bool = False,
             think_last: bool = False) -> list[dict[str, Any]]:
    """The panel on every bundle not already done, a few at a time; each record written as
    it finishes, so an interrupted run resumes. Once ``should_stop`` says so, no briefing
    starts and those in progress are dropped at their next turn; what finished is kept."""
    todo = [b for b in bundles if (b["item_id"], b["repeat"]) not in (done or set())]
    out: list[dict[str, Any]] = []
    stop = should_stop or (lambda: False)

    def guarded(**kw: Any) -> dict[str, Any]:
        if stop():
            raise Stopped()
        return call(**kw)

    def one(b: dict[str, Any]) -> dict[str, Any] | None:
        if stop():
            return None
        try:
            return run_panel(b, call=guarded, models=models, up_front=up_front,
                             thinking=thinking, figures=figures, think_last=think_last)
        except Stopped:
            return None
        except (urllib.error.URLError, OSError, ValueError) as e:
            return {"item_id": b["item_id"], "repeat": b["repeat"], "panel": PANEL_VERSION,
                    "value": None, "error": f"{type(e).__name__}: {e}"}

    i = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for rec in pool.map(one, todo):
            if rec is None:
                continue
            i += 1
            write(rec)
            out.append(rec)
            flag = {True: "flag", False: "ok", None: "—"}[rec.get("flag_for_review")]
            case = rec["item_id"].split(":")[2] if rec["item_id"].count(":") >= 2 else rec[
                "item_id"]
            log(f"  {i}/{len(todo)}  {case} r{rec['repeat']}  "
                f"value {rec.get('value')}  {flag}"
                + (f"  error: {rec['error']}" if rec.get("error") else ""))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the judge panel over prepared bundles.")
    ap.add_argument("--in", dest="inp", required=True, help="bundles.jsonl from the engine")
    ap.add_argument("--out", required=True, help="records.jsonl (appended; resumes)")
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", default="nemotron-3-super", help="model for all three agents")
    ap.add_argument("--reader-model")
    ap.add_argument("--challenger-model")
    ap.add_argument("--arbiter-model")
    ap.add_argument("--api-key-env", help="environment variable holding a bearer token")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--use-env-proxy", action="store_true",
                    help="connect through the proxy in the environment (inside a sandbox)")
    ap.add_argument("--stop-file", help="stop when this file appears (default: STOP next to "
                    "--out)")
    ap.add_argument("--fetch-evidence", dest="up_front", action="store_false",
                    help="panel-v2: the Challenger fetches the case file and each check's "
                    "evidence with tools (default: given up front, with reference figures)")
    ap.add_argument("--no-figures", dest="figures", action="store_false",
                    help="panel-v3: no reference figures for the Challenger")
    ap.add_argument("--think-throughout", dest="think_last", action="store_false",
                    help="the Challenger reasons on every turn (default: once, for its answer)")
    a = ap.parse_args(argv)
    stop_file = a.stop_file or os.path.join(os.path.dirname(os.path.abspath(a.out)), "STOP")
    models = {r: getattr(a, f"{r}_model") or a.model for r in ("reader", "challenger",
                                                              "arbiter")}
    key = os.environ.get(a.api_key_env) if a.api_key_env else None
    bundles = [json.loads(x) for x in open(a.inp, encoding="utf-8") if x.strip()]
    done: set[tuple[str, int]] = set()
    if os.path.exists(a.out):
        for x in open(a.out, encoding="utf-8"):
            if x.strip():
                r = json.loads(x)
                if not r.get("error"):
                    done.add((r["item_id"], r["repeat"]))

    def call(**kw: Any) -> dict[str, Any]:
        return chat(a.base_url, api_key=key, use_env_proxy=a.use_env_proxy, **kw)

    with open(a.out, "a", encoding="utf-8") as fh:
        def write(rec: dict[str, Any]) -> None:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()

        run_many(bundles, call=call, models=models, workers=a.workers, done=done, write=write,
                 log=lambda s: print(s, file=sys.stderr, flush=True),
                 should_stop=lambda: os.path.exists(stop_file), up_front=a.up_front,
                 figures=a.up_front and a.figures, think_last=a.think_last)
    return 0


if __name__ == "__main__":
    sys.exit(main())
