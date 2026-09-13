# Week 1 design note outline — Credit Evidence Engine (4-week plan)

Status: outline for Clyde's two-pager. Axis cluster claimed: `omc-termh`. Curiosity v2 docs = HPC only (Slurm/K8s/Jupyter); hosted NVIDIA Build remains the Nemotron path.

## 1. Problem / DoD
- Input: referred loan application the bank's rules could not decide.
- Output: underwriter-facing package with retrieval, omission checks, evidence report, and tamper-check.
- Week 1 bar (Wed 16 Sep): twenty cases E2E; deliberately bad summary fails omission check by name.

## 2. Models
- Hosted Nemotron only (NVIDIA Build / Codefest credits).
- Reference model link posted in Slack: https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b
- Embeddings: pick-one (open call).
- No own CFM / no in-cluster model serving on the critical path.

## 3. Search / RAG
- Normalize case docs → top-k retrieval with citations → grounded JSON summary.
- Frozen corpus hash per case (loader fingerprints already in scaffold).
- Record what retrieval returned for every case (separate RAG miss vs model omission).

## 4. Safety
- Grounding to retrieved spans.
- Omission checklist (Luca owns "what must be in a summary").
- PII / redaction — synthetic cases only for demo.
- Untrusted retrieval; no instruction-following from case text (prompt-injection test = Week 3 stretch).
- Secrets via env (`.env.example`); never commit keys.
- Tamper hashes on evidence package (scaffold `evidence.py`).

## 5. Data flow
`Case files → loader (fingerprint) → RAG → hosted Nemotron → omission_check → evidence report → tamper verify`

Optional later: Axis / Curiosity GPU job for local experiments only — not required for Week 1 DoD.

## 6. Axis one-screen slice
- Portal: https://axis-raplabhackathon.axisportal.io/apps (Event `omc-2026`, cluster `omc-termh`).
- Apps visible: Curiosity v2 Doc, Curiosity Hub, Curiosity-v2-login.
- Curiosity docs: https://curioisty-v2-doc-raplabhackathon.axisapps.io/ — HPC (Slurm, Enroot, Apptainer, rootless Docker, K8s `$USER-restricted`, JupyterHub). No app-push / Nemotron API docs there.

## 7. Non-goals → pitch architecture / OpenShift DataMesh+CFM deploy design (stretch)
- OpenShift DataMesh (Iceberg/Trino/Hive), CFM score API, in-cluster Nemotron ServingRuntime, Marquez, Airflow.
- Repo archive: `zaga-products/opencredit-evidence` (frozen).

## 8. Open calls
| Call | Owner | Notes |
|---|---|---|
| Embeddings model | Sriram | By Fri 11 Sep per plan |
| Vector store | Clyde | Local first; defer managed |
| Omission checklist content | Luca | Blocks Sriram marking |
| Axis contract / deploy surface | Clyde | Beyond HPC docs |
| Evidence package storage | Clyde | Local artifacts → later object store |
| Assistant / judge / search model picks | Sriram | Hosted Nemotron family |

## Scaffold pointer
Python package already on this Origin repo: loader, runner stub, omission_check, evidence/tamper, sample cases, 47 tests. Expand RAG + live Nemotron client next; do not rebuild OpenShift path for Week 1.
