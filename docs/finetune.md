# Fine-tuning the assistant

How a fine-tuned Nemotron 3.5 Lightning is made, served beside the current one, and shown
to be better. Every step is a command; every result is sealed.

## The idea

A bigger model (the **teacher**, Nemotron 3 Ultra) writes memos for new cases. The six
checks keep only the memos that are right. Lightning is trained on those, with LoRA: a
small set of extra weights (about 44 MB) on top of the unchanged model. The result runs on
its own server, and the web UI puts the two assistants side by side on the same new cases.

```
new cases ──► teacher writes a memo ──► six checks ──► kept? ──► training data
   (never a test)     (Ultra)             │  no: shown what failed, tries again
                                          ▼
              LoRA training (NeMo AutoModel) ──► adapter ──► second Lightning NIM
                                                                   │
                        New test: "Both, side by side on new cases" ◄┘
```

## 1. Training data: `evidence distill`

```bash
.venv/bin/evidence distill cases --name lightning-sft-v1 --n 2000 --from-pack underwriter-de
```

```bash
.venv/bin/evidence distill teach --name lightning-sft-v1 --attempts 3 --workers 8
```

```bash
.venv/bin/evidence distill build --name lightning-sft-v1
```

- **Cases** come from the same recipe and market as the pack named, with seeds no pack has
  used. A case whose application form appears in any test pack is dropped. The cases live
  in `training/`, never `packs/`, and the UI's case generator treats their seeds and
  applications as taken: a training case can never become a test.
- **The teacher** gets exactly what the assistant gets: the task prompt and the documents
  (`as_is`: the case file only). It thinks first; only its final answer is kept. Set it
  with `EVIDENCE_TEACHER_BASE_URL` and `EVIDENCE_TEACHER_MODEL`. By default it is Ultra on
  the NVIDIA API catalog; Ultra on the team's B300 works the same way through the
  `ultra-tunnel` SSH entry (`http://127.0.0.1:18000/v1`).
- **A memo is kept** only if it passes all six checks and fits the assistant's answer
  budget (900 tokens, taken as 3,200 characters). A memo that fails is tried again with
  the teacher shown its memo and what the checks found. Lightning is trained on the case
  and the final memo only. In the pilot, 24% of first attempts passed and 65% of second
  ones; 83% of cases ended with a kept memo.
- `teach` can be stopped and started again: it picks up where it was. A busy or failing
  endpoint is retried with a wait and does not use up a case's attempts.
- **The output** in `training/<name>/`:
  - `teacher.jsonl`: every memo, kept or not, with its check results;
  - `sft/train.jsonl` and `sft/val.jsonl`: chat format, split by case;
  - `manifest.json` and `README.md`: counts, failures by check, the teacher, the check
    versions;
  - sealed, and anchored when anchoring is on.
- `--feedback runs/<run>/feedback/handover` adds the memos people corrected in a feedback
  pack. Those come from a test, so the manifest names the pack, and a model trained on
  them must be compared on other cases.

## 2. Training: NeMo AutoModel on the node

Copy the training folder to the cluster, then start training on two of the GPUs the
servers job holds but does not use:

```bash
rsync -a training/lightning-sft-v1 codefest:/data/team08/training/
```

```bash
ssh codefest "ssh rtx-3se-06-04 'bash ~/open-credit-evidence/scripts/finetune/train_lightning.sh /data/team08/training/lightning-sft-v1 1,2'"
```

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
- Speed on two RTX PRO 6000 GPUs: about 3,400 tokens a second, 41 GB per GPU; about half an
  hour for 2,000 examples.
- Output: `/data/team08/runs/ft/<name>-<time>/`, with `train.log`, `config.yaml` and the
  adapter in `checkpoints/…/model/` (`adapter_model.safetensors`, `adapter_config.json`).
  The checkpoint with the lowest validation loss is marked `LOWEST_VAL`.

## 3. Serving: a second Lightning NIM

```bash
ssh codefest "ssh rtx-3se-06-04 'bash ~/open-credit-evidence/scripts/cluster/serve_lightning_ft.sh 1'"
```

- A separate NIM container (`team08-lightning-ft`) on GPU 1, port 8210, with the
  full-precision LoRA profile. The assistant's own NIM (port 8200) is untouched.
- It serves the base model in full precision (`nvidia/nemotron-3.5-lightning`, a fair
  control) and every adapter in `/data/team08/loras/<name>/`, each under its folder's name.
  A new adapter is picked up within a minute, without a restart.
- Two things this script handles that are easy to get wrong on a shared node:
  - the NIM runs vLLM on a second, internal port (8001 by default), which the assistant's
    NIM already holds, so it gets one of its own;
  - the container resolves our user ID from a mounted password file.

To publish an adapter:

```bash
ssh codefest "mkdir -p /data/team08/loras/lightning-credit-v1 && cp /data/team08/runs/ft/<run>/checkpoints/LOWEST_VAL/model/adapter_* /data/team08/loras/lightning-credit-v1/"
```

## 4. Both assistants side by side

Point the engine at it in `.env`:

```
EVIDENCE_CANDIDATE_BASE_URL=http://10.130.232.21:8210/v1
EVIDENCE_CANDIDATE_MODEL=lightning-credit-v1
```

In the web UI, **New test** then offers three assistants:
- the assistant;
- the fine-tuned assistant;
- **both, side by side on new cases**: new cases like the chosen set, both assistants on
  the same cases, then the comparison. The comparison page names the models, gives each
  check's pass rate for both, and lists every case memo beside memo with the checks each
  failed.

A test run with either assistant records which one wrote the memos (`sut.role` in the
manifest) and fingerprints its server like any other.

## What proves it

- The comparison on new cases, with enough of them to decide (100 or more, run twice).
- The capability gate (`evidence capabilities gate`) with the fine-tuned model as the
  candidate: credit memos better, and not worse on what else is measured.
- Both sealed and anchored, with the training data's seal in the adapter's record.
