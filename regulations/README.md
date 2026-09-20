# Jurisdiction rule packs and obligation registries

Regulatory overlays for the Credit Evidence Engine, one directory per ISO 3166-1
country code. Legislation is not copied here; official publications remain the
canonical text. The files give stable IDs, applicability conditions, evidence
expectations, and links to those sources.

```text
regulations/
├── README.md
├── ruleset.schema.json        machine-readable rules: applicability + required evidence keys
├── registry.schema.json       obligation registry: stable IDs, status, sources, FINOS mapping
└── IT/
    ├── README.md              the Italy rule pack and what a result means
    ├── REGISTRY.md            the Italy obligation registry, priorities and transition notes
    ├── ruleset.json           IT-CREDIT-LENDING v1.0.0 — 16 rules
    ├── registry.json          obligation IDs with citations and official sources
    └── case-context.example.json   a complete regulatory context to start from
```

## How the engine uses a rule pack

A pack may carry `regulatory_context.json` (start from the example). `evidence run`
evaluates the rule pack for that jurisdiction and writes `regulations.json` into the
run, covered by the run's checksums; `evidence rules <pack>` evaluates it on its own.

- `pass` — every required evidence key for every applicable, required rule is present.
- `fail` — an applicable, required rule lacks an evidence reference; the key is named.
- `advisory` — a transition or contextual rule; reported, does not block.
- `not_applicable` — the context does not match the rule's applicability conditions.

A pass means *evidence complete against this rule-pack version*, not legally
compliant. The checker verifies that required evidence references are present. It
does not determine legal applicability, interpret law, or certify compliance; a
lender's legal and compliance functions approve the scope and the evidence behind
each reference.

## Stable IDs

`<COUNTRY>-<INSTRUMENT>-<PROVISION>`, uppercase, e.g. `IT-TUB-124-BIS-2-BIS-A`. IDs
are permanent. Correct a description or a source URL without changing the ID; if
legislation creates a materially different obligation, add a new ID and deprecate
the old one. The tests reject malformed and duplicate IDs.

## Adding a country

1. Copy `IT/` to the new country code.
2. Replace the Italy entries with the national instruments, from official sources.
3. Keep EU-wide obligations in `docs/regulations/eu-ai-act-finos-controls.md`
   rather than duplicating them.
4. Map each national obligation to the engine's evidence and, where one applies,
   to a FINOS AI Governance Framework control.
5. Record the verification date and any transition status.
6. Run `pytest tests/test_regulations.py`.

## Interpretation rule

A FINOS control reference means the control may produce useful evidence for an
obligation. It does not mean that using the control proves compliance. Likewise,
the engine verifies materiality and evidence integrity; it does not make legal
decisions or certify a lender.
