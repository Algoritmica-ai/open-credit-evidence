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
set -euo pipefail
JOB=$1 LOGIN=$2 NODE=$3 MODEL=${4:-nano-judge} WORKERS=${5:-4}
HERE=$(cd "$(dirname "$0")" && pwd)
REMOTE=panel-job-$(date +%Y%m%dT%H%M%S)-$$

ssh -o ConnectTimeout=10 "$LOGIN" "mkdir -p ~/$REMOTE"
scp -q "$JOB/bundles.jsonl" "$JOB/panel.py" "$HERE/panel_in_sandbox.sh" "$LOGIN:$REMOTE/"
ssh -o ConnectTimeout=10 "$LOGIN" \
  "ssh -o BatchMode=yes $NODE 'bash -l ~/$REMOTE/panel_in_sandbox.sh ~/$REMOTE $MODEL $WORKERS'"
scp -q "$LOGIN:$REMOTE/records.jsonl" "$LOGIN:$REMOTE/runtime.json" "$JOB/"
ssh -o ConnectTimeout=10 "$LOGIN" "rm -rf ~/$REMOTE"
