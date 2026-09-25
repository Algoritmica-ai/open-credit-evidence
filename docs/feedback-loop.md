# Evaluate, review, improve: the feedback loop

The engine evaluates an AI assistant that drafts credit memos, routes the results to people
for review, and turns their verdicts into data that improves the model — then proves the
improvement with a fresh evaluation. Every step is sealed.

## What makes it different

1. **No production loan data.** Every case is generated from the lender's credit policy by
   the Synthetic Data Designer. No customer file leaves the bank, no data-sharing agreement
   is needed, and neither the evaluation nor the improvement data carries personal data.
   The lender supplies policy (rules, thresholds, factors that may not be used, such as
   those in BDSG § 37a), not records.
2. **Sealed evaluation evidence.** Because the cases are generated, the right answer is
   known; deterministic checks mark every memo against it, and the evidence pack can be
   re-derived by anyone — model risk, audit, a supervisor.
3. **Feedback that improves the model.** People review the evaluated memos; their verdicts,
   checked against the known answers, become a sealed feedback pack for fine-tuning or fixing
   the assistant — and for the evaluator itself. The next evaluation, on cases the model has
   never seen, shows whether it improved.

## The loop

1. **Evaluate.** Generate a pack from the lender's policy; run the assistant; the checks and
   the judge panel produce the evidence per memo, each finding tied to the memo sentence,
   the case-file line and any calculation.
2. **Queue.** The evaluated memos go to a review queue, ordered by the evidence:

   | Lane | Rule | Review |
   |---|---|---|
   | Red | a check failed and the panel confirms it, or the panel has a material finding backed by a tool | every finding |
   | Amber | check and panel disagree | the disputed findings |
   | Green | every check passes and the panel does not flag | sign-off; a sample gets full review |

   The queue holds evaluation outputs, never live applications.
3. **Review.** One card per finding: the memo sentence, the evidence and who found it.
   **Confirm** (and correct the sentence), **Dispute** with a reason code (*wrong figure*,
   *wrong reading of policy*, *not material*, *finding is wrong*) or **Needs more**. For green
   memos the reviewer signs off or raises a finding the evidence missed. Time per memo is
   recorded.
4. **Check the labels.** A reviewer's verdict becomes training data only once it is known to
   be right. Where a finding rests on the known answer, the verdict is compared with it; a
   verdict that disagrees, and every dispute or raised finding, goes to adjudication by model
   risk. Only confirmed verdicts pass.
5. **Feedback pack.** From the checked verdicts, sealed with a link from each example to its
   review, its evidence and its case:

   | Content | Use |
   |---|---|
   | corrected memos | supervised fine-tuning of the assistant |
   | original and corrected memo pairs | preference tuning |
   | findings with checked labels | training and calibrating the judge and panel |
   | failure summary by type | the assistant's owner: prompt, data or model fixes |
   | upheld disputes | fixes to the deterministic checks, each with a regression case |
   | new failure patterns | generator rules that produce more cases of that kind |

6. **Improve.** The assistant's owner — the lender's ML team or its vendor — fine-tunes or
   fixes the assistant from the feedback pack. For the demonstration the engine does it on an
   open model (LoRA on Nemotron with NeMo).
7. **Re-evaluate.** The improved assistant is evaluated on a **fresh pack** generated with a
   different seed, never on the cases it learned from. The comparison report against the
   previous run is the proof of improvement, or of none.

## What is measured

| Measure | Definition |
|---|---|
| Improvement | the change in every check's pass rate between runs on fresh packs, with confidence intervals |
| Reviewer agreement with the known answer | share of verdicts on known-answer findings that were right |
| Automation bias | memos signed off although they carried a confirmed error (AI Act Art. 14(4)(b)) |
| Evaluator precision | findings that reviewers and adjudication upheld, per check and for the panel |
| Lane miss rate | errors found by review in green-lane memos |
| Time per memo, per lane | recorded review time: the speed claim, measured |

## Who decides what

Nothing changes on its own: every change is made by a person, versioned and re-tested.

| Change | Decided by | Proven by |
|---|---|---|
| A memo correction | the reviewer | the sealed review record |
| Whether a verdict enters the feedback pack | model risk, for disputes and disagreements with the known answer | the adjudication record |
| A check fix | model risk | the pack re-run; a regression case |
| An assistant change | the assistant's owner | re-evaluation on a fresh pack; go/no-go |
| Lane tolerances and sampling | the lender's head of credit operations | the next review round |

## Boundaries

- The engine reviews **evaluation outputs**. Routing live applications and recording credit
  decisions stay in the lender's systems.
- The engine **produces** the feedback pack and **proves** the improvement; production
  training runs in the lender's or vendor's ML stack (for example NeMo).
- A pattern seen in live operations comes back as a **generator rule**, never as a copied
  customer file.

## Realism: the condition for the first point

Generated cases must resemble the lender's real applications, or the evaluation proves
little about production. The generator is calibrated to aggregate statistics the lender can
share (distributions and rates, not records), and credit experts review sample cases before
a pack is approved. The pack manifest records the calibration source.

## Later: seeded memos

While the assistant makes many errors, its own errors are enough material. Two needs will
call for seeding memos with known, inserted errors: errors that no check or agent is built to
detect (blind spots), and a good assistant whose natural errors become rare. Seeds would also
serve as quality control on reviewers' labels.

## Decisions and defaults

| Decision | Default |
|---|---|
| Lane rules | as in step 2 |
| Green sampling rate | 10% |
| Reason codes | wrong figure, wrong reading of policy, not material, finding is wrong |
| Who adjudicates | model risk, not the reviewer |
| Held-out testing | every improvement evaluated on a fresh pack with a new seed |
| Reviewer identity | pseudonymous ids in the record; the lender holds the key |
| Loop cadence | per assistant release, and on every model change (the fingerprint shows it) |

## Build order

1. The review queue over evaluation outputs (lanes, cards) writing a sealed review record.
2. Label checking and adjudication; the sealed feedback pack.
3. A LoRA fine-tune of an open Nemotron model on the feedback pack.
4. Re-evaluation on a fresh pack and the comparison as the proof of improvement.
