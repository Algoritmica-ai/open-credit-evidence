# Public-sector lenders: who the engine is for

Source: the team's market briefing *Public Sector Bank Loan Review Market — Germany and
the European Union* (22 September 2026). The figures below are planning estimates for
scoping, not audited statistics: no regulator publishes a harmonised count of
public-bank applications or manual reviews.

## The market

| | Institutions | Applications per day | Needing real human review per day |
|---|---|---|---|
| Germany | 365 to 370 | 12,000 to 20,000 | 1,500 to 5,000 |
| EU 27 including Germany | 400 to 500 | 60,000 to 120,000 | 10,000 to 30,000 |

- Germany is the core market: 339 Sparkassen, 6 Landesbank groups and DekaBank, 5 public
  building societies and about 17 to 20 federal and state development banks. The
  Sparkassen alone held EUR 1.081 trillion of customer loans at the end of 2025.
- The European Association of Public Banks represents more than 90 institutions with
  more than EUR 3.4 trillion in assets, about 15% of the European financial sector.
- Shared service providers and common risk infrastructure across the Sparkassen offer a
  route from one validated setup to many institutions.
- Best first segment: **SME and development-loan applications** — structured figures
  plus substantial documents and programme rules, and not yet automated the way
  point-of-sale credit is.

Use the ranges, not a midpoint, in any external claim. The briefing's validation plan
(interviews with three to five Sparkassen or development banks; measured handling
times; an observed pilot volume) comes before an external market claim.

## Where the engine sits

The briefing recommends that a prototype support the work around a credit decision,
not replace it, and keep a credit officer accountable. Its workflow:

1. receive the application package;
2. extract applicant, facility, collateral, affordability and programme-eligibility
   data into a case file;
3. check completeness and policy rules;
4. **draft a credit memo** with evidence links, calculation steps and separated model
   observations;
5. a credit officer decides, with reason codes and an audit trail.

An AI assistant doing steps 2 to 4 is a high-risk system under the EU AI Act (Annex III,
point 5). The Credit Evidence Engine is the **evaluation and evidence layer** for that
assistant: before the assistant is used, and every time it or its model changes, it
tests the memos against cases whose right answer is known, and seals evidence a
validator, an auditor or a supervisor can check without trusting the bank or the vendor.

For a public lender the second reader matters as much as the first: the institution's
own model risk and internal audit functions, and the supervisors (BaFin and the
Bundesbank, the ECB for significant institutions, market surveillance authorities under
the AI Act). `evidence verify --recompute` is the step they run.

## The briefing's criteria against what the engine does today

Status: **covered** — built and shown in committed runs; **partial** — part of it;
**not yet** — outside today's scope.

| Briefing criterion | What the engine does | Status |
|---|---|---|
| Model evaluation: a test set with omissions, contradictions and edge cases; measured extraction, citation and policy-check accuracy | Cases generated with a sealed marking key; six deterministic checks (omission, numbers, decoy reasons, direction of factors, comparisons, claims against the memo's own figures), three repeats, confidence intervals and go/no-go thresholds | covered |
| Credit memo: the officer can verify each material statement | Every figure in the memo checked against the case file or a derivation from it; the judge panel's Challenger verifies claims with tools and reports what it found | covered |
| Exception flags that route uncertain cases to a person | Results that need an auditor are marked; the judge panel flags memos for review with reasons (reported, never gated) | covered |
| Policy version, model version and timestamp on every recommendation | Every transcript records the model, endpoint, prompt version, weights-level model fingerprint and time; each run records the pack, rule pack and regulation corpus versions | covered |
| Distinguish extracted facts, calculated values and model commentary | The numeric check tells figures copied from the file from figures derived from them; commentary is not separately labelled | partial |
| Citations to the source application documents | Figures are traced to the case file; regulation citations are checked; page-level links into source PDFs are not | partial |
| Eligibility rules in machine-readable form, correct pass / fail / manual routing | The pack's scorecard and the Italian rule pack are machine-readable; programme-eligibility rules for development loans are not yet modelled | partial |
| Document intake from mixed PDF and spreadsheet packages | The engine tests the memo, not document extraction | not yet |
| Human approval with a complete record of edits and the final reason | The assistant never decides by design; officer decisions and reason codes are not captured | not yet |

## Next steps this points to

1. **A German SME / development-loan pack**: euro figures, programme-eligibility rules
   (a promotional-loan style programme), SME financial statements; the same marking-key
   construction and checks.
2. **German supervisory texts in the corpus**: MaRisk and the EBA guidelines on loan
   origination and monitoring (EBA/GL/2020/06), next to the AI Act and CCD2.
3. **Officer decision capture**: record the credit officer's decision, edits and reason
   codes against each memo, so the evidence shows human oversight working, not only
   that it was possible.
