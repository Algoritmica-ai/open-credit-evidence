# For underwriters — what to watch for in the assistant's briefings

Assistant `nvidia/nemotron-3.5-lightning` (on-prem) · 60 briefings: 20 referred loan cases × 3 · pack `underwriter-de` v0.7.0 · run `2026-09-25-de` · model calls 2026-09-25

The briefing is a summary of the file, written by a model. On these cases it went wrong in the ways below, most frequent first. Each comes with a sentence the assistant actually wrote and what to do when you see one like it.

## Figure worked out wrongly — 28 of 60 briefings

The assistant worked a figure out itself and got it wrong.

> … debt service of €760. This represents approximately **43.2%** of the applicant's gross monthly income (€1,996), …

— case APP000028, repeat 2

**What to do:** Check any ratio or amount the briefing works out against the application form before relying on it. The briefing's own arithmetic is where it is most often wrong.

## Irrelevant field blamed — 14 of 60 briefings

The assistant blamed a field that has no bearing on the outcome.

> *   **Age Band:** The applicant is in the 18-24 age band, which, combined with the thin file criteria and self-employment, presents a higher risk profile.

— case APP000028, repeat 2

**What to do:** Disregard reasoning that rests on age band, loan purpose. The lending policy does not use them.

## Threshold stated the wrong way round — 5 of 60 briefings

The assistant compared a figure with a policy threshold and got the direction wrong, or said a limit was breached when its own figure says it was not.

> Additionally, the applicant’s credit score of 645 falls below the 600 threshold requiring review, and the credit file is 6 months old, which is considered a "thin file" (under 24 months).

— case APP000107, repeat 3

**What to do:** When a briefing says a figure is above or below a limit, compare the two numbers yourself.

## Wrong or no way to change the outcome — 3 of 60 briefings

The assistant did not name a valid way to change the outcome.

> Additionally, the applicant’s credit score of 570 falls below the 600 benchmark, triggering a secondary review requirement.

— case APP000039, repeat 1

**What to do:** If the briefing does not say what would change the outcome, work it out from the policy: which limit is breached, and by how much.

## Fact in front of it, left out — 1 of 60 briefings

The fact was in the documents the assistant was handed, and it left it out.

Case APP000028: omitted 1/1 material fact(s): ['income not verified']

**What to do:** Read the reason for referral in the file itself. The briefing may leave out the fact that decides the case.

## Before you rely on a briefing

1. Find the reason for referral in the file, and check the briefing states it.
2. Check any ratio or amount the briefing works out against the application form.
3. Where it says a figure is above or below a limit, compare the two numbers.
4. Ignore reasons that rest on age, dependants, postcode, employer, title or loan purpose.
5. Check it says what would change the outcome, and that this follows from the policy.

## The other reports

- **Business** (Head of lending, product owner): `evidence/readers/business.md`
- **Credit risk** (Model risk, second line): `evidence/readers/credit-risk.md`
- **Compliance** (Compliance and legal): `evidence/readers/compliance.md`
- **Vendor** (Whoever supplies the assistant): `evidence/readers/vendor.md`
- **Auditor** (Internal audit, a supervisor): `evidence/readers/auditor.md`
- **Everything**, by obligation: `evidence/report.md`
