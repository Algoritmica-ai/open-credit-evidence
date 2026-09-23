#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
#
# Slurm batch job for the Ultra teacher NIM on Curiosity B300.
#
# Why this exists: hand-started docker sits outside Slurm accounting. This job
# holds 4 B300 GPUs for its lifetime and stops the Ultra container on EXIT or
# scancel, so the GPUs are properly released back to the cluster.
#
# Submit from the login node:
#
#   sbatch ~/open-credit-evidence/scripts/cluster/ultra.sbatch
#   squeue --me          # check status
#   scancel <jobid>      # stop when the labeling pass is done
#
# The job writes connection info to:
#   /storage/hackathon_teams/omc-team08/runs/ultra.env
# Source that file to set EVIDENCE_JUDGE_BASE_URL and EVIDENCE_JUDGE_MODEL.
#
# ~400 readability labels should finish well before the 2-day limit. scancel
# when done to release the GPUs.
#
# Directory layout:
#   $HOME/open-credit-evidence/         # repo clone (can live anywhere)
#   $HOME/nim-cache-ultra/              # NIM weight cache (default, avoids ACL issues)
#   /storage/hackathon_teams/omc-team08/  # TEAM_ROOT (runs/logs only)
#     runs/
#       ultra-%j.log                      # job output
#       ultra.env                         # EVIDENCE_JUDGE_* for labeling

#SBATCH --job-name=team08-ultra-teacher
#SBATCH --partition=hackathon
#SBATCH --gpus=4
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --mem=0
#SBATCH --time=2-00:00:00
#SBATCH --output=/storage/hackathon_teams/omc-team08/runs/ultra-%j.log

# Memory note: Ultra 550B NVFP4 TP4 needs substantial host RAM during engine init.
# --mem=0 requests all memory on the node (override with sbatch --mem=900G if unsupported).
# GPU note: requests 4 GPUs for TP4 profile. If Slurm shows more (e.g. whole node),
# serve_ultra.sh pins to the first 4. Do NOT use --exclusive (wastes 4 GPUs).

set -euo pipefail

# --- Repo location (override with OPEN_CREDIT_REPO if cloned elsewhere) ---
REPO_ROOT="${OPEN_CREDIT_REPO:-$HOME/open-credit-evidence}"

# --- Team shared storage (runs/logs only; cache defaults to $HOME) ---
TEAM_ROOT=/storage/hackathon_teams/omc-team08
RUNS_DIR="$TEAM_ROOT/runs"
# Default cache under $HOME avoids team-storage ACL + GID 0 conflicts
NIM_CACHE="${LOCAL_NIM_CACHE:-$HOME/nim-cache-ultra}"

CONTAINER_NAME=team08_nt-ultra
ENV_FILE="${RUNS_DIR}/ultra.env"
# PORT is determined by serve_ultra.sh (auto-selects free port if NIM_PORT unset)

cleanup() {
    echo "$(date): stopping $CONTAINER_NAME"
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    echo "$(date): cleanup complete"
}
trap cleanup EXIT

echo "$(date): job $SLURM_JOB_ID starting on $(hostname)"
echo "$(date): CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES"
echo "$(date): REPO_ROOT=$REPO_ROOT"
echo "$(date): TEAM_ROOT=$TEAM_ROOT"

source ~/.ngc_key
if [[ -z "${NGC_API_KEY:-}" ]]; then
    echo "NGC_API_KEY not set after sourcing ~/.ngc_key" >&2
    exit 1
fi

# Curiosity B300: rootless-docker; RTX fallback: docker
if ! module load rootless-docker/1.75 2>/dev/null; then
  module load docker 2>/dev/null || true
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "$(date): docker not found. Tried: module load rootless-docker/1.75, then module load docker" >&2
  echo "Run: module avail 2>&1 | grep -i docker" >&2
  exit 1
fi

mkdir -p "$RUNS_DIR" "$NIM_CACHE"

# Find serve_ultra.sh. Under Slurm the batch script is copied to a spool path,
# so BASH_SOURCE[0] won't point to the repo. Resolution order:
#   1. $REPO_ROOT (explicit or $HOME/open-credit-evidence)
#   2. $SLURM_SUBMIT_DIR (if user ran sbatch from repo root)
#   3. Same dir as BASH_SOURCE (last resort, rarely works under sbatch)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd 2>/dev/null || echo "")"
SERVE_SCRIPT=""

if [[ -f "${REPO_ROOT}/scripts/cluster/serve_ultra.sh" ]]; then
    SERVE_SCRIPT="${REPO_ROOT}/scripts/cluster/serve_ultra.sh"
elif [[ -n "${SLURM_SUBMIT_DIR:-}" && -f "${SLURM_SUBMIT_DIR}/scripts/cluster/serve_ultra.sh" ]]; then
    SERVE_SCRIPT="${SLURM_SUBMIT_DIR}/scripts/cluster/serve_ultra.sh"
elif [[ -n "$SCRIPT_DIR" && -f "${SCRIPT_DIR}/serve_ultra.sh" ]]; then
    SERVE_SCRIPT="${SCRIPT_DIR}/serve_ultra.sh"
fi

if [[ -z "$SERVE_SCRIPT" ]]; then
    echo "$(date): cannot find serve_ultra.sh" >&2
    echo "Paths tried:" >&2
    echo "  REPO_ROOT:        ${REPO_ROOT}/scripts/cluster/serve_ultra.sh" >&2
    echo "  SLURM_SUBMIT_DIR: ${SLURM_SUBMIT_DIR:-<unset>}/scripts/cluster/serve_ultra.sh" >&2
    echo "  SCRIPT_DIR:       ${SCRIPT_DIR:-<unset>}/serve_ultra.sh" >&2
    echo "Set OPEN_CREDIT_REPO to the repo root, or run 'sbatch' from the repo directory." >&2
    exit 1
fi

echo "$(date): calling $SERVE_SCRIPT"
export LOCAL_NIM_CACHE="$NIM_CACHE"

if ! bash "$SERVE_SCRIPT"; then
    echo "$(date): serve_ultra.sh failed" >&2
    exit 1
fi

# Read the port that serve_ultra.sh selected (written to $NIM_CACHE/.nim_port)
if [[ -f "$NIM_CACHE/.nim_port" ]]; then
    PORT=$(cat "$NIM_CACHE/.nim_port")
    echo "$(date): serve_ultra.sh selected port $PORT"
else
    echo "$(date): warning: could not read selected port from $NIM_CACHE/.nim_port" >&2
    PORT=8001
fi

NODE_IP=$(hostname -i 2>/dev/null || hostname)
cat > "$ENV_FILE" <<EOF
# Generated by ultra.sbatch job $SLURM_JOB_ID on $(date)
# Node: $(hostname) ($NODE_IP)
EVIDENCE_JUDGE_BASE_URL=http://${NODE_IP}:${PORT}/v1
EVIDENCE_JUDGE_MODEL=nvidia/nemotron-3-ultra-550b-a55b
EOF
chmod 664 "$ENV_FILE" 2>/dev/null || true

echo "$(date): Ultra NIM ready"
echo "$(date): env file written to $ENV_FILE"
echo "$(date): holding allocation while container runs (scancel $SLURM_JOB_ID when done)"

while docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; do
    sleep 60
done

echo "$(date): container stopped unexpectedly"
exit 1
