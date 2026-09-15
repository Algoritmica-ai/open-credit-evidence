# Jurisdiction rule packs

This directory contains versioned, machine-readable evidence rules selected by the ISO 3166-1
country code in a case's `regulatory_context`.

```text
regulations/
└── IT/
    ├── README.md
    ├── case-context.example.json
    └── ruleset.json
```

Run every rule in the selected pack:

```bash
oce check-rules cases/<case-directory>
```

`oce process` runs the same check automatically and places the complete assessment, ruleset
version, ruleset fingerprint, and every evaluated rule ID in the tamper-evident report.

The checker verifies that required evidence references are present. It does not determine legal
applicability, interpret law, or certify compliance. A lender's legal and compliance functions must
approve the scope and the evidence behind each reference.

