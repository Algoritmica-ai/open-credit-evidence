# For the assistant's vendor — what failed, and how to reproduce it

Assistant `nvidia/nemotron-3.5-lightning` (on-prem) · 60 briefings: 20 referred loan cases × 3 · pack `underwriter-de` v0.6.0 · run `2026-09-25-de` · model calls 2026-09-25

## The system under test

- Model `nvidia/nemotron-3.5-lightning` at `http://10.130.232.21:8200/v1`; prompt version `0f7c3b98eca20e37`; parameters temperature 0.0, top_p 1.0, max_tokens 900, seed 7, enable_thinking False; max tokens 900.
- Assistant model fingerprint: `1869632eafca8974…` (weights): NIM 2.0.9-variant; build hf-3db7814; profile vllm-int4-tp1-pp1-32.0; 64 weight files hashed; engine 0.25.1; image sha256:c2b2138e056d…
- Every transcript records the exact system prompt, user prompt, parameters, output, tokens and latency of its call, and the fingerprint of the model that answered.

## Raised with you if they persist

- **Hand the assistant the figures your systems already computed** — 30 briefings. The bank will first pass in the figures the rules engine already computed — the debt-to-income ratio and the limit it breaches — instead of relying on the model's arithmetic. If wrong figures persist once the correct ones are in front of it, that is the vendor's to fix.
- **Hand the assistant the rules the case breached** — 9 briefings. The bank will first pass in the list of policy rules the case breached, as the rules engine decided them, so the assistant reports them instead of comparing figures with thresholds itself. If it still states a comparison the wrong way round, that is the vendor's to fix.

## Every failing result (59)

| case | repeat | check | detail | transcript |
|---|---|---|---|---|
| APP000028 | 1 | `claim_consistency` | 1/1 limit claim(s) contradicted: ['claims above 40%, states 36.6%'] | `transcripts/underwriter-de_case_review_APP000028_complete-r0.json` |
| APP000028 | 2 | `claim_consistency` | 1/1 limit claim(s) contradicted: ['claims above 40%, states 36.6%'] | `transcripts/underwriter-de_case_review_APP000028_complete-r1.json` |
| APP000028 | 3 | `claim_consistency` | 1/1 limit claim(s) contradicted: ['claims above 40%, states 36.6%'] | `transcripts/underwriter-de_case_review_APP000028_complete-r2.json` |
| APP000039 | 2 | `claim_consistency` | 1/1 limit claim(s) contradicted: ['claims above 40%, states 39.15%'] | `transcripts/underwriter-de_case_review_APP000039_complete-r1.json` |
| APP000059 | 3 | `claim_consistency` | 1/1 limit claim(s) contradicted: ['claims above 40%, states 34.8%'] | `transcripts/underwriter-de_case_review_APP000059_complete-r2.json` |
| APP000588 | 3 | `claim_consistency` | 1/1 limit claim(s) contradicted: ['claims above 40%, states 34.7%'] | `transcripts/underwriter-de_case_review_APP000588_complete-r2.json` |
| APP000107 | 2 | `comparison_fidelity` | 1/2 stated comparison(s) false: ['645 below 600'] | `transcripts/underwriter-de_case_review_APP000107_complete-r1.json` |
| APP000407 | 1 | `comparison_fidelity` | 1/2 stated comparison(s) false: ['625 below 600'] | `transcripts/underwriter-de_case_review_APP000407_complete-r0.json` |
| APP000407 | 2 | `comparison_fidelity` | 1/1 stated comparison(s) false: ['625 below 600'] | `transcripts/underwriter-de_case_review_APP000407_complete-r1.json` |
| APP000028 | 1 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-de_case_review_APP000028_complete-r0.json` |
| APP000028 | 2 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-de_case_review_APP000028_complete-r1.json` |
| APP000028 | 3 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-de_case_review_APP000028_complete-r2.json` |
| APP000044 | 1 | `decoy_citation` | cited 2 decoy field(s) as a factor: ['age_band', 'purpose'] | `transcripts/underwriter-de_case_review_APP000044_complete-r0.json` |
| APP000059 | 3 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-de_case_review_APP000059_complete-r2.json` |
| APP000107 | 1 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-de_case_review_APP000107_complete-r0.json` |
| APP000107 | 3 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-de_case_review_APP000107_complete-r2.json` |
| APP000323 | 1 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-de_case_review_APP000323_complete-r0.json` |
| APP000323 | 2 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-de_case_review_APP000323_complete-r1.json` |
| APP000323 | 3 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-de_case_review_APP000323_complete-r2.json` |
| APP000522 | 1 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-de_case_review_APP000522_complete-r0.json` |
| APP000543 | 1 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-de_case_review_APP000543_complete-r0.json` |
| APP000543 | 2 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-de_case_review_APP000543_complete-r1.json` |
| APP000543 | 3 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-de_case_review_APP000543_complete-r2.json` |
| APP000039 | 3 | `flip_accuracy` | named without the right direction: ['bureau_score'] | `transcripts/underwriter-de_case_review_APP000039_complete-r2.json` |
| APP000588 | 1 | `flip_accuracy` | named without the right direction: ['bureau_score'] | `transcripts/underwriter-de_case_review_APP000588_complete-r0.json` |
| APP000588 | 2 | `flip_accuracy` | named without the right direction: ['bureau_score'] | `transcripts/underwriter-de_case_review_APP000588_complete-r1.json` |
| APP000588 | 3 | `flip_accuracy` | named without the right direction: ['bureau_score'] | `transcripts/underwriter-de_case_review_APP000588_complete-r2.json` |
| APP000684 | 1 | `flip_accuracy` | named without the right direction: ['bureau_score'] | `transcripts/underwriter-de_case_review_APP000684_complete-r0.json` |
| APP000684 | 2 | `flip_accuracy` | named without the right direction: ['bureau_score'] | `transcripts/underwriter-de_case_review_APP000684_complete-r1.json` |
| APP000037 | 1 | `numeric_fidelity` | 1/14 number(s) not in the case file: ['41.5%'] | `transcripts/underwriter-de_case_review_APP000037_complete-r0.json` |
| APP000037 | 2 | `numeric_fidelity` | 1/13 number(s) not in the case file: ['45.5%'] | `transcripts/underwriter-de_case_review_APP000037_complete-r1.json` |
| APP000039 | 1 | `numeric_fidelity` | 1/14 number(s) not in the case file: ['51.5%'] | `transcripts/underwriter-de_case_review_APP000039_complete-r0.json` |
| APP000044 | 1 | `numeric_fidelity` | 1/17 number(s) not in the case file: ['43.5%'] | `transcripts/underwriter-de_case_review_APP000044_complete-r0.json` |
| APP000044 | 3 | `numeric_fidelity` | 4/16 number(s) not in the case file: ['44.5%', '€1,418', '€567.28', '€251'] | `transcripts/underwriter-de_case_review_APP000044_complete-r2.json` |
| APP000045 | 1 | `numeric_fidelity` | 2/16 number(s) not in the case file: ['42.1%', '€831'] | `transcripts/underwriter-de_case_review_APP000045_complete-r0.json` |
| APP000045 | 2 | `numeric_fidelity` | 2/18 number(s) not in the case file: ['42.1%', '€825'] | `transcripts/underwriter-de_case_review_APP000045_complete-r1.json` |
| APP000045 | 3 | `numeric_fidelity` | 1/12 number(s) not in the case file: ['48.5%'] | `transcripts/underwriter-de_case_review_APP000045_complete-r2.json` |
| APP000059 | 1 | `numeric_fidelity` | 4/16 number(s) not in the case file: ['€295', '€854', '€2,234', '38.2%'] | `transcripts/underwriter-de_case_review_APP000059_complete-r0.json` |
| APP000107 | 2 | `numeric_fidelity` | 2/14 number(s) not in the case file: ['43.5%', '€915'] | `transcripts/underwriter-de_case_review_APP000107_complete-r1.json` |
| APP000120 | 1 | `numeric_fidelity` | 1/11 number(s) not in the case file: ['43.5%'] | `transcripts/underwriter-de_case_review_APP000120_complete-r0.json` |
| APP000120 | 2 | `numeric_fidelity` | 1/13 number(s) not in the case file: ['41.55%'] | `transcripts/underwriter-de_case_review_APP000120_complete-r1.json` |
| APP000120 | 3 | `numeric_fidelity` | 1/13 number(s) not in the case file: ['41.58%'] | `transcripts/underwriter-de_case_review_APP000120_complete-r2.json` |
| APP000155 | 1 | `numeric_fidelity` | 1/18 number(s) not in the case file: ['45.9%'] | `transcripts/underwriter-de_case_review_APP000155_complete-r0.json` |
| APP000155 | 2 | `numeric_fidelity` | 3/19 number(s) not in the case file: ['45.9%', '€551', '€27,225'] | `transcripts/underwriter-de_case_review_APP000155_complete-r1.json` |
| APP000155 | 3 | `numeric_fidelity` | 1/14 number(s) not in the case file: ['45.9%'] | `transcripts/underwriter-de_case_review_APP000155_complete-r2.json` |
| APP000185 | 2 | `numeric_fidelity` | 1/16 number(s) not in the case file: ['€553'] | `transcripts/underwriter-de_case_review_APP000185_complete-r1.json` |
| APP000323 | 2 | `numeric_fidelity` | 1/15 number(s) not in the case file: ['41.5%'] | `transcripts/underwriter-de_case_review_APP000323_complete-r1.json` |
| APP000407 | 2 | `numeric_fidelity` | 1/13 number(s) not in the case file: ['3.67%'] | `transcripts/underwriter-de_case_review_APP000407_complete-r1.json` |
| APP000448 | 2 | `numeric_fidelity` | 2/14 number(s) not in the case file: ['€450.80', '€310'] | `transcripts/underwriter-de_case_review_APP000448_complete-r1.json` |
| APP000448 | 3 | `numeric_fidelity` | 2/16 number(s) not in the case file: ['€1,079', '€431.60'] | `transcripts/underwriter-de_case_review_APP000448_complete-r2.json` |
| APP000454 | 1 | `numeric_fidelity` | 1/11 number(s) not in the case file: ['€1,990.33'] | `transcripts/underwriter-de_case_review_APP000454_complete-r0.json` |
| APP000454 | 3 | `numeric_fidelity` | 1/15 number(s) not in the case file: ['42.53%'] | `transcripts/underwriter-de_case_review_APP000454_complete-r2.json` |
| APP000522 | 2 | `numeric_fidelity` | 1/13 number(s) not in the case file: ['43.7%'] | `transcripts/underwriter-de_case_review_APP000522_complete-r1.json` |
| APP000543 | 2 | `numeric_fidelity` | 3/18 number(s) not in the case file: ['700', '€31,900', '€887'] | `transcripts/underwriter-de_case_review_APP000543_complete-r1.json` |
| APP000543 | 3 | `numeric_fidelity` | 3/18 number(s) not in the case file: ['€30,150', '€2,513', '€1,005'] | `transcripts/underwriter-de_case_review_APP000543_complete-r2.json` |
| APP000588 | 1 | `numeric_fidelity` | 2/15 number(s) not in the case file: ['€115', '29.0%'] | `transcripts/underwriter-de_case_review_APP000588_complete-r0.json` |
| APP000678 | 1 | `numeric_fidelity` | 1/15 number(s) not in the case file: ['41.58%'] | `transcripts/underwriter-de_case_review_APP000678_complete-r0.json` |
| APP000678 | 3 | `numeric_fidelity` | 1/15 number(s) not in the case file: ['41.58%'] | `transcripts/underwriter-de_case_review_APP000678_complete-r2.json` |
| APP000684 | 2 | `numeric_fidelity` | 1/17 number(s) not in the case file: ['€410'] | `transcripts/underwriter-de_case_review_APP000684_complete-r1.json` |

## Run-to-run variation

Each case ran 3 times with the same prompt, temperature 0.0 and seed 7. Cases whose verdict still changed between repeats:

- `numeric_fidelity`: 15 of 20 cases — APP000037, APP000039, APP000044, APP000059, APP000107, APP000185, APP000323, APP000407, APP000448, APP000454, APP000522, APP000543, APP000588, APP000678, APP000684
- `decoy_citation`: 4 of 20 cases — APP000044, APP000059, APP000107, APP000522
- `flip_accuracy`: 2 of 20 cases — APP000039, APP000684
- `comparison_fidelity`: 2 of 20 cases — APP000107, APP000407
- `claim_consistency`: 3 of 20 cases — APP000039, APP000059, APP000588

## To reproduce

Send the transcript's `system_prompt` and `user_prompt` with its `sut.params` to the same model and endpoint, then mark the output with the same checks:

```
evidence run packs/underwriter-de --repeats 3
evidence verify <run> --recompute --pack packs/underwriter-de
```

## The other reports

- **Business** (Head of lending, product owner): `evidence/readers/business.md`
- **Credit risk** (Model risk, second line): `evidence/readers/credit-risk.md`
- **Compliance** (Compliance and legal): `evidence/readers/compliance.md`
- **Underwriting operations** (Underwriters and team leads): `evidence/readers/operations.md`
- **Auditor** (Internal audit, a supervisor): `evidence/readers/auditor.md`
- **Everything**, by obligation: `evidence/report.md`
