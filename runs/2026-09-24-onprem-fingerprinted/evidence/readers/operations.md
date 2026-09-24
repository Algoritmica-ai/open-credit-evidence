# For underwriters — what to watch for in the assistant's briefings

Assistant `nvidia/nemotron-3.5-lightning` (on-prem) · 60 briefings: 20 referred loan cases × 3 · pack `underwriter-sample` v0.5.0 · run `2026-09-24-onprem-fingerprinted` · model calls 2026-09-24

The briefing is a summary of the file, written by a model. On these cases it went wrong in the ways below, most frequent first. Each comes with a sentence the assistant actually wrote and what to do when you see one like it.

## Figure worked out wrongly — 30 of 60 briefings

The assistant worked a figure out itself and got it wrong.

> … threshold**, and the applicant falls within the **600–699 credit score band**, which triggers underwriter review per …

— case APP000028, repeat 1

**What to do:** Check any ratio or amount the briefing works out against the application form before relying on it. The briefing's own arithmetic is where it is most often wrong.

## Threshold stated the wrong way round — 16 of 60 briefings

The assistant compared a figure with a policy threshold and got the direction wrong, or said a limit was breached when its own figure says it was not.

> This application was referred for underwriter review because the automated rules flagged two policy breaches: the applicant’s credit score of 679 falls below the 600 threshold requiring review, and the calculated affordability ratio exceeds the 40% maximum limit.

— case APP000543, repeat 2

**What to do:** When a briefing says a figure is above or below a limit, compare the two numbers yourself.

## Irrelevant field blamed — 11 of 60 briefings

The assistant blamed a field that has no bearing on the outcome.

> A score of 608 is considered a "thin file" risk area, though there are no missed payments or defaults in the last 24 months.

— case APP000028, repeat 1

**What to do:** Disregard reasoning that rests on age band, postcode. The lending policy does not use them.

## Wrong or no way to change the outcome — 2 of 60 briefings

The assistant did not name a valid way to change the outcome.

> *   **Credit History:** The applicant has a bureau score of **549**, which is below the 600 threshold requiring underwriter review.

— case APP000684, repeat 2

**What to do:** If the briefing does not say what would change the outcome, work it out from the policy: which limit is breached, and by how much.

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
