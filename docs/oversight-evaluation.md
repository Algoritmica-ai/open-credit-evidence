# Oversight evaluation: human review as the evaluation's feedback loop

**Evaluation is the product.** The engine tests an AI assistant that drafts credit memos
against cases whose right answer is known, and seals evidence anyone can re-derive.
**Oversight is its feedback loop.** People test that evidence, their verdicts are recorded
and scored, and what they find flows back into the checks, the assistant and the way
review effort is spent. The engine measures whether human oversight works; it does not run
the lender's review operations.

## Scope

| The engine does (evaluation) | The lender's own systems do (operations) |
|---|---|
| Evaluate the assistant on known-answer cases (the core, built) | Route live applications to officers |
| An **oversight test**: reviewers work through evaluated memos on review cards; their verdicts are recorded and scored | Be the system of record for credit decisions |
| A **triage simulation**: which review lane each memo would fall in, and what each lane would miss | Apply lanes to live work |
| **Seeded memos** with known errors, to measure what checks, panel and people miss | Mix known-answer cases into the live queue, if they choose |
| A sealed **oversight record** format a lender's workflow tool can also write | Staff training and assignment |
| The **feedback loops** into the checks and the assistant | |

## The flow

1. **Evaluate.** `evidence run` and `evidence panel` produce, per memo, the deterministic
   check results and the panel's findings, each tied to the memo sentence, the case-file
   line and any calculation. This is the evidence the rest of the flow tests.
2. **Seed.** A share of the memos are copied and given one known error each (see below). The
   reviewer does not know which. The seed record is sealed before review begins.
3. **Simulate triage.** Each memo is placed in a lane from its evidence alone:

   | Lane | Rule | Review |
   |---|---|---|
   | Red | a check failed and the panel confirms it, or the panel has a material finding backed by a tool | every card |
   | Amber | check and panel disagree | the disputed cards |
   | Green | every check passes and the panel does not flag | sign-off; a sample gets full review |

4. **Review cards.** The reviewer sees one card per finding: the memo sentence, the
   evidence (case-file line, calculation, which check or agent found it) and three actions —
   **Confirm**, **Dispute** with a reason code (*wrong figure*, *wrong reading of policy*,
   *not material*, *finding is wrong*) or **Needs more**. For green memos the reviewer reads
   the memo and either signs it off or raises a finding the evidence did not have. The time on
   each memo is recorded.
5. **Record.** Every action, reason, raised finding and time goes to `oversight/records.jsonl`
   in the run, with `oversight/manifest.json` (reviewers as pseudonymous ids, seeds, lane
   rules, sampling rate). The run is sealed again; `verify` covers the record; the scores in
   `evidence/oversight.json` and `oversight.md` are rebuilt from it by `verify --recompute`.
6. **Score.** Against the known answers — see *What is measured*.
7. **Feed back.** Through the four loops below; the next evaluation run shows the effect.

## Seeded memos: a ground truth that does not depend on our checks

On the known-answer pack a check failure is the ground truth for what the checks cover. To
measure what they miss, and what a fast lane would miss, errors must exist that we know about
independently. A seeded memo is a copy of a real memo with one inserted error:

| Seed type | Example | Should be caught by |
|---|---|---|
| wrong figure | a ratio or amount changed | `numeric_fidelity` |
| contradicted claim | "within the 40% limit" beside a figure above it | `claim_consistency` |
| decoy reason | age band or postcode given as a reason (BDSG § 37a) | `decoy_citation` |
| omission | the breached limit or a recent missed payment removed | `material_omission` |
| wrong direction | "higher income would worsen the case" | `flip_accuracy` |
| outside the checks | wrong applicant name, wrong loan term, an invented condition | only the panel or a person |

The last row measures blind spots: errors no deterministic check is built to see.

## What is measured

| Measure | Definition | Why it matters |
|---|---|---|
| Evaluator recall | seeded errors the checks caught; the panel caught; either caught | what the evidence can be trusted to surface |
| Reviewer catch rate | seeded errors the reviewer confirmed or raised | whether oversight works |
| Automation bias | memos signed off although they carried a known error (seeded or check-confirmed) | AI Act Art. 14(4)(b) names it |
| False disputes | true findings the reviewer disputed and that adjudication upheld as true | reviewer calibration; disputes that were right are check bugs |
| Lane miss rate | seeded errors that landed in the green lane | what the fast lane costs; the lender sets the tolerance |
| Time per memo, per lane | recorded review time | the speed claim, measured instead of assumed |

With several reviewers, their agreement on the same memos is reported too.

## The four feedback loops

Nothing changes on its own: every change is made by a person, versioned and re-tested.

| Loop | Input | Decided by | Changes | Proven by |
|---|---|---|---|---|
| Case | the reviewer's card actions | the reviewer | that memo only | the sealed record |
| Evaluator | disputes and raised findings | model risk (second line), not the reviewer | upheld: the check is fixed and the case becomes a regression item; rejected: reviewer guidance | the pack re-run; the comparison report |
| Assistant | patterns in confirmed findings | the assistant's owner | prompt, data or model; the vendor report names the likely fix | the pack re-run; go/no-go |
| Oversight | lane miss rate, catch rate, automation bias | the lender's head of credit operations | lane tolerances, sampling rate, training | the next oversight test |

A disputed live case, if a lender feeds one back, becomes a regression item only as a
synthetic look-alike rebuilt with the data generator — never as copied customer data.

## Decisions and defaults

| Decision | Default |
|---|---|
| Lane rules | as in step 3 |
| Green sampling rate | 10% |
| Lane miss tolerance | set by the lender; report against 2% as an example |
| Share of seeded memos | 20% of the memos a reviewer sees |
| Reason codes | wrong figure, wrong reading of policy, not material, finding is wrong |
| Who adjudicates disputes | model risk, not the reviewer who raised them |
| Evaluator loop cadence | weekly, and on every change of the assistant or its model (the fingerprint shows it) |
| Reviewer identity | pseudonymous ids in the record; the lender holds the key |

## What this adds to the evidence pack

An **Oversight** section: evaluator recall on seeded errors, reviewer catch rate, automation
bias, false disputes, lane miss rate and time per lane — each re-derivable from the sealed
record. For AI Act Art. 14 and Art. 26(2), and BDSG § 30 Abs. 6 from 20 November 2026, it
shows that human review was not only possible but effective, with numbers.

## Build order

1. Seeded memos: the mutation step and its sealed record.
2. Triage simulation: lanes from the evidence, in the evidence pack.
3. Review cards in the web UI as the oversight test, writing the oversight record.
4. Scoring and the Oversight section; `verify --recompute` covers it.
5. The evaluator loop: dispute adjudication and turning an upheld dispute into a regression item.
