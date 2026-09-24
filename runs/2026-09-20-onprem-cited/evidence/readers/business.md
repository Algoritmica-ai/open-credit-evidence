# underwriter-sample — the assistant, on one page

Assistant `nvidia/nemotron-3.5-lightning` (on-prem) · 60 briefings: 20 referred loan cases × 3 · pack `underwriter-sample` v0.3.0 · run `2026-09-20-onprem-cited` · model calls 2026-09-20

## Verdict: **NO-GO**

The assistant is not ready to brief underwriters on cases like these without changes.

## What went wrong, and how often

| In how many briefings the assistant … | briefings | share | allowed for GO |
|---|---|---|---|
| stated a figure that is not in, or worked out from, the case file | 33 of 60 | 55% | at most 2% |
| did not say correctly what would change the outcome | 16 of 60 | 27% | at most 10% |
| gave a field with no bearing on the outcome as a reason | 14 of 60 | 23% | at most 5% |
| compared a figure with a threshold the wrong way round | 6 of 60 | 10% | at most 2% |
| left out a fact the decision turned on | 1 of 60 | 2% | at most 5% |

## What to change first

1. **Hand the assistant the figures your systems already computed** — the bank, then the vendor if it persists. Addresses 33 of 60 briefings.
2. **Require a 'what would change the outcome' section** — the bank. Addresses 15 of 60 briefings.
3. **Tell the assistant which fields must not be used as reasons** — the bank. Addresses 14 of 60 briefings.

Make one change, run the pack again, and compare the two runs: a change is accepted only if it helps and nothing else gets worse.

## What this does not tell you

- Whether the lending decisions are right. The underwriter decides; the loan book shows it, later.
- How the assistant does on real applications. These cases are built so the answer is known: a failure proves a problem exists, a pass does not prove there is none.
- Fairness across groups of applicants.
- How readable the briefings are. That is a model's opinion, in the credit risk report, and not part of this verdict.

## The other reports

- **Credit risk** (Model risk, second line): `evidence/readers/credit-risk.md`
- **Compliance** (Compliance and legal): `evidence/readers/compliance.md`
- **Underwriting operations** (Underwriters and team leads): `evidence/readers/operations.md`
- **Vendor** (Whoever supplies the assistant): `evidence/readers/vendor.md`
- **Auditor** (Internal audit, a supervisor): `evidence/readers/auditor.md`
- **Everything**, by obligation: `evidence/report.md`
