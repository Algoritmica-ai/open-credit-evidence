#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
#
# On the GPU node: copy a panel job into the NemoClaw sandbox, run panel.py there
# against the sandbox's managed inference route, copy the records back, and
# write runtime.json: what the panel ran inside (versions, sandbox, policy,
# inference route). Called by panel_nemoclaw.sh.
#
#   panel_in_sandbox.sh <job dir> [model] [workers]
#
# Inside the sandbox every connection goes through OpenShell's proxy, which allows
# only what the sandbox's network policy names (runtime.json records the entry
# names and a hash of the policy). The panel's one destination is
# https://inference.local/v1, which OpenShell routes to the team's judge
# (through stream_relay.py to the Nano NIM).
set -euo pipefail
DIR=$1 MODEL=${2:-nano-judge} WORKERS=${3:-4}
SANDBOX=${SANDBOX:-evidence-judge}
export NVM_DIR=$HOME/.nvm; . "$NVM_DIR/nvm.sh" >/dev/null
export PATH=$HOME/.local/bin:$PATH
module load docker >/dev/null 2>&1 || true
export NEMOCLAW_GATEWAY_PORT=${NEMOCLAW_GATEWAY_PORT:-8300}
export OPENSHELL_GATEWAY=${OPENSHELL_GATEWAY:-nemoclaw-$NEMOCLAW_GATEWAY_PORT}
clean() { sed "s/\x1b\[[0-9;]*m//g" | { grep -v "Active gateway" || true; }; }
NAME=$(basename "$DIR")
BOX=/sandbox/$NAME   # the sandbox workspace: files can be copied in and out only here

started=$(date -u +%FT%TZ)
openshell sandbox upload "$SANDBOX" "$DIR" /sandbox 2>&1 | clean | tail -1
nemoclaw "$SANDBOX" exec --no-tty -- python3 "$BOX/panel.py" --in "$BOX/bundles.jsonl" \
  --out "$BOX/records.jsonl" --base-url https://inference.local/v1 --model "$MODEL" \
  --workers "$WORKERS" --use-env-proxy 2>&1 | clean
openshell sandbox download "$SANDBOX" "$BOX/records.jsonl" "$DIR/" 2>&1 | clean | tail -1
nemoclaw "$SANDBOX" exec --no-tty -- rm -rf "$BOX" >/dev/null 2>&1 || true

# What the panel ran inside, for the evidence.
nemoclaw "$SANDBOX" status 2>&1 | clean | sed -n '/^Policy:/,$p' > "$DIR/policy.txt"
python3 - "$DIR/runtime.json" "$started" "$SANDBOX" "$DIR/policy.txt" <<'PY'
import json, re, subprocess, sys, hashlib, socket
out, started, sandbox, policy_file = sys.argv[1:5]
def run(*cmd):
    try:
        return re.sub(r"\x1b\[[0-9;]*m", "", subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout)
    except Exception as e:
        return f"unavailable: {e}"
policy = open(policy_file).read()
status = run("nemoclaw", sandbox, "status")
route = run("openshell", "inference", "get")
def grab(pattern, text):
    m = re.search(pattern, text)
    return m.group(1).strip() if m else None
json.dump({
    "node": socket.gethostname(), "sandbox": sandbox, "started_at": started,
    "endpoint": "https://inference.local/v1",
    "nemoclaw": grab(r"nemoclaw v?([\d.]+)", run("nemoclaw", "--version")),
    "openshell": grab(r"OpenShell:\s*([\d.]+)", status),
    "agent_runtime": grab(r"Agent:\s*(.+)", status),
    "inference_route": {"provider": grab(r"Provider:\s*(\S+)", route),
                        "model": grab(r"Model:\s*(\S+)", route),
                        "timeout": grab(r"Timeout:\s*(\S+)", route)},
    "network_policies": sorted(set(re.findall(r"^    (\w[\w-]*):\n      name:", policy, re.M))),
    "policy_sha256": hashlib.sha256(policy.encode()).hexdigest(),
}, open(out, "w"), indent=2)
PY
rm -f "$DIR/policy.txt"
echo "panel done: $(wc -l < "$DIR/records.jsonl") records"
