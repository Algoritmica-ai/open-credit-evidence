# For underwriters — what to watch for in the assistant's briefings

Assistant `nvidia/nemotron-3.5-lightning` (on-prem) · 60 briefings: 20 referred loan cases × 3 · pack `underwriter-de` v0.6.0 · run `2026-09-25-de` · model calls 2026-09-25

The briefing is a summary of the file, written by a model. On these cases it went wrong in the ways below, most frequent first. Each comes with a sentence the assistant actually wrote and what to do when you see one like it.

## Figure worked out wrongly — 30 of 60 briefings

The assistant worked a figure out itself and got it wrong.

> … of €367, results in a TMDS ratio of approximately 41.5%, which sits above the policy limit of 40%. **What the …

— case APP000037, repeat 1

**What to do:** Check any ratio or amount the briefing works out against the application form before relying on it. The briefing's own arithmetic is where it is most often wrong.

## Irrelevant field blamed — 14 of 60 briefings

The assistant blamed a field that has no bearing on the outcome.

> Specifically, the applicant’s total monthly debt service exceeds the policy threshold of 40% of gross monthly income, and the applicant falls within the "thin file" category due to a credit file age of under 24 months.

— case APP000028, repeat 1

**What to do:** Disregard reasoning that rests on age band, loan purpose. The lending policy does not use them.

## Threshold stated the wrong way round — 9 of 60 briefings

The assistant compared a figure with a policy threshold and got the direction wrong, or said a limit was breached when its own figure says it was not.

> Credit History: The bureau score is 645, which is below the 600 threshold requiring review.

— case APP000107, repeat 2

**What to do:** When a briefing says a figure is above or below a limit, compare the two numbers yourself.

## Wrong or no way to change the outcome — 6 of 60 briefings

The assistant did not name a valid way to change the outcome.

> *   **Bureau Score:** The credit score is 570, which is below the 600 cutoff requiring review.

— case APP000039, repeat 3

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
