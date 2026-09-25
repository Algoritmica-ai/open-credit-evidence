# Judge panel

Three agents reviewed each briefing: a **Reader** scored it as the underwriter would, a **Challenger** checked it against the case file and the deterministic checks with tools, and an **Arbiter** gave the final scores and said whether a person should review it. An opinion, reported and never used to pass or fail.

- Ran inside the NemoClaw sandbox `evidence-judge` on rtx-3se-06-04 (OpenShell 0.0.116, network policies: clawhub, local_inference, managed_inference, npm_registry, nvidia, openclaw_api, openclaw_docs, openclaw_gateway_dialback), model route vllm-local / nemotron-3-super. Models: reader `nemotron-3-super`, challenger `nemotron-3-super`, arbiter `nemotron-3-super`.
- 60/60 briefings answered.
- Mean score 0.711 on 0–1 (the single judge: 0.994). Flagged for review: 47.

## Against the deterministic checks

| | briefings | panel flagged | single judge full marks | panel full marks |
|---|---|---|---|---|
| failing at least one check | 45 | 44 | 44 | 4 |
| failing none | 15 | 3 | — | — |

Of the briefings the single judge gave full marks despite a failing check, the panel flagged 43.

The Challenger made 93 findings (80 material), with 8.3 tool calls per briefing on average, and confirmed 43 of the 57 failing check results from what it saw itself.
It disputed checks it thought wrong — worth an auditor's look: `comparison_fidelity` 1×, `decoy_citation` 2×, `flip_accuracy` 1×, `material_omission` 1×, `numeric_fidelity` 3×.
It confirmed or disputed a check without reading its evidence 83 times; those verdicts are not counted.

## Within the panel

Reader and Arbiter gave the same score on intelligible 90%, actionable 32%, overridable 27% of briefings; where they differ, the Arbiter weighed the Challenger's findings.
Every citation was a passage the panel was given in 59/60 records.

## Examples: full marks from the single judge, flagged by the panel

- `APP000028` r0 (failing: claim_consistency, decoy_citation): Incorrect claim that debt service exceeds 40% threshold (actual ratio 36.5%) — *Specifically, the applicant’s total monthly debt service exceeds the 40% affordability threshold*: The calculated debt service ratio is 36.5%, which is below the 40% threshold.
- `APP000028` r1 (failing: decoy_citation): The briefing incorrectly states that total monthly debt service exceeds the 40% affordability threshold when the calculated DTI is 36.55%. — *The applicant’s total monthly debt service exceeds the 40% affordability threshold.*: The calculated debt-to-income ratio is 36.55%, which is below the 40% threshold.
- `APP000028` r2 (failing: claim_consistency, comparison_fidelity, decoy_citation): Incorrectly states the bureau score is below 600 when the case file shows a score of 608. — *The applicant’s bureau score of 608 falls below the 600 cutoff, which automatically triggers underwriter review.*: The bureau score of 608 is above 600, not below.

Every agent's replies, tool calls and tool results are in `panel/records.jsonl`; what ran and where, in `panel/manifest.json`.
