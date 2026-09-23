# The Codefest cluster

What we have, verified 16 Sep 2026, and how the framework uses it.

## Facts

| | |
|---|---|
| Login node | `10.130.232.14` over the `codefest.ovpn` VPN. No GPUs, no docker. SLURM commands need a login shell (`bash -l`). |
| Team node | `rtx-3se-05-36`: 8× RTX PRO 6000 Blackwell, 97.9 GB each. One node per team (`AssocGrpNodeLimit`). |
| Getting a GPU | `srun --gres=gpu:1 -n1 -p defq --time=HH:MM:SS --pty bash`. `$CUDA_VISIBLE_DEVICES` tells you which one you got. |
| Docker | On GPU nodes only: `module load docker`. Containers are node-level and **outside SLURM** — they survive your session and hold their GPU until stopped. `--gpus 1` takes GPU 0 regardless of your allocation; always use `--gpus "device=$CUDA_VISIBLE_DEVICES"`. |
| Proxy | Shell sets `HTTP(S)_PROXY=http://10.130.232.8:3128`. `NO_PROXY` already covers `localhost`, `127.0.0.1`, `10.0.0.0/8`. Containers need the proxy passed in to reach NGC; `curl --noproxy '*'` for anything on the node. |
| Egress | Works through the proxy: huggingface.co and nvcr.io both reachable. |
| Storage | `/home/<user>` 2 TB shared; `/data/team08` 2 TB team-shared, group-writable — model weights and checkpoints go here; node-local `/raid` 47 TB scratch. |
| Already on the node | `nvcr.io/nim/nvidia/nemotron-3.5-lightning-30b-a3b:2.0.9-variant` (NIM), `nvcr.io/nvidia/nemo:26.08.00` (NeMo framework, for the Nano LoRA), CUDA 12.9 toolkit module, Python 3.12. |
| Accounts | Sriram is `team08_user3`. Key-based ssh: `ssh codefest`. Keep the NGC key in `~/.ngc_key` (mode 600) and `source` it — not on the command line, which lands in `.bash_history`. |

## What runs where

| Role | Where | Why |
|---|---|---|
| Assistant (Lightning) | NIM on the team node | Fixed seed on a local vLLM is reproducible; the free endpoint was not, and took 8–150 s per call. Runner at volume needs both. |
| Teacher (Ultra) | NVIDIA Build, or Curiosity B300 (`scripts/cluster/serve_ultra.sh`) | 550B; too large for a single RTX GPU. Used once, to label the judge's training set. B300 option needs 4 GPUs (NVFP4 TP4). |
| Judge (Nano) | vLLM on the team node, GPU 7, port 8002 (`scripts/cluster/serve_nano.sh`) | Nemotron Nano 9B v2, un-tuned today — the baseline; the fine-tuned adapter is served by the same script with `ADAPTER=`. Loan files never leave the box. |
| Embed | vLLM on the team node, GPU 6, port 8003 (`scripts/cluster/serve_embed.sh`) | Nemotron 3 Embed 1B. With this, no case content and no query leaves the node, and a local run needs no NVIDIA key. |

Switching a role is two lines in `.env`; see `.env.example`. Every `ChatResponse`
records its `endpoint`, so a transcript can always say cloud or on-prem.

## Serving the Nano judge

```
srun --gres=gpu:1 -n1 -p defq --time=00:30:00 --pty bash
GPU=7 bash ~/open-credit-evidence/scripts/cluster/serve_nano.sh
```

Pick a free GPU from `nvidia-smi` (run it through docker with `--gpus all` to see
all eight; SLURM's cgroup hides the others). Port 8001 is taken on the node, so
the judge is on 8002. Reachable from the laptop over the VPN at
`http://10.130.232.20:8002/v1`.

## Serving Lightning

```
ssh codefest
srun --gres=gpu:1 -n1 -p defq --time=08:00:00 --pty bash
source ~/.ngc_key
bash ~/open-credit-evidence/scripts/cluster/serve_lightning.sh
```

The script waits for the health check and prints the `.env` lines. From the login
node or another GPU session, `scripts/cluster/check_endpoint.sh http://rtx-3se-05-36:8000/v1`
makes one chat call. To stop: `docker stop nemotron-lightning` on the node.

## Serving Ultra on Curiosity B300

Ultra (550B) is too large for a single RTX GPU, so by default it runs on NVIDIA
Build. For the one-time teacher/judge labeling pass (~400 readability labels), it
can be served on Curiosity B300 with 4 GPUs (NVFP4 TP4).

### Curiosity B300 directory layout

All Ultra scripts use this layout as the single source of truth:

```
/storage/hackathon_teams/omc-team08/
  open-credit-evidence/     # recommended clone location
  nim-cache-ultra/          # NIM weight cache
  runs/
    ultra-%j.log            # sbatch job output
    ultra.env               # EVIDENCE_JUDGE_* for labeling
```

### Option 1: sbatch (preferred)

Submit a batch job that holds the GPUs under Slurm accounting and cleans up on
cancel:

```bash
# Clone the branch (once)
git clone -b cursor/serve-ultra-b300-da12 --single-branch \
  https://github.com/Algoritmica-ai/open-credit-evidence.git \
  /storage/hackathon_teams/omc-team08/open-credit-evidence

# Edit #SBATCH --partition=<b300-partition> in ultra.sbatch

# Submit from the login node
sbatch /storage/hackathon_teams/omc-team08/open-credit-evidence/scripts/cluster/ultra.sbatch
squeue --me          # check status
scancel <jobid>      # stop when the labeling pass is done
```

The job writes connection info to `/storage/hackathon_teams/omc-team08/runs/ultra.env`:

```bash
source /storage/hackathon_teams/omc-team08/runs/ultra.env
# sets EVIDENCE_JUDGE_BASE_URL and EVIDENCE_JUDGE_MODEL
```

Logs go to `/storage/hackathon_teams/omc-team08/runs/ultra-<jobid>.log`. The job
has a 2-day time limit; ~400 labels should finish well before that. `scancel`
when done to release the GPUs — the trap stops the container automatically.

### Option 2: interactive srun

For debugging or quick tests:

```bash
# On Curiosity B300 — replace <b300-partition> with the real partition name
srun --gres=gpu:4 -n1 -p <b300-partition> --time=04:00:00 --pty bash
source ~/.ngc_key
bash /storage/hackathon_teams/omc-team08/open-credit-evidence/scripts/cluster/serve_ultra.sh
```

The script prints `.env` lines for `EVIDENCE_JUDGE_*`. The container outlives
your srun session; stop it manually: `docker stop team08_nt-ultra` on the B300 node.

### Defaults

| Setting | Value |
|---|---|
| Port | 8001 (Lightning owns 8000) |
| Container | `team08_nt-ultra` |
| Cache | `/storage/hackathon_teams/omc-team08/nim-cache-ultra` |

This is **not** the RTX cluster — different nodes, different storage paths.

After Ultra labels the training set, the fine-tuned Nano+LoRA (`serve_nano.sh`
with `ADAPTER=`) becomes the runtime judge, and Ultra is no longer needed.

## GPU budget (8 GPUs, three people)

| GPU | Use |
|---|---|
| one | Lightning NIM, long-lived |
| one (GPU 7) | Nano judge, vLLM |
| one (GPU 6) | Embedder, vLLM |
| one–two | LoRA training (`nemo:26.08.00`) |
| rest | interactive work |

## One server per team

Two copies of the same model hold two GPUs for nothing. On 16 Sep two of us started
Lightning within three minutes of each other; the second failed on the port and the
health check was answered by the first, which looked like success. Rule: one named
container, one port, written here. Currently: **`team08_nt-lightning` on port 8000**
(started by a teammate). `serve_lightning.sh` now refuses to start if the port is
taken and tells you which container has it.

## Gotchas found so far

- `squeue` only shows our own account; a node that looks idle to us may be full.
- The NIM's `/v1/completions` with a raw prompt leaks `</think>` into the text. We
  use `/v1/chat/completions` with `enable_thinking` set explicitly; confirm on the
  first call.
- `docker` on a GPU node only shows containers on that node, and shows every team member's. `docker ps -a` before starting anything.
- Running `docker` on the login node fails with a socket permission error — that
  is expected, it only exists on GPU nodes.
