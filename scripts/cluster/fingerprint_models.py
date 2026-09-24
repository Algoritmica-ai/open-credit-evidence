#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""What only the node can see about the running model servers, as models.json.

The laptop running an evaluation can ask each server what it is (see
``evidence.fingerprint``), but not which container image it runs or which
weight files it loaded. This script, run on the GPU node, records both:

- per container: the image it was started from and that image's digest, and
  the serving arguments (dtype, context length) that change its output
- per weights directory mounted into a container: the Hugging Face commit it
  was downloaded at, and the SHA-256 of every weights file — read from the
  download metadata for large files (the LFS etag is the file's SHA-256),
  computed for small ones

servers.sbatch runs it once the servers are ready and writes
/data/team08/runs/models.json next to servers.env; copy it next to .env.

    python3 fingerprint_models.py --out /data/team08/runs/models.json

Standard library only: the node has Python 3 and docker, nothing else.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path

CONTAINERS = {"team08-lightning": "assistant", "team08-judge": "judge", "team08-embed": "embed"}
SMALL = 64 * 1024 * 1024  # hash files up to this size directly
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ARGS_THAT_MATTER = ("--dtype", "--max-model-len", "--quantization", "--served-model-name",
                    "--mamba_ssm_cache_dtype", "--runner", "--tokenizer", "--revision")


def _docker(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True, stderr=subprocess.DEVNULL)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def weights(directory: Path) -> dict:
    """Commit and per-file SHA-256 of a Hugging Face download."""
    meta_dir = directory / ".cache" / "huggingface" / "download"
    commits: set[str] = set()
    files: dict[str, str] = {}
    for path in sorted(p for p in directory.rglob("*") if p.is_file() and ".cache" not in p.parts):
        rel = path.relative_to(directory).as_posix()
        meta = meta_dir / f"{rel}.metadata"
        etag = None
        if meta.is_file():
            lines = meta.read_text().splitlines()
            if lines:
                commits.add(lines[0].strip())
            if len(lines) > 1 and HEX64.match(lines[1].strip()):
                etag = lines[1].strip()  # an LFS file: the etag is its SHA-256
        if etag:
            files[rel] = etag
        elif path.stat().st_size <= SMALL:
            files[rel] = _sha256(path)
        else:
            files[rel] = "unhashed: large file without download metadata"
    return {"dir": str(directory), "hf_commit": sorted(commits)[0] if len(commits) == 1
            else sorted(commits) or None, "files": files}


def container(name: str) -> dict | None:
    try:
        info = json.loads(_docker("inspect", name))[0]
    except (subprocess.CalledProcessError, IndexError, json.JSONDecodeError):
        return None
    image_id = info["Image"]
    try:
        repo_digests = json.loads(_docker("image", "inspect", "-f", "{{json .RepoDigests}}",
                                          image_id))
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        repo_digests = []
    args = info.get("Args") or []
    kept = {a: args[i + 1] for i, a in enumerate(args[:-1]) if a in ARGS_THAT_MATTER}
    mounts = [m for m in info.get("Mounts", []) if m.get("Type") == "bind"]
    out = {
        "container": name,
        "image": info["Config"]["Image"],
        "image_id": image_id,
        "repo_digests": repo_digests,
        "started_at": info["State"].get("StartedAt"),
        "args": kept,
        "mounts": {m["Destination"]: m["Source"] for m in mounts},
        "weights": None,
    }
    # a vLLM server's weights are the directory mounted at its --model path
    model_arg = next((args[i + 1] for i, a in enumerate(args[:-1]) if a == "--model"), None)
    for m in mounts:
        if model_arg and model_arg.startswith(m["Destination"]):
            out["weights"] = weights(Path(m["Source"]))
    return out


def ports(servers_env: Path) -> dict[str, str]:
    """role -> host:port, from the servers.env the job published."""
    out = {}
    if servers_env.is_file():
        for line in servers_env.read_text().splitlines():
            m = re.match(r"EVIDENCE_(\w+)_BASE_URL=https?://([^/]+)", line)
            if m:
                out[m.group(1).lower()] = m.group(2)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--servers-env", type=Path, default=Path("/data/team08/runs/servers.env"))
    a = ap.parse_args()
    where = ports(a.servers_env)
    servers = {}
    for name, role in CONTAINERS.items():
        c = container(name)
        if c:
            servers[role] = {"address": where.get(role)} | c
    doc = {
        "written_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "node": socket.gethostname(),
        "servers": servers,
    }
    a.out.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"wrote {a.out}: " + ", ".join(f"{r} {s['image_id'][:19]}" for r, s in servers.items()))


if __name__ == "__main__":
    main()
