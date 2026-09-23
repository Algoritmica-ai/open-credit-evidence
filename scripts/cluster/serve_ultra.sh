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
# login node. Example (Curiosity B300 partition is 'hackathon'):
#
#   srun --gres=gpu:4 -n1 -p hackathon --time=04:00:00 --pty bash
#   source ~/.ngc_key
#   bash ~/open-credit-evidence/scripts/cluster/serve_ultra.sh
#
# Directory layout on Curiosity B300:
#   $HOME/open-credit-evidence/           # repo clone (can live anywhere)
#   $HOME/nim-cache-ultra/                # NIM weight cache (default, avoids ACL issues)
#   /storage/hackathon_teams/omc-team08/  # TEAM_ROOT (runs/logs only)
#     runs/                               # sbatch logs and ultra.env
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
# Default cache under $HOME avoids team-storage ACL + GID 0 conflicts
CACHE=${LOCAL_NIM_CACHE:-$HOME/nim-cache-ultra}
# Curiosity B300 has direct NGC egress; do not default to RTX proxy (times out)
PROXY="${HTTPS_PROXY:-}"

# Port selection: use NIM_PORT if set, otherwise scan for a free port starting at 8001
find_free_port() {
  local start=${1:-8001}
  local end=${2:-8100}
  for port in $(seq "$start" "$end"); do
    if ! ss -tln 2>/dev/null | grep -q ":${port} "; then
      echo "$port"
      return 0
    fi
  done
  return 1
}

if [[ -n "${NIM_PORT:-}" ]]; then
  PORT="$NIM_PORT"
  echo "using NIM_PORT=$PORT (from environment)"
else
  PORT=$(find_free_port 8001 8100) || {
    echo "no free port found in range 8001-8100" >&2
    exit 1
  }
  echo "selected free port $PORT"
fi

# B300 4-GPU NVFP4 throughput profile (vllm-nvidia-b300-sxm6-ac-nvfp4-tp4-pp1-throughput-90.0)
# Auto profile match fails on Curiosity; default to the known working profile id.
MODEL_PROFILE=${NIM_MODEL_PROFILE:-5b3441c9d0f55e8b4442537a4294304d5401d3a5542870bda16f3f8e18971878}

if [[ "$(hostname)" == *login* ]]; then
  echo "This is the login node. Start an srun session first (see header)." >&2
  exit 1
fi
if [[ -z "${NGC_API_KEY:-}" ]]; then
  echo "NGC_API_KEY is not set. export it (from ~/.ngc_key, not your history)." >&2
  exit 1
fi
: "${CUDA_VISIBLE_DEVICES:?not inside an srun allocation — no GPU assigned}"

# Curiosity B300: rootless-docker; RTX fallback: docker
# Only load if docker daemon not already running (reloading rootless-docker kills the daemon)
if ! docker info >/dev/null 2>&1; then
  if ! module load rootless-docker/1.75 2>/dev/null; then
    module load docker 2>/dev/null || true
  fi
fi
if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "docker daemon not available. Tried: module load rootless-docker/1.75, then module load docker" >&2
  echo "Run: module avail 2>&1 | grep -i docker" >&2
  exit 1
fi

mkdir -p "$CACHE"
chmod -R u+rwX,g+rwX "$CACHE" 2>/dev/null || true

# Write selected port to cache dir for ultra.sbatch to read
echo "$PORT" > "$CACHE/.nim_port"

if docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
  echo "$NAME is already running:"
  docker ps --filter "name=$NAME" --format '  {{.Image}}  {{.Status}}'
else
  # Final check: port may have been taken since find_free_port (race)
  if ss -tln 2>/dev/null | grep -q ":${PORT} "; then
    echo "port $PORT became unavailable (race). Re-run to try another port." >&2
    exit 1
  fi
  docker rm -f "$NAME" >/dev/null 2>&1 || true

  PROFILE_ENV=()
  if [[ -n "$MODEL_PROFILE" ]]; then
    PROFILE_ENV=(-e NIM_MODEL_PROFILE="$MODEL_PROFILE")
    echo "using NIM_MODEL_PROFILE=$MODEL_PROFILE"
  fi

  PROXY_ENV=()
  if [[ -n "$PROXY" ]]; then
    PROXY_ENV=(
      -e HTTP_PROXY="$PROXY" -e HTTPS_PROXY="$PROXY"
      -e http_proxy="$PROXY" -e https_proxy="$PROXY"
      -e NO_PROXY="${NO_PROXY:-localhost,127.0.0.1}" -e no_proxy="${no_proxy:-localhost,127.0.0.1}"
    )
    echo "using proxy $PROXY"
  fi

  echo "starting $NAME on GPU(s) $CUDA_VISIBLE_DEVICES, cache $CACHE, port $PORT"
  # Use --gpus all; Slurm sets CUDA_VISIBLE_DEVICES. The quoted device form fails under rootless Docker.
  docker run -d \
    --name "$NAME" \
    --gpus all \
    --shm-size=16GB \
    --network host \
    -e NGC_API_KEY \
    -e NIM_SERVED_MODEL_NAME=nvidia/nemotron-3-ultra-550b-a55b \
    -e NIM_SERVER_PORT="$PORT" -e NIM_HEALTH_PORT="$PORT" \
    "${PROXY_ENV[@]}" \
    "${PROFILE_ENV[@]}" \
    -u "$(id -u):0" --group-add "$(id -g)" \
    -v "$CACHE:/opt/nim/.cache" \
    "$IMAGE" >/dev/null
fi

# First-time Ultra NVFP4 cold cache can take well over 50 minutes; default ~3h wait
HEALTH_WAIT_TRIES=${HEALTH_WAIT_TRIES:-1080}
HEALTH_READY=false

echo -n "waiting for health (up to $((HEALTH_WAIT_TRIES * 10 / 60)) min)"
for _ in $(seq 1 "$HEALTH_WAIT_TRIES"); do
  if [[ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" != "true" ]]; then
    echo " $NAME has stopped. Last lines of its log:" >&2
    docker logs --tail 15 "$NAME" >&2
    exit 1
  fi
  if curl -s --noproxy '*' --max-time 3 "http://127.0.0.1:${PORT}/v1/health/ready" | grep -q '"ready"'; then
    echo " ready"
    HEALTH_READY=true
    break
  fi
  echo -n "."
  sleep 10
done

if [[ "$HEALTH_READY" != "true" ]]; then
  echo
  echo "timed out waiting for /v1/health/ready after $HEALTH_WAIT_TRIES tries (~$((HEALTH_WAIT_TRIES * 10 / 3600))h)" >&2
  echo "check progress: docker logs -f $NAME" >&2
  exit 1
fi

echo
echo "models served:"
curl -s --noproxy '*' "http://127.0.0.1:${PORT}/v1/models" | python3 -c 'import json,sys; [print("  " + m["id"]) for m in json.load(sys.stdin)["data"]]' \
  || echo "  (could not list models)"

echo
echo "Ultra is the one-time teacher for ~400 readability labels."
echo "put these two lines in .env on the machine running the labeling pass:"
echo "  EVIDENCE_JUDGE_BASE_URL=http://$(hostname):${PORT}/v1"
echo "  EVIDENCE_JUDGE_MODEL=nvidia/nemotron-3-ultra-550b-a55b"
