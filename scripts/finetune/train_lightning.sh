#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
#
# LoRA fine-tune of Nemotron 3.5 Lightning with NVIDIA NeMo AutoModel, on GPUs the team's
# servers job already holds. Run on the GPU node (rtx-3se-06-04), from the login node:
#
#   ssh rtx-3se-06-04 'bash ~/open-credit-evidence/scripts/finetune/train_lightning.sh \
#       /data/team08/training/<name> [GPUS] [extra lightning_lora.py options]'
#
#   GPUS  defaults to 1,2: free of the assistant, the judges and the embedder.
#
# The training folder is what `evidence distill` wrote (copy it to /data/team08/training).
# Everything lands in /data/team08/runs/ft/<name>-<time>/: the config, the log, and the
# LoRA adapter (checkpoints/…/model/adapter_model.safetensors). The container runs
# detached: the training keeps going when you log out. Follow it with
#   tail -f /data/team08/runs/ft/<name>-<time>/train.log
set -euo pipefail

DATA=${1:?the training folder, e.g. /data/team08/training/lightning-sft-v1}
GPUS=${2:-1,2}
shift $(( $# < 2 ? $# : 2 ))
IMAGE=nvcr.io/nvidia/nemo-automodel:26.08.00
REPO=/data/team08/nim-cache/ngc/hub/models--nim--nvidia--nemotron-3.5-lightning
SNAPSHOT=hf-b3caaab  # the full-precision (bf16) weights
NAME=$(basename "$DATA")
OUT=/data/team08/runs/ft/${NAME}-$(date -u +%Y-%m-%dT%H%M%SZ)
N=$(tr ',' '\n' <<<"$GPUS" | wc -l)

if [[ "$(hostname)" == *login* ]]; then echo "run this on the GPU node" >&2; exit 1; fi
[[ -s "$DATA/sft/train.jsonl" ]] || { echo "$DATA/sft/train.jsonl not found" >&2; exit 1; }
set +u; source /etc/profile.d/modules.sh 2>/dev/null; module load docker 2>/dev/null; set -u
for g in ${GPUS//,/ }; do
  used=$(nvidia-smi -i "$g" --query-gpu=memory.used --format=csv,noheader,nounits | tr -d ' ')
  if (( used > 8000 )); then echo "GPU $g has ${used} MiB in use; pick others" >&2; exit 1; fi
done
if docker ps --format '{{.Names}}' | grep -qx team08-ft; then
  echo "a fine-tune is already running (team08-ft)" >&2; exit 1
fi

mkdir -p "$OUT"
# the container resolves our user ID from this file (NGC images do not know it)
PW=/data/team08/runs/passwd.$(id -u); (cat /etc/passwd; getent passwd "$(id -u)") > "$PW"
docker rm -f team08-ft >/dev/null 2>&1 || true
docker run -d --name team08-ft --gpus "\"device=$GPUS\"" --ipc host --shm-size 32g \
  -u "$(id -u)" -e HOME=/tmp -e HF_HUB_OFFLINE=1 -e TOKENIZERS_PARALLELISM=false \
  -v "$PW:/etc/passwd:ro" -v "$REPO:/repo:ro" -v "$DATA:/data:ro" -v "$OUT:/out" \
  -v "$(dirname "$0"):/scripts:ro" \
  "$IMAGE" bash -c "
    set -e
    python /scripts/lightning_lora.py --model /repo/snapshots/$SNAPSHOT --data /data \
      --out /out --gpus $N $* > /out/config.yaml
    cd /opt/Automodel
    torchrun --nproc-per-node $N examples/llm_finetune/finetune.py -c /out/config.yaml
  " > /dev/null
( docker logs -f team08-ft > "$OUT/train.log" 2>&1 & )
echo "training on GPU(s) $GPUS: $OUT"
echo "  tail -f $OUT/train.log"
