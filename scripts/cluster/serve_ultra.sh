#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
#
# Serve Nemotron 3 Ultra 550B as a NIM on Curiosity B300 for the one-time
# teacher/judge labeling pass (~400 readability labels). After that pass, the
# fine-tuned Nano+LoRA becomes the runtime judge; Ultra is not needed for
# normal evaluation runs.
#
# This script targets Curiosity B300 with 4 GPUs (NVFP4 TP4). It does NOT run
# on the RTX cluster that serve_lightning.sh uses.
#
# Run this INSIDE an srun session on a Curiosity B300 GPU node, never on a
# login node. Example (replace <b300-partition> with the real partition name):
#
#   srun --gres=gpu:4 -n1 -p <b300-partition> --time=04:00:00 --pty bash
#   source ~/.ngc_key
#   bash ~/open-credit-evidence/scripts/cluster/serve_ultra.sh
#
# What it does:
#   - uses the GPUs SLURM gave you ($CUDA_VISIBLE_DEVICES), not "--gpus 4",
#     which silently takes GPU 0-3 whether or not they are yours;
#   - keeps the weight cache on team storage so the ~300+ GB download happens
#     once for the whole team;
#   - passes the cluster's HTTP proxy into the container so it can reach NGC,
#     and talks to the container on localhost with the proxy bypassed;
#   - waits for the health check and prints the two lines to put in .env.
#
# The container keeps running after you leave the srun session (docker is
# node-level, outside SLURM), so the GPUs stay busy until you `docker stop` it.
set -euo pipefail

NAME=${NAME:-team08_nt-ultra}
IMAGE=${IMAGE:-nvcr.io/nim/nvidia/nemotron-3-ultra-550b-a55b:2.0.12}
PORT=${NIM_PORT:-8001}
CACHE=${LOCAL_NIM_CACHE:-/storage/hackathon_teams/omc-team08/nim-cache-ultra}
PROXY=${HTTPS_PROXY:-http://10.130.232.8:3128}

# NIM_MODEL_PROFILE may be required for B300 NVFP4 TP4 deployment. If the NIM
# logs show a profile selection error, set this to the profile id from NVIDIA's
# NIM documentation for Ultra on B300.
# Example: NIM_MODEL_PROFILE=nvfp4-tp4-b300 bash serve_ultra.sh
MODEL_PROFILE=${NIM_MODEL_PROFILE:-}

if [[ "$(hostname)" == *login* ]]; then
  echo "This is the login node. Start an srun session first (see header)." >&2
  exit 1
fi
if [[ -z "${NGC_API_KEY:-}" ]]; then
  echo "NGC_API_KEY is not set. export it (from ~/.ngc_key, not your history)." >&2
  exit 1
fi
: "${CUDA_VISIBLE_DEVICES:?not inside an srun allocation — no GPU assigned}"

module load docker 2>/dev/null || true
mkdir -p "$CACHE"
chmod g+rwx "$CACHE" 2>/dev/null || true

if docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
  echo "$NAME is already running:"
  docker ps --filter "name=$NAME" --format '  {{.Image}}  {{.Status}}'
else
  if ss -tln 2>/dev/null | grep -q ":${PORT} "; then
    echo "port $PORT is already in use on $(hostname):" >&2
    docker ps --format '  {{.Names}}  {{.Image}}  {{.Status}}' 2>/dev/null >&2 || true
    echo "either use that server, or start ours on another port: NIM_PORT=8002 $0" >&2
    exit 1
  fi
  docker rm -f "$NAME" >/dev/null 2>&1 || true

  PROFILE_ENV=()
  if [[ -n "$MODEL_PROFILE" ]]; then
    PROFILE_ENV=(-e NIM_MODEL_PROFILE="$MODEL_PROFILE")
    echo "using NIM_MODEL_PROFILE=$MODEL_PROFILE"
  fi

  echo "starting $NAME on GPU(s) $CUDA_VISIBLE_DEVICES, cache $CACHE, port $PORT"
  docker run -d \
    --name "$NAME" \
    --gpus "\"device=${CUDA_VISIBLE_DEVICES}\"" \
    --shm-size=16GB \
    --network host \
    -e NGC_API_KEY \
    -e NIM_SERVED_MODEL_NAME=nvidia/nemotron-3-ultra-550b-a55b \
    -e NIM_SERVER_PORT="$PORT" -e NIM_HEALTH_PORT="$PORT" \
    -e HTTP_PROXY="$PROXY" -e HTTPS_PROXY="$PROXY" \
    -e http_proxy="$PROXY" -e https_proxy="$PROXY" \
    -e NO_PROXY="${NO_PROXY:-localhost,127.0.0.1}" -e no_proxy="${no_proxy:-localhost,127.0.0.1}" \
    "${PROFILE_ENV[@]}" \
    -u "$(id -u)" \
    -v "$CACHE:/opt/nim/.cache" \
    "$IMAGE" >/dev/null
fi

echo -n "waiting for health"
for _ in $(seq 1 300); do
  if [[ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" != "true" ]]; then
    echo " $NAME has stopped. Last lines of its log:" >&2
    docker logs --tail 15 "$NAME" >&2
    exit 1
  fi
  if curl -s --noproxy '*' --max-time 3 "http://127.0.0.1:${PORT}/v1/health/ready" | grep -q '"ready"'; then
    echo " ready"
    break
  fi
  echo -n "."
  sleep 10
done

echo
echo "models served:"
curl -s --noproxy '*' "http://127.0.0.1:${PORT}/v1/models" | python3 -c 'import json,sys; [print("  " + m["id"]) for m in json.load(sys.stdin)["data"]]' \
  || { echo "  (not ready yet — docker logs -f $NAME)"; exit 1; }

echo
echo "Ultra is the one-time teacher for ~400 readability labels."
echo "put these two lines in .env on the machine running the labeling pass:"
echo "  EVIDENCE_JUDGE_BASE_URL=http://$(hostname):${PORT}/v1"
echo "  EVIDENCE_JUDGE_MODEL=nvidia/nemotron-3-ultra-550b-a55b"
