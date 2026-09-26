# Credit Evidence Engine

Tests an AI assistant that compiles a case file for a human making a regulated
credit decision, and produces the evidence a validator or supervisor needs to
approve it for use.

The assistant does not decide the loan. It writes the briefing the underwriter
decides from. A briefing can read well, state the right conclusion, and still be
dangerous — because of what it leaves out, or because a number in it is wrong.
This engine catches both, by name, without asking another model to judge.

**Who it is for: public-sector lenders and their supervisors.** Europe's public banks —
in Germany alone about 365 to 370 lenders, 339 of them Sparkassen — take an estimated
60,000 to 120,000 loan applications a day across the EU, of which 10,000 to 30,000 need
real human review (planning estimates, see [`docs/market/public-sector.md`](docs/market/public-sector.md)).
An assistant that drafts the credit memo for those reviews is high-risk under the EU AI
Act. This engine is the evidence layer for it: the institution's model risk and audit
functions, and its supervisors, can check the assistant against known answers and
re-derive every result without trusting the bank or the vendor.

## How

**Ground truth by construction.** The loan applications are generated, not
collected. A hidden repayment-capacity tier drives the observable fields; a
scorecard decides approve, refer or decline; the fields that drove each decision
are recorded before any model runs. Fields with no path to the outcome — age
band, dependants, postcode, employer — are declared as decoys. That sealed
marking key is what makes an omission check possible.

**Deterministic checks are the evidence.** Each briefing is compared with the
marking key by plain code: did it state the facts the decision turned on, are
its numbers in the file, did it cite a decoy as a reason, did it name what would
change the outcome. A judge model grades readability and oversight against the
regulation passage retrieved for it — and must cite that passage — but is
reported, not gated.

**The output is an evidence pack**, organised by EU AI Act article, with every
result traceable to a transcript and every file covered by a checksum. Anyone
with the pack and the run can re-derive every number.

**Evaluate, review, improve.** The cases are generated from the lender's credit policy, so
no production loan data is ever used. The evaluated memos go to a review queue; reviewers'
verdicts, checked against the known answers, become a sealed feedback pack for improving
the assistant (and the evaluator); the improved assistant is re-evaluated on a fresh pack it
has never seen. Every step is sealed. Design: [`docs/feedback-loop.md`](docs/feedback-loop.md).

```
Synthetic Data Designer ──▶ scorecard ──▶ pack (documents + sealed marking key)
                                               │
                                               ▼
                       assistant under test (Nemotron, NIM or NVIDIA Build)
                                               │ briefing, N repeats
                                               ▼
        material_omission · numeric_fidelity · comparison_fidelity · claim_consistency
                   decoy_citation · flip_accuracy
                          + readability judge (reported)
                                               │
                                               ▼
              evidence pack by obligation ── checksums ── evidence verify
```

## Quick start

Guides: [local setup](docs/setup.md) · [underwriter guide to the UI](docs/underwriter-guide.md) ·
[architecture and the end-to-end flow](docs/architecture.md)

```bash
git clone https://github.com/Algoritmica-ai/open-credit-evidence.git
cd open-credit-evidence
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env            # points all three roles at the team's node (VPN); no key needed
.venv/bin/pytest -q             # no network needed
```

The catch, with no model involved:

```bash
.venv/bin/python scripts/demo_gate.py --case APP000044
```

A full run of the sample pack — 20 referred cases, three repeats, all checks, the
readability judge — and the evidence pack it produces:

```bash
.venv/bin/evidence run packs/underwriter-sample --repeats 3 --out runs/today
.venv/bin/evidence report runs/today
.venv/bin/evidence verify runs/today --recompute --pack packs/underwriter-sample
```

Change one digit in any transcript and `verify` fails, naming the file.

Every run's evidence pack now opens with **the decision** — GO / GO WITH CONDITIONS /
NO-GO / INCONCLUSIVE against the bank's thresholds (`evidence/thresholds.yaml`) — then
**why each failure happened** (a root cause per failing result, by fixed rules, no model)
and **what to change and who can** (the bank through the assistant's instructions, what
it is handed or its output template; the vendor when a failure survives those). To
prove a change helped, run again and compare, case by case:

```bash
.venv/bin/evidence compare runs/before runs/after     # ACCEPT / REJECT / INCONCLUSIVE / NO EFFECT
.venv/bin/evidence report runs/today --rewrite --thresholds bank.yaml   # re-decide, no model calls
```

The same evidence comes as a report for each person who acts on it, under
`evidence/readers/`:

| Report | For | Answers |
|---|---|---|
| `business.md` | Head of lending, product owner | Can we use it, and what does it take? One page. |
| `credit-risk.md` | Model risk, second line | Is the method sound and the result stable? Test design, results with intervals over cases, stability, root causes, limitations. |
| `compliance.md` | Compliance and legal | What does this evidence, article by article, and the lender's rule pack |
| `operations.md` | Underwriters and team leads | What to watch for, with sentences the assistant actually wrote |
| `vendor.md` | Whoever supplies the assistant | Every failing result, with its transcript and how to reproduce it |
| `auditor.md` | Internal audit, a supervisor | What each file is and how to check that none has changed |

```bash
.venv/bin/evidence report runs/today --for business
.venv/bin/evidence export runs/today            # all seven as PDF, into exports/today/
```

A PDF carries what ties it to its run: the run's seal (SHA-256 of
`checksums.sha256`) on every page, the SHA-256 of the Markdown it renders, when
the model calls ran, when the checks were scored and when it was exported, and an
integrity section saying how to check it. The auditor's PDF lists every file's
checksum. PDFs are printed by a local Chrome or Chromium (`EVIDENCE_CHROME` names
one); they are renderings, so they are written outside the run and never sealed.

`verify --recompute` rebuilds all of it from the results and names the first number
that does not match — even if someone re-sealed the checksums after editing it.

A second opinion from three agents, after a run:

```bash
.venv/bin/evidence panel runs/today                       # here, on the judge endpoint
EVIDENCE_PANEL_SSH="codefest rtx-3se-06-04" \
  .venv/bin/evidence panel runs/today --runtime nemoclaw   # inside the NemoClaw sandbox
```

A **Reader** scores each briefing as the underwriter would; a **Challenger** checks it
against the case file and the deterministic checks, with tools (a case-file search, a
calculator, each check's evidence); an **Arbiter** gives the final scores, citations and
whether a person should review it. Every agent's replies and tool calls are kept in
`panel/`, and `evidence/panel.md` sets the panel against the checks and the single judge.
Like the judge it is reported, never gated. The panel is one standard-library file
(`src/evidence/panel.py`), so the same code runs in the engine or inside a NemoClaw
sandbox, where its calls go through OpenShell's managed inference route
(`scripts/cluster/panel_nemoclaw.sh`; the route reaches the judge NIM through
`scripts/cluster/stream_relay.py`).

In a browser, for business users, in three steps. The home page starts a new test, shows
the latest test's steps and lists the tests waiting for review. **Test** asks which
assistant, which rules and which cases (new ones generated on the spot, with how many and
how many times each is run), and gives the result in plain words: what went wrong, what to
change, how often the same case got a different result between runs, and the sealed report
as a PDF. **Review** sorts the flagged memos into three groups and shows each memo between
the case file's figures and its findings, with the case file's number beside every
highlighted sentence, and every run of the same case; one question per finding: is the
memo wrong here? A **coach** on the judge model answers when asked, about one finding or all
of them, and never sees the answer key. **Improve** settles disagreements, collects the
corrected wording of confirmed mistakes, builds the feedback pack with a fine-tuning handover
(training data in chat and DPO formats, a starting LoRA configuration, provenance, the
acceptance test) and tests a change on new cases, compared case by case. **Case sets**
creates cases from the credit policy with the Synthetic Data Designer, which starts with the
UI at `/sdd/` (vendored in `src/sdd`, synced by `scripts/sync_sdd.sh`). The full console is
at `/advanced/`. A test started in the browser runs the panel in the NemoClaw sandbox when
`EVIDENCE_PANEL_SSH` is set, else directly against the judge endpoint. To start it:

```bash
.venv/bin/pip install -e ".[web]"
.venv/bin/evidence ui               # http://127.0.0.1:8765
```

Committed runs of the sample pack, all sealed and verifiable:

| Run | Assistant | Judge |
|---|---|---|
| [`runs/2026-09-20-build/`](runs/2026-09-20-build/) | Lightning on NVIDIA Build | Ultra, no corpus |
| [`runs/2026-09-20-onprem/`](runs/2026-09-20-onprem/) | Lightning NIM on the team's node | Ultra, no corpus |
| [`runs/2026-09-20-onprem-cited/`](runs/2026-09-20-onprem-cited/) | same briefings as above | Ultra, citing the EU AI Act corpus (55/60 citations) |

A hosted, shared demo of the UI is on Hugging Face:
<https://huggingface.co/spaces/Algoritmica/open-credit-evidence> (`deploy/huggingface/`).

## Models and where they run

| Role | Model | Where |
|---|---|---|
| Assistant under test | `nvidia/nemotron-3.5-lightning` | The NIM on the team's GPU node (`.env.example` points there); or NVIDIA Build |
| Judge and judge panel (readability and oversight, citing the regulation) | Nemotron 3 Super 120B-A12B (`nemotron-3-super`), FP8 on two GPUs | NIM on the team's node, tool calling on (`.env.example` points there); Nemotron 3 Ultra on NVIDIA Build is the teacher for the fine-tune |
| Retriever (corpus build, judge retrieval) | Nemotron 3 Embed 1B | NIM on the team's node; or NVIDIA Build |

Any role moves between cloud and on-prem with two lines in `.env`
(`EVIDENCE_<ROLE>_BASE_URL`, `EVIDENCE_<ROLE>_MODEL`); every transcript records
which endpoint produced it. See [`docs/models.md`](docs/models.md) and
[`docs/cluster.md`](docs/cluster.md).

## Repository

| Path | What it is |
|---|---|
| `packs/underwriter-sample/` | The sample pack: 20 items, three documents each, marking keys, obligations map, regulatory context |
| `specs/credit_underwriting.yaml` | The Synthetic Data Designer recipe the pack was generated from |
| `src/evidence/` | Contracts, checks, runner, judge, evidence pack writer and verifier, CLI, web UI |
| `regulations/` | Jurisdiction rule packs and obligation registries (Italy), and regulation corpora: EU (AI Act Art 9, 13–15, 26, Annex III 5; CCD2 Art 18–19), IT (TUB creditworthiness and credit-database articles, D.Lgs. 212/2025 transition), DE (BGB §§ 505a–505d, KWG § 18a, BDSG § 31 in force today, and the CCD2 transposition from 20 Nov 2026: new KWG § 18a, BDSG § 30 and § 37a), US (SR 26-2); rule packs for IT and DE. Built with `evidence corpus build` and checked word for word against the official text with `evidence corpus verify-sources` (result in `source_check.json`) |
| `scripts/` | Pack builder, the no-model demo, cluster serving scripts, LoRA fine-tuning |
| `notebooks/` | Executed notebooks: the three models on one case; the on-prem setup |
| `runs/` | A committed evidence pack from a real run |
| `examples/nemo_evaluator/` | The same pack as a NeMo Evaluator benchmark, with a gate policy |
| `docs/` | Setup, the underwriter guide, architecture, contracts, models, cluster, regulations, the Verifier’s Law framing, the deck |

## What it claims, and what it does not

For the sample pack, per obligation (from `packs/underwriter-sample/obligations.yaml`):

| Obligation | Level |
|---|---|
| Art 14 human oversight | Evidences — omission, decoy, flip checks |
| Art 15 accuracy and robustness | Evidences — numeric fidelity, repeat agreement |
| Art 13 transparency, Art 9 risk management | Contributes |
| Art 10, 12, 17 | Not covered, and the report says so |

It does not make or score the credit decision, does not grade regulatory
compliance, and does not measure fairness across a population. The jurisdiction
rule packs check that required evidence references are present; they do not
interpret law.

## Team

Sriram Krishnan (cases, marking, models) · Clyde Tedrick (engine, evidence,
deployment) · Luca Borella (materiality, regulation). Built for the NVIDIA Open
Models Codefest, mentored by Tosin Adesuyi.

## Licence

Apache 2.0. See [LICENSE](LICENSE), [NOTICE](NOTICE) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
