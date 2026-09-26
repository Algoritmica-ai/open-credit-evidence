# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""One line of ``items.jsonl`` — the contract between the pack and the engine.

The item carries everything the engine needs to *grade* an answer and nothing
that would let a holder of the pack *reconstruct the scorecard*. Driver,
decoy and omission references travel because the checks resolve model output
against them. Contributions, margins and flip thresholds stay behind: they are
the answer key, and a pack that carries them can be gamed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# What the assistant under test is given. "as_is": the case file as the bank sends it today.
# "with_figures": the case file plus the figures the bank's own systems already compute (a
# rules-engine document, present in packs generated with bank figures). An assistant
# setup is a change the bank makes on its side; the cases and the known answers stay the same.
SETUPS = {
    "as_is": "the case file, as the bank sends it today",
    "with_figures": "the case file plus the figures the bank's systems already compute",
}
BANK_FIGURES = "rules_engine"  # the renderer of the document the with_figures setup adds


class ItemContext(_Strict):
    """One rendered document, exactly as the assistant under test receives it."""

    renderer: str
    variant: str
    content: str


class FlipRef(_Strict):
    """A lever that would change the outcome — field and direction only.

    The threshold is deliberately absent. A check can confirm the assistant
    named the right lever; nobody can recover the cutoff from a published pack.
    """

    ref: str
    direction: str  # "increase" | "decrease"


class GradingSpec(_Strict):
    """What the engine needs to grade, and nothing more."""

    disposition: str
    top_n: int = 3

    driver_refs: list[str] = Field(default_factory=list)
    driver_labels: dict[str, str] = Field(default_factory=dict)
    driver_aliases: dict[str, list[str]] = Field(default_factory=dict)
    driver_directions: dict[str, str] = Field(default_factory=dict)

    decoy_refs: list[str] = Field(default_factory=list)
    decoy_aliases: dict[str, list[str]] = Field(default_factory=dict)

    # Facts a briefing MUST surface. The headline check resolves against these.
    omission_refs: list[str] = Field(default_factory=list)
    omission_labels: dict[str, str] = Field(default_factory=dict)
    omission_aliases: dict[str, list[str]] = Field(default_factory=dict)

    flip_refs: list[FlipRef] = Field(default_factory=list)
    flip_aliases: dict[str, list[str]] = Field(default_factory=dict)
    # Other levers that change the same outcome, keyed by the flip ref they stand
    # in for. A debt-to-income breach is cured by more income, a smaller loan, a
    # longer term or lower existing commitments: naming any one of them, in its
    # direction, names a way to change the outcome. Field and direction only.
    flip_alternatives: dict[str, list[FlipRef]] = Field(default_factory=dict)
    # Quantities a briefing may hold against a policy limit, with the words that
    # name them — so a claim ("debt service exceeds the 40% threshold") can be
    # checked against the figure the same briefing gives. No threshold travels.
    claim_aliases: dict[str, list[str]] = Field(default_factory=dict)

    contradiction_refs: list[str] = Field(default_factory=list)
    contradiction_labels: dict[str, str] = Field(default_factory=dict)


class BenchmarkItem(_Strict):
    """One gradeable item: a case, a task, one rendering of the documents."""

    item_id: str
    pack: str
    domain: str
    task: str

    prompt: str
    context: list[ItemContext]

    deterministic_checks: list[str] = Field(default_factory=list)
    judges: list[str] = Field(default_factory=list)

    tags: dict[str, str] = Field(default_factory=dict)
    grading: GradingSpec

    # Pair fields, present only on counterfactual twins.
    counterfactual_of: str | None = None
    perturbation_kind: str | None = None  # "invariance" | "sensitivity"
    expected_disposition_change: bool | None = None

    def documents_text(self) -> str:
        """Every document the assistant saw, joined — what numeric checks resolve against."""
        return "\n\n".join(c.content for c in self.context)

    def has_bank_figures(self) -> bool:
        return any(c.renderer == BANK_FIGURES for c in self.context)

    def for_setup(self, setup: str) -> BenchmarkItem:
        """The item as the assistant receives it under an assistant setup. The same item
        goes to the checks and to verification, so each judges what the assistant saw."""
        if setup not in SETUPS:
            raise ValueError(f"unknown assistant setup {setup!r}; one of {sorted(SETUPS)}")
        if setup == "with_figures" or not self.has_bank_figures():
            return self
        return self.model_copy(update={"context": [c for c in self.context
                                                   if c.renderer != BANK_FIGURES]})
