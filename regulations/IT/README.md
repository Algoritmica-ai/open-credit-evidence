# Italy — credit and lending evidence rules

`ruleset.json` is the Italy rule pack for the Credit Evidence Engine. It covers the core national instruments
relevant to an Italian bank or Article 106 financial intermediary assessing consumer or residential
mortgage credit with personal data, credit databases, and AI-assisted processing.

## What the result means

- `pass`: every required evidence key for every applicable active rule is populated.
- `fail`: at least one applicable active rule lacks an evidence reference.
- `advisory`: the instrument is a transition or contextual rule and does not block the result.
- `not_applicable`: the case facts do not match the encoded applicability conditions.

Coverage is complete only when the output contains one finding for every rule in this file. A pass
means *evidence complete against this ruleset version*, not legally compliant.

## Current transition

Legislative Decree 212/2025 transposes Directive (EU) 2023/2225. The decree says lenders and credit
intermediaries must adapt by 20 November 2026 or, if later, within 90 days after the relevant Bank of
Italy implementing provisions enter into force. Its new automated-processing and data-source rules
are therefore tracked as non-blocking transition rules in this version. Compliance should approve a
new ruleset version when the operative date is known.

## Scope boundaries

This is a maintainable operational baseline, not an exhaustive legal inventory. It excludes
entity-specific supervisory measures and specialist regimes such as business lending, microcredit,
agricultural credit, salary-backed loans, non-performing-loan servicing, securitisation, guarantees,
subsidised credit, and product distribution unless added to a later profile. EU rules such as the AI
Act, GDPR, DORA, and EBA guidelines remain a separate EU baseline; the FINOS control IDs here connect
the Italian evidence requirements to the Steel Thread platform layer.

Start from [`case-context.example.json`](case-context.example.json), replace every example
string with a real artefact ID, document path, workflow task or control result, and save the
complete object as `regulatory_context.json` in the pack directory. `evidence rules <pack>`
evaluates it; `evidence run` includes the assessment in the evidence pack.
