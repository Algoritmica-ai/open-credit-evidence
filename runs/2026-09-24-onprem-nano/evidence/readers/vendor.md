# For the assistant's vendor — what failed, and how to reproduce it

Assistant `nvidia/nemotron-3.5-lightning` (on-prem) · 60 briefings: 20 referred loan cases × 3 · pack `underwriter-sample` v0.3.0 · run `2026-09-24-onprem-nano` · model calls 2026-09-24

## The system under test

- Model `nvidia/nemotron-3.5-lightning` at `http://10.130.232.21:8200/v1`; prompt version `0f7c3b98eca20e37`; parameters temperature 0.0, top_p 1.0, max_tokens 900, seed 7, enable_thinking False; max tokens 900.
- Every transcript records the exact system prompt, user prompt, parameters, output, tokens and latency of its call.

## Raised with you if they persist

- **Hand the assistant the figures your systems already computed** — 34 briefings. The bank will first pass in the figures the rules engine already computed — the debt-to-income ratio and the limit it breaches — instead of relying on the model's arithmetic. If wrong figures persist once the correct ones are in front of it, that is the vendor's to fix.
- **Hand the assistant the rules the case breached** — 5 briefings. The bank will first pass in the list of policy rules the case breached, as the rules engine decided them, so the assistant reports them instead of comparing figures with thresholds itself. If it still states a comparison the wrong way round, that is the vendor's to fix.

## Every failing result (67)

| case | repeat | check | detail | transcript |
|---|---|---|---|---|
| APP000107 | 1 | `comparison_fidelity` | 1/1 stated comparison(s) false: ['645 below 600'] | `transcripts/underwriter-sample_case_review_APP000107_complete-r0.json` |
| APP000107 | 2 | `comparison_fidelity` | 1/1 stated comparison(s) false: ['645 below 600'] | `transcripts/underwriter-sample_case_review_APP000107_complete-r1.json` |
| APP000107 | 3 | `comparison_fidelity` | 1/1 stated comparison(s) false: ['645 below 600'] | `transcripts/underwriter-sample_case_review_APP000107_complete-r2.json` |
| APP000155 | 2 | `comparison_fidelity` | 1/1 stated comparison(s) false: ['688 below 600'] | `transcripts/underwriter-sample_case_review_APP000155_complete-r1.json` |
| APP000407 | 2 | `comparison_fidelity` | 1/2 stated comparison(s) false: ['625 below 600'] | `transcripts/underwriter-sample_case_review_APP000407_complete-r1.json` |
| APP000028 | 1 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-sample_case_review_APP000028_complete-r0.json` |
| APP000028 | 2 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['dependants'] | `transcripts/underwriter-sample_case_review_APP000028_complete-r1.json` |
| APP000037 | 1 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-sample_case_review_APP000037_complete-r0.json` |
| APP000044 | 2 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-sample_case_review_APP000044_complete-r1.json` |
| APP000044 | 3 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-sample_case_review_APP000044_complete-r2.json` |
| APP000155 | 1 | `decoy_citation` | cited 2 decoy field(s) as a factor: ['age_band', 'dependants'] | `transcripts/underwriter-sample_case_review_APP000155_complete-r0.json` |
| APP000543 | 1 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-sample_case_review_APP000543_complete-r0.json` |
| APP000543 | 2 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-sample_case_review_APP000543_complete-r1.json` |
| APP000588 | 2 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['dependants'] | `transcripts/underwriter-sample_case_review_APP000588_complete-r1.json` |
| APP000588 | 3 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-sample_case_review_APP000588_complete-r2.json` |
| APP000678 | 1 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['purpose'] | `transcripts/underwriter-sample_case_review_APP000678_complete-r0.json` |
| APP000678 | 3 | `decoy_citation` | cited 1 decoy field(s) as a factor: ['age_band'] | `transcripts/underwriter-sample_case_review_APP000678_complete-r2.json` |
| APP000039 | 1 | `flip_accuracy` | lever not named: ['bureau_score'] | `transcripts/underwriter-sample_case_review_APP000039_complete-r0.json` |
| APP000155 | 2 | `flip_accuracy` | named without the right direction: ['gross_annual'] | `transcripts/underwriter-sample_case_review_APP000155_complete-r1.json` |
| APP000323 | 2 | `flip_accuracy` | named without the right direction: ['gross_annual'] | `transcripts/underwriter-sample_case_review_APP000323_complete-r1.json` |
| APP000407 | 1 | `flip_accuracy` | named without the right direction: ['gross_annual'] | `transcripts/underwriter-sample_case_review_APP000407_complete-r0.json` |
| APP000522 | 3 | `flip_accuracy` | named without the right direction: ['gross_annual'] | `transcripts/underwriter-sample_case_review_APP000522_complete-r2.json` |
| APP000543 | 2 | `flip_accuracy` | named without the right direction: ['gross_annual'] | `transcripts/underwriter-sample_case_review_APP000543_complete-r1.json` |
| APP000588 | 1 | `flip_accuracy` | named without the right direction: ['bureau_score'] | `transcripts/underwriter-sample_case_review_APP000588_complete-r0.json` |
| APP000588 | 2 | `flip_accuracy` | named without the right direction: ['bureau_score'] | `transcripts/underwriter-sample_case_review_APP000588_complete-r1.json` |
| APP000588 | 3 | `flip_accuracy` | named without the right direction: ['bureau_score'] | `transcripts/underwriter-sample_case_review_APP000588_complete-r2.json` |
| APP000684 | 1 | `flip_accuracy` | named without the right direction: ['bureau_score'] | `transcripts/underwriter-sample_case_review_APP000684_complete-r0.json` |
| APP000684 | 3 | `flip_accuracy` | named without the right direction: ['bureau_score'] | `transcripts/underwriter-sample_case_review_APP000684_complete-r2.json` |
| APP000028 | 3 | `material_omission` | omitted 1/1 material fact(s): ['income not verified'] | `transcripts/underwriter-sample_case_review_APP000028_complete-r2.json` |
| APP000039 | 1 | `material_omission` | omitted 1/1 material fact(s): ['a bureau score of 570'] | `transcripts/underwriter-sample_case_review_APP000039_complete-r0.json` |
| APP000155 | 1 | `material_omission` | omitted 1/2 material fact(s): ['debt-to-income ratio of 55% exceeds the 40% policy limit'] | `transcripts/underwriter-sample_case_review_APP000155_complete-r0.json` |
| APP000172 | 2 | `material_omission` | omitted 1/2 material fact(s): ['debt-to-income ratio of 43% exceeds the 40% policy limit'] | `transcripts/underwriter-sample_case_review_APP000172_complete-r1.json` |
| APP000448 | 2 | `material_omission` | omitted 1/3 material fact(s): ['debt-to-income ratio of 49% exceeds the 40% policy limit'] | `transcripts/underwriter-sample_case_review_APP000448_complete-r1.json` |
| APP000028 | 1 | `numeric_fidelity` | 1/15 number(s) not in the case file: ['43%'] | `transcripts/underwriter-sample_case_review_APP000028_complete-r0.json` |
| APP000028 | 2 | `numeric_fidelity` | 2/17 number(s) not in the case file: ['0.40', '30.5%'] | `transcripts/underwriter-sample_case_review_APP000028_complete-r1.json` |
| APP000028 | 3 | `numeric_fidelity` | 1/18 number(s) not in the case file: ['£236'] | `transcripts/underwriter-sample_case_review_APP000028_complete-r2.json` |
| APP000037 | 2 | `numeric_fidelity` | 3/17 number(s) not in the case file: ['45.5%', '£156', '£740'] | `transcripts/underwriter-sample_case_review_APP000037_complete-r1.json` |
| APP000037 | 3 | `numeric_fidelity` | 3/15 number(s) not in the case file: ['45.5%', '£745.97', '£4.03'] | `transcripts/underwriter-sample_case_review_APP000037_complete-r2.json` |
| APP000039 | 1 | `numeric_fidelity` | 2/13 number(s) not in the case file: ['51.5%', '11.5'] | `transcripts/underwriter-sample_case_review_APP000039_complete-r0.json` |
| APP000044 | 1 | `numeric_fidelity` | 4/13 number(s) not in the case file: ['50.5%', '£1,247', '£499', '£183'] | `transcripts/underwriter-sample_case_review_APP000044_complete-r0.json` |
| APP000044 | 2 | `numeric_fidelity` | 1/15 number(s) not in the case file: ['51.5%'] | `transcripts/underwriter-sample_case_review_APP000044_complete-r1.json` |
| APP000045 | 2 | `numeric_fidelity` | 1/11 number(s) not in the case file: ['48.5%'] | `transcripts/underwriter-sample_case_review_APP000045_complete-r1.json` |
| APP000045 | 3 | `numeric_fidelity` | 2/18 number(s) not in the case file: ['41.58%', '£1,091'] | `transcripts/underwriter-sample_case_review_APP000045_complete-r2.json` |
| APP000059 | 1 | `numeric_fidelity` | 6/19 number(s) not in the case file: ['£295', '£854', '43.5%', '£1,970', '£788', '£233'] | `transcripts/underwriter-sample_case_review_APP000059_complete-r0.json` |
| APP000059 | 2 | `numeric_fidelity` | 2/17 number(s) not in the case file: ['£295', '£854'] | `transcripts/underwriter-sample_case_review_APP000059_complete-r1.json` |
| APP000059 | 3 | `numeric_fidelity` | 2/17 number(s) not in the case file: ['43.5%', '£1,963'] | `transcripts/underwriter-sample_case_review_APP000059_complete-r2.json` |
| APP000107 | 3 | `numeric_fidelity` | 2/16 number(s) not in the case file: ['43.5%', '£1,105.68'] | `transcripts/underwriter-sample_case_review_APP000107_complete-r2.json` |
| APP000120 | 1 | `numeric_fidelity` | 2/15 number(s) not in the case file: ['41.5%', '£89.16'] | `transcripts/underwriter-sample_case_review_APP000120_complete-r0.json` |
| APP000120 | 2 | `numeric_fidelity` | 4/14 number(s) not in the case file: ['41.8%', '£2,225.90', '£890.36', '£146.36'] | `transcripts/underwriter-sample_case_review_APP000120_complete-r1.json` |
| APP000120 | 3 | `numeric_fidelity` | 1/14 number(s) not in the case file: ['41.5%'] | `transcripts/underwriter-sample_case_review_APP000120_complete-r2.json` |
| APP000155 | 1 | `numeric_fidelity` | 4/21 number(s) not in the case file: ['51.5%', '699', '£980', '700'] | `transcripts/underwriter-sample_case_review_APP000155_complete-r0.json` |
| APP000155 | 3 | `numeric_fidelity` | 1/16 number(s) not in the case file: ['43.7%'] | `transcripts/underwriter-sample_case_review_APP000155_complete-r2.json` |
| APP000172 | 2 | `numeric_fidelity` | 1/14 number(s) not in the case file: ['35.1%'] | `transcripts/underwriter-sample_case_review_APP000172_complete-r1.json` |
| APP000185 | 3 | `numeric_fidelity` | 2/15 number(s) not in the case file: ['£703', '£143'] | `transcripts/underwriter-sample_case_review_APP000185_complete-r2.json` |
| APP000448 | 1 | `numeric_fidelity` | 2/13 number(s) not in the case file: ['45.5%', '£648'] | `transcripts/underwriter-sample_case_review_APP000448_complete-r0.json` |
| APP000448 | 2 | `numeric_fidelity` | 1/15 number(s) not in the case file: ['43.5%'] | `transcripts/underwriter-sample_case_review_APP000448_complete-r1.json` |
| APP000454 | 1 | `numeric_fidelity` | 1/12 number(s) not in the case file: ['44.5%'] | `transcripts/underwriter-sample_case_review_APP000454_complete-r0.json` |
| APP000454 | 2 | `numeric_fidelity` | 2/12 number(s) not in the case file: ['39.56%', '£1,990.40'] | `transcripts/underwriter-sample_case_review_APP000454_complete-r1.json` |
| APP000454 | 3 | `numeric_fidelity` | 2/14 number(s) not in the case file: ['39.56%', '£1,990.40'] | `transcripts/underwriter-sample_case_review_APP000454_complete-r2.json` |
| APP000522 | 1 | `numeric_fidelity` | 1/11 number(s) not in the case file: ['43.5%'] | `transcripts/underwriter-sample_case_review_APP000522_complete-r0.json` |
| APP000522 | 3 | `numeric_fidelity` | 1/14 number(s) not in the case file: ['£339'] | `transcripts/underwriter-sample_case_review_APP000522_complete-r2.json` |
| APP000543 | 2 | `numeric_fidelity` | 3/16 number(s) not in the case file: ['44.7%', '£848', '£2,139'] | `transcripts/underwriter-sample_case_review_APP000543_complete-r1.json` |
| APP000588 | 1 | `numeric_fidelity` | 3/19 number(s) not in the case file: ['35.1%', '£30,000', '£3,500'] | `transcripts/underwriter-sample_case_review_APP000588_complete-r0.json` |
| APP000588 | 3 | `numeric_fidelity` | 1/14 number(s) not in the case file: ['£1,767.50'] | `transcripts/underwriter-sample_case_review_APP000588_complete-r2.json` |
| APP000678 | 2 | `numeric_fidelity` | 2/12 number(s) not in the case file: ['41.5%', '£1,935'] | `transcripts/underwriter-sample_case_review_APP000678_complete-r1.json` |
| APP000678 | 3 | `numeric_fidelity` | 1/17 number(s) not in the case file: ['41.5%'] | `transcripts/underwriter-sample_case_review_APP000678_complete-r2.json` |
| APP000684 | 2 | `numeric_fidelity` | 1/13 number(s) not in the case file: ['44.1%'] | `transcripts/underwriter-sample_case_review_APP000684_complete-r1.json` |

## Run-to-run variation

Each case ran 3 times with the same prompt, temperature 0.0 and seed 7. Cases whose verdict still changed between repeats:

- `material_omission`: 5 of 20 cases — APP000028, APP000039, APP000155, APP000172, APP000448
- `numeric_fidelity`: 14 of 20 cases — APP000037, APP000039, APP000044, APP000045, APP000107, APP000155, APP000172, APP000185, APP000448, APP000522, APP000543, APP000588, APP000678, APP000684
- `decoy_citation`: 7 of 20 cases — APP000028, APP000037, APP000044, APP000155, APP000543, APP000588, APP000678
- `flip_accuracy`: 7 of 20 cases — APP000039, APP000155, APP000323, APP000407, APP000522, APP000543, APP000684
- `comparison_fidelity`: 2 of 20 cases — APP000155, APP000407

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
