#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
#
# The fine-tuned assistant: a second Nemotron 3.5 Lightning NIM, separate from the one the
# servers job runs, with the full-precision LoRA profile. It serves two models:
#
#   nvidia/nemotron-3.5-lightning   the base model in full precision (the fair control)
#   <adapter name>                  the base model with a fine-tuned LoRA adapter
#
# every adapter being a folder in /data/team08/loras/ (adapter_config.json and
# adapter_model.safetensors, as NeMo AutoModel writes them). New adapters are picked up
# without a restart. Run on the GPU node, on a GPU the servers job holds but does not use:
#
#   ssh rtx-3se-06-04 'bash ~/open-credit-evidence/scripts/cluster/serve_lightning_ft.sh [GPU]'
#
# It publishes its address in /data/team08/runs/servers.env as EVIDENCE_CANDIDATE_BASE_URL.
set -euo pipefail

GPU=${1:-1}
NAME=team08-lightning-ft
IMAGE=nvcr.io/nim/nvidia/nemotron-3.5-lightning-30b-a3b:2.0.9-variant
PROFILE=508fb3f74f19aac6956f8441229c7bde06461f5916b81ffe983e93b422b72366  # vllm-bf16-tp1-pp1-feat_lora
LORAS=/data/team08/loras
PROXY=http://10.130.232.8:3128

if [[ "$(hostname)" == *login* ]]; then echo "run this on the GPU node" >&2; exit 1; fi
set +u; source /etc/profile.d/modules.sh 2>/dev/null; module load docker 2>/dev/null; set -u
source ~/.ngc_key 2>/dev/null || true
used=$(nvidia-smi -i "$GPU" --query-gpu=memory.used --format=csv,noheader,nounits | tr -d ' ')
if (( used > 8000 )) && ! docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
  echo "GPU $GPU has ${used} MiB in use; pick another" >&2; exit 1
fi
free_port() { local p=$1; while ss -tln | grep -q ":${p} "; do p=$((p+1)); done; echo "$p"; }
PW=/data/team08/runs/passwd.$(id -u); (cat /etc/passwd; getent passwd "$(id -u)") > "$PW"
mkdir -p "$LORAS"

if ! docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
  PORT=$(free_port 8210)
  # the NIM runs vLLM behind its own server on a second port, 8001 by default, which the
  # assistant's NIM already holds on this node (host networking): give it one of its own
  BACKEND=$(free_port $((PORT + 1)))
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  docker run -d --name "$NAME" --gpus "\"device=$GPU\"" --shm-size=16GB --network host \
    -u "$(id -u)" -e HOME=/tmp -v "$PW:/etc/passwd:ro" \
    -e NGC_API_KEY -e NIM_MODEL_PROFILE="$PROFILE" \
    -e NIM_SERVED_MODEL_NAME=nvidia/nemotron-3.5-lightning \
    -e NIM_SERVER_PORT="$PORT" -e NIM_BACKEND_PORT="$BACKEND" \
    -e NIM_PEFT_SOURCE=/opt/nim/loras -e NIM_PEFT_REFRESH_INTERVAL=60 \
    -e NIM_MAX_LORA_RANK=64 -e NIM_MAX_GPU_LORAS=4 \
    -e HTTP_PROXY="$PROXY" -e HTTPS_PROXY="$PROXY" -e http_proxy="$PROXY" -e https_proxy="$PROXY" \
    -e NO_PROXY=localhost,127.0.0.1 -e no_proxy=localhost,127.0.0.1 \
    -v /data/team08/nim-cache:/opt/nim/.cache -v "$LORAS:/opt/nim/loras:ro" \
    "$IMAGE" >/dev/null
else
  PORT=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$NAME" \
         | sed -n 's/^NIM_SERVER_PORT=//p')
fi

echo -n "waiting for $NAME on port $PORT"
for _ in $(seq 1 120); do
  if [[ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" != "true" ]]; then
    echo; docker logs --tail 30 "$NAME" >&2; exit 1
  fi
  if curl -s --noproxy '*' --max-time 3 "http://127.0.0.1:$PORT/v1/health/ready" | grep -q '"ready"'
  then echo " ready"; break; fi
  echo -n "."; sleep 10
done
echo "models served:"
curl -s --noproxy '*' "http://127.0.0.1:$PORT/v1/models" | python3 -c \
  'import json,sys; [print("  " + m["id"]) for m in json.load(sys.stdin)["data"]]'
ENV=/data/team08/runs/servers.env
touch "$ENV"
sed -i '/^EVIDENCE_CANDIDATE_BASE_URL=/d' "$ENV"
echo "EVIDENCE_CANDIDATE_BASE_URL=http://$(hostname -i | awk '{print $1}'):$PORT/v1" >> "$ENV"
grep '^EVIDENCE_CANDIDATE' "$ENV"
