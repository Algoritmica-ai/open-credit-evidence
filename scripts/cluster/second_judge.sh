#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
#
# On the GPU node, inside the team's job: start a second judge NIM (Nemotron 3 Super,
# the same pinned image, profile and settings as servers.sbatch) on two free GPUs, wait
# until it answers, then list it in the relay's upstreams file. The relay reads that
# file whenever it changes and sends the judge panel's requests to both judges in turn,
# so the panel reviews about twice as many memos at once.
#
#   second_judge.sh [gpus] [port]        # default: 5,7 and 8205
#   second_judge.sh --stop               # stop it and take it out of the relay
#
# The GPUs must be part of the job's allocation and hold nothing (under 4 GB in use).
set -euo pipefail
UPSTREAMS=${RELAY_UPSTREAMS_FILE:-$HOME/.config/stream-relay/upstreams}
NAME=team08-judge2
module load docker >/dev/null 2>&1 || true

if [[ ${1:-} == --stop ]]; then
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  : > "$UPSTREAMS"
  echo "second judge stopped; the relay uses the first judge only"
  exit 0
fi

GPUS=${1:-5,7} PORT=${2:-8205}
JUDGE_IMAGE=nvcr.io/nim/nvidia/nemotron-3-super-120b-a12b@sha256:d56c72bdbb532008dc97c16d291f638e1b47fdb4d6a1daf02568ff9b2e1b66fc
JUDGE_PROFILE=1e705d1cf3866d22b04077194c735b651f0bfec8e7ae4cf8d8f551f803c064f6
PROXY=http://10.130.232.8:3128
source ~/.ngc_key 2>/dev/null || true

for g in ${GPUS//,/ }; do
  used=$(nvidia-smi -i "$g" --query-gpu=memory.used --format=csv,noheader,nounits | tr -d ' ')
  if [[ "$used" -gt 4000 ]]; then echo "GPU $g has ${used} MiB in use; refusing to start on it" >&2; exit 1; fi
done
if ss -tln | grep -q ":${PORT} "; then echo "port $PORT is taken" >&2; exit 1; fi

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" --gpus "\"device=$GPUS\"" --shm-size=16GB \
  -u "$(id -u)" -p "$PORT:8000" -e NGC_API_KEY \
  -e HTTP_PROXY="$PROXY" -e HTTPS_PROXY="$PROXY" -e http_proxy="$PROXY" -e https_proxy="$PROXY" \
  -e NO_PROXY="localhost,127.0.0.1" -e no_proxy="localhost,127.0.0.1" \
  -e NIM_MODEL_PROFILE="$JUDGE_PROFILE" -e NIM_SERVED_MODEL_NAME=nemotron-3-super \
  -e NIM_MAX_MODEL_LEN=65536 -e NIM_ENABLE_AUTO_TOOL_CHOICE=1 \
  -v /data/team08/nim-cache:/opt/nim/.cache "$JUDGE_IMAGE" >/dev/null
echo "$(date +%H:%M:%S) $NAME starting on GPUs $GPUS, port $PORT"

for i in $(seq 1 120); do  # the weights are in the shared NIM cache: minutes, not an hour
  if curl -s --noproxy '*' --max-time 3 "http://127.0.0.1:$PORT/v1/models" | grep -q nemotron-3-super; then
    mkdir -p "$(dirname "$UPSTREAMS")"
    echo "http://127.0.0.1:$PORT" > "$UPSTREAMS"
    echo "$(date +%H:%M:%S) $NAME ready; listed in $UPSTREAMS for the relay"
    exit 0
  fi
  if ! docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
    echo "$NAME stopped while starting:" >&2; docker logs --tail 20 "$NAME" >&2; exit 1
  fi
  sleep 10
done
echo "$NAME did not answer within 20 minutes" >&2
exit 1
