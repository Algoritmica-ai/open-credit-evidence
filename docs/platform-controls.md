# AI Steel Thread as the platform-control layer

OpenCredit Evidence owns the credit-evidence rules and omission result. The FINOS AI Steel Thread
demo owns the execution envelope: workflow, architecture-as-code, data-boundary controls,
observability, acceptance testing, human review, and token/cost records.

## Evidence flow

```text
Steel Thread process instance (businessKey = case_id)
  ├─ mi-1: minimize and police model-bound data
  ├─ mi-4: record calls, model/version, latency, errors, tokens and cost
  ├─ mi-5: run platform and OpenCredit acceptance criteria
  ├─ OpenCredit: evaluate materiality + jurisdiction rules
  └─ mi-11: route omissions, uncertainty and challenges to a human
          ↓
Steel Thread compliance report + OpenCredit evidence report
          ↓
One tamper-evident case record linked by processInstanceId and case_id
```

The pinned profile is
[`platforms/ai-steel-thread/control-profile.json`](../platforms/ai-steel-thread/control-profile.json).
It is based on Steel Thread revision `2782173d47f5074f8767dbdf553fa9165ee1ccd8` and its CALM loan
architecture plus per-instance compliance-report endpoint.

## Importing platform evidence

From a running demo:

```bash
oce process cases/<case> \
  --steel-thread-url http://localhost:8080 \
  --steel-thread-instance <process-instance-id> \
  --output reports/<case>.json
```

Or from an exported report:

```bash
oce process cases/<case> \
  --steel-thread-report compliance-report.json \
  --output reports/<case>.json
```

The adapter imports only structured control and usage evidence. It does not import raw prompts,
responses, identity media, or conversation traces.

## Claim gate

`claim_status=linked` means a Steel Thread report was attached, but at least one proof condition is
missing. `claim_status=verified` requires the same case/business key, frozen instance controls,
mi-1/mi-4/mi-5/mi-11 enabled, passing platform checks, an accepted mi-5 snapshot, and an explicit
`openCreditEvidence` activity/report link.

Until the Steel Thread BPMN actually invokes OpenCredit and emits that link, describe the systems as
**integrated**, not as automatically compliant and not as inheriting controls. When the upstream
activity is added, the same adapter will promote complete evidence to `verified`.

Both the normalized platform evidence and the Italy assessment are included in the evidence chain's
governance fingerprint, so changing either makes report verification fail.

