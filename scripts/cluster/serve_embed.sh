#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
#
# Serve Nemotron 3 Embed 1B on the team's Codefest node as an NVIDIA NIM, so that
# the judge's retrieval (and corpus builds) need no cloud call. The servers job
# (servers.sbatch) runs the same container; this script is for starting it alone
# while debugging.
#
#   srun --gres=gpu:1 -n1 -p defq --time=00:30:00 --pty bash
#   GPU=6 bash ~/open-credit-evidence/scripts/cluster/serve_embed.sh
#
# The NIM downloads its model from NGC on first start into MODEL_DIR (mounted at
# /model, its NIM_ENGINE_MODEL_PATH); NGC_API_KEY comes from ~/.ngc_key.
set -euo pipefail

NAME=${NAME:-team08_embed}
IMAGE=${IMAGE:-nvcr.io/nim/nvidia/nemotron-3-embed-1b:2.2.2}
MODEL_DIR=${MODEL_DIR:-/data/team08/nim-cache/nemotron-3-embed-1b}
SERVED=nvidia/nemotron-3-embed-1b
PORT=${EMBED_PORT:-8003}
GPU=${GPU:?set GPU=<index of a free GPU>}
PROXY=http://10.130.232.8:3128

if [[ "$(hostname)" == *login* ]]; then
  echo "This is the login node. Start an srun session first." >&2; exit 1
fi
module load docker 2>/dev/null || true
source ~/.ngc_key 2>/dev/null || true
: "${NGC_API_KEY:?NGC_API_KEY is not set; put it in ~/.ngc_key}"

if docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
  echo "$NAME is already running:"; docker ps --filter "name=$NAME" --format '  {{.Image}}  {{.Status}}'
else
  if ss -tln | grep -q ":${PORT} "; then
    echo "port $PORT is already in use on $(hostname); choose another with EMBED_PORT=" >&2; exit 1
  fi
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  mkdir -p "$MODEL_DIR"
  echo "starting $NAME on GPU $GPU, port $PORT"
  docker run -d --name "$NAME" --gpus "\"device=${GPU}\"" --shm-size=4GB -u "$(id -u)" \
    -p "${PORT}:8000" -e NGC_API_KEY \
    -e HTTP_PROXY="$PROXY" -e HTTPS_PROXY="$PROXY" -e http_proxy="$PROXY" -e https_proxy="$PROXY" \
    -e NO_PROXY="localhost,127.0.0.1" -e no_proxy="localhost,127.0.0.1" \
    -v "$MODEL_DIR:/model" "$IMAGE" >/dev/null
fi

echo -n "waiting for the model to load"
for _ in $(seq 1 90); do
  if [[ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" != "true" ]]; then
    echo " $NAME has stopped. Last lines of its log:" >&2; docker logs --tail 20 "$NAME" >&2; exit 1
  fi
  if [[ "$(curl -s --noproxy '*' --max-time 3 -o /dev/null -w '%{http_code}' \
           "http://127.0.0.1:${PORT}/v1/health/ready")" == 200 ]]; then
    echo " ready"; break
  fi
  echo -n "."; sleep 10
done
echo
echo "put these two lines in .env on the machine running the evaluation:"
echo "  EVIDENCE_EMBED_BASE_URL=http://$(hostname):${PORT}/v1"
echo "  EVIDENCE_EMBED_MODEL=${SERVED}"
