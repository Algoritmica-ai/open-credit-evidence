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
# Finished briefings are copied back to the job directory every 30 s while the
# panel runs, and once more at the end, whatever happens.
set -uo pipefail
JOB=$1 LOGIN=$2 NODE=$3 MODEL=${4:-nemotron-3-super} WORKERS=${5:-4}
HERE=$(cd "$(dirname "$0")" && pwd)
REMOTE=panel-job-$(date +%Y%m%dT%H%M%S)-$$

# The node now and then refuses a connection (exit 255): try each step three times.
retry() {
  local n
  for n in 1 2 3; do
    "$@" && return 0
    echo "  attempt $n failed: $1; retrying in 15 s" >&2
    sleep 15
  done
  return 1
}
fetch() {  # what the node has so far; replaced whole, never half-written
  scp -q "$LOGIN:$REMOTE/records.jsonl" "$JOB/records.part" 2>/dev/null \
    && mv "$JOB/records.part" "$JOB/records.jsonl"
}

retry ssh -o ConnectTimeout=10 "$LOGIN" "mkdir -p ~/$REMOTE" || exit 1
retry scp -q "$JOB/bundles.jsonl" "$JOB/panel.py" "$HERE/panel_in_sandbox.sh" "$LOGIN:$REMOTE/" \
  || exit 1

# The panel step. A dropped connection is retried; panel.py resumes from the
# records it already has, so a retry only reviews what is left.
rc=1
for attempt in 1 2 3; do
  ssh -o ConnectTimeout=10 "$LOGIN" \
    "ssh -o BatchMode=yes $NODE 'bash -l ~/$REMOTE/panel_in_sandbox.sh ~/$REMOTE $MODEL $WORKERS'" &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do sleep 30; fetch; done
  wait "$pid"; rc=$?
  fetch
  [[ $rc -eq 0 ]] && break
  echo "  panel step exited $rc (attempt $attempt); retrying in 15 s" >&2
  sleep 15
done

retry scp -q "$LOGIN:$REMOTE/runtime.json" "$JOB/" || rc=1
[[ $rc -eq 0 ]] && ssh -o ConnectTimeout=10 "$LOGIN" "rm -rf ~/$REMOTE"
exit "$rc"
