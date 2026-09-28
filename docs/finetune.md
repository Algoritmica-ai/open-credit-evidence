# Fine-tuning the assistant

How a fine-tuned Nemotron 3.5 Lightning is made, served beside the current one, and shown
to be better, or not. Every step is a command; every result is sealed.

## The result

On 100 new cases, each run twice, marked by the six checks (current versions):

| Assistant | Case file only | With the bank's figures |
|---|---|---|
| Lightning as deployed (8-bit) | 22% | 60% |
| Lightning, full precision (the fair control) | 31% | 76% |
| Fine-tuned v3 (case file only) | 46% | |
| **Fine-tuned `lightning-credit-fig-v2`** | | **97%** |

Share of memos in which no check found a mistake. `fig-v2` is accepted against every
baseline: no check is worse, and figures (99%), omissions (100%) and decoys (100%) are
better. Its memos state as many figures as the base model's, and are as long.

What made the difference, in order of size:

1. **Hand the assistant the figures the bank's systems already compute** (the `with_figures`
   setup): 22% → 60%.
2. **Run Lightning in full precision** rather than 8-bit: 60% → 76%.
3. **Fine-tune it to quote those figures, not work out new ones,** and to leave out
   fields with no bearing on the decision: 76% → 97%.

## The idea

A bigger model (the **teacher**, Nemotron 3 Ultra) writes memos for new cases. The six
checks keep only the memos that are right. Lightning is trained on those, with LoRA: a
small set of extra weights (about 44 MB) on top of the unchanged model. The result runs on
its own server, and the web UI puts the two assistants side by side on the same new cases.

```
new cases ──► teacher writes a memo ──► six checks ──► kept? ──► cleaned ──► training data
   (never a test)     (Ultra)             │  no: shown what failed, tries again
                                          ▼
              LoRA training (NeMo AutoModel) ──► adapter ──► fine-tuned Lightning NIM
                                                                   │
                        New test: "Both, side by side on new cases" ◄┘
```

## What each version taught

| Version | Trained on | Lesson |
|---|---|---|
| pilot | 155 memos as Ultra wrote them | Worse than the base model. It copied Ultra's figure-rich style, not its arithmetic. |
| v1, v2 | Ultra with a writing guide: working before the result | 28% → 40%. They learned to say "two dependants increase living costs": Ultra's memos mentioned decoys, and the student turned mentions into reasons. |
| v3 | v2's memos without the clauses that mention a decoy | Decoys solved (98%), but it worked out "what would change" figures (the largest instalment, the income needed) and got them wrong. |
| fig-v1 | Ultra given the bank's figures | 78%. Still worked out extra figures ("€877, which is €236.08 above the threshold"): wrong. |
| **fig-v2** | fig-v1's memos, quoting only: clauses with a worked-out figure taken out | **97%**. |

A model that answers without thinking copies habits, not arithmetic. The training data must
hold only what it can do reliably.

The checks were made stricter along the way, each as a new version (older runs still
re-derive with the versions they were scored with; `evidence checks` lists them):

- `numeric_fidelity` 3 and 4 read working written out in a memo, chains and brackets
  included, and fail an equation that does not add up;
- `decoy_citation` 2 reads the singular ("one dependant") and more ways of reasoning with a
  field ("increases living costs"). Re-scored with it, v1 cited a decoy in half its memos;
- `material_omission` 2 reads a computed figure stated more precisely ("48.9%" for 49%).

## 1. Training data: `evidence distill`

```bash
.venv/bin/evidence distill cases --name lightning-sft-fig-v1 --n 2000 --from-pack underwriter-de
```

```bash
.venv/bin/evidence distill teach --name lightning-sft-fig-v1 --setup with_figures --limit 1000 --attempts 3 --workers 8
```

```bash
.venv/bin/evidence distill build --name lightning-sft-fig-v2 --setup with_figures --quote-only
```

(`fig-v2` was built from `fig-v1`'s teacher memos: copy `cases/` and `teacher.jsonl` into a
new folder and build it there.)

- **Cases** come from the same recipe and market as the pack named, with seeds no pack has
  used, and carry the bank's figures. A case whose application form appears in any test
  pack is dropped. The cases live in `training/`, never `packs/`, and the UI's case
  generator treats their seeds and applications as taken: a training case can never become
  a test.
- **The teacher** gets exactly what the assistant gets under the setup: the task prompt and
  the documents. It thinks first; only its final answer is kept. It also gets a writing
  guide the fine-tuned model never sees (`GUIDES` in [distill.py](../src/evidence/distill.py)):
  - `as_is`: work out every figure in one line of arithmetic before using it;
  - `with_figures`: quote the bank's figures as given; do not work them out again.

  Set the teacher with `EVIDENCE_TEACHER_BASE_URL` and `EVIDENCE_TEACHER_MODEL`. By default
  it is Ultra on the NVIDIA API catalog, which limits the rate: about 5 memos a minute, so
  1,000 cases take 4–5 hours. Ultra on the team's B300 works the same way through the
  `ultra-tunnel` SSH entry (`http://127.0.0.1:18000/v1`).
- **A memo is kept** only if it passes all six checks and fits the assistant's answer budget
  (900 tokens, taken as 3,200 characters). A memo that fails is tried again with the
  teacher shown its memo and what the checks found. With the figures, 97% of cases ended
  with a kept memo.
- `teach` can be stopped and started again: it picks up where it was. A busy or failing
  endpoint is retried with a wait and does not use up a case's attempts; a case refused
  too often is left for the next `teach`. It runs on the laptop: keep it awake
  (`caffeinate -i -w <pid>` on macOS).
- **`build` cleans the memos**, checks each one again with the current checks, and keeps it
  only if it still passes:
  - the clauses that mention a decoy (every alias, singular and plural) are taken out;
  - with `--quote-only`, so are the clauses stating a figure the teacher worked out rather
    than quoted (months as years and a percentage as a decimal stay).
- **The output** in `training/<name>/`:
  - `teacher.jsonl`: every memo, kept or not, as the teacher wrote it, with its check
    results;
  - `sft/train.jsonl` and `sft/val.jsonl`: chat format, split by case;
  - `manifest.json` and `README.md`: counts, failures by check, what was cleaned, the
    teacher and its guide, the check versions;
  - sealed, and anchored when anchoring is on.
- `--feedback runs/<run>/feedback/handover` adds the memos people corrected in a feedback
  pack. Those come from a test, so the manifest names the pack, and a model trained on
  them must be compared on other cases.

## 2. Training: NeMo AutoModel on the node

Copy the training data to the cluster, check it arrived whole, and start training on two
GPUs the servers job does not use (2 and 6 hold only small services):

```bash
rsync -a --partial training/lightning-sft-fig-v2/sft training/lightning-sft-fig-v2/manifest.json codefest:/data/team08/training/lightning-sft-fig-v2/
```

```bash
ssh codefest "ssh rtx-3se-06-04 'setsid nohup bash ~/open-credit-evidence/scripts/finetune/train_lightning.sh /data/team08/training/lightning-sft-fig-v2 2,6 > /data/team08/runs/ft/launch.log 2>&1 < /dev/null &'"
```

(`setsid nohup`: the training keeps going when the VPN drops the SSH connection.)

- It runs NVIDIA's `nvcr.io/nvidia/nemo-automodel:26.08.00` container on Lightning's
  full-precision weights (`hf-b3caaab` in the NIM cache), with the configuration from
  [scripts/finetune/lightning_lora.py](../scripts/finetune/lightning_lora.py):
  - LoRA rank 16 on every linear layer except the Mamba `out_proj`, as in NVIDIA's recipe
    for this architecture;
  - loss on the memo only;
  - 2 passes over the data, learning rate 1e-4 with a cosine decay;
  - **the chat format Lightning is served with**: its own template with thinking off. A
    training example is exactly the prompt the NIM renders (ending `<think></think>`),
    then the memo.
- About 3,400 tokens a second on two RTX PRO 6000 GPUs, 41 GB each: 10–20 minutes for
  800–1,800 examples.
- Output: `/data/team08/runs/ft/<name>-<time>/`, with `train.log`, `config.yaml` and the
  adapter in `checkpoints/…/model/` (`adapter_model.safetensors`, `adapter_config.json`).
  The checkpoint with the lowest validation loss is marked `LOWEST_VAL`.

## 3. Serving: the fine-tuned NIM in the servers job

The servers job ([scripts/cluster/servers.sbatch](../scripts/cluster/servers.sbatch)) runs a
second Lightning NIM, `team08-lightning-ft`, beside the assistant's: full precision with
LoRA, on its own GPU, port 8210. It serves the base model in full precision
(`nvidia/nemotron-3.5-lightning`, the fair control) and every adapter in
`/data/team08/loras/<name>/`, each under its folder's name. A new adapter is picked up
within a minute, without a restart. The job writes `EVIDENCE_CANDIDATE_BASE_URL` and
`EVIDENCE_CANDIDATE_MODEL` (default `lightning-credit-fig-v2`; `CANDIDATE_MODEL=` to change
it) into `servers.env`.

To publish an adapter:

```bash
ssh codefest "mkdir -p /data/team08/loras/lightning-credit-fig-v2 && cp -L /data/team08/runs/ft/<run>/checkpoints/LOWEST_VAL/model/adapter_* /data/team08/loras/lightning-credit-fig-v2/ && chmod -R g+rX /data/team08/loras"
```

[scripts/cluster/serve_lightning_ft.sh](../scripts/cluster/serve_lightning_ft.sh) starts the
same NIM by hand, for trying things out. Two things it and the job handle that are easy to
get wrong on a shared node:
- the NIM runs vLLM on a second, internal port (8001 by default), which the assistant's
  NIM already holds, so it gets one of its own (`NIM_BACKEND_PORT`);
- the container resolves our user ID from a mounted password file.

## 4. Both assistants side by side

`.env` names the fine-tuned assistant (copy the lines from `servers.env`):

```
EVIDENCE_CANDIDATE_BASE_URL=http://10.130.232.21:8210/v1
EVIDENCE_CANDIDATE_MODEL=lightning-credit-fig-v2
```

In the web UI, **New test** then offers:
- the assistant;
- the fine-tuned assistant;
- **both, side by side on new cases**: new cases like the chosen set, both assistants on
  the same cases, then the comparison. The comparison page names the two models, gives each
  check's pass rate for both, and lists every case memo beside memo with the checks each
  failed.

Tick **"Give it the figures your systems already calculate"** to give the assistant (or
both) the bank's figures. From the command line: `evidence run <pack> --setup with_figures`.

A test run with either assistant records which one wrote the memos (`sut.role` in the
manifest) and fingerprints its server like any other.

## What proves it

- The comparison on new cases, with enough of them to decide (100 or more, run twice), and
  against the fair control: the same model in full precision, given the same documents.
- A look at the memos, not only the scores: a model can pass the checks by saying less. For
  `fig-v2` the median memo states 13 figures, as the base model's does, and names what
  would change the outcome as often.
- The capability gate (`evidence capabilities gate`) with the fine-tuned model as the
  candidate.
- Everything sealed, with the training data's seal next to the adapter
  (`training-data.sha256`).
