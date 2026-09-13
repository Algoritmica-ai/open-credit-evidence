# Runtime — Credit Evidence Engine

**Primary runtime:** your laptop (venv) or Docker Compose.  
**Model inference:** hosted NVIDIA Build (Nemotron) via environment variables.  
**This app is a CLI.** It is not an HTTP service and is not hosted on Axis or Curiosity.

See also: [README.md](../README.md) (quick start), [BUILD.md](../BUILD.md) (technical spec).

---

## How to run locally (venv)

Python 3.11+:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Edit .env — set NEMOTRON_API_KEY for live NVIDIA Build calls

pytest

python -m open_credit_evidence.cli load cases/sample_case_001/
python -m open_credit_evidence.cli process cases/sample_case_001/ -o reports/case_001_report.json
python -m open_credit_evidence.cli verify reports/case_001_report.json
```

After install, `oce` is the same CLI (`oce --help`, `oce version`, `oce load|process|verify`).

Without `NEMOTRON_API_KEY`, `process` uses a stub summary; omission check will fail. That is expected. Named-fact omission is proven by `pytest` fixtures, not by the stub.

---

## How to run with Docker Compose

From the repo root (Docker Engine + Compose v2):

```bash
cp .env.example .env   # optional; Compose still starts without a key
docker compose up --build
```

This **builds** the image and runs `oce --help`, then exits. That is the smoke check that the package installed and the CLI entrypoint works. There is **no** published port and **no** health URL.

Useful overrides:

```bash
# Version / help
docker compose run --rm app oce version

# Tests
docker compose run --rm app pytest -v

# Process a sample case (cases/ is baked into the image)
docker compose run --rm app oce process cases/sample_case_001/
```

Single-service Compose: `app` only. A later vector store can be a second service; do not add OpenShift or Axis to this file.

Equivalent without Compose: `docker build -t open-credit-evidence . && docker run --rm open-credit-evidence` (same default: CLI help).

---

## NVIDIA Build env vars

From [`.env.example`](../.env.example). Secrets stay in `.env` (gitignored). Never commit keys.

| Variable | Required | Meaning |
|----------|----------|---------|
| `NEMOTRON_BASE_URL` | Yes (has default) | Hosted NVIDIA API, default `https://integrate.api.nvidia.com/v1` |
| `NEMOTRON_API_KEY` | For live calls | NVIDIA Build key |
| `NEMOTRON_MODEL` | No | Default in code: `nvidia/nemotron-4-340b-instruct` |
| `EVIDENCE_VERIFICATION_MODE` | No | Declared `strict` / `permissive` (not fully wired yet) |
| `LOG_LEVEL` | No | Logging |

Inference is **always** this hosted API (or the stub). Not self-hosted Nemotron. Not Curiosity GPUs on the critical path.

---

## What Axis / Curiosity is — and is not

Hackathon Axis (portal, event `omc-2026`, cluster `omc-termh`) and **Curiosity v2** are **optional compute**: Jupyter, Slurm, Enroot, private Kubernetes pods for experiments.

They are **not**:

- An application host for the Evidence Engine
- A place we `axis deploy` this repo
- A public Ingress / Service / Route for this CLI
- The system of record for cases, reports, or fingerprints

Do **not** expect URLs like `/apps/open-credit-evidence/health`. This project does not expose that surface.

Origin is **source control only**, not a deploy target. After Clyde moves upstream to Algoritmica GitHub, **CI** (GitHub Actions, e.g. pytest) can run there. That workflow is not in this repo yet.

---

## Explicit non-goals

- No Axis portal app hosting
- No Curiosity as system of record or HTTP front door
- No self-hosted model serving on the critical path
- No OpenShift DataMesh / CFM pitch stack in this runtime
