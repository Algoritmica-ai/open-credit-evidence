#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
#
# The three model servers as ONE SLURM job, so the GPUs they hold are accounted
# to the team. Docker containers started by hand sit outside SLURM: sacct shows
# nothing for them and the cluster sees the team as idle. This job holds its
# GPUs for its whole lifetime and stops the containers when it ends.
#
#   sbatch ~/open-credit-evidence/scripts/cluster/servers.sbatch
#   squeue --me            # the job stays RUNNING while the servers are up
#   scancel <jobid>        # stops all three
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
NIM_IMAGE=nvcr.io/nim/nvidia/nemotron-3.5-lightning-30b-a3b:2.0.9-variant
VLLM_IMAGE=vllm/vllm-openai:nightly
PROXY=http://10.130.232.8:3128
source ~/.ngc_key 2>/dev/null || true

# A whole node is the team's allocation and the only thing SLURM can actually
# guarantee: containers started by hand on a "free" node hold GPUs SLURM knows
# nothing about. Use the three GPUs with the least memory in use.
mapfile -t FREE < <(docker run --rm --gpus all --entrypoint nvidia-smi "$VLLM_IMAGE" \
  --query-gpu=index,memory.used --format=csv,noheader,nounits \
  | tr -d ' ' | awk -F, -v ids="$CUDA_VISIBLE_DEVICES" 'BEGIN{split(ids,a,","); for(i in a) ok[a[i]]=1} ok[$1]{print $2","$1}' \
  | sort -n | head -3 | cut -d, -f2)
echo "allocation $CUDA_VISIBLE_DEVICES -> using GPUs ${FREE[*]}; ports $LIGHTNING_PORT $JUDGE_PORT $EMBED_PORT"
for g in "${FREE[@]}"; do
  used=$(docker run --rm --gpus "\"device=$g\"" --entrypoint nvidia-smi "$VLLM_IMAGE" --query-gpu=memory.used --format=csv,noheader,nounits | tr -d ' ')
  if [[ "$used" -gt 4000 ]]; then echo "GPU $g has ${used} MiB in use by a process outside SLURM; refusing to start on it" >&2; exit 1; fi
done

cleanup() { docker stop team08-lightning team08-judge team08-embed >/dev/null 2>&1; echo "servers stopped"; }
trap cleanup EXIT

docker rm -f team08-lightning team08-judge team08-embed >/dev/null 2>&1
mkdir -p /data/team08/nim-cache && chmod g+rwx /data/team08/nim-cache

docker run -d --name team08-lightning --gpus "\"device=${FREE[0]}\"" --shm-size=16GB --network host \
  -u "$(id -u)" -e NGC_API_KEY -e NIM_SERVER_PORT="$LIGHTNING_PORT" \
  -e HTTP_PROXY="$PROXY" -e HTTPS_PROXY="$PROXY" -e http_proxy="$PROXY" -e https_proxy="$PROXY" \
  -e NO_PROXY="localhost,127.0.0.1" -e no_proxy="localhost,127.0.0.1" \
  -v /data/team08/nim-cache:/opt/nim/.cache "$NIM_IMAGE" >/dev/null

docker run -d --name team08-judge --gpus "\"device=${FREE[1]}\"" --shm-size=16GB --network host \
  -e HF_HUB_OFFLINE=1 -v /data/team08/models/nemotron-nano-9b-v2:/models/nano:ro "$VLLM_IMAGE" \
  --model /models/nano --served-model-name nano-judge --trust-remote-code --port "$JUDGE_PORT" \
  --dtype bfloat16 --max-model-len 16384 --gpu-memory-utilization 0.60 --mamba_ssm_cache_dtype float32 >/dev/null

docker run -d --name team08-embed --gpus "\"device=${FREE[2]}\"" --shm-size=4GB --network host \
  -e HF_HUB_OFFLINE=1 -v /data/team08/models/nemotron-3-embed-1b:/models/embed:ro "$VLLM_IMAGE" \
  --model /models/embed --served-model-name nemotron-3-embed-1b --runner pooling --port "$EMBED_PORT" \
  --dtype bfloat16 --max-model-len 8192 --gpu-memory-utilization 0.25 >/dev/null

for i in $(seq 1 180); do
  a=$(curl -s --noproxy '*' --max-time 3 "http://127.0.0.1:${LIGHTNING_PORT}/v1/models" | grep -c lightning)
  j=$(curl -s --noproxy '*' --max-time 3 "http://127.0.0.1:${JUDGE_PORT}/v1/models" | grep -c nano-judge)
  e=$(curl -s --noproxy '*' --max-time 3 "http://127.0.0.1:${EMBED_PORT}/v1/models" | grep -c embed)
  echo "$(date +%H:%M:%S) lightning=$a judge=$j embed=$e"
  [[ $a -gt 0 && $j -gt 0 && $e -gt 0 ]] && break
  sleep 10
done
IP=$(getent hosts "$(hostname)" | awk '{print $1}')
echo "READY on $(hostname) ($IP): assistant :$LIGHTNING_PORT  judge :$JUDGE_PORT  embed :$EMBED_PORT"
cat > /data/team08/runs/servers.env <<ENV
# written by SLURM job $SLURM_JOB_ID on $(hostname) at $(date -Is)
EVIDENCE_ASSISTANT_BASE_URL=http://$IP:$LIGHTNING_PORT/v1
EVIDENCE_ASSISTANT_MODEL=nvidia/nemotron-3.5-lightning
EVIDENCE_JUDGE_BASE_URL=http://$IP:$JUDGE_PORT/v1
EVIDENCE_JUDGE_MODEL=nano-judge
EVIDENCE_EMBED_BASE_URL=http://$IP:$EMBED_PORT/v1
EVIDENCE_EMBED_MODEL=nemotron-3-embed-1b
ENV

# Hold the allocation while the servers live; SLURM accounts every minute of it.
while docker ps --format '{{.Names}}' | grep -q team08-judge; do sleep 60; done
