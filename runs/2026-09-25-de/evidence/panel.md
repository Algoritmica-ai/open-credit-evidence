# Judge panel

Three agents reviewed each briefing: a **Reader** scored it as the underwriter would, a **Challenger** checked it against the case file and the deterministic checks with tools, and an **Arbiter** gave the final scores and said whether a person should review it. An opinion, reported and never used to pass or fail.

- Ran inside the NemoClaw sandbox `evidence-judge` on rtx-3se-06-04 (OpenShell 0.0.116, network policies: clawhub, local_inference, managed_inference, npm_registry, nvidia, openclaw_api, openclaw_docs, openclaw_gateway_dialback), model route vllm-local / nemotron-3-super. Models: reader `nemotron-3-super`, challenger `nemotron-3-super`, arbiter `nemotron-3-super`.
- 60/60 briefings answered.
- Mean score 0.731 on 0–1 (the single judge: 0.997). Flagged for review: 50.

## Against the deterministic checks

| | briefings | panel flagged | single judge full marks | panel full marks |
|---|---|---|---|---|
| failing at least one check | 46 | 45 | 46 | 3 |
| failing none | 14 | 5 | — | — |

Of the briefings the single judge gave full marks despite a failing check, the panel flagged 45.

The Challenger made 99 findings (87 material), with 7.8 tool calls per briefing on average, and confirmed 44 of the 59 failing check results from what it saw itself.
It disputed checks it thought wrong — worth an auditor's look: `claim_consistency` 4×, `comparison_fidelity` 1×, `flip_accuracy` 2×, `numeric_fidelity` 2×.
It confirmed or disputed a check without reading its evidence 81 times; those verdicts are not counted.

## Within the panel

Reader and Arbiter gave the same score on intelligible 93%, actionable 25%, overridable 27% of briefings; where they differ, the Arbiter weighed the Challenger's findings.
Every citation was a passage the panel was given in 60/60 records.

## Examples: full marks from the single judge, flagged by the panel

- `APP000028` r0 (failing: claim_consistency, decoy_citation): The briefing incorrectly states that the applicant's total monthly debt service exceeds the 40% policy threshold (calculated ratio is 36.6%). — *Specifically, the applicant’s total monthly debt service exceeds the policy threshold of 40% of gross monthly income*: The debt service ratio is 36.6%, which is below the 40% threshold.
- `APP000028` r1 (failing: claim_consistency, decoy_citation): Incorrect claim that debt service exceeds 40% threshold (actual 36.6%) — *the applicant’s total monthly debt service exceeds the policy threshold of 40% of gross monthly income*: The debt service ratio is 36.6%, which is below the 40% threshold.
- `APP000028` r2 (failing: claim_consistency, decoy_citation): Incorrect claim that debt service exceeds the 40% threshold when it is actually 36.6% — *Specifically, the applicant’s total monthly debt service exceeds the policy threshold of 40% of gross monthly income*: The debt service ratio is 36.6%, which is below the 40% threshold, so it does not exceed it.

Every agent's replies, tool calls and tool results are in `panel/records.jsonl`; what ran and where, in `panel/manifest.json`.
