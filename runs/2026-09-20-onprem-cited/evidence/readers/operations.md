# For underwriters — what to watch for in the assistant's briefings

Assistant `nvidia/nemotron-3.5-lightning` (on-prem) · 60 briefings: 20 referred loan cases × 3 · pack `underwriter-sample` v0.3.0 · run `2026-09-20-onprem-cited` · model calls 2026-09-20

The briefing is a summary of the file, written by a model. On these cases it went wrong in the ways below, most frequent first. Each comes with a sentence the assistant actually wrote and what to do when you see one like it.

## Figure worked out wrongly — 33 of 60 briefings

The assistant worked a figure out itself and got it wrong.

> … annual income would need to increase to approximately **£32,300+** (bringing the DTI below 40% with the current …

— case APP000028, repeat 3

**What to do:** Check any ratio or amount the briefing works out against the application form before relying on it. The briefing's own arithmetic is where it is most often wrong.

## Wrong or no way to change the outcome — 15 of 60 briefings

The assistant did not name a valid way to change the outcome.

> Additionally, the applicant's **bureau score of 570 falls below the 600 benchmark**, triggering a secondary requirement for underwriter review.

— case APP000039, repeat 3

**What to do:** If the briefing does not say what would change the outcome, work it out from the policy: which limit is breached, and by how much.

## Irrelevant field blamed — 14 of 60 briefings

The assistant blamed a field that has no bearing on the outcome.

> Specifically, the applicant’s debt-to-income ratio exceeds the policy threshold of 40%, and the applicant falls within the "thin file" category due to the age of their credit file.

— case APP000028, repeat 1

**What to do:** Disregard reasoning that rests on age band, dependants, loan purpose. The lending policy does not use them.

## Threshold comparison stated wrongly — 6 of 60 briefings

The assistant compared a figure with a policy threshold and got the direction wrong.

> Additionally, the applicant's Bureau score of 652 falls below the 600 threshold requiring underwriter review.

— case APP000044, repeat 1

**What to do:** When a briefing says a figure is above or below a limit, compare the two numbers yourself.

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
