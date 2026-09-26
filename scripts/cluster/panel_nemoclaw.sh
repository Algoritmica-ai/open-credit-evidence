#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
#
# Run the judge panel inside the NemoClaw sandbox on the GPU node. Called by
# `evidence panel <run> --runtime nemoclaw` with a job directory holding
# bundles.jsonl and panel.py; leaves records.jsonl and runtime.json in it.
#
#   panel_nemoclaw.sh <job dir> <login host> <node> [model] [workers]
#
# The node is reached through the login host (pam_slurm_adopt: only a node where
# the team has a job). The home directory is shared, so the job is copied once.
# Finished briefings are copied back to the job directory every 10 s while the
# panel runs, and once more at the end, whatever happens. A STOP file in the job
# directory stops the panel in the sandbox at its next turn; what finished comes back.
set -uo pipefail
JOB=$1 LOGIN=$2 NODE=$3 MODEL=${4:-nemotron-3-super} WORKERS=${5:-4}
HERE=$(cd "$(dirname "$0")" && pwd)
# One SSH connection to the login host, reused by every step and every fetch: a new
# connection now and then stalls for minutes before it is closed. A stalled connection is
# noticed within 15 s (keepalives), not when a TCP timeout would notice it.
SSH=(-o ConnectTimeout=10 -o ServerAliveInterval=5 -o ServerAliveCountMax=3
     -o ControlMaster=auto -o "ControlPath=$HOME/.ssh/cm-evidence-%C" -o ControlPersist=5m)
HOP="-o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=5 -o ServerAliveCountMax=3"
REMOTE=panel-job-$(date +%Y%m%dT%H%M%S)-$$

# The node now and then refuses a connection (exit 255): try each step three times.
retry() {
  local n
  for n in 1 2 3; do
    "$@" && return 0
    echo "  attempt $n failed: $1; retrying in 5 s" >&2
    sleep 5
  done
  return 1
}
fetch() {  # what the node has so far; replaced whole, never half-written
  scp -q "${SSH[@]}" "$LOGIN:$REMOTE/records.jsonl" "$JOB/records.part" 2>/dev/null \
    && mv "$JOB/records.part" "$JOB/records.jsonl"
}
stopped=0
stop_if_asked() {  # pass a stop from the laptop to the node, once; the node checks every 5 s
  [[ -f "$JOB/STOP" && $stopped -eq 0 ]] || return 0
  stopped=1
  retry ssh "${SSH[@]}" "$LOGIN" "touch ~/$REMOTE/STOP" || true
}

retry ssh "${SSH[@]}" "$LOGIN" "mkdir -p ~/$REMOTE" || exit 1
retry scp -q "${SSH[@]}" "$JOB/bundles.jsonl" "$JOB/panel.py" "$HERE/panel_in_sandbox.sh" "$LOGIN:$REMOTE/" \
  || exit 1

# The panel step. A dropped connection is retried; panel.py resumes from the
# records it already has, so a retry only reviews what is left.
rc=1
for attempt in 1 2 3; do
  ssh "${SSH[@]}" "$LOGIN" \
    "ssh $HOP $NODE 'bash -l ~/$REMOTE/panel_in_sandbox.sh ~/$REMOTE $MODEL $WORKERS'" &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    for _ in 1 2; do  # a stop is checked every 5 s, results fetched every 10 s
      kill -0 "$pid" 2>/dev/null || break
      sleep 5
      stop_if_asked
    done
    fetch
  done
  wait "$pid"; rc=$?
  fetch
  [[ $rc -eq 0 || $stopped -eq 1 ]] && break
  echo "  panel step exited $rc (attempt $attempt); retrying in 5 s" >&2
  sleep 5
done

if [[ $stopped -eq 1 ]]; then  # a stop before the sandbox ran leaves no runtime.json
  scp -q "${SSH[@]}" "$LOGIN:$REMOTE/runtime.json" "$JOB/" 2>/dev/null || true
  rc=0
else
  retry scp -q "${SSH[@]}" "$LOGIN:$REMOTE/runtime.json" "$JOB/" || rc=1
fi
[[ $rc -eq 0 ]] && ssh "${SSH[@]}" "$LOGIN" "rm -rf ~/$REMOTE"
exit "$rc"
