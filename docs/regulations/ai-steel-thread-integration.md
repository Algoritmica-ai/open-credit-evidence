# AI Steel Thread integration contract

## Objective

Run OpenCredit Evidence as the materiality and omission-checking control inside the FINOS AI Steel
Thread loan workflow. The Steel Thread remains the process and control host; OpenCredit produces a
linked evidence report before a credit decision proceeds.

## Target flow

```text
Steel Thread case and source documents
                ↓
        AI-generated case summary
                ↓
 OpenCredit materiality + omission check
                ↓
 OpenCredit evidence report linked to the same process instance
          ↙                              ↘
 omission/failure                  complete/pass
 mandatory human review       continue under lending policy
```

## Control composition

| Stage | Control owner | Required evidence |
|---|---|---|
| Data sent to the summary/checking service | Steel Thread `FINOS-AIGF-MI-1` | Allowed data categories, redaction result, blocked fields |
| OpenCredit execution and report production | Steel Thread `FINOS-AIGF-MI-4` + OpenCredit | Process/activity ID, model and checker version, timestamps, result and report ID |
| Materiality and omission test | OpenCredit + Steel Thread `FINOS-AIGF-MI-5` | Critical facts, results, thresholds and test-suite version |
| Omission, uncertainty or challenge | Steel Thread `FINOS-AIGF-MI-11` | Human task, reviewer decision, override/reason and timestamp |

## Minimum linking fields

The Steel Thread and OpenCredit records must share:

- `process_instance_id` — canonical Steel Thread workflow instance;
- `case_id` — OpenCredit case identifier;
- `evidence_report_id` and `chain_fingerprint`;
- `jurisdiction` — ISO country code such as `IT`;
- `regulatory_obligation_ids` — IDs from the country registry;
- `finos_controls` — control IDs active for that run;
- `control_posture_captured_at`;
- OpenCredit version, materiality-rule version, checker version, and model identifier;
- final human outcome and reason where a human review occurs.

## When control inheritance may be stated

OpenCredit may say it **operated within the Steel Thread control environment** only when all of the
following are evidenced for the same process instance:

1. OpenCredit is invoked from the governed Steel Thread workflow.
2. The Steel Thread records the active control posture for the run.
3. `mi-1` covers every OpenCredit-related data boundary.
4. `mi-4` records the OpenCredit invocation and result.
5. OpenCredit tests are included in or referenced from `mi-5` acceptance evidence.
6. Failed or uncertain OpenCredit results route to the `mi-11` human-review path.

If any condition is absent, state only that the systems are integrated. Do not claim inherited
controls or compliance.

## Example evidence metadata

```json
{
  "jurisdiction": "IT",
  "regulatory_obligation_ids": [
    "IT-TUB-124-BIS-1-TER",
    "IT-TUB-124-BIS-2-BIS-A",
    "IT-TUB-124-BIS-2-BIS-C"
  ],
  "steel_thread": {
    "process_instance_id": "loan-process-123",
    "activity_id": "open-credit-materiality-check",
    "controls": [
      "FINOS-AIGF-MI-1",
      "FINOS-AIGF-MI-4",
      "FINOS-AIGF-MI-5",
      "FINOS-AIGF-MI-11"
    ],
    "control_posture_captured_at": "2026-09-15T12:00:00Z"
  },
  "open_credit": {
    "evidence_report_id": "EVR-20260915-EXAMPLE",
    "chain_fingerprint": "sha256:example",
    "materiality_rule_version": "1.0.0",
    "checker_version": "0.1.0"
  }
}
```

## Important integrity gap

OpenCredit's current chain fingerprint covers the case, summary, and marking result, but not the
free-form report metadata. Before production integration, the fields above should become typed
fields in the evidence schema and be included in the tamper-verification payload.
