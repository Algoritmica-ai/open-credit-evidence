# OpenCredit Evidence

**Credit Evidence Engine** (4-week plan) — OpenCredit Evidence Hackathon. Runs locally (venv or Docker Compose). Inference is hosted NVIDIA Build. Axis/Curiosity are optional GPU/Jupyter only — not an app host.

A credit decision evidence verification system that ensures AI-generated loan summaries include all decision-critical facts from source documents.

## Team

- **Luca** — Product / Regulatory
- **Sriram** — Cases / Models / Marking
- **Clyde** — Backend / Repo / RAG / Evidence / Deploy

## Week 1 Success Criteria (ends Wed 16 Sep 2026)

- [ ] Twenty referred loan application cases run end-to-end
- [ ] System catches a deliberately bad summary that omits decision-critical facts
- [ ] Evidence verification pipeline with tamper detection
- [ ] Basic whole-file summarization via hosted NVIDIA Build (embeddings later)

## Quick Start

### Prerequisites

- Python 3.11+
- uv (recommended) or pip

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd open-credit-evidence

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Or with pip
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Configuration

```bash
cp .env.example .env
# Set NVIDIA_API_KEY (or NEMOTRON_API_KEY) for live NVIDIA Build calls
```

### Running Tests

```bash
pytest
```

### Running the Pipeline (Week 1)

```bash
# Whole-file summarization via NVIDIA Build (stub if no key)
python -m open_credit_evidence.cli process cases/sample_case_001/

# With a key in .env — live Build call:
#   NVIDIA_API_KEY=... python -m open_credit_evidence.cli process cases/sample_case_001/ -o reports/case_001_report.json

# Verify evidence report integrity
python -m open_credit_evidence.cli verify reports/case_001_report.json
```

### Docker Compose (same CLI, no HTTP port)

```bash
docker compose up --build          # builds image, prints `oce --help`, exits
docker compose run --rm app pytest -v
docker compose run --rm app oce process cases/sample_case_001/
```

Full run/runtime notes: [`docs/runtime.md`](docs/runtime.md).

## Project Structure

```
open-credit-evidence/
├── BUILD.md                  # Detailed technical spec
├── cases/                    # Sample referred loan application cases
│   ├── sample_case_001/     # Application form + bureau report
│   └── sample_case_002/
├── docker-compose.yml        # Local CLI container (no published ports)
├── Dockerfile                # Image for Compose; default CMD is oce --help
├── docs/
│   ├── runtime.md           # How to run: venv, Compose, NVIDIA env; Axis is not a host
│   ├── design-note.md       # System design (models, RAG, safety)
│   └── week1-design-outline.md
├── src/open_credit_evidence/
│   ├── loader.py            # Case loading with fingerprint verification
│   ├── runner.py            # Nemotron assistant interface
│   ├── omission_check.py    # Decision-critical fact verification
│   ├── evidence.py          # Evidence report generation
│   └── schemas.py           # Data models
├── tests/
│   ├── fixtures/            # Good/bad summary test fixtures
│   └── test_*.py           # Test suite
└── pyproject.toml
```

## Architecture Overview

**Docs / architecture.** Detailed technical spec: BUILD.md. How to run: [`docs/runtime.md`](docs/runtime.md).

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│  Case Docs  │───▶│    Loader    │───▶│  Fingerprinted  │
│  (MD/Text)  │    │  + Hash      │    │     Case        │
└─────────────┘    └──────────────┘    └────────┬────────┘
                                                │
                   ┌──────────────┐             ▼
                   │   Nemotron   │◀───────────────────────
                   │   (NVIDIA)   │    RAG Context + Query
                   └──────┬───────┘
                          │
                          ▼
                   ┌──────────────┐    ┌─────────────────┐
                   │   Summary    │───▶│ Omission Check  │
                   │  Generation  │    │ (Critical Facts)│
                   └──────────────┘    └────────┬────────┘
                                                │
                                                ▼
                                       ┌─────────────────┐
                                       │ Evidence Report │
                                       │ + Tamper Proof  │
                                       └─────────────────┘
```

## Key Constraints (Mentor Guidance Day 1)

1. **Design before coding** — See `docs/design-note.md`
2. **Start small** — Twenty cases end-to-end first
3. **Use RAG** — Not fine-tuned models on critical path
4. **NVIDIA Build** — Hosted `nvidia/nemotron-3.5-lightning-30b-a3b`; whole-file context first, embeddings later. No self-hosted models.
5. **Runtime** — Local machine + Docker Compose. Hosted NVIDIA Build for Nemotron. Origin is source control only. After Algoritmica GitHub upstream, CI can be GitHub Actions (pytest) — not in this repo yet.

## What This Is NOT

This is the **4-week plan**: Credit Evidence Engine (RAG, hosted Nemotron, omission/tamper). Stretch is the **pitch architecture**: OpenShift DataMesh+CFM deploy design — not this repo's path.
No Iceberg, Trino, Hive, Airflow, or Kustomize here.

**Axis portal / Curiosity** are optional GPU, Jupyter, Slurm, or private Kubernetes pods for experiments. They do **not** host this Evidence Engine as an HTTP app. There is no `axis deploy` and no `/apps/open-credit-evidence/health` URL.

## License

Apache 2.0 — See [LICENSE](LICENSE) and [NOTICE](NOTICE).

Copyright holders: Algoritmica GmbH + ZAGA Open Source (pending confirmation from Luca).

## Future: GitHub Upstream

This repository is temporarily hosted on Origin (source control only, not a deploy target). Clyde will migrate upstream to Algoritmica GitHub after the hackathon; pytest CI via GitHub Actions can follow there.
