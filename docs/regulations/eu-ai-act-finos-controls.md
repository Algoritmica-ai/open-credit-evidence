# EU AI Act baseline and FINOS controls

Country registries contain national law only. EU-wide AI Act obligations are referenced once here
and implemented through the FINOS AI Governance Framework where a relevant control exists.

## Creditworthiness scope

An AI system used to evaluate a natural person's creditworthiness or establish their credit score
is within the scenario described by EU AI Act Article 6 and Annex III, point 5(b), except systems
used only to detect financial fraud. Classification still depends on the actual intended purpose
and deployment.

Canonical legal source: [current consolidated EU AI Act](https://eur-lex.europa.eu/eli/reg/2024/1689/2026-07-27/eng).

## Evidence-oriented mapping

| FINOS control ID | Steel Thread implementation | EU AI Act relevance | Honest claim |
|---|---|---|---|
| `FINOS-AIGF-MI-1` | Data leakage prevention and redaction | Arts. 10 and 15; also supports privacy controls outside the AI Act | Contributes evidence; does not establish data governance compliance |
| `FINOS-AIGF-MI-4` | LLM metadata, latency/error metrics, sanitized audit and tracing | Arts. 12 and 15 | Strong record-keeping evidence, subject to retention, access and integrity controls |
| `FINOS-AIGF-MI-5` | Deterministic system acceptance tests | Arts. 9 and 15 | Test evidence; not a complete lifecycle risk-management or accuracy programme |
| `FINOS-AIGF-MI-11` | Loan-officer review and structured feedback on manual-review paths | Arts. 14 and 26 | Human-review evidence; does not prove that oversight is sufficient for every decision path |

Steel Thread source: [FINOS AI Steel Thread Demo](https://github.com/finos-hack/ai-steel-thread-demo).

## the engine-specific contribution

the Credit Evidence Engine adds controls that are not supplied by the Steel Thread:

- a materiality specification for what a credit summary must contain;
- omission testing against decision-critical source facts;
- case, summary, and marking fingerprints;
- an evidence report that can be attached to the governed workflow.

This contributes particularly to EU AI Act Articles 9, 11, 12, 13, 14, and 15. It does not perform
conformity assessment, registration, post-market monitoring, incident reporting, a fundamental
rights impact assessment, or an affected-person explanation by itself.
