# For the assistant's vendor — what failed, and how to reproduce it

Assistant `nvidia/nemotron-3.5-lightning` (on-prem) · 60 briefings: 20 referred loan cases × 3 · pack `underwriter-sample` v0.5.0 · run `2026-09-24-onprem-fingerprinted` · model calls 2026-09-24

## The system under test

- Model `nvidia/nemotron-3.5-lightning` at `http://10.130.232.21:8200/v1`; prompt version `0f7c3b98eca20e37`; parameters temperature 0.0, top_p 1.0, max_tokens 900, seed 7, enable_thinking False; max tokens 900.
- Assistant model fingerprint: `1869632eafca8974…` (weights): NIM 2.0.9-variant; build hf-3db7814; profile vllm-int4-tp1-pp1-32.0; 64 weight files hashed; engine 0.25.1; image sha256:c2b2138e056d…
- Every transcript records the exact system prompt, user prompt, parameters, output, tokens and latency of its call, and the fingerprint of the model that answered.

## Raised with you if they persist

- **Hand the assistant the figures your systems already computed** — 30 briefings. The bank will first pass in the figures the rules engine already computed — the debt-to-income ratio and the limit it breaches — instead of relying on the model's arithmetic. If wrong figures persist once the correct ones are in front of it, that is the vendor's to fix.
- **Hand the assistant the rules the case breached** — 16 briefings. The bank will first pass in the list of policy rules the case breached, as the rules engine decided them, so the assistant reports them instead of comparing figures with thresholds itself. If it still states a comparison the wrong way round, that is the vendor's to fix.

## Every failing result (56)

| case | repeat | check | detail | transcript |
|---|---|---|---|---|
| APP000028 | 1 | `claim_consistency` | 1/1 limit claim(s) contradicted: ['claims above 40%, states 36.6%'] | `transcripts/underwriter-sample_case_review_APP000028_complete-r0.json` |
| APP000028 | 2 | `claim_consistency` | 1/1 limit claim(s) contradicted: ['claims above 40%, states 36.6%'] | `transcripts/underwriter-sample_case_review_APP000028_complete-r1.json` |
| APP000028 | 3 | `claim_consistency` | 1/1 limit claim(s) contradicted: ['claims above 40%, states 36.6%'] | `transcripts/underwriter-sample_case_review_APP000028_complete-r2.json` |
| APP000039 | 2 | `claim_consistency` | 1/1 limit claim(s) contradicted: ['claims above 40%, states 39.1%'] | `transcripts/underwriter-sample_case_review_APP000039_complete-r1.json` |
| APP000044 | 3 | `claim_consistency` | 1/1 limit claim(s) contradicted: ['claims above 40%, states 39.6%'] | `transcripts/underwriter-sample_case_review_APP000044_complete-r2.json` |
| APP000059 | 1 | `claim_consistency` | 1/1 limit claim(s) contradicted: ['claims above 40%, states 34.5%'] | `transcripts/underwriter-sample_case_review_APP000059_complete-r0.json` |
| APP000107 | 1 | `claim_consistency` | 1/1 limit claim(s) contradicted: ['claims above 40%, states 33.2%'] | `transcripts/underwriter-sample_case_review_APP000107_complete-r0.json` |
| APP000107 | 3 | `claim_consistency` | 1/1 limit claim(s) contradicted: ['claims above 40%, states 31.1%'] | `transcripts/underwriter-sample_case_review_APP000107_complete-r2.json` |
| APP000155 | 1 | `claim_consistency` | 1/1 limit claim(s) contradicted: ['claims above 40%, states 4.59%'] | `transcripts/underwriter-sample_case_review_APP000155_complete-r0.json` |
| APP000155 | 2 | `claim_consistency` | 1/1 limit claim(s) contradicted: ['claims above 40%, states 4.6%'] | `transcripts/underwriter-sample_case_review_APP000155_complete-r1.json` |
| APP000172 | 3 | `claim_consistency` | 1/1 limit claim(s) contradicted: ['claims above 40%, states 35.8%'] | `transcripts/underwriter-sample_case_review_APP000172_complete-r2.json` |
| APP000407 | 3 | `claim_consistency` | 1/1 limit claim(s) contradicted: ['claims above 40%, states 36.67%'] | `transcripts/underwriter-sample_case_review_APP000407_complete-r2.json` |
| APP000448 | 3 | `claim_consistency` | 1/1 limit claim(s) contradicted: ['claims above 40%, states 4.04%'] | `transcripts/underwriter-sample_case_review_APP000448_complete-r2.json` |
| APP000588 | 2 | `claim_consistency` | 1/1 limit claim(s) contradicted: ['claims above 40%, states 34.7%'] | `transcripts/underwriter-sample_case_review_APP000588_complete-r1.json` |
| APP000684 | 3 | `claim_consistency` | 1/1 limit claim(s) contradicted: ['claims above 40%, states 3.7%'] | `transcripts/underwriter-sample_case_review_APP000684_complete-r2.json` |
| APP000543 | 2 | `comparison_fidelity` | 1/1 stated comparison(s) false: ['679 below 600'] | `transcripts/underwriter-sample_case_review_APP000543_complete-r1.json` |
| APP000028 | 1 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['postcode_district'] | `transcripts/underwriter-sample_case_review_APP000028_complete-r0.json` |
| APP000037 | 2 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-sample_case_review_APP000037_complete-r1.json` |
| APP000044 | 1 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-sample_case_review_APP000044_complete-r0.json` |
| APP000044 | 2 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-sample_case_review_APP000044_complete-r1.json` |
| APP000059 | 3 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-sample_case_review_APP000059_complete-r2.json` |
| APP000407 | 3 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['postcode_district'] | `transcripts/underwriter-sample_case_review_APP000407_complete-r2.json` |
| APP000522 | 1 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-sample_case_review_APP000522_complete-r0.json` |
| APP000522 | 2 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-sample_case_review_APP000522_complete-r1.json` |
| APP000684 | 2 | `flip_accuracy` | named without the right direction: ['bureau_score'] | `transcripts/underwriter-sample_case_review_APP000684_complete-r1.json` |
| APP000684 | 3 | `flip_accuracy` | named without the right direction: ['bureau_score'] | `transcripts/underwriter-sample_case_review_APP000684_complete-r2.json` |
| APP000028 | 1 | `numeric_fidelity` | 1/14 number(s) not in the case file: ['699'] | `transcripts/underwriter-sample_case_review_APP000028_complete-r0.json` |
| APP000037 | 1 | `numeric_fidelity` | 1/20 number(s) not in the case file: ['£373'] | `transcripts/underwriter-sample_case_review_APP000037_complete-r0.json` |
| APP000037 | 2 | `numeric_fidelity` | 1/14 number(s) not in the case file: ['48.7%'] | `transcripts/underwriter-sample_case_review_APP000037_complete-r1.json` |
| APP000044 | 3 | `numeric_fidelity` | 1/15 number(s) not in the case file: ['39.6%'] | `transcripts/underwriter-sample_case_review_APP000044_complete-r2.json` |
| APP000045 | 1 | `numeric_fidelity` | 3/19 number(s) not in the case file: ['43.5%', '£1,072', '£162'] | `transcripts/underwriter-sample_case_review_APP000045_complete-r0.json` |
| APP000045 | 2 | `numeric_fidelity` | 1/14 number(s) not in the case file: ['45.5%'] | `transcripts/underwriter-sample_case_review_APP000045_complete-r1.json` |
| APP000045 | 3 | `numeric_fidelity` | 1/10 number(s) not in the case file: ['41.5%'] | `transcripts/underwriter-sample_case_review_APP000045_complete-r2.json` |
| APP000059 | 1 | `numeric_fidelity` | 2/22 number(s) not in the case file: ['£295', '£850'] | `transcripts/underwriter-sample_case_review_APP000059_complete-r0.json` |
| APP000059 | 3 | `numeric_fidelity` | 7/19 number(s) not in the case file: ['£295', '£854', '43.5%', '£1,970', '3.5%', '£788', '£229'] | `transcripts/underwriter-sample_case_review_APP000059_complete-r2.json` |
| APP000120 | 1 | `numeric_fidelity` | 1/11 number(s) not in the case file: ['41.58%'] | `transcripts/underwriter-sample_case_review_APP000120_complete-r0.json` |
| APP000155 | 1 | `numeric_fidelity` | 1/14 number(s) not in the case file: ['4.59%'] | `transcripts/underwriter-sample_case_review_APP000155_complete-r0.json` |
| APP000155 | 3 | `numeric_fidelity` | 4/15 number(s) not in the case file: ['£643', '£876', '54.8%', '£237'] | `transcripts/underwriter-sample_case_review_APP000155_complete-r2.json` |
| APP000172 | 2 | `numeric_fidelity` | 4/19 number(s) not in the case file: ['43.5%', '£1,980', '£792', '465'] | `transcripts/underwriter-sample_case_review_APP000172_complete-r1.json` |
| APP000172 | 3 | `numeric_fidelity` | 2/13 number(s) not in the case file: ['35.8%', '650'] | `transcripts/underwriter-sample_case_review_APP000172_complete-r2.json` |
| APP000185 | 1 | `numeric_fidelity` | 2/14 number(s) not in the case file: ['42.5%', '£27,600'] | `transcripts/underwriter-sample_case_review_APP000185_complete-r0.json` |
| APP000323 | 1 | `numeric_fidelity` | 3/15 number(s) not in the case file: ['43.5%', '£2,031', '£812.40'] | `transcripts/underwriter-sample_case_review_APP000323_complete-r0.json` |
| APP000323 | 2 | `numeric_fidelity` | 3/14 number(s) not in the case file: ['£2,031', '53.9%', '£812'] | `transcripts/underwriter-sample_case_review_APP000323_complete-r1.json` |
| APP000407 | 3 | `numeric_fidelity` | 1/16 number(s) not in the case file: ['36.67%'] | `transcripts/underwriter-sample_case_review_APP000407_complete-r2.json` |
| APP000448 | 2 | `numeric_fidelity` | 2/15 number(s) not in the case file: ['£1,416', '£17,000'] | `transcripts/underwriter-sample_case_review_APP000448_complete-r1.json` |
| APP000448 | 3 | `numeric_fidelity` | 1/15 number(s) not in the case file: ['4.04%'] | `transcripts/underwriter-sample_case_review_APP000448_complete-r2.json` |
| APP000454 | 1 | `numeric_fidelity` | 2/13 number(s) not in the case file: ['42.58%', '£1,070'] | `transcripts/underwriter-sample_case_review_APP000454_complete-r0.json` |
| APP000454 | 3 | `numeric_fidelity` | 4/13 number(s) not in the case file: ['39.55%', '£1,990.33', '£796.13', '£336'] | `transcripts/underwriter-sample_case_review_APP000454_complete-r2.json` |
| APP000522 | 1 | `numeric_fidelity` | 1/17 number(s) not in the case file: ['£111'] | `transcripts/underwriter-sample_case_review_APP000522_complete-r0.json` |
| APP000522 | 3 | `numeric_fidelity` | 1/15 number(s) not in the case file: ['43.6%'] | `transcripts/underwriter-sample_case_review_APP000522_complete-r2.json` |
| APP000543 | 2 | `numeric_fidelity` | 5/18 number(s) not in the case file: ['37.5%', '£2,670.60', '£30,240', '£1,068.24', '£856.24'] | `transcripts/underwriter-sample_case_review_APP000543_complete-r1.json` |
| APP000543 | 3 | `numeric_fidelity` | 4/14 number(s) not in the case file: ['£785', '£997', '£30,168', '£2,514'] | `transcripts/underwriter-sample_case_review_APP000543_complete-r2.json` |
| APP000588 | 1 | `numeric_fidelity` | 1/16 number(s) not in the case file: ['29.1%'] | `transcripts/underwriter-sample_case_review_APP000588_complete-r0.json` |
| APP000678 | 1 | `numeric_fidelity` | 1/11 number(s) not in the case file: ['48.3%'] | `transcripts/underwriter-sample_case_review_APP000678_complete-r0.json` |
| APP000678 | 2 | `numeric_fidelity` | 2/15 number(s) not in the case file: ['43.58%', '749'] | `transcripts/underwriter-sample_case_review_APP000678_complete-r1.json` |
| APP000678 | 3 | `numeric_fidelity` | 1/14 number(s) not in the case file: ['£402'] | `transcripts/underwriter-sample_case_review_APP000678_complete-r2.json` |

## Run-to-run variation

Each case ran 3 times with the same prompt, temperature 0.0 and seed 7. Cases whose verdict still changed between repeats:

- `numeric_fidelity`: 15 of 20 cases — APP000028, APP000037, APP000044, APP000059, APP000120, APP000155, APP000172, APP000185, APP000323, APP000407, APP000448, APP000454, APP000522, APP000543, APP000588
- `decoy_citation`: 6 of 20 cases — APP000028, APP000037, APP000044, APP000059, APP000407, APP000522
- `flip_accuracy`: 1 of 20 cases — APP000684
- `comparison_fidelity`: 1 of 20 cases — APP000543
- `claim_consistency`: 10 of 20 cases — APP000039, APP000044, APP000059, APP000107, APP000155, APP000172, APP000407, APP000448, APP000588, APP000684

## To reproduce

Send the transcript's `system_prompt` and `user_prompt` with its `sut.params` to the same model and endpoint, then mark the output with the same checks:

```
evidence run packs/underwriter-sample --repeats 3
evidence verify <run> --recompute --pack packs/underwriter-sample
```

## The other reports

- **Business** (Head of lending, product owner): `evidence/readers/business.md`
- **Credit risk** (Model risk, second line): `evidence/readers/credit-risk.md`
- **Compliance** (Compliance and legal): `evidence/readers/compliance.md`
- **Underwriting operations** (Underwriters and team leads): `evidence/readers/operations.md`
- **Auditor** (Internal audit, a supervisor): `evidence/readers/auditor.md`
- **Everything**, by obligation: `evidence/report.md`
