# Next steps

Written on 26 September 2026, after the first 100-case end-to-end run. Most important first.
Each step says what it proves and what it needs.

## Where we are

The full loop runs end to end on 100 new cases in about 25 minutes:
- generate cases;
- test the assistant, with the three AI reviewers;
- review;
- rulings;
- the feedback pack and the fine-tuning handover;
- sealed PDFs;
- every milestone anchored in Bitcoin.

The 26 September run (`runs/underwriter-de-s12251-2026-09-26T144911Z`):
- **Result:** NO-GO, with 132 of 200 memos wrong in a way an underwriter could act on.
- **Consistency:** 43 of 100 cases changed result between runs on "figures match the case
  file".
- **Pack:** 76 memos corrected and verified by all six checks, and 514 finding labels.
- **Anchors:** one confirmed in Bitcoin block 968,685.

What the run doesn't have yet:
- a real person's review (it was scripted);
- a fine-tuned model;
- a release decision at full scale.

## 1. Fine-tune Lightning, with Ultra as teacher

**Proves:** the loop actually improves the assistant, the product's central claim.

1. **Pilot.** Ultra writes memos for about 200 new cases (thinking on, only its final answer
   kept). The six checks keep the memos that pass; we measure how many pass and how fast
   Ultra writes.
2. **Training data.** About 2,000 cases from seeds kept apart from every test set:
   - Ultra's passing memos (supervised fine-tuning);
   - Lightning's failing memo against Ultra's passing one for the same case (preference
     pairs);
   - the human-corrected memos from the feedback packs.
3. **LoRA fine-tune** of Lightning, on one B300 or two free GPUs on the team's node, with
   NeMo-RL or NeMo AutoModel (NVIDIA's training tools).
4. **Serve the adapter** alongside the base model: through the Lightning NIM if it takes
   LoRA adapters, otherwise vLLM.
5. **Prove it:**
   - `evidence capabilities gate` with the standard suite: credit memos better, arithmetic,
     German maths and knowledge no worse;
   - a new test on new cases, compared case by case with the base model;
   - both sealed and anchored.
6. **Later: reinforcement learning,** with the six checks as the reward.

**Needs from you:**
- the SSH tunnel to Ultra (`ssh -N ultra-tunnel`, see the config entry agreed earlier);
- where a trainable Lightning checkpoint is, and confirmation that its licence allows
  fine-tuning;
- GPU time for training.

**Watch for:** the model learning to pass the checks without being useful, for example
leaving out figures. The judge's usefulness score and a human spot check guard against that.

## 2. A real review by underwriters

**Proves:** people can use the review screen, and their answers are reliable.

- Two or three underwriters review one test (the 26 September one is ready): the 56 memos
  waiting for corrected wording, plus a sample of flagged memos.
- Measure:
  - agreement with the known answers;
  - mistakes waved through;
  - time per memo;
  - how often the coach was asked, and whether it changed answers.
- Collect what confused them on each screen, and fix it.

**Needs from you:** reviewers and an hour of their time.

## 3. A release decision at full scale

**Proves:** the gate can decide, not only say INCONCLUSIVE.

- Run the capability checker's standard suite (about 100 problems per benchmark, the whole
  case set, twice) on the base model. That's the baseline every candidate is gated
  against.
- Tests of 100 cases or more, run at least twice, for any decision. At 20 cases the gate
  rightly refuses to decide.
- **Speed up the second opinion.** It took 17.6 of the run's 25 minutes (about 11 memos a
  minute, with both judges fully busy). Options:
  - a third judge;
  - running the AI reviewers only on memos the checks passed, plus a sample of the rest;
  - a smaller judge for the Reader.

## 4. Evidence and anchoring

- **Rekor signatures:** record *who* sealed a test (a signature with the bank's key in
  Sigstore's public log). It lands in seconds, and goes in the same anchor records.
- **The PDFs** should show whether the test is anchored, and in which Bitcoin block.
- **The relay** that spreads the AI reviewers' calls over the two judges was started by
  hand; put it under the servers job's watchdog.
- **For a bank:** document running its own OpenTimestamps calendar and Bitcoin node, for
  networks without outbound access.

## 5. NVIDIA tooling

- **Report upstream to NeMo Evaluator**, all listed in [capabilities.md](capabilities.md):
  - its reasoning filter misses output without an opening `<think>` tag;
  - MMLU-Pro's reader misses `$D$`;
  - a judge's score replaces the benchmark's score by default, and the judge's `rubric`
    setting isn't read;
  - normal-approximation intervals can fall outside 0–100%;
  - `xstest` has a stale dataset link;
  - `ifeval` is missing dependencies.
- **In the UI:** Improve's "Prove the fix" step should show a table of the other skills,
  from the capability gate.
- **NeMo Guardrails:** run the six checks on the live assistant in production. The checks
  that test it would also guard it.
- **NeMo Curator:** check that no test case leaked into the training data, for the model
  risk file.

## 6. Housekeeping

- **Teammates' open PRs:** decide whether to finish or close them.
  - [Algoritmica-ai/open-credit-evidence#2](https://github.com/Algoritmica-ai/open-credit-evidence/pull/2)
    (report export by default, a Docker volume);
  - [Algoritmica-ai/open-credit-evidence#3](https://github.com/Algoritmica-ai/open-credit-evidence/pull/3)
    (Steel Thread controls, Italy rule checks).
- **Italian rules:** the UI offers them, but all our recent tests used the German cases.
  Run one Italian test end to end.
- **Unplaced quotes:** 6 of 440 quoted findings still can't be placed on a memo sentence.
  Look at them.
- **The hosted Hugging Face demo** is behind: update it to the current UI.
- **Old test runs** clutter Earlier tests: archive the ones from before today.
