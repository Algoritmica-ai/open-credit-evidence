#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
#
# The model servers as ONE SLURM job, so the GPUs they hold are accounted
# to the team: the assistant (Lightning), the judge and a second judge (Super, for
# the judge panel), the embedder, and the fine-tuned assistant (a second Lightning
# NIM, full precision with LoRA, serving the adapters in /data/team08/loras). Docker containers started by hand sit outside SLURM: sacct shows
# nothing for them and the cluster sees the team as idle. This job holds its
# GPUs for its whole lifetime and stops the containers when it ends.
#
#   sbatch ~/open-credit-evidence/scripts/cluster/servers.sbatch
#   squeue --me            # the job stays RUNNING while the servers are up
#   scancel <jobid>        # stops them all
#
# The partition allows 7 days. To keep the servers up longer, queue the next job to
# start when this one ends:  sbatch --dependency=afterany:<jobid> servers.sbatch
# CANDIDATE_MODEL (default lightning-credit-fig-v2) is the adapter the engine uses as
# the fine-tuned assistant: sbatch --export=ALL,CANDIDATE_MODEL=<name> servers.sbatch
#
# It also runs stream_relay.py, a small Python process in front of the judge for
# NemoClaw agents (the judge NIM refuses streamed tool calls; OpenClaw streams
# every request). The evidence engine calls the judge directly and never uses it.
#
#SBATCH --job-name=team08-evidence-servers
#SBATCH --partition=defq
#SBATCH --gres=gpu:8
#SBATCH --exclusive
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --time=7-00:00:00
#SBATCH --output=/data/team08/runs/servers-%j.log
set -uo pipefail
module load docker

# Ports: the node is shared and other teams' servers may hold any port, so
# take the first three free ones from 8100 upward and publish them in
# /data/team08/runs/servers.env for the laptop's .env.
free_port() { local p=$1; while ss -tln | grep -q ":${p} "; do p=$((p+1)); done; echo "$p"; }
LIGHTNING_PORT=$(free_port 8200); JUDGE_PORT=$(free_port $((LIGHTNING_PORT+1))); EMBED_PORT=$(free_port $((JUDGE_PORT+1)))
RELAY_PORT=$(free_port $((EMBED_PORT+1)))
JUDGE2_PORT=$(free_port 8205); FT_PORT=$(free_port 8210); FT_BACKEND=$(free_port $((FT_PORT+1)))
CANDIDATE_MODEL=${CANDIDATE_MODEL:-lightning-credit-fig-v2}
FT_PROFILE=508fb3f74f19aac6956f8441229c7bde06461f5916b81ffe983e93b422b72366  # vllm-bf16-tp1-pp1-feat_lora
UPSTREAMS=$HOME/.config/stream-relay/upstreams  # the relay's second judge
RELAY="$HOME/open-credit-evidence/scripts/cluster/stream_relay.py"
# All three roles are NVIDIA NIMs, pinned to fixed releases (never a moving tag).
NIM_IMAGE=nvcr.io/nim/nvidia/nemotron-3.5-lightning-30b-a3b:2.0.9-variant
# The judge (and every agent of the judge panel): Nemotron 3 Super 120B-A12B. Its NIM
# publishes a moving tag only, so it is pinned by digest; FP8 across two GPUs
# (profile vllm-fp8-tp2-pp1).
JUDGE_IMAGE=nvcr.io/nim/nvidia/nemotron-3-super-120b-a12b@sha256:d56c72bdbb532008dc97c16d291f638e1b47fdb4d6a1daf02568ff9b2e1b66fc
JUDGE_PROFILE=1e705d1cf3866d22b04077194c735b651f0bfec8e7ae4cf8d8f551f803c064f6
EMBED_IMAGE=nvcr.io/nim/nvidia/nemotron-3-embed-1b:2.2.2
PROXY=http://10.130.232.8:3128
source ~/.ngc_key 2>/dev/null || true

# A whole node is the team's allocation and the only thing SLURM can actually
# guarantee: containers started by hand on a "free" node hold GPUs SLURM knows
# nothing about. Use the seven GPUs with the least memory in use: one each for the
# assistant, the embedder and the fine-tuned assistant, two for each judge.
mapfile -t FREE < <(docker run --rm --gpus all --entrypoint nvidia-smi "$JUDGE_IMAGE" \
  --query-gpu=index,memory.used --format=csv,noheader,nounits \
  | tr -d ' ' | awk -F, -v ids="$CUDA_VISIBLE_DEVICES" 'BEGIN{split(ids,a,","); for(i in a) ok[a[i]]=1} ok[$1]{print $2","$1}' \
  | sort -n | head -7 | cut -d, -f2)
echo "allocation $CUDA_VISIBLE_DEVICES -> using GPUs ${FREE[*]}; ports $LIGHTNING_PORT $JUDGE_PORT $EMBED_PORT"
for g in "${FREE[@]}"; do
  used=$(docker run --rm --gpus "\"device=$g\"" --entrypoint nvidia-smi "$JUDGE_IMAGE" --query-gpu=memory.used --format=csv,noheader,nounits | tr -d ' ')
  if [[ "$used" -gt 4000 ]]; then echo "GPU $g has ${used} MiB in use by a process outside SLURM; refusing to start on it" >&2; exit 1; fi
done

RELAY_PID=
cleanup() {
  [[ -n "$RELAY_PID" ]] && kill "$RELAY_PID" 2>/dev/null
  docker stop team08-lightning team08-judge team08-embed team08-judge2 team08-lightning-ft \
    >/dev/null 2>&1; : > "$UPSTREAMS"; echo "servers stopped"
}
start_relay() {
  python3 "$RELAY" --upstream "http://127.0.0.1:$JUDGE_PORT" --port "$RELAY_PORT" \
    >> /data/team08/runs/relay.log 2>&1 &
  RELAY_PID=$!
}
trap cleanup EXIT

docker rm -f team08-lightning team08-judge team08-embed team08-judge2 team08-lightning-ft \
  >/dev/null 2>&1
mkdir -p /data/team08/nim-cache/nemotron-3-embed-1b && chmod -R g+rwx /data/team08/nim-cache
PROXY_ENV=(-e HTTP_PROXY="$PROXY" -e HTTPS_PROXY="$PROXY" -e http_proxy="$PROXY" -e https_proxy="$PROXY"
           -e NO_PROXY="localhost,127.0.0.1" -e no_proxy="localhost,127.0.0.1")

docker run -d --name team08-lightning --gpus "\"device=${FREE[0]}\"" --shm-size=16GB --network host \
  -u "$(id -u)" -e NGC_API_KEY -e NIM_SERVER_PORT="$LIGHTNING_PORT" \
  -e HTTP_PROXY="$PROXY" -e HTTPS_PROXY="$PROXY" -e http_proxy="$PROXY" -e https_proxy="$PROXY" \
  -e NO_PROXY="localhost,127.0.0.1" -e no_proxy="localhost,127.0.0.1" \
  -v /data/team08/nim-cache:/opt/nim/.cache "$NIM_IMAGE" >/dev/null

# 64k context: agent runtimes and the judge panel send long prompts. Tool calling on,
# for the panel's Challenger and for NemoClaw agents.
# The judge and embedder NIMs listen on 8000 (and 8001) inside their containers;
# they are published on the job's ports rather than run on the host network, where
# 8001 is taken by the Lightning NIM's own backend.
docker run -d --name team08-judge --gpus "\"device=${FREE[1]},${FREE[3]}\"" --shm-size=16GB \
  -u "$(id -u)" -p "$JUDGE_PORT:8000" -e NGC_API_KEY "${PROXY_ENV[@]}" -e NIM_MODEL_PROFILE="$JUDGE_PROFILE" \
  -e NIM_SERVED_MODEL_NAME=nemotron-3-super -e NIM_MAX_MODEL_LEN=65536 -e NIM_ENABLE_AUTO_TOOL_CHOICE=1 \
  -v /data/team08/nim-cache:/opt/nim/.cache "$JUDGE_IMAGE" >/dev/null

docker run -d --name team08-embed --gpus "\"device=${FREE[2]}\"" --shm-size=4GB \
  -u "$(id -u)" -p "$EMBED_PORT:8000" -e NGC_API_KEY "${PROXY_ENV[@]}" \
  -v /data/team08/nim-cache/nemotron-3-embed-1b:/model "$EMBED_IMAGE" >/dev/null

# The second judge: the same image and settings, for the judge panel (the relay sends
# the panel's requests to both judges in turn).
docker run -d --name team08-judge2 --gpus "\"device=${FREE[4]},${FREE[5]}\"" --shm-size=16GB \
  -u "$(id -u)" -p "$JUDGE2_PORT:8000" -e NGC_API_KEY "${PROXY_ENV[@]}" -e NIM_MODEL_PROFILE="$JUDGE_PROFILE" \
  -e NIM_SERVED_MODEL_NAME=nemotron-3-super -e NIM_MAX_MODEL_LEN=65536 -e NIM_ENABLE_AUTO_TOOL_CHOICE=1 \
  -v /data/team08/nim-cache:/opt/nim/.cache "$JUDGE_IMAGE" >/dev/null

# The fine-tuned assistant: Lightning in full precision with LoRA, serving the base model
# (the fair control) and every adapter in /data/team08/loras under its folder's name. On
# the host network its vLLM backend needs a port of its own (8001 is the assistant's).
PW=/data/team08/runs/passwd.$(id -u); (cat /etc/passwd; getent passwd "$(id -u)") > "$PW"
docker run -d --name team08-lightning-ft --gpus "\"device=${FREE[6]}\"" --shm-size=16GB --network host \
  -u "$(id -u)" -e HOME=/tmp -v "$PW:/etc/passwd:ro" -e NGC_API_KEY -e NIM_MODEL_PROFILE="$FT_PROFILE" \
  -e NIM_SERVED_MODEL_NAME=nvidia/nemotron-3.5-lightning \
  -e NIM_SERVER_PORT="$FT_PORT" -e NIM_BACKEND_PORT="$FT_BACKEND" \
  -e NIM_PEFT_SOURCE=/opt/nim/loras -e NIM_PEFT_REFRESH_INTERVAL=60 \
  -e NIM_MAX_LORA_RANK=64 -e NIM_MAX_GPU_LORAS=4 "${PROXY_ENV[@]}" \
  -v /data/team08/nim-cache:/opt/nim/.cache -v /data/team08/loras:/opt/nim/loras:ro "$NIM_IMAGE" >/dev/null

for i in $(seq 1 180); do
  a=$(curl -s --noproxy '*' --max-time 3 "http://127.0.0.1:${LIGHTNING_PORT}/v1/models" | grep -c lightning)
  j=$(curl -s --noproxy '*' --max-time 3 "http://127.0.0.1:${JUDGE_PORT}/v1/models" | grep -c nemotron-3-super)
  e=$(curl -s --noproxy '*' --max-time 3 "http://127.0.0.1:${EMBED_PORT}/v1/models" | grep -c embed)
  j2=$(curl -s --noproxy '*' --max-time 3 "http://127.0.0.1:${JUDGE2_PORT}/v1/models" | grep -c nemotron-3-super)
  f=$(curl -s --noproxy '*' --max-time 3 "http://127.0.0.1:${FT_PORT}/v1/models" | grep -c "$CANDIDATE_MODEL")
  echo "$(date +%H:%M:%S) lightning=$a judge=$j embed=$e judge2=$j2 fine-tuned=$f"
  [[ $a -gt 0 && $j -gt 0 && $e -gt 0 && $j2 -gt 0 && $f -gt 0 ]] && break
  sleep 10
done
mkdir -p "$(dirname "$UPSTREAMS")"; echo "http://127.0.0.1:$JUDGE2_PORT" > "$UPSTREAMS"
IP=$(getent hosts "$(hostname)" | awk '{print $1}')
start_relay
echo "READY on $(hostname) ($IP): assistant :$LIGHTNING_PORT  judge :$JUDGE_PORT  embed :$EMBED_PORT  judge2 :$JUDGE2_PORT  fine-tuned :$FT_PORT ($CANDIDATE_MODEL)  relay :$RELAY_PORT"
cat > /data/team08/runs/servers.env <<ENV
# written by SLURM job $SLURM_JOB_ID on $(hostname) at $(date -Is)
EVIDENCE_ASSISTANT_BASE_URL=http://$IP:$LIGHTNING_PORT/v1
EVIDENCE_ASSISTANT_MODEL=nvidia/nemotron-3.5-lightning
EVIDENCE_JUDGE_BASE_URL=http://$IP:$JUDGE_PORT/v1
EVIDENCE_JUDGE_MODEL=nemotron-3-super
EVIDENCE_EMBED_BASE_URL=http://$IP:$EMBED_PORT/v1
EVIDENCE_EMBED_MODEL=nvidia/nemotron-3-embed-1b
# the fine-tuned assistant (the candidate); the same server also serves the base model
# in full precision as nvidia/nemotron-3.5-lightning
EVIDENCE_CANDIDATE_BASE_URL=http://$IP:$FT_PORT/v1
EVIDENCE_CANDIDATE_MODEL=$CANDIDATE_MODEL
# the second judge, for the judge panel (EVIDENCE_PANEL_* reach it through the relay)
# http://$IP:$JUDGE2_PORT/v1
# NemoClaw only (streamed tool calls), not read by the engine:
# openshell provider update vllm-local --config OPENAI_BASE_URL=http://host.openshell.internal:$RELAY_PORT/v1
ENV

# What only the node can see about the servers — image digests, weights commits
# and file hashes — for the model fingerprints in every evidence pack. Copy it
# next to .env with servers.env.
python3 "$HOME/open-credit-evidence/scripts/cluster/fingerprint_models.py" \
  --out /data/team08/runs/models.json --servers-env /data/team08/runs/servers.env \
  || echo "fingerprint_models.py failed: runs will record server-reported fingerprints only"

# Hold the allocation while the servers live; SLURM accounts every minute of it.
# A server that stops is started again with the same GPU, port and settings: on
# 23 Sep the judge received a SIGTERM from outside the job and, with no restart,
# the job ended and took the other two down with it. Each server is restarted at
# most MAX_RESTARTS times; after that the job ends rather than loop on a fault.
MAX_RESTARTS=5
declare -A RESTARTS=([team08-lightning]=0 [team08-judge]=0 [team08-embed]=0 [team08-judge2]=0
                     [team08-lightning-ft]=0 [relay]=0)
while true; do
  sleep 60
  # The models matter more than the relay: a relay that keeps failing is left
  # down (and said so once), the job goes on.
  if [[ -n "$RELAY_PID" ]] && ! kill -0 "$RELAY_PID" 2>/dev/null; then
    if (( RESTARTS[relay] >= MAX_RESTARTS )); then
      echo "$(date -Is) relay stopped again after $MAX_RESTARTS restarts; leaving it down"
      RELAY_PID=
    else
      RESTARTS[relay]=$((RESTARTS[relay] + 1))
      echo "$(date -Is) relay not running; restart ${RESTARTS[relay]}/$MAX_RESTARTS"
      tail -5 /data/team08/runs/relay.log | sed "s/^/  relay | /"
      start_relay
    fi
  fi
  running=$(docker ps --format '{{.Names}}') || { echo "$(date -Is) docker ps failed"; continue; }
  for c in team08-lightning team08-judge team08-embed team08-judge2 team08-lightning-ft; do
    grep -qx "$c" <<<"$running" && continue
    if (( RESTARTS[$c] >= MAX_RESTARTS )); then
      echo "$(date -Is) $c stopped again after $MAX_RESTARTS restarts; ending the job"
      exit 1
    fi
    RESTARTS[$c]=$((RESTARTS[$c] + 1))
    code=$(docker inspect -f '{{.State.ExitCode}} oom={{.State.OOMKilled}}' "$c" 2>/dev/null)
    echo "$(date -Is) $c not running (exit $code); restart ${RESTARTS[$c]}/$MAX_RESTARTS"
    docker logs --tail 20 "$c" 2>&1 | sed "s/^/  $c | /"
    docker start "$c" >/dev/null || echo "$(date -Is) docker start $c failed"
  done
done
