#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
#
# Serve Nemotron Nano 9B v2 with vLLM, for the fine-tuned judge: with
# ADAPTER=/data/team08/runs/<run>/adapter it serves the LoRA adapter on top of
# the base weights. The judge in the servers job is the Nano NIM
# (nvcr.io/nim/nvidia/nvidia-nemotron-nano-9b-v2); this script is for adapter
# experiments until the fine-tuned judge is served the same way.
#
# Run inside an srun session on the GPU node:
#   srun --gres=gpu:1 -n1 -p defq --time=00:30:00 --pty bash
#   GPU=7 bash ~/open-credit-evidence/scripts/cluster/serve_nano.sh
#
# The container is docker, outside SLURM, so it keeps running after the
# session ends and holds its GPU until `docker stop`. GPU is chosen explicitly
# because the Lightning NIM already holds GPU 0 whatever SLURM allocates.
set -euo pipefail

NAME=${NAME:-team08_nano-judge}
# pinned by digest: the vLLM build the judge ran on before the NIM (never "nightly")
IMAGE=${IMAGE:-vllm/vllm-openai@sha256:1e1f56a164a3dfdf87a57168983602421a295b0b3570d27c5b49c54b97b341b4}
MODEL_DIR=${MODEL_DIR:-/data/team08/models/nemotron-nano-9b-v2}
SERVED=${SERVED:-nano-judge}
PORT=${NANO_PORT:-8002}
GPU=${GPU:?set GPU=<index of a free GPU; nvidia-smi shows usage>}
ADAPTER=${ADAPTER:-}

if [[ "$(hostname)" == *login* ]]; then
  echo "This is the login node. Start an srun session first." >&2; exit 1
fi
module load docker 2>/dev/null || true

if docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
  echo "$NAME is already running:"; docker ps --filter "name=$NAME" --format '  {{.Image}}  {{.Status}}'
else
  if ss -tln | grep -q ":${PORT} "; then
    echo "port $PORT is already in use on $(hostname); choose another with NANO_PORT=" >&2; exit 1
  fi
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  ARGS=(--model /models/nano --served-model-name "$SERVED" --trust-remote-code --port "$PORT"
        --dtype bfloat16 --max-model-len 16384 --gpu-memory-utilization 0.60
        --mamba_ssm_cache_dtype float32)
  MOUNTS=(-v "$MODEL_DIR:/models/nano:ro")
  if [[ -n "$ADAPTER" ]]; then
    MOUNTS+=(-v "$ADAPTER:/models/adapter:ro")
    ARGS+=(--enable-lora --lora-modules "$SERVED-lora=/models/adapter")
  fi
  echo "starting $NAME on GPU $GPU, port $PORT, model $MODEL_DIR"
  docker run -d --name "$NAME" --gpus "\"device=${GPU}\"" --shm-size=16GB --network host \
    -e HF_HUB_OFFLINE=1 "${MOUNTS[@]}" "$IMAGE" "${ARGS[@]}" >/dev/null
fi

echo -n "waiting for the model to load"
for _ in $(seq 1 90); do
  if [[ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" != "true" ]]; then
    echo " $NAME has stopped. Last lines of its log:" >&2; docker logs --tail 20 "$NAME" >&2; exit 1
  fi
  if curl -s --noproxy '*' --max-time 3 "http://127.0.0.1:${PORT}/v1/models" | grep -q "$SERVED"; then
    echo " ready"; break
  fi
  echo -n "."; sleep 10
done
curl -s --noproxy '*' "http://127.0.0.1:${PORT}/v1/models" | python3 -c 'import json,sys; [print("  " + m["id"]) for m in json.load(sys.stdin)["data"]]'
echo
echo "put these two lines in .env on the machine running the evaluation:"
echo "  EVIDENCE_JUDGE_BASE_URL=http://$(hostname):${PORT}/v1"
echo "  EVIDENCE_JUDGE_MODEL=${SERVED}"
