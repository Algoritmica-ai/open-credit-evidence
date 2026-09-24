# For underwriters — what to watch for in the assistant's briefings

Assistant `nvidia/nemotron-3.5-lightning` (on-prem) · 60 briefings: 20 referred loan cases × 3 · pack `underwriter-sample` v0.5.0 · run `2026-09-24-onprem-nano` · model calls 2026-09-24

The briefing is a summary of the file, written by a model. On these cases it went wrong in the ways below, most frequent first. Each comes with a sentence the assistant actually wrote and what to do when you see one like it.

## Figure worked out wrongly — 34 of 60 briefings

The assistant worked a figure out itself and got it wrong.

> … is that the applicant’s **Total monthly debt service (43%) exceeds the policy threshold of 40%**. Additionally, the …

— case APP000028, repeat 1

**What to do:** Check any ratio or amount the briefing works out against the application form before relying on it. The briefing's own arithmetic is where it is most often wrong.

## Threshold stated the wrong way round — 12 of 60 briefings

The assistant compared a figure with a policy threshold and got the direction wrong, or said a limit was breached when its own figure says it was not.

> Specifically, the applicant’s total monthly debt service exceeds the policy threshold of 40% of gross monthly income, and the credit bureau score of 645 falls below the 600 trigger requiring review.

— case APP000107, repeat 1

**What to do:** When a briefing says a figure is above or below a limit, compare the two numbers yourself.

## Irrelevant field blamed — 12 of 60 briefings

The assistant blamed a field that has no bearing on the outcome.

> Additionally, the applicant falls within the **18-24 age band**, and while the credit file is 44 months old (meeting the "thin file" criteria of over 24 months), the age band may be a contributing factor to the manual review.

— case APP000028, repeat 1

**What to do:** Disregard reasoning that rests on age band, dependants, loan purpose. The lending policy does not use them.

## Wrong or no way to change the outcome — 3 of 60 briefings

The assistant did not name a valid way to change the outcome.

> *   **Credit History:** The applicant has a bureau score of **532**, which is below the 600 threshold requiring review.

— case APP000588, repeat 1

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
