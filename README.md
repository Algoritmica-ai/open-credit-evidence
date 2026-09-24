# Credit Evidence Engine

Tests an AI assistant that compiles a case file for a human making a regulated
credit decision, and produces the evidence a validator or supervisor needs to
approve it for use.

The assistant does not decide the loan. It writes the briefing the underwriter
decides from. A briefing can read well, state the right conclusion, and still be
dangerous — because of what it leaves out, or because a number in it is wrong.
This engine catches both, by name, without asking another model to judge.

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

```
Synthetic Data Designer ──▶ scorecard ──▶ pack (documents + sealed marking key)
                                               │
                                               ▼
                       assistant under test (Nemotron, NIM or NVIDIA Build)
                                               │ briefing, N repeats
                                               ▼
        material_omission · numeric_fidelity · comparison_fidelity
                   decoy_citation · flip_accuracy
                          + readability judge (reported)
                                               │
                                               ▼
              evidence pack by obligation ── checksums ── evidence verify
```

## Quick start

```bash
git clone https://github.com/Algoritmica-ai/open-credit-evidence.git
cd open-credit-evidence
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env            # points all three roles at the team's node (VPN); no key needed
.venv/bin/pytest -q             # 40 tests, no network
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

`verify --recompute` rebuilds all of it from the results and names the first number
that does not match — even if someone re-sealed the checksums after editing it.

The same flow in a browser — pack (choose, build from a spec, or upload), cases,
run (with cancel), evidence (the decision, why it failed and what to change, every
briefing with its verdicts, then the pack by obligation), verify (with a tamper demo on
a copy of the run), compare (did a change help?):

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
| Judge (readability and oversight, citing the regulation) | Nemotron Nano 9B v2 (`nano-judge`), un-tuned today | vLLM on the team's node (`.env.example` points there); Nemotron 3 Ultra on NVIDIA Build is the teacher for the fine-tune |
| Retriever (corpus build, judge retrieval) | Nemotron 3 Embed 1B | vLLM on the team's node; or NVIDIA Build |

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
| `regulations/` | Jurisdiction rule packs and obligation registries (Italy), and the regulation corpus the judge cites (EU AI Act), built with `evidence corpus build` |
| `scripts/` | Pack builder, the no-model demo, cluster serving scripts, LoRA fine-tuning |
| `notebooks/` | Executed notebooks: the three models on one case; the on-prem setup |
| `runs/` | A committed evidence pack from a real run |
| `examples/nemo_evaluator/` | The same pack as a NeMo Evaluator benchmark, with a gate policy |
| `docs/` | Architecture, contracts, models, cluster, regulations, the Verifier's Law framing, the deck |

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
