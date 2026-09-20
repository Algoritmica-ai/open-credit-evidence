# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""The sample pack as a NeMo Evaluator benchmark.

The evidence pack is the product; this file is how the same pack runs inside a
harness a lender may already operate — with repeats, confidence intervals,
run-to-run comparison (``nel compare``) and pass/fail gates (``nel gate``).

    pip install nemo-evaluator            # github.com/NVIDIA-NeMo/Evaluator
    export NVIDIA_API_KEY=...
    nel validate -b examples/nemo_evaluator/credit_evidence_bench.py --samples 2
    nel eval run -b examples/nemo_evaluator/credit_evidence_bench.py --repeats 3 \\
        --model-url https://integrate.api.nvidia.com/v1/chat/completions \\
        --model-id nvidia/nemotron-3.5-lightning-30b-a3b --api-key $NVIDIA_API_KEY \\
        --output-dir results/credit-evidence

The scorer is our own check battery; the reward is the share of gated checks
passed, and every check's score and detail travel in ``scoring_details``.
"""

from __future__ import annotations

from pathlib import Path

from nemo_evaluator import ScorerInput, benchmark, scorer
from nemo_evaluator.environments.base import SeedResult

from evidence.checks import run_checks
from evidence.contracts.item import BenchmarkItem

PACK = Path(__file__).resolve().parents[2] / "packs" / "underwriter-sample"


def seed(row: dict, idx: int) -> SeedResult:
    """Build the messages ourselves: the task prompt as system, the documents as user."""
    item = BenchmarkItem.model_validate(row)
    return SeedResult(
        prompt=item.documents_text(),
        # What the harness prints as "expected": the facts a briefing must state.
        expected_answer="; ".join(
            item.grading.omission_labels[r] for r in item.grading.omission_refs
        ),
        messages=[
            {"role": "system", "content": item.prompt},
            {"role": "user", "content": item.documents_text()},
        ],
        system=item.prompt,
        metadata={"item": row, "category": item.tags.get("difficulty", "unknown")},
    )


@benchmark(
    name="credit-evidence-underwriter",
    dataset=str(PACK / "items.jsonl"),
    seed_fn=seed,
)
@scorer
def score(sample: ScorerInput) -> dict:
    item = BenchmarkItem.model_validate(sample.metadata["item"])
    results = run_checks(item.deterministic_checks, output=sample.response, item=item)
    out: dict = {
        "correct": sum(r.passed for r in results) / len(results) if results else 0.0,
        "needs_audit": any(r.needs_audit for r in results),
    }
    for r in results:
        out[f"{r.name}_passed"] = r.passed
        out[f"{r.name}_score"] = r.score
        out[f"{r.name}_detail"] = r.detail
    return out
