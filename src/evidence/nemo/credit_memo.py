# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""The credit memo benchmark, for NeMo Evaluator.

``nel`` loads this file (``name: .../credit_memo.py`` in a run's config). Each case of a
case set is sent to the assistant as the engine sends it: the task prompt as the system
message, the documents the setup gives it as the user message. Every memo is then marked
twice:

- **the six deterministic checks** decide: the memo passes only if all six pass. This is
  the benchmark's score, the one ``nel compare`` and ``nel gate`` act on;
- **a judge** (optional) scores how useful the memo is to an underwriter, 1 to 5, and is
  recorded beside the checks, never in place of them. NeMo Evaluator's default judge
  replaces the score; ours returns the checks' score unchanged.

Settings come from the environment, which ``evidence.capabilities`` sets:
``CREDIT_PACK`` (a case set's ``items.jsonl``), ``CREDIT_SETUP`` (``as_is`` or
``with_figures``) and ``CREDIT_JUDGE`` (``on`` to ask the judge service).
"""

from __future__ import annotations

import os
import re
from typing import Any

from nemo_evaluator import ScorerInput, SeedResult, benchmark, scorer

from evidence.checks import run_checks
from evidence.contracts.item import BenchmarkItem

PACK = os.environ.get("CREDIT_PACK", "packs/underwriter-de/items.jsonl")
SETUP = os.environ.get("CREDIT_SETUP", "as_is")
JUDGE = os.environ.get("CREDIT_JUDGE", "off") == "on"

RUBRIC = (
    "You are a senior credit underwriter. Below is the case file an AI assistant was "
    "given, then the memo it wrote for the underwriter.\n\nCASE FILE:\n{case}\n\nMEMO:\n{memo}"
    "\n\nScore how useful the memo is to an underwriter deciding this case: clear, stating "
    "why it was referred, what the file shows for and against the applicant, and what would "
    "change the outcome. 1 = useless or misleading, 5 = could be relied on as written. "
    'Reply with JSON only: {{"score": <1-5>, "reason": "<one sentence>"}}'
)


def _item(row: dict[str, Any]) -> BenchmarkItem:
    return BenchmarkItem.model_validate(row).for_setup(SETUP)  # what the assistant sees


def seed(row: dict[str, Any], idx: int) -> SeedResult:
    item = _item(row)
    return SeedResult(
        prompt=item.documents_text(),
        expected_answer="; ".join(item.grading.omission_labels[r]
                                  for r in item.grading.omission_refs),
        messages=[{"role": "system", "content": item.prompt},
                  {"role": "user", "content": item.documents_text()}],
        system=item.prompt,
        metadata={"item": row, "category": item.tags.get("difficulty", "unknown")},
    )


@benchmark(name="credit-memo", dataset=PACK, seed_fn=seed)
@scorer
def score(sample: ScorerInput) -> dict[str, Any]:
    item = _item(sample.metadata["item"])
    results = run_checks(item.deterministic_checks, output=sample.response, item=item)
    passed = {r.name: bool(r.passed) for r in results if r.passed is not None}
    reward = 1.0 if passed and all(passed.values()) else 0.0
    out: dict[str, Any] = {"correct": reward == 1.0,
                           **{f"check_{k}": v for k, v in passed.items()},
                           "extracted": sample.response[:200]}
    if not JUDGE:
        return out

    async def judge(client: Any) -> dict[str, Any]:
        resp = await client.chat(prompt=RUBRIC.format(case=item.documents_text(),
                                                      memo=sample.response))
        text = resp.content or ""
        m = re.search(r'"score"\s*:\s*([1-5])', text)
        why = re.search(r'"reason"\s*:\s*"([^"]*)', text)
        s = int(m.group(1)) if m else None
        # the checks stay the score; the judge is recorded beside them
        return {"reward": reward, "judge": {"score": s, "reason": why.group(1) if why
                                            else text[:200]},
                "details": {"judge_usefulness": s}}

    out.update(needs_judge=True, _judge_fn=judge)
    return out
