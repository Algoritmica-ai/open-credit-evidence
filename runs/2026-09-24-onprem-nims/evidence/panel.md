# Judge panel

Three agents reviewed each briefing: a **Reader** scored it as the underwriter would, a **Challenger** checked it against the case file and the deterministic checks with tools, and an **Arbiter** gave the final scores and said whether a person should review it. An opinion, reported and never used to pass or fail.

- Ran inside the NemoClaw sandbox `evidence-judge` on rtx-3se-06-04 (OpenShell 0.0.116, network policies: clawhub, local_inference, managed_inference, npm_registry, nvidia, openclaw_api, openclaw_docs, openclaw_gateway_dialback), model route vllm-local / nano-judge. Models: reader `nano-judge`, challenger `nano-judge`, arbiter `nano-judge`.
- 60/60 briefings answered.
- Mean score 0.692 on 0–1 (the single judge: 0.981). Flagged for review: 46.

## Against the deterministic checks

| | briefings | panel flagged | single judge full marks | panel full marks |
|---|---|---|---|---|
| failing at least one check | 46 | 44 | 42 | 4 |
| failing none | 14 | 2 | — | — |

Of the briefings the single judge gave full marks despite a failing check, the panel flagged 40.

The Challenger made 83 findings (70 material), with 0.8 tool calls per briefing on average, and confirmed 0 of the 61 failing check results from what it saw itself.
It disputed checks it thought wrong — worth an auditor's look: `claim_consistency` 2×.
It confirmed or disputed a check without reading its evidence 193 times; those verdicts are not counted.

## Within the panel

Reader and Arbiter gave the same score on intelligible 70%, actionable 48%, overridable 30% of briefings; where they differ, the Arbiter weighed the Challenger's findings.
Every citation was a passage the panel was given in 60/60 records.

## Examples: full marks from the single judge, flagged by the panel

- `APP000028` r0 (failing: claim_consistency, decoy_citation): Material error in debt service ratio claim (36.5% vs. incorrectly stated 40%) contradicts case file and undermines referral rationale — *the applicant’s total monthly debt service exceeds the 40% affordability threshold*: the actual debt service ratio is 36.5%, not above 40%
- `APP000028` r1 (failing: decoy_citation): Material error in affordability calculation (3.04% vs. claimed 40%+), misuse of unverified income for critical assessment — *total monthly debt service exceeds 40% of gross monthly income*: Calculated total debt service (£760) is 3.04% of £24,951 annual income, not exceeding 40%
- `APP000028` r2 (failing: claim_consistency, comparison_fidelity, decoy_citation): Material error in debt service ratio claim (36.5% vs. 40% threshold) — *The total monthly debt service exceeds the 40% threshold of gross monthly income*: The actual debt service ratio is 36.5%, not above 40%

Every agent's replies, tool calls and tool results are in `panel/records.jsonl`; what ran and where, in `panel/manifest.json`.
