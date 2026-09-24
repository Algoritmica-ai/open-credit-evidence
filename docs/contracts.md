# Contracts

Three records cross the boundary between the pack and the engine. The typed
versions are in `src/evidence/contracts/`; this page is the same thing as JSON so
it can be read without opening Python. A fourth record, the regulatory context and
assessment, is in `contracts/regulatory.py` and described at the end.

---

## 1. Item — what the pack gives the engine

One line of `packs/<pack>/items.jsonl`. Typed as `BenchmarkItem` in `contracts/item.py`.

```jsonc
{
  "item_id": "underwriter-sample:case_review:APP000044:complete",
  "pack": "underwriter-sample",
  "domain": "credit_underwriting",
  "task": "case_review",

  "prompt": "You are supporting an underwriter. This application was referred ...",
  "context": [
    { "renderer": "application_form", "variant": "complete", "content": "# Personal Loan Application ..." },
    { "renderer": "bureau_summary",   "variant": "complete", "content": "# Credit Bureau Summary ..." }
  ],

  "deterministic_checks": ["material_omission"],
  "judges": [],
  "tags": { "difficulty": "near_boundary", "variant": "complete", "policy_dim": "oversight" },

  "grading": {
    "disposition": "refer",
    "top_n": 1,
    "driver_refs":   ["dti_ratio"],
    "driver_labels": { "dti_ratio": "debt-to-income ratio of 47% exceeds the 40% policy limit" },
    "driver_aliases": { "dti_ratio": ["debt to income", "DTI", "debt service", "..."] },
    "driver_directions": { "dti_ratio": "decreases" },
    "decoy_refs":    ["age_band", "dependants", "employer_name", "postcode_district", "..."],
    "decoy_aliases": { "postcode_district": ["postcode", "..."] },
    "omission_refs":   ["dti_ratio", "policy_limit_dti"],
    "omission_labels": { "dti_ratio": "...", "policy_limit_dti": "the 40% debt-to-income policy limit" },
    "omission_aliases": { "dti_ratio": ["47%", "exceeds the 40%", "..."], "policy_limit_dti": ["40%", "..."] },
    "flip_refs": [ { "ref": "gross_annual", "direction": "increase" } ],
    "flip_aliases": { "gross_annual": ["income", "gross monthly income", "earnings"], "amount": ["loan amount", "..."] },
    "flip_alternatives": { "gross_annual": [ { "ref": "amount", "direction": "decrease" },
                                             { "ref": "term_months", "direction": "increase" },
                                             { "ref": "existing_credit_monthly", "direction": "decrease" } ] },
    "contradiction_refs": [],
    "contradiction_labels": {}
  },

  "counterfactual_of": null,
  "perturbation_kind": null,
  "expected_disposition_change": null
}
```

**What the engine does with it:** send `prompt` as the system message and the joined
`context` contents as the user message (or, with RAG, retrieve from `context` first).
Pass the whole item to every check named in `deterministic_checks`. Never read `grading`
for anything except grading.

**What is deliberately absent:** scores, margins, contributions, flip thresholds. The
loader should refuse an item that carries any key named `score`, `margin`,
`contributions` or `threshold` — that is a leaked answer key.

---

## 2. Transcript — what the runner writes per item

Typed as `Transcript` in `contracts/transcript.py`. One per (item, repeat).

```jsonc
{
  "item_id": "underwriter-sample:case_review:APP000044:complete",
  "run_id": "2026-09-20-build",
  "repeat": 0,
  "sut": {
    "model_id": "nvidia/nemotron-3.5-lightning-30b-a3b",
    "prompt_version": "0f7c3b98eca20e37",
    "params": { "temperature": 0.0, "top_p": 1.0, "max_tokens": 900, "seed": 7, "enable_thinking": false },
    "endpoint": "https://integrate.api.nvidia.com/v1"
  },
  "system_prompt": "...",
  "user_prompt": "...",
  "retrieved": [
    { "renderer": "application_form", "chunk_id": "application_form#0", "score": 0.39, "text": "..." }
  ],
  "output": "**Case Summary for Underwriter Review: APP000044** ...",
  "latency_ms": 101475,
  "tokens_in": 439,
  "tokens_out": 598,
  "provider_id": "chatcmpl-...",
  "started_at": "2026-09-16T10:22:03Z",
  "sha256": "..."
}
```

`retrieved` is the field that matters for RAG. If the chunk containing the ratio was never
retrieved, an omission is a retrieval failure, not a model failure, and the evidence pack
has to say which. Empty list means the model was handed everything.

`endpoint` says whether the briefing was produced in the cloud or on the team's own
hardware; `repeat` is the 0-based index when an item is run more than once.

---

## 3. Check result — what every check returns

Typed as `CheckResult` in `contracts/check.py`; `.to_score()` gives the stored form.

```jsonc
{
  "judge": "check:material_omission",
  "judge_trace_id": null,
  "value": 0.5,
  "passed": false,
  "detail": "omitted 1/2 material fact(s): ['the 40% debt-to-income policy limit']",
  "evidence": [
    { "ref": "dti_ratio",        "matched": true,  "method": "exact", "form": "47%", "span": [612, 615] },
    { "ref": "policy_limit_dti", "matched": false, "method": null }
  ],
  "needs_audit": false
}
```

A judge result uses the same shape with `"judge": "model:<model id>"`, a real
`judge_trace_id`, the `endpoint`, `passed: null` (readability is reported, not gated) and
`needs_audit: true` (a model opinion is always auditable). **`needs_audit` is mandatory
reporting** — the evidence pack shows the count of results that leaned on similarity
matching.

---

## 4. Where things go on disk

```
runs/<run_id>/
  manifest.json                    pack id + sha256, SUT and judge pins, endpoints, checks, repeats, engine commit, timings
  results.jsonl                    one record per (item, repeat, check): item_id, repeat, check + the check-result shape above
  transcripts/<item>-r<n>.json     one Transcript per (item, repeat)
  regulations.json                 jurisdiction rule-pack assessment
  evidence/report.md               the pack, by obligation, with everything
  evidence/readers/<reader>.md     the same evidence per reader: business (one page), credit-risk,
                                   compliance, operations, vendor, auditor
  evidence/summary.json            the numbers behind the report
  evidence/decision.json           GO / GO WITH CONDITIONS / NO-GO / INCONCLUSIVE, against thresholds.yaml
  evidence/diagnosis.json          a root cause for every failing result
  evidence/recommendations.json    what to change, and who can
  evidence/thresholds.yaml         the bank's thresholds — an input
  evidence/obligations.yaml        the pack's claims, copied verbatim
  checksums.sha256                 every file above
```

The runner is **resumable**: a transcript that exists is reused. `evidence verify`
re-hashes every file; `--recompute` re-runs every deterministic check from the
transcripts and compares.

---

## 5. Regulatory context and assessment

Typed in `contracts/regulatory.py`. A pack may carry `regulatory_context.json`: the
jurisdiction, product, customer and lender type, decision mode, and a map of evidence
references keyed by requirement id. `evidence run` evaluates the matching rule pack in
`regulations/<CC>/ruleset.json` and writes `regulations.json` into the run:

```jsonc
{
  "jurisdiction": "IT",
  "ruleset_id": "IT-CREDIT-LENDING",
  "ruleset_version": "1.0.0",
  "ruleset_sha256": "...",
  "context_sha256": "...",
  "status": "pass",                 // pass | fail | unscoped | ruleset_not_found
  "coverage_complete": true,
  "total_rules": 16, "applicable_rules": 12, "passed_rules": 9, "failed_rules": 0, "advisory_rules": 3,
  "findings": [ { "rule_id": "IT-TUB-124-BIS-CURRENT", "status": "pass", "missing_evidence": [], "...": "..." } ],
  "note": "evidence-presence assessment only; legal applicability and substantive compliance require lender and legal review"
}
```

The assessment is covered by `checksums.sha256` like every other file in the run.

---

## Calls the engine makes

```python
from evidence.adapters.nvidia_build import chat, embed
from evidence.checks import run_checks

r = chat("assistant", system=item.prompt, user=joined_context)       # -> ChatResponse
results = run_checks(item.deterministic_checks, output=r.text, item=item)
```

Rate limit on the account: 40 requests/minute. One worker is fine; the endpoint is the
bottleneck, not us.
