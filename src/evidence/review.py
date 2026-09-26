# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Review and feedback: people test the evaluation's evidence, and their verdicts improve the model.

Design: ``docs/feedback-loop.md``. The loop, on a finished and sealed run:

1. **Queue.** Every memo in the run becomes a review item: its findings as cards (one per
   problem the deterministic checks or the judge panel found, with the memo sentence and the
   evidence) and a lane — red, amber or green — from that evidence alone.
2. **Review.** A reviewer confirms (and corrects), disputes (with a reason) or asks for
   more on each card, may raise a finding the evidence missed, and submits the memo. Each
   submission is appended to ``review/records.jsonl``; the run is sealed again.
3. **Check the labels.** A verdict on a card backed by a deterministic check is compared with
   the known answer; a verdict that disagrees, every dispute and every raised finding go to
   adjudication (``review/adjudications.jsonl``). Only settled verdicts reach the feedback
   pack: those that agree with the known answer, those adjudication ruled on, and reviewer
   confirmations of findings that have no known answer.
4. **Feedback pack.** ``feedback/``: corrected memos for fine-tuning, original and corrected
   pairs for preference tuning, checked labels for the judge, upheld check disputes as check
   fixes, and a failure summary for the assistant's owner.

The queue reviews evaluation outputs — generated cases — never live applications.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evidence.contracts.transcript import Transcript

ACTIONS = ("confirm", "dispute", "needs_more")
REASONS = ("wrong_figure", "wrong_policy_reading", "not_material", "finding_wrong")
KIND = {
    "numeric_fidelity": "Figure not in the case file",
    "claim_consistency": "Claim contradicts the memo's own figure",
    "comparison_fidelity": "Comparison stated the wrong way round",
    "decoy_citation": "Irrelevant or prohibited factor used as a reason",
    "flip_accuracy": "What would change the outcome is wrong or missing",
    "material_omission": "Material fact left out",
    "panel": "Found by the AI review panel",
}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _key(item_id: str, repeat: int) -> str:
    return f"{item_id}#r{repeat}"


def _card_id(memo: str, source: str, n: int) -> str:
    return hashlib.sha256(f"{memo}|{source}|{n}".encode()).hexdigest()[:12]


def _clean(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().strip("*").strip()


def _wording(s: Any) -> str:
    """A reviewer's correction, kept as written: it replaces memo text, markdown and all."""
    return str(s or "").strip()


_IGNORE = r"[\s*_`]*"  # spacing and markdown emphasis, which checks and agents drop when quoting


_QUOTES = str.maketrans({c: "'" for c in "\u2018\u2019\u201c\u201d\"`"})


def _fold(s: str) -> str:
    """Case and quote style folded, one character for one, so positions are kept."""
    return s.translate(_QUOTES).lower()


def locate(text: str, quote: str) -> tuple[int, int] | None:
    """Where a quoted sentence sits in the memo, ignoring spacing, markdown emphasis, case
    and quote style."""
    chars = [ch for ch in _fold(quote) if not ch.isspace() and ch not in "*_"]
    folded = _fold(text)

    def find(n: int) -> re.Match[str] | None:
        return re.search(_IGNORE.join(re.escape(ch) for ch in chars[:n]), folded)

    if len(chars) < 8:
        return None
    m = find(len(chars))
    if m is None:
        # A check may quote a window of a tidied copy of the memo (list markers removed):
        # keep the longest opening part of the quote that is in the memo, if it is long enough.
        lo, hi = 20, len(chars) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if find(mid):
                lo = mid + 1
            else:
                hi = mid - 1
        m = find(hi) if hi >= 20 else None
    return (m.start(), m.end()) if m else None


_BREAK = re.compile(r"\n|(?<=[.!?])\s")  # a line break, or a full stop and a space
_END = re.compile(r"[.!?](?=\s|$)|\n")


def sentence_span(text: str, start: int, end: int) -> tuple[int, int]:
    """Widen a located quote to the whole sentence, or list line, it sits in. Findings on
    the same sentence then quote it the same way, and one correction covers them all."""
    left = 0
    for m in _BREAK.finditer(text, 0, start):
        left = m.end()
    m = _END.search(text, max(start, end - 1))
    right = (m.end() if m.group() != "\n" else m.start()) if m else len(text)
    while left < start and text[left].isspace():
        left += 1
    return left, max(right, end)


def _field(ref: Any) -> str:
    return str(ref or "").replace("_", " ")


def _check_cards(r: dict[str, Any], labels: dict[str, str]) -> list[dict[str, Any]]:
    """The problems one failing check result names, each with its memo sentence, in plain words."""
    name, out = r["check"], []
    for e in r.get("evidence") or []:
        if name == "numeric_fidelity" and e.get("grounded") is False:
            out.append({"problem": f"{e.get('value')} is not in the case file and does not follow "
                                   "from it",
                        "sentence": _clean(e.get("context")),
                        "anchor": str(e.get("value") or ""),  # the figure: its sentence is quoted
                        "memo_value": str(e.get("value") or ""),
                        "evidence": "Checked against every figure in the case file and the "
                                    "calculations that follow from them."})
        elif name == "claim_consistency" and e.get("holds") is False:
            out.append({"problem": f"Says the ratio is {e.get('claims')}, but the memo itself "
                                   f"gives {e.get('contradicted_by')}%",
                        "sentence": _clean(e.get("claim_sentence")),
                        # both of its statements: the case file shows which one is wrong
                        "memo_value": f"{e.get('claims')}, and {e.get('contradicted_by')}%",
                        "evidence": _clean(e.get("figure_sentence"))})
        elif name == "comparison_fidelity" and e.get("holds") is False:
            out.append({"problem": f"Says {e.get('left')} is {e.get('relation')} {e.get('right')}, "
                                   "which is false",
                        "sentence": _clean(e.get("sentence")),
                        "evidence": f"{e.get('left')} is not {e.get('relation')} "
                                    f"{e.get('right')}."})
        elif name == "decoy_citation" and e.get("cited"):
            out.append({"problem": f"Gives {_field(e.get('ref'))} as a reason for the decision",
                        "sentence": _clean(e.get("sentence")),
                        "evidence": f"Under the lending policy, {_field(e.get('ref'))} has no "
                                    "bearing on the outcome."})
        elif name == "flip_accuracy" and e.get("expected") and e.get("direction") != e.get(
                "expected"):
            out.append({"problem": f"Does not say correctly how {_field(e.get('ref'))} would have "
                                   "to change for a different outcome",
                        "sentence": _clean(e.get("sentence")),
                        "evidence": f"For this case, {_field(e.get('ref'))} would need to "
                                    f"{e.get('expected')}."})
        elif name == "material_omission" and e.get("matched") is False:
            out.append({"problem": f"Leaves out: {labels.get(e.get('ref'), _field(e.get('ref')))}",
                        "sentence": "",
                        "evidence": "The decision turned on this fact; the memo does not "
                                    "state it."})
    return out


def queue(run: Path, items: dict[str, Any]) -> list[dict[str, Any]]:
    """Every memo in the run as a review item: text, lane and cards."""
    results: dict[str, list[dict[str, Any]]] = {}
    for line in (run / "results.jsonl").read_text(encoding="utf-8").splitlines():
        if line:
            r = json.loads(line)
            results.setdefault(_key(r["item_id"], r["repeat"]), []).append(r)
    panel: dict[str, dict[str, Any]] = {}
    ppath = run / "panel" / "records.jsonl"
    if ppath.is_file():
        for line in ppath.read_text(encoding="utf-8").splitlines():
            if line:
                p = json.loads(line)
                if not p.get("error"):
                    panel[_key(p["item_id"], p["repeat"])] = p
    out = []
    for path in sorted((run / "transcripts").glob("*.json")):
        t = Transcript.model_validate_json(path.read_text(encoding="utf-8"))
        memo = _key(t.item_id, t.repeat)
        item = items.get(t.item_id)
        labels = dict(item.grading.omission_labels) if item else {}
        cards: list[dict[str, Any]] = []
        failing = []
        for r in results.get(memo, []):
            if r.get("passed") is False:
                failing.append(r["check"])
                for c in _check_cards(r, labels):
                    cards.append(c | {"source": r["check"], "known_answer": True})
        p = panel.get(memo)
        for f in (p or {}).get("findings") or []:
            src = str(f.get("source", ""))
            if src.startswith("check:") and src.removeprefix("check:") in failing:
                continue  # the check's own card already says it
            cards.append({"problem": _clean(f.get("problem")), "sentence": _clean(f.get("claim")),
                          "evidence": _clean(f.get("evidence")), "source": "panel",
                          "severity": f.get("severity"), "known_answer": False})
        for n, c in enumerate(cards):
            c["card_id"] = _card_id(memo, c["source"], n)
            c["kind"] = KIND.get(c["source"], c["source"])
            span = locate(t.output, c["sentence"]) if c["sentence"] else None
            anchor = c.pop("anchor", "")
            if span and anchor:  # a window around a figure: take the figure's own sentence
                at = t.output.find(anchor, span[0], span[1])
                span = (at, at + len(anchor)) if at >= 0 else span
            span = sentence_span(t.output, *span) if span else None
            c["span"] = list(span) if span else None
            if span:  # quote the memo's sentence exactly, so it can be highlighted and corrected
                c["sentence"] = t.output[span[0]:span[1]]
        flagged = bool((p or {}).get("flag_for_review"))
        if failing and (flagged or p is None):
            lane = "red"
        elif failing or flagged:
            lane = "amber"
        else:
            lane = "green"
        out.append({"memo": memo, "item_id": t.item_id, "repeat": t.repeat,
                    "case": t.item_id.split(":")[2] if t.item_id.count(":") >= 2 else t.item_id,
                    "lane": lane, "failing_checks": sorted(set(failing)),
                    "panel_flag": flagged if p else None,
                    "panel_reasons": (p or {}).get("flag_reasons") or [],
                    "text": t.output, "cards": cards,
                    "transcript_sha256": t.sha256})
    order = {"red": 0, "amber": 1, "green": 2}
    return sorted(out, key=lambda q: (order[q["lane"]], q["case"], q["repeat"]))


# ------------------------------------------------------------------ records

def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def reviews(run: Path) -> dict[str, dict[str, Any]]:
    """The latest submission per memo."""
    latest: dict[str, dict[str, Any]] = {}
    for r in _read_jsonl(run / "review" / "records.jsonl"):
        latest[r["memo"]] = r
    return latest


def adjudications(run: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for a in _read_jsonl(run / "review" / "adjudications.jsonl"):
        latest[a["verdict_id"]] = a
    return latest


def submit(run: Path, memo: str, reviewer: str, verdicts: list[dict[str, Any]],
           raised: list[dict[str, Any]] | None = None, seconds: float | None = None,
           queue_items: list[dict[str, Any]] | None = None,
           coach: dict[str, Any] | None = None) -> dict[str, Any]:
    """Record a reviewer's verdicts on one memo. Validates actions, reasons and card ids."""
    qi = next((q for q in queue_items or [] if q["memo"] == memo), None)
    if qi is None:
        raise ValueError(f"no memo {memo!r} in this run's review queue")
    ids = {c["card_id"] for c in qi["cards"]}
    clean = []
    for v in verdicts:
        if v.get("card_id") not in ids:
            raise ValueError(f"unknown card {v.get('card_id')!r}")
        if v.get("action") not in ACTIONS:
            raise ValueError(f"action must be one of {ACTIONS}")
        if v["action"] == "dispute" and v.get("reason") not in REASONS:
            raise ValueError(f"a dispute needs a reason: one of {REASONS}")
        clean.append({"card_id": v["card_id"], "action": v["action"],
                      "reason": v.get("reason"), "correction": _wording(v.get("correction"))})
    rec = {"memo": memo, "item_id": qi["item_id"], "repeat": qi["repeat"],
           "reviewer": _clean(reviewer) or "reviewer", "submitted_at": _now(),
           "seconds": round(float(seconds), 1) if seconds is not None else None,
           "lane": qi["lane"], "verdicts": clean,
           "raised": [{"sentence": _clean(r.get("sentence")), "problem": _clean(r.get("problem")),
                       "correction": _wording(r.get("correction"))}
                      for r in raised or [] if _clean(r.get("problem"))],
           "signed_off": not any(v["action"] == "confirm" for v in clean) and not raised,
           **({"coach": coach} if coach else {})}
    (run / "review").mkdir(exist_ok=True)
    with (run / "review" / "records.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    return rec


def adjudicate(run: Path, verdict_id: str, decision: str, by: str, note: str = "") -> dict:
    """Model risk's ruling on a verdict that needs one: ``uphold`` (the reviewer is right) or
    ``reject``."""
    if decision not in ("uphold", "reject"):
        raise ValueError("decision must be uphold or reject")
    rec = {"verdict_id": verdict_id, "decision": decision, "by": _clean(by) or "model-risk",
           "note": _clean(note), "at": _now()}
    (run / "review").mkdir(exist_ok=True)
    with (run / "review" / "adjudications.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    return rec


# ------------------------------------------------------------------ labels

def labels(run: Path, queue_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every verdict with its standing: agrees with the known answer, needs adjudication,
    upheld or rejected by adjudication, or reviewer-confirmed (no known answer)."""
    cards = {c["card_id"]: (q, c) for q in queue_items for c in q["cards"]}
    adj = adjudications(run)
    out = []
    for memo, rec in sorted(reviews(run).items()):
        for v in rec["verdicts"]:
            q, c = cards.get(v["card_id"], (None, None))
            if c is None:
                continue
            vid = f"{memo}|{v['card_id']}"
            if c["known_answer"]:
                standing = "agrees" if v["action"] == "confirm" else "needs_adjudication"
            else:
                standing = "reviewer_confirmed" if v["action"] == "confirm" else \
                    "needs_adjudication"
            if v["action"] == "needs_more":
                standing = "needs_adjudication"
            if standing == "needs_adjudication" and vid in adj:
                standing = "upheld" if adj[vid]["decision"] == "uphold" else "rejected"
            out.append({"verdict_id": vid, "memo": memo, "card": c, "verdict": v,
                        "standing": standing, "reviewer": rec["reviewer"]})
        for n, r in enumerate(rec.get("raised") or []):
            vid = f"{memo}|raised-{n}"
            standing = "needs_adjudication"
            if vid in adj:
                standing = "upheld" if adj[vid]["decision"] == "uphold" else "rejected"
            out.append({"verdict_id": vid, "memo": memo,
                        "card": {"problem": r["problem"], "sentence": r["sentence"],
                                 "source": "reviewer", "kind": "Raised by the reviewer",
                                 "known_answer": False},
                        "verdict": {"action": "raise", "correction": r.get("correction")},
                        "standing": standing, "reviewer": rec["reviewer"]})
    return out


def _settled(label: dict[str, Any]) -> bool:
    """A verdict whose truth is settled: it can go into the feedback pack."""
    return label["standing"] in ("agrees", "upheld", "rejected", "reviewer_confirmed")


def _is_error(label: dict[str, Any]) -> bool:
    """Whether a settled verdict says the memo has this error."""
    action, standing = label["verdict"]["action"], label["standing"]
    if action == "confirm":
        return standing in ("agrees", "reviewer_confirmed")
    if action == "raise":
        return standing == "upheld"
    return standing == "rejected"  # a dispute adjudication rejected: the finding stands


def summary(run: Path, queue_items: list[dict[str, Any]]) -> dict[str, Any]:
    """What the review found, for the evidence pack and the UI."""
    revs = reviews(run)
    lab = labels(run, queue_items)
    by_memo = {q["memo"]: q for q in queue_items}
    lanes = {k: sum(1 for q in queue_items if q["lane"] == k) for k in ("red", "amber", "green")}
    known = [x for x in lab if x["card"].get("known_answer")]
    # automation bias: a memo with a known error that the reviewer signed off as it was
    bias = sum(1 for m, r in revs.items()
               if r.get("signed_off")
               and any(c["known_answer"] for c in by_memo.get(m, {}).get("cards", [])))
    secs = {}
    for lane in lanes:
        vals = [r["seconds"] for r in revs.values() if r.get("seconds") and r["lane"] == lane]
        secs[lane] = round(sum(vals) / len(vals), 1) if vals else None
    return {
        "memos": len(queue_items), "lanes": lanes, "reviewed": len(revs),
        "reviewers": sorted({r["reviewer"] for r in revs.values()}),
        "verdicts": len(lab),
        "known_answer_verdicts": len(known),
        "agree_with_known_answer": sum(1 for x in known if x["standing"] == "agrees"),
        "needs_adjudication": sum(1 for x in lab if x["standing"] == "needs_adjudication"),
        "upheld": sum(1 for x in lab if x["standing"] == "upheld"),
        "rejected": sum(1 for x in lab if x["standing"] == "rejected"),
        "raised": sum(1 for x in lab if x["verdict"]["action"] == "raise"),
        "automation_bias_memos": bias,
        "seconds_per_memo_by_lane": secs,
        "settled": sum(1 for x in lab if _settled(x)),
        **coach_effect(revs, by_memo),
    }


def coach_effect(revs: dict[str, dict[str, Any]], by_memo: dict[str, Any]) -> dict[str, Any]:
    """Did the coach help? On findings with a known answer (the rule checks, where the memo
    is known to be wrong), how often the reviewer's answer agreed before the coach and after.
    Absent when no review used the coach, so earlier evidence is unchanged."""
    coached = {m: r for m, r in revs.items() if r.get("coach")}
    if not coached:
        return {}
    before = after = known = changed = 0
    for m, r in coached.items():
        cards = {c["card_id"]: c for c in by_memo.get(m, {}).get("cards", [])}
        first = {v["card_id"]: v for v in r["coach"].get("answers_before") or []}
        changed += len(r["coach"].get("changed_after_coach") or [])
        for v in r["verdicts"]:
            c = cards.get(v["card_id"])
            if not (c and c.get("known_answer")) or v["card_id"] not in first:
                continue
            known += 1
            before += first[v["card_id"]].get("action") == "confirm"
            after += v["action"] == "confirm"
    return {"coach": {"memos": len(coached), "answers_changed": changed,
                      "known_answer_findings": known, "agreed_before_coach": before,
                      "agreed_after_coach": after}}


# ------------------------------------------------------------------ feedback pack

def _corrected(text: str, fixes: list[tuple[str, str]]) -> tuple[str, int]:
    """The memo with each confirmed sentence replaced by its correction; additions appended."""
    applied = 0
    for sentence, correction in fixes:
        if sentence and sentence in text:
            text = text.replace(sentence, correction, 1)
            applied += 1
        elif not sentence:
            text = text.rstrip() + "\n\n" + correction + "\n"
            applied += 1
    return text, applied


def build_feedback(run: Path, queue_items: list[dict[str, Any]]) -> dict[str, Any]:
    """Write ``feedback/`` from the verdicts whose truth is settled."""
    lab = labels(run, queue_items)
    by_memo = {q["memo"]: q for q in queue_items}
    out = run / "feedback"
    out.mkdir(exist_ok=True)
    sft, prefs, judge, fixes = [], [], [], []
    uncorrected: list[str] = []
    failures: dict[str, int] = {}
    by_sha = {}
    for path in (run / "transcripts").glob("*.json"):
        tr = Transcript.model_validate_json(path.read_text(encoding="utf-8"))
        by_sha[tr.sha256] = tr
    for memo, q in by_memo.items():
        mine = [x for x in lab if x["memo"] == memo and _settled(x)]
        if not mine:
            continue
        t = by_sha[q["transcript_sha256"]]
        provenance = {"memo": memo, "transcript_sha256": q["transcript_sha256"],
                      "verdicts": [x["verdict_id"] for x in mine]}
        errors = [x for x in mine if _is_error(x)]
        for x in errors:
            failures[x["card"]["kind"]] = failures.get(x["card"]["kind"], 0) + 1
        # One correction per sentence: findings on the same sentence share it. An error
        # with no sentence (something left out) is corrected by an addition.
        by_sentence: dict[str, str] = {}
        additions: list[str] = []
        for x in errors:
            sentence, fix = x["card"].get("sentence") or "", x["verdict"].get("correction") or ""
            if sentence and fix:
                by_sentence.setdefault(sentence, fix)
            elif fix:
                additions.append(fix)
        # a quote that sits inside a longer corrected quote is corrected by it
        by_sentence = {k: v for k, v in by_sentence.items()
                       if not any(k != o and k in o for o in by_sentence)}
        missing = any(not x["verdict"].get("correction") and
                      (not x["card"].get("sentence")
                       or not any(x["card"]["sentence"] in k for k in by_sentence))
                      for x in errors)
        # a memo becomes a training target only when every error in it was corrected
        if errors and missing:
            uncorrected.append(memo)
        elif errors:
            fixes_here = list(by_sentence.items()) + [("", a) for a in additions]
            text, applied = _corrected(t.output, fixes_here)
            if applied == len(fixes_here):
                prompt = [{"role": "system", "content": t.system_prompt},
                          {"role": "user", "content": t.user_prompt}]
                sft.append({"messages": prompt + [{"role": "assistant", "content": text}],
                            "provenance": provenance})
                prefs.append({"prompt": prompt, "chosen": text, "rejected": t.output,
                              "provenance": provenance})
            else:  # the corrections overlap in a way that cannot be applied: a person rewords
                uncorrected.append(memo)
        for x in mine:
            if x["card"]["source"] == "reviewer":
                continue  # raised findings have no judge counterpart to label
            judge.append({"memo_sentence": x["card"].get("sentence"),
                          "finding": x["card"].get("problem"), "source": x["card"]["source"],
                          "label": _is_error(x),
                          "basis": {"agrees": "known answer", "upheld": "adjudicated",
                                    "rejected": "adjudicated",
                                    "reviewer_confirmed": "reviewer"}[x["standing"]],
                          "provenance": provenance | {"verdict": x["verdict_id"]}})
            if (x["standing"] == "upheld" and x["card"].get("known_answer")
                    and x["verdict"]["action"] != "raise"):
                fixes.append({"check": x["card"]["source"], "problem": x["card"]["problem"],
                              "sentence": x["card"].get("sentence"),
                              "reviewer_reason": x["verdict"].get("reason"),
                              "provenance": provenance | {"verdict": x["verdict_id"]}})
    files = {"sft.jsonl": sft, "preferences.jsonl": prefs, "judge_labels.jsonl": judge,
             "check_fixes.jsonl": fixes}
    for name, rows in files.items():
        (out / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                encoding="utf-8")
    manifest = {
        "built_at": _now(), "run": run.name,
        "counts": {name: len(rows) for name, rows in files.items()},
        # memos with a confirmed error that has no correction: not yet a training example
        "memos_awaiting_correction": uncorrected,
        "failure_summary": dict(sorted(failures.items(), key=lambda kv: -kv[1])),
        "sha256": {name: hashlib.sha256((out / name).read_bytes()).hexdigest()
                   for name in files},
        "rule": "only verdicts whose truth is settled: they agree with the known answer, were "
                "ruled on by adjudication, or were confirmed by a reviewer where no known "
                "answer exists",
        "personal_data": "none: every case is generated",
    }
    manifest["handover"] = build_handover(run, out, sft, prefs, judge, manifest)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
    return manifest


# ------------------------------------------------------------------ fine-tune handover

HANDOVER_README = """# Fine-tuning handover: {model}

For the engineering team that owns the credit memo assistant. Everything here comes from
test `{run}` and the people who reviewed its memos. No customer data: every case is
generated from the credit policy.

## Files

- `sft_train.jsonl` ({sft_train} rows) and `sft_validation.jsonl` ({sft_val}): supervised
  fine-tuning, chat format. `messages` holds the system prompt, the case file (user) and the
  corrected memo (assistant).
- `dpo_train.jsonl` ({dpo}): preference tuning (DPO). `prompt` is the chat so far (system and
  user messages), `chosen_response` the corrected memo, `rejected_response` the assistant's
  original. Flatten `prompt` with the model's chat template if the trainer wants a string.
- `judge_labels.jsonl` ({labels}): findings labelled true or false, for training or checking
  the AI reviewers, not the assistant.
- `training_config.yaml`: a starting point for a LoRA run. The team owns the settings.
- `manifest.json`: where every file came from, and its SHA-256.

Every row carries its provenance: the memo, the SHA-256 of the sealed transcript it came
from, and the review verdicts behind it. `evidence verify` on the test proves the source.

## Most common confirmed mistakes

{failures}

## How the result is accepted

1. Serve the tuned model at an endpoint the engine can reach.
2. Generate new cases (never used for training): **Test**, then **Generate new cases**.
3. Test the current model and the tuned model on those same new cases, and compare the two
   (`evidence compare <before> <after>`, or **Earlier tests**, then **Compare**).
4. Accept only if the comparison says the change helped and nothing got worse.

## Size

{size_note}
"""

TRAINING_CONFIG = """# A starting point for LoRA supervised fine-tuning.
# The engineering team owns these settings; they are not tuned for this data.
base_model: {model}
finetuning: lora
lora:
  rank: 16
  alpha: 32
  dropout: 0.05
training:
  epochs: 3
  learning_rate: 1.0e-4
  batch_size: 8
  max_seq_length: 8192
data:
  train: sft_train.jsonl
  validation: sft_validation.jsonl
  preference: dpo_train.jsonl   # for a DPO stage after SFT, if used
acceptance: re-test on new cases and compare with the current model (README)
"""


def build_handover(run: Path, out: Path, sft: list[dict[str, Any]],
                   prefs: list[dict[str, Any]], judge: list[dict[str, Any]],
                   fb: dict[str, Any]) -> dict[str, Any]:
    """``feedback/handover/``: the fine-tuning data in training formats, a starting
    configuration and a README, for the team that fine-tunes the assistant."""
    h = out / "handover"
    h.mkdir(exist_ok=True)
    m = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    model = (m.get("sut") or {}).get("model_id") or "the assistant's model"

    def split(row: dict[str, Any]) -> bool:  # a stable 10% for validation, by memo
        memo = row["provenance"]["memo"]
        return int(hashlib.sha256(memo.encode()).hexdigest(), 16) % 10 == 0

    val = [r for r in sft if split(r)] if len(sft) >= 10 else []
    train = [r for r in sft if r not in val]
    dpo = [{"prompt": p["prompt"], "chosen_response": p["chosen"],
            "rejected_response": p["rejected"], "provenance": p["provenance"]} for p in prefs]
    files: dict[str, str] = {
        "sft_train.jsonl": "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in train),
        "sft_validation.jsonl": "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in val),
        "dpo_train.jsonl": "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in dpo),
        "judge_labels.jsonl": "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in judge),
        "training_config.yaml": TRAINING_CONFIG.format(model=model),
    }
    n = len(sft)
    size_note = (f"{n} corrected memos. A LoRA run usually wants a few hundred or more: "
                 "review more memos, or several tests, before training on this alone."
                 if n < 200 else f"{n} corrected memos.")
    failures = "\n".join(f"- {k}: {v}" for k, v in fb["failure_summary"].items()) or "- none"
    files["README.md"] = HANDOVER_README.format(
        model=model, run=run.name, sft_train=len(train), sft_val=len(val), dpo=len(dpo),
        labels=len(judge), failures=failures, size_note=size_note)
    for name, body in files.items():
        (h / name).write_text(body, encoding="utf-8")
    manifest = {
        "run": run.name, "built_at": fb["built_at"], "base_model": model,
        "pack": m.get("pack", {}).get("pack_id"), "pack_version": m.get("pack", {}).get("version"),
        "assistant_fingerprint": ((m.get("models") or {}).get("assistant") or {}).get(
            "fingerprint"),
        "counts": {"sft_train": len(train), "sft_validation": len(val), "dpo": len(dpo),
                   "judge_labels": len(judge)},
        "sha256": {name: hashlib.sha256((h / name).read_bytes()).hexdigest()
                   for name in sorted(files)},
        "personal_data": "none: every case is generated",
    }
    (h / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                     encoding="utf-8")
    return {"dir": "feedback/handover", "counts": manifest["counts"]}


# ------------------------------------------------------------------ the evaluator itself

def evaluator(run: Path, queue_items: list[dict[str, Any]]) -> dict[str, Any]:
    """How good the rule checks and the AI reviewers are, from what is known: the known
    answers, and every settled review verdict. A panel flag on a memo that passes every rule
    check is either a problem the rules miss or a false alarm; only a review can tell which."""
    lab = labels(run, queue_items)
    settled = [x for x in lab if _settled(x)]
    with_panel = [q for q in queue_items if q["panel_flag"] is not None]
    failing = [q for q in with_panel if q["failing_checks"]]
    clean = [q for q in with_panel if not q["failing_checks"]]
    by_memo: dict[str, list[dict[str, Any]]] = {}
    for x in settled:
        by_memo.setdefault(x["memo"], []).append(x)
    real = alarm = 0
    for q in clean:
        if not q["panel_flag"]:
            continue
        panel = [x for x in by_memo.get(q["memo"], []) if x["card"]["source"] == "panel"]
        if not panel:
            continue
        if any(_is_error(x) for x in panel):
            real += 1
        else:
            alarm += 1
    flagged_clean = sum(1 for q in clean if q["panel_flag"])
    panel_settled = [x for x in settled if x["card"]["source"] == "panel"]
    rule_settled = [x for x in settled if x["card"].get("known_answer")]
    return {
        "panel": {
            "memos_with_a_rule_failure": len(failing),
            "flagged_with_a_rule_failure": sum(1 for q in failing if q["panel_flag"]),
            "memos_passing_every_rule": len(clean),
            "flagged_passing_every_rule": flagged_clean,
            "flags_on_rule_clean_memos_reviewed": real + alarm,
            "problems_the_rules_missed": real,
            "false_alarms": alarm,
            "findings_settled": len(panel_settled),
            "findings_confirmed": sum(1 for x in panel_settled if _is_error(x)),
        },
        "rule_checks": {
            "findings_settled": len(rule_settled),
            "findings_confirmed": sum(1 for x in rule_settled if _is_error(x)),
            "shown_wrong": sum(1 for x in rule_settled if not _is_error(x)),
        },
    }


def lines(s: dict[str, Any]) -> list[str]:
    """The review section of the evidence, in markdown."""
    ln, sec = s["lanes"], s["seconds_per_memo_by_lane"]
    kv = s["known_answer_verdicts"]
    fmt = lambda v: "—" if v is None else f"{v:.0f} s"  # noqa: E731
    return [
        "# Review", "",
        "People tested this run's evidence: one card per finding, confirmed and corrected, "
        "disputed with a reason, or raised where the evidence missed something. Verdicts that "
        "disagree with the known answer, disputes and raised findings are ruled on by model risk "
        "before they reach the feedback pack.", "",
        f"- Memos: {s['memos']} — red {ln['red']}, amber {ln['amber']}, green {ln['green']}. "
        f"Reviewed: {s['reviewed']} by {len(s['reviewers'])} reviewer(s).",
        f"- Verdicts on findings with a known answer: {kv}; agreeing with it: "
        f"{s['agree_with_known_answer']}.",
        f"- Memos signed off although they carried a known error (automation bias): "
        f"{s['automation_bias_memos']}.",
        f"- Awaiting adjudication: {s['needs_adjudication']}; upheld {s['upheld']}, rejected "
        f"{s['rejected']}. Findings raised by reviewers: {s['raised']}.",
        f"- Review time per memo: red {fmt(sec['red'])}, amber {fmt(sec['amber'])}, "
        f"green {fmt(sec['green'])}.",
        f"- Verdicts settled and usable for the feedback pack: {s['settled']}.", "",
        "Every verdict is in `review/records.jsonl`, every ruling in "
        "`review/adjudications.jsonl`; the feedback pack, if built, in `feedback/`.", ""]
