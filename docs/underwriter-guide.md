# Underwriter guide

This guide is for the people who test the credit memo assistant and review its memos. It
walks through every screen in the order you use them. No technical knowledge is needed.

To install and start the UI, see [setup](setup.md).

## What the tool is for

When the bank's rules cannot decide a loan application automatically, it is referred to
an underwriter. An AI assistant writes a short memo for that underwriter: why the case was
referred, what the file shows for and against the applicant, and what would have to change
for a different outcome.

A memo can read well and still be wrong: a figure the case file doesn't contain, a limit
stated the wrong way round, or a reason the policy forbids (such as the applicant's age).
This tool finds those mistakes before anyone relies on the assistant.

It works in three steps, shown across the top of every page:

1. **Test.** The assistant writes memos for made-up loan applications, and every memo is
   checked against the rules.
2. **Review.** You confirm which of the mistakes the machine found are real.
3. **Improve.** Your answers become a feedback pack for the team that improves the
   assistant. A new test on new cases proves whether the fix worked.

**No customer data is used anywhere.** Every loan application is made up from the credit
policy. Because the tool built each case itself, it knows the right answer for every one.

## Words used on the screens

| Word | Meaning |
|---|---|
| Case | One made-up loan application: an application form, a credit bureau summary and the lending policy |
| Case set | A group of cases, usually 20. **New cases** are ones the assistant has never seen |
| Memo | What the assistant wrote for one case |
| Run | One time the assistant is given a case. A case run twice gives two memos |
| Finding | A possible mistake in a memo, found by the rule checks or by the AI reviewers |
| Rule checks | Fixed checks with no AI involved. They know the right answer, so what they find is reliable |
| AI reviewers (second opinion) | Three AI agents that read each memo against the case file. They can catch problems the rule checks miss, but can also be wrong |
| Feedback pack | Your confirmed answers and corrections, packaged for the model team |
| Sealed | Every file of a test is fingerprinted, so any later change shows |

## Home

The home page starts with **Start a new test**. Below it is the latest test, with its three
steps and the one to do next. Further down, **Waiting for review** lists the newest five tests
that still have flagged memos to check, with each test's number, when it started and how
far the review has got. The rest are in **Earlier tests**.

Every test has a short number (Test 17) and a start date and time, so tests from the same
day are easy to tell apart. On a wide screen, the open test is also shown at the top of every page.

## Starting a test

**Start a new test** asks three questions:

1. **Which assistant are you testing?** Usually there is one.
2. **Which rules must its memos follow?** German or Italian rules.
3. **Which test cases?** Pick a case set, or press **Generate new cases**.

**Generate new cases** opens a small window:

- **How many cases:** 5 to 200. Five is enough to try something out.
- **Times each case is run:** once to five times. See below for why more than once.
- **Include the figures your systems calculate:** leave this ticked.

The new cases are made in about a minute and chosen for the test. The line under the case
sets shows the size of the test ("5 cases, each run twice = 10 memos"). For an existing set,
press **Change** there to use fewer cases or a different number of runs.

Leave **Also get a second opinion from three AI reviewers** ticked for a real test. It
takes a few minutes longer and sorts the memos so you check the most likely mistakes first.

Press **Start test**. The progress page shows each stage. You can close the page, and the
result waits on the home page. **Stop the test** keeps everything finished so far.

### Why run each case more than once?

The assistant does not write the same memo twice, even for the same case. In our tests, a
mistake often appears in one run and not in the next. One run per case therefore finds only
some of the mistakes, and it can't show whether the assistant is consistent. Run each case
at least twice; three times gives firmer numbers.

## The result

The result page answers: **can the assistant be used?**

- **The headline:** how many memos had a mistake an underwriter could act on, with a
  verdict (for example, **Not ready for use**).
- **What went wrong:** the kinds of mistake, and how often each happened.
- **What to change:** the changes most likely to help, and who can make them (your team, or
  the vendor that supplies the assistant).
- **Same case, different result:** for each check, how many cases passed in one run and
  failed in another. The more cases that change, the less the assistant can be relied on to
  give the same answer twice.
- **Download the sealed report (PDF):** the full evidence, for model risk, compliance or
  audit.
- **Sealed and anchored:** under the buttons, whether the test's fingerprint is anchored in
  the Bitcoin blockchain yet (usually within a few hours of the test). Once it is, nobody
  can change a memo or a check result without it showing. **Show the technical detail**
  lists each anchor, and **Check the seal** checks them. See [anchoring](anchoring.md).
- **Review the flagged memos** takes you to step 2.

## Review

### The groups

The flagged memos are sorted into three groups:

| Group | Meaning | What to do |
|---|---|---|
| **Check first** | The rule checks and the AI reviewers both found a problem | Check all of them |
| **Worth a look** | Only one of the two found a problem | Check them: your answers show whether the AI reviewers raise false alarms |
| **Probably fine** | Nothing was found | Check two or three, to make sure the machine isn't missing things |

Press **Start** on a group to open its first memo.

### The review screen

The screen shows everything for one memo at once, in three columns.

**Across the top:** every application in the test, with the arrows to go to the previous or
next one. Reviewed ones are ticked, and the open one is highlighted.

**Left: the case file at a glance.** The figures the case turns on, read from the case file:
income, existing commitments, the new instalment, total debt service, and debt service as a
share of income. Each is marked within or outside the policy limit. Where the tool works a
figure out, it shows how (for example "€760 ÷ €2,079.25"). Fields the policy says must not
count, such as age band, postcode or dependants, are marked **not a factor**. Figures that a
finding is about are outlined and carry the finding's number. **See the original documents**
opens the case file exactly as the assistant received it.

**Middle: the memo the assistant wrote.** Sentences with a finding are highlighted, with
the finding's number. Next to each highlight, a chip gives what the case file says, for
example **Case file: debt ratio 36.55%** right after a sentence claiming 51.5%. If the case
ran more than once, a box above the memo lists every run and which checks each failed.
**Compare** opens another run's memo below this one, so you can see where the runs differ.

**Right: the findings.** One card per finding:

- **What was found**, in one sentence.
- **The memo says / Case file**, side by side, with the policy limit and how the figure was
  worked out. A figure that isn't in the case file at all is struck through.
- **Proof** (for rule checks) or **Why the reviewers think so** (for the AI reviewers).
- **Found by the rule check, which knows the right answer**, or **Found by the AI
  reviewers**. A rule check finding is very likely right; an AI reviewer finding needs your
  judgement.

The findings column stays in place while you scroll the memo. Hovering over a finding
outlines its sentence and its figures.

### Answering

For each finding there is one question: **Is the memo wrong here?**

| Answer | When | What happens next |
|---|---|---|
| **Yes, it's wrong** | The memo is wrong at this point | You can write how the sentence should read. With your wording, the model team gets a corrected memo to train on. One correction covers every finding on the same sentence |
| **No, the memo is right** | The finding is mistaken | Say why: the figure is correct, the policy was read correctly, it doesn't change the decision, or the finding itself is mistaken |
| **Not sure** | You can't tell | A colleague from model risk decides |

Found a mistake the machine missed? Press **I found another problem** and describe it.

Press **Save and open the next memo** when every finding has an answer. **Skip** moves on
without saving.

### The coach

The coach is an AI you can ask for a second view, on a finding you're unsure about. Answer
the finding first, then press **Ask the coach about this** under it. The coach points at the
evidence and may ask you a question. It does not know the right answers, and the decision
stays yours. **Ask the coach about all my answers** at the end of the findings asks about
all of them, and you can reply to what it says.

Use it only when you need it. Your answers are what the assistant learns from, so they
should be your own judgement. The review records your first answer on each finding, before
the coach said anything, so its influence can be measured.

## Improve

The Improve page turns the review into something the model team can use. At the top it
says what the review found and the one thing to do next. Below that are five steps; the one
to do now is marked **Do this next**.

**Can the review be trusted?** Because every case has a known right answer, the review is
checked too:

- **Answers that match the known answer:** how often reviewers agreed with the rule checks
  where those are certain.
- **Mistakes waved through:** memos passed as right although they have a known mistake.
  Above zero means people trust the machine too much.
- **What the AI reviewers raised beyond the rules:** of their flags on memos that passed
  every rule check, how many were real problems and how many false alarms.

**1. Settle disagreements.** Where a reviewer said the memo was right, was not sure, or
found a problem of their own, someone from model risk decides: **The reviewer** or **The
machine**. Only settled answers go into the feedback pack.

**2. Write the corrections.** A confirmed mistake teaches the assistant only once someone
writes how the memo should have read. This step lists every such sentence with the problem
and the current wording. Change the wording in the box and press **Save correction**.

**3. Build the feedback pack.** Press **Build the feedback pack**. It shows what the pack
holds: corrected memos, before-and-after pairs, confirmed findings, and fixes to the rule
checks. If answers or corrections change afterwards, the page asks you to build it again.

**4. Hand over for fine-tuning.** One zip file for the engineering team that retrains the
assistant. It holds the training data, a starting configuration, and a README saying where
every row came from.

**5. Prove the fix on new cases.** A change is accepted only when it helps on cases the
assistant has never seen:

- **A change your team can make today:** for example, giving the assistant the figures your
  systems already calculate. **Test this change on new cases** runs the assistant as it is
  and with the change on the same new cases, then compares them case by case.
- **The fine-tuned model, when it comes back:** start a new test with it on new cases, then
  compare it with this test in **Earlier tests**.

## Earlier tests and case sets

**Earlier tests** lists every test with its number, start time, size, result and review
progress. Tick two and press **Compare** to see, check by check, whether the later one is
better or worse.

**Case sets** lists every set of cases, how many tests each was used in, and when it was
made. A set already used in a test no longer appears on the New test page, so a test always
starts from cases the assistant hasn't seen; open it from Case sets to use it again.
