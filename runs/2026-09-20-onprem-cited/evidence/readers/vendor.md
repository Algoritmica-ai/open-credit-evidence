# For the assistant's vendor — what failed, and how to reproduce it

Assistant `nvidia/nemotron-3.5-lightning` (on-prem) · 60 briefings: 20 referred loan cases × 3 · pack `underwriter-sample` v0.4.0 · run `2026-09-20-onprem-cited` · model calls 2026-09-20

## The system under test

- Model `nvidia/nemotron-3.5-lightning` at `http://10.130.232.20:8000/v1`; prompt version `0f7c3b98eca20e37`; parameters temperature 0.0, top_p 1.0, max_tokens 900, seed 7, enable_thinking False; max tokens 900.
- Every transcript records the exact system prompt, user prompt, parameters, output, tokens and latency of its call.

## Raised with you if they persist

- **Hand the assistant the figures your systems already computed** — 33 briefings. The bank will first pass in the figures the rules engine already computed — the debt-to-income ratio and the limit it breaches — instead of relying on the model's arithmetic. If wrong figures persist once the correct ones are in front of it, that is the vendor's to fix.
- **Hand the assistant the rules the case breached** — 6 briefings. The bank will first pass in the list of policy rules the case breached, as the rules engine decided them, so the assistant reports them instead of comparing figures with thresholds itself. If it still states a comparison the wrong way round, that is the vendor's to fix.

## Every failing result (60)

| case | repeat | check | detail | transcript |
|---|---|---|---|---|
| APP000044 | 1 | `comparison_fidelity` | 2/3 stated comparison(s) false: ['652 below 600', '652 below 600'] | `transcripts/underwriter-sample_case_review_APP000044_complete-r0.json` |
| APP000407 | 2 | `comparison_fidelity` | 2/3 stated comparison(s) false: ['625 below 600', '625 below 600'] | `transcripts/underwriter-sample_case_review_APP000407_complete-r1.json` |
| APP000407 | 3 | `comparison_fidelity` | 2/3 stated comparison(s) false: ['625 below 600', '625 below 600'] | `transcripts/underwriter-sample_case_review_APP000407_complete-r2.json` |
| APP000454 | 2 | `comparison_fidelity` | 2/3 stated comparison(s) false: ['624 below 600', '624 below 600'] | `transcripts/underwriter-sample_case_review_APP000454_complete-r1.json` |
| APP000454 | 3 | `comparison_fidelity` | 2/3 stated comparison(s) false: ['624 below 600', '624 below 600'] | `transcripts/underwriter-sample_case_review_APP000454_complete-r2.json` |
| APP000678 | 1 | `comparison_fidelity` | 1/1 stated comparison(s) false: ['653 below 600'] | `transcripts/underwriter-sample_case_review_APP000678_complete-r0.json` |
| APP000028 | 1 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-sample_case_review_APP000028_complete-r0.json` |
| APP000028 | 2 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-sample_case_review_APP000028_complete-r1.json` |
| APP000028 | 3 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-sample_case_review_APP000028_complete-r2.json` |
| APP000037 | 1 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['dependants'] | `transcripts/underwriter-sample_case_review_APP000037_complete-r0.json` |
| APP000037 | 2 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['dependants'] | `transcripts/underwriter-sample_case_review_APP000037_complete-r1.json` |
| APP000044 | 2 | `decoy_citation` | cited 2 decoy field(s) as a factor: ['age_band', 'purpose'] | `transcripts/underwriter-sample_case_review_APP000044_complete-r1.json` |
| APP000107 | 1 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-sample_case_review_APP000107_complete-r0.json` |
| APP000107 | 2 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-sample_case_review_APP000107_complete-r1.json` |
| APP000155 | 2 | `decoy_citation` | cited 2 decoy field(s) as a factor: ['age_band', 'dependants'] | `transcripts/underwriter-sample_case_review_APP000155_complete-r1.json` |
| APP000172 | 2 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['dependants'] | `transcripts/underwriter-sample_case_review_APP000172_complete-r1.json` |
| APP000185 | 3 | `decoy_citation` | cited 2 decoy field(s) as a factor: ['age_band', 'purpose'] | `transcripts/underwriter-sample_case_review_APP000185_complete-r2.json` |
| APP000522 | 3 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-sample_case_review_APP000522_complete-r2.json` |
| APP000543 | 2 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-sample_case_review_APP000543_complete-r1.json` |
| APP000684 | 3 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-sample_case_review_APP000684_complete-r2.json` |
| APP000039 | 3 | `flip_accuracy` | named without the right direction: ['bureau_score'] | `transcripts/underwriter-sample_case_review_APP000039_complete-r2.json` |
| APP000059 | 1 | `flip_accuracy` | named without the right direction: ['bureau_score'] | `transcripts/underwriter-sample_case_review_APP000059_complete-r0.json` |
| APP000059 | 3 | `flip_accuracy` | named without the right direction: ['bureau_score'] | `transcripts/underwriter-sample_case_review_APP000059_complete-r2.json` |
| APP000588 | 1 | `flip_accuracy` | named without the right direction: ['bureau_score'] | `transcripts/underwriter-sample_case_review_APP000588_complete-r0.json` |
| APP000588 | 2 | `flip_accuracy` | named without the right direction: ['bureau_score'] | `transcripts/underwriter-sample_case_review_APP000588_complete-r1.json` |
| APP000684 | 3 | `flip_accuracy` | named without the right direction: ['bureau_score'] | `transcripts/underwriter-sample_case_review_APP000684_complete-r2.json` |
| APP000543 | 3 | `material_omission` | omitted 1/2 material fact(s): ['debt-to-income ratio of 45% exceeds the 40% policy limit'] | `transcripts/underwriter-sample_case_review_APP000543_complete-r2.json` |
| APP000028 | 3 | `numeric_fidelity` | 3/18 number(s) not in the case file: ['£32,300', '£9,500', '£833'] | `transcripts/underwriter-sample_case_review_APP000028_complete-r2.json` |
| APP000037 | 1 | `numeric_fidelity` | 1/19 number(s) not in the case file: ['48.8%'] | `transcripts/underwriter-sample_case_review_APP000037_complete-r0.json` |
| APP000037 | 3 | `numeric_fidelity` | 1/18 number(s) not in the case file: ['£385'] | `transcripts/underwriter-sample_case_review_APP000037_complete-r2.json` |
| APP000039 | 1 | `numeric_fidelity` | 1/12 number(s) not in the case file: ['£28,000'] | `transcripts/underwriter-sample_case_review_APP000039_complete-r0.json` |
| APP000039 | 2 | `numeric_fidelity` | 2/11 number(s) not in the case file: ['32.6%', '£2,372.33'] | `transcripts/underwriter-sample_case_review_APP000039_complete-r1.json` |
| APP000044 | 2 | `numeric_fidelity` | 1/17 number(s) not in the case file: ['700'] | `transcripts/underwriter-sample_case_review_APP000044_complete-r1.json` |
| APP000044 | 3 | `numeric_fidelity` | 1/14 number(s) not in the case file: ['41.58%'] | `transcripts/underwriter-sample_case_review_APP000044_complete-r2.json` |
| APP000045 | 3 | `numeric_fidelity` | 1/13 number(s) not in the case file: ['43.5%'] | `transcripts/underwriter-sample_case_review_APP000045_complete-r2.json` |
| APP000059 | 2 | `numeric_fidelity` | 4/17 number(s) not in the case file: ['£295', '£854', '£2,135', '£25,620'] | `transcripts/underwriter-sample_case_review_APP000059_complete-r1.json` |
| APP000120 | 1 | `numeric_fidelity` | 1/13 number(s) not in the case file: ['41.5%'] | `transcripts/underwriter-sample_case_review_APP000120_complete-r0.json` |
| APP000120 | 2 | `numeric_fidelity` | 1/13 number(s) not in the case file: ['£333'] | `transcripts/underwriter-sample_case_review_APP000120_complete-r1.json` |
| APP000155 | 1 | `numeric_fidelity` | 1/16 number(s) not in the case file: ['51.5%'] | `transcripts/underwriter-sample_case_review_APP000155_complete-r0.json` |
| APP000155 | 2 | `numeric_fidelity` | 1/14 number(s) not in the case file: ['£613'] | `transcripts/underwriter-sample_case_review_APP000155_complete-r1.json` |
| APP000172 | 1 | `numeric_fidelity` | 5/15 number(s) not in the case file: ['48.5%', '£1,241', '£2,060', '£824', '£497'] | `transcripts/underwriter-sample_case_review_APP000172_complete-r0.json` |
| APP000172 | 2 | `numeric_fidelity` | 4/17 number(s) not in the case file: ['51.5%', '£1,311', '11.5', '£8,000'] | `transcripts/underwriter-sample_case_review_APP000172_complete-r1.json` |
| APP000172 | 3 | `numeric_fidelity` | 1/17 number(s) not in the case file: ['£511'] | `transcripts/underwriter-sample_case_review_APP000172_complete-r2.json` |
| APP000185 | 2 | `numeric_fidelity` | 1/15 number(s) not in the case file: ['42.1%'] | `transcripts/underwriter-sample_case_review_APP000185_complete-r1.json` |
| APP000185 | 3 | `numeric_fidelity` | 1/14 number(s) not in the case file: ['35.2%'] | `transcripts/underwriter-sample_case_review_APP000185_complete-r2.json` |
| APP000323 | 1 | `numeric_fidelity` | 2/14 number(s) not in the case file: ['41.6%', '£415'] | `transcripts/underwriter-sample_case_review_APP000323_complete-r0.json` |
| APP000323 | 3 | `numeric_fidelity` | 1/13 number(s) not in the case file: ['41.5%'] | `transcripts/underwriter-sample_case_review_APP000323_complete-r2.json` |
| APP000407 | 1 | `numeric_fidelity` | 2/16 number(s) not in the case file: ['36.67%', '35%'] | `transcripts/underwriter-sample_case_review_APP000407_complete-r0.json` |
| APP000448 | 1 | `numeric_fidelity` | 1/13 number(s) not in the case file: ['48.4%'] | `transcripts/underwriter-sample_case_review_APP000448_complete-r0.json` |
| APP000448 | 3 | `numeric_fidelity` | 1/19 number(s) not in the case file: ['43.54%'] | `transcripts/underwriter-sample_case_review_APP000448_complete-r2.json` |
| APP000454 | 2 | `numeric_fidelity` | 2/12 number(s) not in the case file: ['42.58%', '£886'] | `transcripts/underwriter-sample_case_review_APP000454_complete-r1.json` |
| APP000522 | 1 | `numeric_fidelity` | 2/18 number(s) not in the case file: ['45.7%', '£2,799'] | `transcripts/underwriter-sample_case_review_APP000522_complete-r0.json` |
| APP000522 | 3 | `numeric_fidelity` | 1/18 number(s) not in the case file: ['43.6%'] | `transcripts/underwriter-sample_case_review_APP000522_complete-r2.json` |
| APP000543 | 1 | `numeric_fidelity` | 3/12 number(s) not in the case file: ['£2,054', '48.7%', '£821'] | `transcripts/underwriter-sample_case_review_APP000543_complete-r0.json` |
| APP000543 | 3 | `numeric_fidelity` | 1/15 number(s) not in the case file: ['45.5%'] | `transcripts/underwriter-sample_case_review_APP000543_complete-r2.json` |
| APP000588 | 1 | `numeric_fidelity` | 1/16 number(s) not in the case file: ['43.5%'] | `transcripts/underwriter-sample_case_review_APP000588_complete-r0.json` |
| APP000678 | 1 | `numeric_fidelity` | 1/18 number(s) not in the case file: ['8.1'] | `transcripts/underwriter-sample_case_review_APP000678_complete-r0.json` |
| APP000678 | 2 | `numeric_fidelity` | 5/18 number(s) not in the case file: ['40.1%', '£2,003.75', '£801.60', '£513.60', '£2.40'] | `transcripts/underwriter-sample_case_review_APP000678_complete-r1.json` |
| APP000678 | 3 | `numeric_fidelity` | 1/13 number(s) not in the case file: ['4.02%'] | `transcripts/underwriter-sample_case_review_APP000678_complete-r2.json` |
| APP000684 | 3 | `numeric_fidelity` | 1/13 number(s) not in the case file: ['3.72%'] | `transcripts/underwriter-sample_case_review_APP000684_complete-r2.json` |

## Run-to-run variation

Each case ran 3 times with the same prompt, temperature 0.0 and seed 7. Cases whose verdict still changed between repeats:

- `material_omission`: 1 of 20 cases — APP000543
- `numeric_fidelity`: 17 of 20 cases — APP000028, APP000037, APP000039, APP000044, APP000045, APP000059, APP000120, APP000155, APP000185, APP000323, APP000407, APP000448, APP000454, APP000522, APP000543, APP000588, APP000684
- `decoy_citation`: 9 of 20 cases — APP000037, APP000044, APP000107, APP000155, APP000172, APP000185, APP000522, APP000543, APP000684
- `flip_accuracy`: 4 of 20 cases — APP000039, APP000059, APP000588, APP000684
- `comparison_fidelity`: 4 of 20 cases — APP000044, APP000407, APP000454, APP000678

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
