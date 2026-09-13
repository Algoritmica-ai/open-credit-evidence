# BUILD.md — Credit Evidence Engine technical spec

This is the **detailed technical spec** for the 4-week plan (Credit Evidence Engine: RAG, hosted Nemotron, omission/tamper). It is not the schedule. Who does what and week dates live in the Google Doc only.

Related: [`docs/design-note.md`](docs/design-note.md) (system design stub), [`docs/week1-design-outline.md`](docs/week1-design-outline.md) (Week 1 outline), [`docs/runtime.md`](docs/runtime.md) (how to run).

---

## 1. Purpose / problem

The bank refers loan applications its rules could not decide. An assistant then writes a fluent summary of the application form and bureau report. That summary can be **true in every sentence it contains** and still **omit the fact that would change the underwriting decision** (boundary score, recent 30-day late pay, credit-shopping enquiry, high utilisation, etc.).

This system produces an underwriter-facing package that:

- Loads source documents with frozen fingerprints (tamper detect).
- Retrieves or (Week 1 fallback) passes whole-file context to hosted Nemotron.
- Checks the summary against named critical facts.
- Emits an evidence report whose chain hashes can be recomputed.

If a decision-critical fact is missing, the package **fails by fact id**, not by a vague quality score.

---

## 2. Non-goals

Out of scope for this repo and for the 4-week plan:

- **Pitch architecture** — OpenShift DataMesh + CFM deploy design (Iceberg, Trino, Hive, Airflow, Kustomize, in-cluster Nemotron ServingRuntime, Marquez, CFM score API). Do not build that stack here.
- **Curiosity / Axis HPC** — optional GPU, Jupyter, Slurm, private K8s pods for experiments only. **Not** an application host. Not the system of record. Hosted NVIDIA Build remains the Nemotron path.
- **LLM-as-judge for Week 1 omission** — Week 1 omission check is **deterministic** (keyword/pattern match against named facts). Do not gate Week 1 DoD on a second model scoring the summary.
- Live production PII. Demo cases are synthetic.
- Fine-tuned or self-hosted models on the critical path.

---

## 3. System components (this repo)

| Component | Path | Role today |
|-----------|------|------------|
| **loader** | `src/open_credit_evidence/loader.py` | Read a case directory; SHA-256 each file; combined fingerprint; refuse hash mismatch |
| **runner** | `src/open_credit_evidence/runner.py` | Whole-file context + hosted Nemotron (`nvidia/nemotron-3.5-lightning-30b-a3b`); stub if no API key |
| **omission_check** | `src/open_credit_evidence/omission_check.py` | Match `critical_facts` against summary; fail if any fact missing (and if any `critical` severity omitted) |
| **evidence** | `src/open_credit_evidence/evidence.py` | Chain fingerprint over case + summary + marking; save/load JSON; re-verify |
| **schemas** | `src/open_credit_evidence/schemas.py` | Pydantic types: `Case`, `CriticalFact`, `Summary`, `MarkingResult`, `EvidenceReport` |
| **CLI** | `src/open_credit_evidence/cli.py` | `process`, `verify`, `load` (`oce` entrypoint) |
| **cases** | `cases/sample_case_001/`, `cases/sample_case_002/` | Referred application + bureau markdown + `metadata.json` |
| **fixtures** | `tests/fixtures/summaries.py` | Engineering good/bad summaries for pytest |

There is **no RAG module yet**. Week 1 uses `build_context(case)` (full application + bureau in the prompt). Embeddings / vector search come later.

Data flow:

`Case files → loader (fingerprint) → build_context (whole-file) → hosted Nemotron → omission_check → evidence report → tamper verify`

---

## 4. Data contracts (as implemented)

Align with `schemas.py` and sample cases. Taxonomy and canonical fact wording are **open with Sriram** (and Luca for the omission checklist). Do not treat sample `cf_*` ids as locked product language.

### 4.1 Case folder layout

```
cases/<case_slug>/
  metadata.json          # required
  application.md         # typical; name listed in metadata.documents
  bureau_report.md       # typical
```

Loader requires a directory and `metadata.json`. Each `documents[].name` must exist as a sibling file. Extra files not listed are ignored.

### 4.2 `metadata.json`

On disk (sample `cases/sample_case_001/metadata.json`):

| Field | Type | Notes |
|-------|------|--------|
| `case_id` | string | e.g. `LOAN-2026-09-001` |
| `case_type` | string | e.g. `referred_loan_application` |
| `created_at` | ISO-8601 datetime | Parsed by Pydantic |
| `documents[]` | `{name, type, description}` | `type`: `loan_application`, `credit_bureau_report`, … |
| `critical_facts[]` | see below | Decision-critical checklist for this case |
| `referral_reason` | string, optional | Why rules referred it |

**Critical fact object** (`CriticalFact`):

| Field | Type | As-is values |
|-------|------|----------------|
| `id` | string | e.g. `cf_001` — **must be stable**; omission fail is reported by this id |
| `category` | enum | `credit_score`, `delinquency`, `enquiry_pattern`, `debt_to_income`, `credit_utilization`, `debt_pattern`, `payment_behavior`, `employment`, `collateral`, `other` |
| `fact` | string | Human statement the summary must cover |
| `severity` | enum | `critical`, `high`, `medium`, `low` |
| `source` | string | Filename(s), e.g. `bureau_report.md` |
| `evidence_text` | string, optional | Exact span; unused in sample JSON today |

**Open lock (Sriram):** category list, severity policy, and the exact fact statements that “fail by name” in the demo. Sample cases are engineering stand-ins.

After load, the in-memory `Case` adds:

- `documents`: map filename → `CaseDocument` with `content` and per-file SHA-256 `fingerprint`
- `fingerprint`: combined SHA-256 of sorted document fingerprints
- `loaded_at`: UTC timestamp

### 4.3 Summary shape (`Summary`)

| Field | Type | Notes |
|-------|------|--------|
| `case_id` | string | Must match the case |
| `text` | string | Free-text summary (not JSON today) |
| `model` | string | e.g. `nvidia/nemotron-3.5-lightning-30b-a3b`, or `stub` / `skipped` |
| `generated_at` | datetime | UTC |
| `prompt_tokens` / `completion_tokens` | int, optional | From API usage if present |

Grounded JSON summaries are a later RAG contract, not implemented.

### 4.4 Marking result (`MarkingResult`)

One `OmissionResult` per critical fact:

| Field | Type | Notes |
|-------|------|--------|
| `fact_id` | string | Same as metadata `id` — **this is the named fail** |
| `fact` | CriticalFact | Copy of the fact |
| `is_present` | bool | Keyword hit rate ≥ `confidence_threshold` (default `0.5`) |
| `confidence` | float 0–1 | `matched_keywords / extracted_keywords` |
| `matched_text` | string, optional | Snippet from the summary |
| `reason` | string | Why present/absent |

Aggregate:

| Field | Type | Pass rule (as-is) |
|-------|------|-------------------|
| `total_facts` / `facts_present` / `facts_omitted` | int | Counts |
| `omission_rate` | float | `facts_omitted / total_facts` |
| `passed` | bool | `omission_rate == 0` **and** no omitted fact with severity `critical` when `require_all_critical=True` (default) |
| `summary_fingerprint` | SHA-256 of summary text | |
| `checked_at` | datetime | |

### 4.5 Evidence report (`EvidenceReport`)

| Field | Notes |
|-------|--------|
| `report_id` | `EVR-YYYYMMDD-<8 hex>` |
| `case_id`, `case_fingerprint` | Frozen case identity |
| `summary`, `marking_result` | Nested objects |
| `chain_fingerprint` | SHA-256 of `case_fp \| summary_fp \| marking_fp` |
| `metadata` | Free dict |

Verify recomputes the chain; mismatch raises tamper error.

---

## 5. Runtime

**Primary runtime:** local machine (Python 3.11+ venv) or **Docker Compose** (`docker-compose.yml`, `app` service only). CLI — no published ports, no HTTP health URL. Details: [`docs/runtime.md`](docs/runtime.md).

**Model inference:** hosted NVIDIA Build, OpenAI-compatible `POST /chat/completions`. Model: `nvidia/nemotron-3.5-lightning-30b-a3b`. Context is **whole-file** (`build_context`). Not self-hosted. Not Curiosity. Embeddings later.

**Origin:** source control only, not a deploy target.

**CI later:** GitHub Actions (pytest) after Algoritmica GitHub upstream. No workflow in this repo yet.

**Axis / Curiosity:** optional compute for experiments. They do **not** host this engine as an HTTP app.

**NVIDIA Build env** (see `.env.example`):

| Variable | Purpose |
|----------|---------|
| `NEMOTRON_BASE_URL` | Default `https://integrate.api.nvidia.com/v1` |
| `NVIDIA_API_KEY` | Secret — never commit |
| `NEMOTRON_MODEL` | Default `nvidia/nemotron-3.5-lightning-30b-a3b` |
| `NEMOTRON_ENABLE_THINKING` | Default off — thinking tokens can muddy omission checks |
| `OCE_STUB_NEMOTRON` | Force stub (pytest sets this) |
| `EVIDENCE_VERIFICATION_MODE` | Declared; `strict` vs `permissive` — not yet wired in checker |
| `LOG_LEVEL` | Logging |

Without a key, the runner returns a stub summary (omission will fail). Live call:

```bash
cp .env.example .env   # set NVIDIA_API_KEY
python -m open_credit_evidence.cli process cases/sample_case_001/ -o reports/case_001_report.json
```

---

## 6. Week 1 technical definition of done

Ends **Wed 16 Sep 2026**. Technical bar (not the Google Doc roster):

1. **Twenty cases** in `cases/` run loader → summary → omission → evidence end-to-end (CLI or batch). Two samples exist today; remaining eighteen are Sriram/Clyde intake.
2. **Deliberately bad summary fails by named fact** — deterministic: pytest asserts omitted `fact_id` (e.g. `cf_002` delinquency, `cf_003` enquiry). Not an LLM judge.
3. **Evidence fingerprints** — load refuses tampered inputs; `verify` refuses a mutated report.
4. **Whole-file context** — concatenate application + bureau into the Nemotron prompt. Embeddings / RAG later.

---

## 7. Deliberately bad summary

`tests/fixtures/summaries.py` holds **engineering stand-ins**: fluent, mostly true copy that drops a named fact (delinquency, Kotak enquiry, utilisation, multi-lender enquiries). Pytest uses these to prove the checker.

**Luca owns canonical hand-written demo copy** for the live/demo “bad summary.” Do not treat fixture prose as the regulatory or demo-final wording.

---

## 8. How to run

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # add NVIDIA_API_KEY for live NVIDIA Build calls

pytest

# Inspect fingerprints and facts
python -m open_credit_evidence.cli load cases/sample_case_001/

# Full pipeline with NVIDIA Build (set NVIDIA_API_KEY). Stub if no key → omission FAIL expected.
python -m open_credit_evidence.cli process cases/sample_case_001/ -o reports/case_001_report.json

# Recompute chain hashes
python -m open_credit_evidence.cli verify reports/case_001_report.json
```

Equivalent: `oce load|process|verify` after install. `--skip-api` on `process` skips Nemotron (placeholder text; omission fails). Omission pass/fail for the demo is proven in `pytest`, not by the stub CLI summary.

Optional container:

```bash
docker compose up --build
docker compose run --rm app pytest -v
```

---

## 9. Open technical decisions

| Decision | Owner | Status |
|----------|--------|--------|
| Embeddings model | Sriram | Later — Week 1 is whole-file |
| Vector store | Clyde | Later; local first when RAG starts |
| Omission checklist content (what must appear) | Luca | Blocks Sriram marking |
| Critical-fact taxonomy and demo `fact_id`s | Sriram | Sample JSON is a stand-in |
| Live NVIDIA Build wiring / model id | Clyde | Whole-file client: `nvidia/nemotron-3.5-lightning-30b-a3b` |
| Assistant vs search vs (later) judge models | Sriram | Hosted Nemotron family only; no Week 1 judge |
| Optional Axis/Curiosity GPU jobs | Clyde | Experiments only — not an app host |
| Evidence package storage | Clyde | Local JSON artifacts → later object store |
| Docker Compose extra services | Clyde | `app` CLI service exists; vector store later |

---

## 10. Pointers

| Doc | Use for |
|-----|---------|
| **This file (`BUILD.md`)** | Technical spec — contracts, components, DoD, how to run |
| [`docs/design-note.md`](docs/design-note.md) | Two-pager system design (models, RAG, safety, data flow) — outlines |
| [`docs/week1-design-outline.md`](docs/week1-design-outline.md) | Week 1 outline (problem, safety, optional compute, open calls) |
| [`docs/runtime.md`](docs/runtime.md) | How to run: venv, Compose, NVIDIA env; Axis is not a host |
| **Google Doc 4-week plan** | Schedule and who does what **only** — not the spec |

Stretch (not this spec): **pitch architecture** / OpenShift DataMesh+CFM deploy design. If a hardened cluster bar is needed later, that is the **data-product OpenShift bar** — out of this file.
