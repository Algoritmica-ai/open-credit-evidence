# Jurisdiction regulation registry

This directory contains jurisdiction-specific regulatory overlays for OpenCredit Evidence.
It does **not** copy legislation into the repository. Official publications remain the canonical
legal text; the files here provide stable IDs, applicability notes, evidence expectations, and
links to those sources.

## Directory layout

```text
docs/regulations/
├── README.md
├── registry.schema.json
├── eu-ai-act-finos-controls.md
├── ai-steel-thread-integration.md
└── jurisdictions/
    └── IT/
        ├── README.md
        └── registry.json
```

Use the ISO 3166-1 alpha-2 country code as the folder name. Future examples are `DE` for Germany,
`FR` for France, and `ES` for Spain.

## Stable regulation IDs

IDs are uppercase and start with the country code:

```text
<COUNTRY>-<INSTRUMENT>-<PROVISION>
```

Examples:

- `IT-TUB-124-BIS-1-TER` — documented and updated creditworthiness procedures.
- `IT-TUB-124-BIS-2-BIS-A` — explanation of an automated creditworthiness assessment.
- `IT-SIC-CODE-2019` — Italian private credit-information systems Code of Conduct.

IDs are permanent API identifiers. Correct a description or source URL without changing its ID.
If legislation creates a materially different obligation, add a new ID and deprecate the old one.

## Linking an evidence report

Until the evidence schema has dedicated regulatory fields, use the existing report `metadata`
object:

```json
{
  "jurisdiction": "IT",
  "regulatory_obligation_ids": [
    "IT-TUB-124-BIS-1-TER",
    "IT-TUB-124-BIS-2-BIS-A"
  ],
  "steel_thread": {
    "process_instance_id": "loan-process-123",
    "controls": [
      "FINOS-AIGF-MI-1",
      "FINOS-AIGF-MI-4",
      "FINOS-AIGF-MI-5",
      "FINOS-AIGF-MI-11"
    ]
  }
}
```

The current chain fingerprint does not cover arbitrary report metadata. Treat this as an
integration format for now; making these references first-class, tamper-covered evidence fields
is a required implementation step before making production assurance claims.

## Adding another country

1. Copy `jurisdictions/IT` to the new ISO country code.
2. Replace Italy-specific entries with official national sources.
3. Keep EU-wide obligations in the shared EU/FINOS mapping rather than duplicating them.
4. Map each national obligation to OpenCredit evidence and, where applicable, FINOS controls.
5. Record the verification date and transitional/application status.
6. Run the test suite; registry tests reject malformed and duplicate IDs.

## Interpretation rule

`FINOS control reference` means that a control may produce useful evidence for an obligation. It
does not mean that using a FINOS control proves compliance. Likewise, OpenCredit Evidence verifies
materiality and evidence integrity; it does not make legal decisions or certify a lender.
