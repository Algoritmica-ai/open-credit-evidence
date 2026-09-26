# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""MMLU-Pro with an answer reader that does not miss the answer.

NeMo Evaluator's ``mmlu_pro`` asks for a last line "Answer: $LETTER" and reads it with
``Answer\\s*:\\s*([A-J])``. Models often copy the template's dollar signs ("Answer: $D$"),
which that pattern does not read, so a right answer scores as wrong: Nemotron 3.5
Lightning scored 15% where the letters it gave were 65% right. This benchmark is the same
dataset, prompt and row preparation, imported from NeMo Evaluator unchanged; only the
reader also takes "$D$", "(D)", "**D**" and "\\boxed{D}".
"""

from __future__ import annotations

from nemo_evaluator import ScorerInput, benchmark, scorer
from nemo_evaluator.benchmarks.mmlu_pro import _PROMPT, _prepare

from evidence.nemo.answers import letter


@benchmark(name="mmlu-pro", dataset="hf://TIGER-Lab/MMLU-Pro?split=test", prompt=_PROMPT,
           target_field="answer", prepare_row=_prepare)
@scorer
def score(sample: ScorerInput) -> dict:
    got = letter(sample.response)  # the last answer line is the answer
    return {"correct": got == str(sample.target).strip().upper(), "extracted": got}
