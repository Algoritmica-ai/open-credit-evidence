#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
#
# Serve Nemotron 3 Embed 1B on the team's Codefest node with vLLM, so that the
# judge's retrieval (and corpus builds) need no cloud call. With this, the
# assistant, the judge and the embedder all run on the node and a local run
# needs no NVIDIA API key.
#
#   srun --gres=gpu:1 -n1 -p defq --time=00:30:00 --pty bash
#   GPU=6 bash ~/open-credit-evidence/scripts/cluster/serve_embed.sh
set -euo pipefail

NAME=${NAME:-team08_embed}
IMAGE=${IMAGE:-vllm/vllm-openai:nightly}
MODEL_DIR=${MODEL_DIR:-/data/team08/models/nemotron-3-embed-1b}
SERVED=${SERVED:-nemotron-3-embed-1b}
PORT=${EMBED_PORT:-8003}
GPU=${GPU:?set GPU=<index of a free GPU>}

if [[ "$(hostname)" == *login* ]]; then
  echo "This is the login node. Start an srun session first." >&2; exit 1
fi
module load docker 2>/dev/null || true

if docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
  echo "$NAME is already running:"; docker ps --filter "name=$NAME" --format '  {{.Image}}  {{.Status}}'
else
  if ss -tln | grep -q ":${PORT} "; then
    echo "port $PORT is already in use on $(hostname); choose another with EMBED_PORT=" >&2; exit 1
  fi
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  echo "starting $NAME on GPU $GPU, port $PORT, model $MODEL_DIR"
  docker run -d --name "$NAME" --gpus "\"device=${GPU}\"" --shm-size=4GB --network host \
    -e HF_HUB_OFFLINE=1 -v "$MODEL_DIR:/models/embed:ro" "$IMAGE" \
    --model /models/embed --served-model-name "$SERVED" --runner pooling --port "$PORT" \
    --dtype bfloat16 --max-model-len 8192 --gpu-memory-utilization 0.25 >/dev/null
fi

echo -n "waiting for the model to load"
for _ in $(seq 1 60); do
  if [[ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" != "true" ]]; then
    echo " $NAME has stopped. Last lines of its log:" >&2; docker logs --tail 20 "$NAME" >&2; exit 1
  fi
  if curl -s --noproxy '*' --max-time 3 "http://127.0.0.1:${PORT}/v1/models" | grep -q "$SERVED"; then
    echo " ready"; break
  fi
  echo -n "."; sleep 10
done
curl -s --noproxy '*' "http://127.0.0.1:${PORT}/v1/embeddings" -H 'Content-Type: application/json' \
  -d "{\"model\":\"$SERVED\",\"input\":[\"query: human oversight\"]}" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print("  embedding dims:", len(d["data"][0]["embedding"]))'
echo
echo "put these two lines in .env on the machine running the evaluation:"
echo "  EVIDENCE_EMBED_BASE_URL=http://$(hostname):${PORT}/v1"
echo "  EVIDENCE_EMBED_MODEL=${SERVED}"
