# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Training data for a fine-tuned assistant: a teacher writes the memos, the six checks
keep the ones that pass.

Three stages, each resumable, all writing into ``training/<name>/``:

1. **cases**: new cases from the same recipe and market as a test pack, with seeds no
   pack has used, and none sharing an application with any pack in ``packs/``. The cases
   live under ``training/``, never ``packs/``, so they cannot become a test; and the web
   UI's case generator treats their seeds and applications as taken.
2. **teach**: the teacher model (``EVIDENCE_TEACHER_*``, Nemotron 3 Ultra by default)
   writes each memo from exactly what the assistant is given: the task prompt as the
   system message, the documents as the user message. It may think first; only its final
   answer is kept. A memo that fails a check is tried again with the teacher shown its
   first memo and what the checks found (the fine-tuned model is trained on the case and
   the final memo only). Every attempt is recorded in ``teacher.jsonl`` with its check
   results.
3. **build**: the memos that pass all six checks and fit the assistant's answer budget
   become supervised fine-tuning data, split by case into ``sft/train.jsonl`` and
   ``sft/val.jsonl`` (chat messages). ``manifest.json`` says where every number came
   from. The folder is sealed, and anchored when anchoring is on.
"""

from __future__ import annotations

import json
import os
import random
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evidence.checks import check_versions, run_checks
from evidence.contracts.item import BenchmarkItem
from evidence.pack import load_pack

ROOT = Path("training")
PACKS = Path("packs")
CASES_PER_SEED = 250
# The assistant answers with thinking off in at most ASSISTANT_MAX_TOKENS (900) tokens. A
# memo longer than that would teach it to write memos it cannot finish: about 4 characters
# a token, with a margin.
MAX_MEMO_CHARS = 3200
VAL_SHARE = 0.05
TEACHER_MAX_TOKENS = 16000  # thinking first, then the memo
RETRY_WAITS = (5, 15, 45, 120)  # seconds, when the teacher is busy (429) or failing (5xx)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _application(item: BenchmarkItem) -> str:
    return next((c.content for c in item.context if c.renderer == "application_form"), "")


def taken(*, training: bool = True) -> tuple[set[int], set[str]]:
    """Seeds and application forms already used by a test pack, and by training data
    unless ``training`` is False."""
    seeds: set[int] = set()
    forms: set[str] = set()
    found = [*PACKS.glob("*/items.jsonl"),
             *(ROOT.glob("*/cases/*/items.jsonl") if training else [])]
    for items in found:
        pack = load_pack(items.parent)
        seed = (pack.manifest.get("sdd") or {}).get("seed")
        if seed:
            seeds.add(int(seed))
        forms |= {_application(i) for i in pack.items}
    return seeds, forms - {""}


def make_cases(name: str, n: int, from_pack: str, *, log: Callable[[str], None] = print) -> int:
    """Stage 1: ``n`` new cases like ``from_pack``'s, in packs of up to CASES_PER_SEED."""
    from evidence.packs.credit_underwriting import build

    out = ROOT / name / "cases"
    out.mkdir(parents=True, exist_ok=True)
    src = load_pack(PACKS / from_pack)
    market = src.manifest.get("market") or "sample"
    family = src.pack_id.rsplit("-s", 1)[0]
    have = sum(len(load_pack(p.parent).items) for p in out.glob("*/items.jsonl"))
    rng = random.SystemRandom()
    while have < n:
        seeds, forms = taken()
        seed = next(s for s in iter(lambda: rng.randrange(100000, 1000000), None)
                    if s not in seeds)
        keep = min(CASES_PER_SEED, n - have)
        pack_id = f"train-{family}-s{seed}"
        generated = keep * 35
        for _ in range(4):  # only referred applications become cases
            manifest = build(generated, keep, seed, out / pack_id, pack_id, None, market,
                             bank_figures=True)
            if manifest["items"] >= keep:
                break
            generated *= 2
        pack = load_pack(out / pack_id)
        shared = [i for i in pack.items if _application(i) in forms]
        if shared:  # never train on a case a test has used: drop it
            ids = {i.item_id for i in shared}
            lines = (out / pack_id / "items.jsonl").read_text(encoding="utf-8").splitlines()
            (out / pack_id / "items.jsonl").write_text(
                "".join(line + "\n" for line in lines if json.loads(line)["item_id"] not in ids),
                encoding="utf-8")
        have += len(pack.items) - len(shared)
        log(f"  {pack_id}: {len(pack.items) - len(shared)} cases ({len(shared)} dropped: "
            f"shared with a test pack); {have}/{n}")
    return have


def cases(name: str, setup: str = "as_is") -> list[BenchmarkItem]:
    return [i.for_setup(setup) for p in sorted((ROOT / name / "cases").glob("*/items.jsonl"))
            for i in load_pack(p.parent).items]


def final_answer(message: dict[str, Any]) -> str:
    """The memo without the teacher's thinking, wherever the server put it."""
    text = message.get("content") or ""
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    return text.strip()


REPAIR = ("Your memo was checked against the case file and failed:\n{failures}\n\n"
          "Write the memo again. Use only figures the documents state, or that follow from "
          "them in one step of arithmetic. Reply with the memo only.")


def ask_teacher(system: str, user: str, previous: dict[str, Any] | None = None
                ) -> dict[str, Any]:
    """One call to the teacher: thinking on, its recommended sampling. ``previous`` is the
    memo that failed and what the checks found: the teacher is asked to write it again."""
    from evidence.adapters.nvidia_build import _bypass_proxy, endpoint_for

    ep = endpoint_for("teacher")
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    if previous:
        messages += [{"role": "assistant", "content": previous["memo"]},
                     {"role": "user", "content": REPAIR.format(
                         failures="\n".join(f"- {f}" for f in previous["failed"]))}]
    body = {"model": ep.model_id, "max_tokens": TEACHER_MAX_TOKENS, "temperature": 0.6,
            "top_p": 0.95, "messages": messages,
            "chat_template_kwargs": {"enable_thinking": True}}
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("EVIDENCE_TEACHER_API_KEY") or (
        os.environ.get("NVIDIA_API_KEY") if ep.is_build else None)
    if key:
        headers["Authorization"] = f"Bearer {key}"
    if not ep.is_build:
        _bypass_proxy(ep.base_url)
    opener = (urllib.request.build_opener() if ep.is_build
              else urllib.request.build_opener(urllib.request.ProxyHandler({})))
    req = urllib.request.Request(ep.base_url + "/chat/completions", method="POST",
                                 data=json.dumps(body).encode(), headers=headers)
    t0 = time.time()
    for wait in (*RETRY_WAITS, None):  # a hosted endpoint limits the rate: wait, try again
        try:
            with opener.open(req, timeout=900) as r:
                reply = json.loads(r.read())
            break
        except urllib.error.HTTPError as exc:
            if wait is None or exc.code not in (429, 500, 502, 503, 504):
                raise
            time.sleep(wait)
    msg = reply["choices"][0]["message"]
    usage = reply.get("usage") or {}
    return {"memo": final_answer(msg), "model": reply.get("model") or ep.model_id,
            "endpoint": ep.base_url, "latency_ms": int((time.time() - t0) * 1000),
            "tokens_out": usage.get("completion_tokens"),
            "finish": reply["choices"][0].get("finish_reason")}


def teach(name: str, *, setup: str = "as_is", attempts: int = 2, workers: int = 8,
          limit: int | None = None, ask: Callable[..., dict[str, Any]] = ask_teacher,
          log: Callable[[str], None] = print) -> dict[str, int]:
    """Stage 2: a teacher memo for every case, up to ``attempts`` tries until one passes."""
    path = ROOT / name / "teacher.jsonl"
    done: dict[str, list[dict[str, Any]]] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            done.setdefault(r["item_id"], []).append(r)
    def tried(item_id: str) -> int:  # a call that failed is not an attempt
        return sum(1 for r in done.get(item_id, []) if "error" not in r)

    todo = [i for i in cases(name, setup)
            if not any(r["kept"] for r in done.get(i.item_id, []))
            and tried(i.item_id) < attempts][:limit]
    lock = threading.Lock()
    counts = {"cases": len(todo), "kept": 0, "failed_checks": 0, "too_long": 0, "errors": 0}

    def one(item: BenchmarkItem) -> None:
        last = next((r for r in reversed(done.get(item.item_id, []))
                     if r.get("failed") and r.get("memo")), None)
        for attempt in range(tried(item.item_id), attempts):
            row: dict[str, Any] = {"item_id": item.item_id, "setup": setup,
                                   "attempt": attempt, "at": _now(),
                                   "repair": bool(last)}
            try:
                row |= (ask(item.prompt, item.documents_text(), last) if last
                        else ask(item.prompt, item.documents_text()))
            except Exception as exc:  # noqa: BLE001 — recorded, the case is retried next time
                row |= {"error": f"{type(exc).__name__}: {exc}"[:300], "kept": False}
                with lock:
                    counts["errors"] += 1
                    path.open("a", encoding="utf-8").write(json.dumps(row) + "\n")
                return
            results = run_checks(item.deterministic_checks, output=row["memo"], item=item)
            row["checks"] = {r.name: r.passed for r in results}
            failed = [r.detail for r in results if r.passed is False]
            row["failed"] = failed
            row["kept"] = not failed and 0 < len(row["memo"]) <= MAX_MEMO_CHARS
            with lock:
                counts["kept" if row["kept"] else
                       "too_long" if not failed else "failed_checks"] += 1
                path.open("a", encoding="utf-8").write(json.dumps(row) + "\n")
                n = sum(counts[k] for k in ("kept", "failed_checks", "too_long", "errors"))
                if n % 10 == 0:
                    log(f"  {n} memos written: {counts['kept']} kept")
            if row["kept"]:
                return
            last = row if failed else None  # a memo too long is simply tried again

    with ThreadPoolExecutor(max(1, workers)) as ex:
        list(ex.map(one, todo))
    return counts


def build(name: str, *, setup: str = "as_is", feedback: list[Path] | None = None,
          log: Callable[[str], None] = print) -> Path:
    """Stage 3: the kept memos as chat-format fine-tuning data, split by case; sealed."""
    out = ROOT / name
    items = {i.item_id: i for i in cases(name, setup)}
    rows = [json.loads(line) for line in
            (out / "teacher.jsonl").read_text(encoding="utf-8").splitlines() if line]
    kept = {r["item_id"]: r for r in rows if r.get("kept") and r["item_id"] in items}
    ids = sorted(kept)
    random.Random(7).shuffle(ids)
    n_val = max(1, round(len(ids) * VAL_SHARE)) if len(ids) > 1 else 0
    split = {"val": sorted(ids[:n_val]), "train": sorted(ids[n_val:])}

    def example(item: BenchmarkItem, memo: str, source: str) -> dict[str, Any]:
        return {"messages": [{"role": "system", "content": item.prompt},
                             {"role": "user", "content": item.documents_text()},
                             {"role": "assistant", "content": memo}],
                "item_id": item.item_id, "source": source}

    (out / "sft").mkdir(exist_ok=True)
    extra = _feedback_examples(feedback or [])
    for part, chosen in split.items():
        lines = [example(items[i], kept[i]["memo"], "teacher") for i in chosen]
        if part == "train":
            lines += extra
        (out / "sft" / f"{part}.jsonl").write_text(
            "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines), encoding="utf-8")
    attempted = {r["item_id"] for r in rows}
    teacher = next((r for r in rows if r.get("model")), {})
    _, forms = taken(training=False)
    leaked = sum(1 for i in ids if _application(items[i]) in forms)
    manifest = {
        "name": name, "built_at": _now(), "setup": setup,
        "teacher": {"model": teacher.get("model"), "endpoint": teacher.get("endpoint"),
                    "sampling": {"temperature": 0.6, "top_p": 0.95, "thinking": True}},
        "cases": len(items), "cases_attempted": len(attempted), "memos_written": len(rows),
        "cases_kept": len(ids), "train": len(split["train"]) + len(extra),
        "val": len(split["val"]), "from_feedback_packs": len(extra),
        "kept_share": round(len(ids) / max(1, len(attempted)), 4),
        "failed_by_check": _failed_by_check(rows),
        "check_versions": check_versions(),
        "max_memo_chars": MAX_MEMO_CHARS,
        "shared_with_test_packs": leaked,
        "feedback_from_test_packs": sorted({_run_pack(h) for h in feedback or []}),
        "case_packs": sorted(p.parent.name for p in (out / "cases").glob("*/items.jsonl")),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (out / "README.md").write_text(_readme(manifest), encoding="utf-8")
    from evidence import anchor
    from evidence.evidence.writer import seal

    seal(out)
    anchor.anchor(out, "training-data")  # a no-op when anchoring is off
    log(f"{manifest['train']} training and {manifest['val']} validation examples; "
        f"{manifest['kept_share']:.0%} of cases kept; written to {out}")
    return out


def _failed_by_check(rows: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        for name, passed in (r.get("checks") or {}).items():
            if passed is False:
                out[name] = out.get(name, 0) + 1
    return dict(sorted(out.items()))


def _feedback_examples(handovers: list[Path]) -> list[dict[str, Any]]:
    """Human-corrected memos from feedback packs' handovers (``feedback/handover/``).

    These are cases from a test: a model trained on them must be compared on other cases.
    The manifest names their packs (``feedback_from_test_packs``)."""
    out: list[dict[str, Any]] = []
    for h in handovers:
        for f in sorted(h.glob("sft_*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    if "messages" in row:
                        out.append({"messages": row["messages"],
                                    "item_id": row.get("item_id"), "source": f"feedback:{h}"})
    return out


def _run_pack(handover: Path) -> str:
    """The test pack a feedback handover's corrected memos came from."""
    manifest = handover.parents[1] / "manifest.json"
    return json.loads(manifest.read_text(encoding="utf-8"))["pack"]["pack_id"]


def _readme(m: dict[str, Any]) -> str:
    fails = ", ".join(f"`{k}` {v}" for k, v in m["failed_by_check"].items()) or "none"
    return (f"# Training data: {m['name']}\n\n"
            f"Memos written by `{m['teacher']['model']}` (thinking on) for {m['cases']} new "
            f"cases, as the assistant receives them ({m['setup']}). A memo is kept only if "
            f"it passes all six checks and fits the assistant's answer budget "
            f"({m['max_memo_chars']} characters).\n\n"
            f"- Cases kept: {m['cases_kept']} of {m['cases_attempted']} "
            f"({m['kept_share']:.0%})\n"
            f"- Training examples: {m['train']} (of which {m['from_feedback_packs']} "
            f"corrected by people in feedback packs); validation: {m['val']}, split by case\n"
            f"- Checks failed by rejected memos: {fails}\n"
            f"- Cases sharing an application with a test pack: {m['shared_with_test_packs']}\n"
            + (f"- Corrected memos from the test packs {', '.join(m['feedback_from_test_packs'])}"
               ": compare a model trained on this data on other cases\n"
               if m["feedback_from_test_packs"] else "") + "\n"
            "`teacher.jsonl` holds every memo the teacher wrote, kept or not, with its check "
            "results. `sft/` is the data in chat format.\n")
