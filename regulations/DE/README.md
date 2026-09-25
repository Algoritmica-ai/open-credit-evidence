# Germany: consumer credit, creditworthiness and scoring

`ruleset.json` is the German rule pack: the evidence a German lender (a Sparkasse,
Landesbank, development bank or other credit institution) must hold for a consumer
creditworthiness assessment, next to the EU baseline (AI Act, CCD2, GDPR Art. 22).
`corpus.yaml` is the text those rules rest on, in German, as published.

## Two layers of law

| Layer | Source | Rules |
|---|---|---|
| In force today | BGB §§ 505a–505d, KWG § 18a, BDSG § 31 (gesetze-im-internet.de) | `required` |
| From 20 November 2026 | Gesetz zur Umsetzung der Richtlinie (EU) 2023/2225, BGBl. 2026 I Nr. 139: new BGB § 505a Abs. 1 Satz 3 and § 505b Abs. 1–2, new KWG § 18a, new BDSG § 30 Abs. 2–9 and § 37a; BDSG § 31 is repealed | `transition` (reported, not blocking) |

The corpus quotes the new law only where the act gives whole new text; amendments of
single words are not consolidated into the old text, because the result would not be
checkable against an official publication. `source_check.json` records that every
passage was found word for word in the official texts.

Two of the new provisions bear directly on an AI assistant in the credit decision:

- **BDSG § 30 Abs. 6**: where the assessment involves automated processing, the borrower
  can require the intervention of a person — an explanation of the assessment including
  the logic of the automated processing, the chance to state their view, and a review.
- **BDSG § 37a**: a score must not use age, gender, name, social-network data, bank
  account flows or address data. The pack's decoy check tests that an assistant does not
  give such fields (age band, postcode) as reasons.

## What a result means

As for Italy: `pass` means every required evidence reference is present, not that the
lender complies with German law. The rule pack is an operational baseline, not a legal
inventory; compliance approves a new version when the transition rules become required.
Start from `case-context.example.json` and replace every reference with the lender's own.
