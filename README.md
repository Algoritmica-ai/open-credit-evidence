# OpenCredit Evidence

**Credit Evidence Engine** (4-week plan) — OpenCredit Evidence Hackathon

A credit decision evidence verification system that ensures AI-generated loan summaries include all decision-critical facts from source documents.

## Team

- **Luca** — Product / Regulatory
- **Sriram** — Cases / Models / Marking
- **Clyde** — Backend / Repo / RAG / Evidence / Deploy

## Week 1 Success Criteria (ends Wed 16 Sep 2026)

- [ ] Twenty referred loan application cases run end-to-end
- [ ] System catches a deliberately bad summary that omits decision-critical facts
- [ ] Evidence verification pipeline with tamper detection
- [ ] Basic RAG retrieval working via NVIDIA Build / Nemotron

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
# Edit .env with your NVIDIA API credentials
```

### Running Tests

```bash
pytest
```

### Running the Pipeline (Week 1)

```bash
# Process a single case
python -m open_credit_evidence.cli process cases/sample_case_001/

# Verify evidence report integrity
python -m open_credit_evidence.cli verify reports/case_001_report.json
```

## Project Structure

```
open-credit-evidence/
├── cases/                    # Sample referred loan application cases
│   ├── sample_case_001/     # Application form + bureau report
│   └── sample_case_002/
├── docs/
│   ├── design-note.md       # System design (models, RAG, safety)
│   └── deploy-axis.md       # Axis portal deployment guide
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
4. **NVIDIA Build** — Hosted Nemotron + RAG blueprints (no self-hosted models)
5. **Eventual deploy** — Target: `https://axis-raplabhackathon.axisportal.io/apps`

## What This Is NOT

This is the **4-week plan**: Credit Evidence Engine (RAG, hosted Nemotron, omission/tamper, Axis). Stretch is the **pitch architecture**: OpenShift DataMesh+CFM deploy design — not this repo's path.
No Iceberg, Trino, Hive, Airflow, or Kustomize here.

## License

Apache 2.0 — See [LICENSE](LICENSE) and [NOTICE](NOTICE).

Copyright holders: Algoritmica GmbH + ZAGA Open Source (pending confirmation from Luca).

## Future: GitHub Upstream

This repository is temporarily hosted on Origin. Clyde will migrate upstream to Algoritmica GitHub after the hackathon.
