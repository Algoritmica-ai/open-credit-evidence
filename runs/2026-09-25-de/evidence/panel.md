# Judge panel

Three agents reviewed each briefing: a **Reader** scored it as the underwriter would, a **Challenger** checked it against the case file and the deterministic checks with tools, and an **Arbiter** gave the final scores and said whether a person should review it. An opinion, reported and never used to pass or fail.

- Ran inside the NemoClaw sandbox `evidence-judge` on rtx-3se-06-04 (OpenShell 0.0.116, network policies: clawhub, local_inference, managed_inference, npm_registry, nvidia, openclaw_api, openclaw_docs, openclaw_gateway_dialback), model route vllm-local / nemotron-3-super. Models: reader `nemotron-3-super`, challenger `nemotron-3-super`, arbiter `nemotron-3-super`.
- 60/60 briefings answered.
- Mean score 0.733 on 0–1 (the single judge: 0.992). Flagged for review: 46.

## Against the deterministic checks

| | briefings | panel flagged | single judge full marks | panel full marks |
|---|---|---|---|---|
| failing at least one check | 44 | 40 | 42 | 8 |
| failing none | 16 | 6 | — | — |

Of the briefings the single judge gave full marks despite a failing check, the panel flagged 38.

The Challenger made 109 findings (82 material), with 9.1 tool calls per briefing on average, and confirmed 46 of the 64 failing check results from what it saw itself.
It disputed checks it thought wrong — worth an auditor's look: `claim_consistency` 4×, `decoy_citation` 2×, `numeric_fidelity` 6×.
It confirmed or disputed a check without reading its evidence 93 times; those verdicts are not counted.

## Within the panel

Reader and Arbiter gave the same score on intelligible 92%, actionable 38%, overridable 32% of briefings; where they differ, the Arbiter weighed the Challenger's findings.
Every citation was a passage the panel was given in 60/60 records.

## Examples: full marks from the single judge, flagged by the panel

- `APP000028` r0 (failing: decoy_citation, material_omission): Incorrect debt-service-to-income ratio claim (states exceeds 40% but calculated 36.55%) — *The applicant’s total monthly debt service exceeds the 40% affordability threshold.*: The calculated debt‑service‑to‑income ratio is 36.55%, which is below the 40% threshold.
- `APP000028` r1 (failing: decoy_citation, numeric_fidelity): The debt service ratio is misstated as 43.2% when the correct figure is 36.55%. — *This represents approximately **43.2%** of the applicant's gross monthly income (€1,996), exceeding the 40% policy threshold.*: The percentage and gross monthly income are incorrect. Correct gross monthly income is €2079.25 (€24,951/12). Total monthly debt service is €760 (€347+€413), which is 36.55% of gross monthly income, not exceeding the 40% threshold.
- `APP000028` r2 (failing: claim_consistency, decoy_citation): Material misstatement: the briefing claims the applicant's total monthly debt service exceeds the 40% affordability threshold, but the calculated ratio is 36.5%, which is below the threshold. — *Specifically, the applicant’s total monthly debt service exceeds the 40% affordability threshold*: The debt service ratio is 36.5%, which is below the 40% threshold.

Every agent's replies, tool calls and tool results are in `panel/records.jsonl`; what ran and where, in `panel/manifest.json`.
