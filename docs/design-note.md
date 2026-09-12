# OpenCredit Evidence — System Design Note

**Author:** Clyde (Backend/RAG/Evidence)  
**Status:** Draft v0.1  
**Last Updated:** September 2026

---

## 1. Executive Summary

OpenCredit Evidence is a credit decision verification system that ensures AI-generated loan application summaries contain all decision-critical facts from source documents. The system detects omissions that could lead to incorrect lending decisions.

---

## 2. Problem Statement

When summarizing referred loan applications, AI systems may:
- Omit negative credit indicators buried in lengthy bureau reports
- Miss conditional approvals or restrictions in application notes
- Fail to surface debt-to-income ratio concerns
- Overlook recent credit inquiries or delinquencies

**Goal:** Detect when a summary is "fluent and true" but missing critical decision factors.

---

## 3. System Architecture

### 3.1 Component Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     OpenCredit Evidence                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐     │
│  │  Loader  │──▶│  Runner  │──▶│ Omission │──▶│ Evidence │     │
│  │          │   │          │   │  Check   │   │  Report  │     │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘     │
│       │              │              │              │            │
│       ▼              ▼              ▼              ▼            │
│  Fingerprint    Nemotron API   Fact Matching   Tamper Proof    │
│  Verification   (NVIDIA Build) (RAG-based)     Generation      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Data Flow

<!-- TODO: Detailed sequence diagram -->

1. **Ingestion:** Load case documents (application + bureau report)
2. **Fingerprinting:** Generate cryptographic hash of source documents
3. **Summarization:** Send to Nemotron via NVIDIA Build API
4. **Fact Extraction:** Extract critical facts from source using RAG
5. **Omission Detection:** Verify summary contains all critical facts
6. **Report Generation:** Produce evidence report with tamper-proof chain

---

## 4. Models and AI Components

### 4.1 Primary Model: NVIDIA Nemotron

- **Endpoint:** NVIDIA Build hosted API
- **Model:** nemotron-4-340b-instruct (or latest available)
- **Use Case:** Summary generation and fact extraction
- **Constraint:** No self-hosted models on critical path (Mentor guidance)

### 4.2 RAG Pipeline

<!-- TODO: Specific RAG blueprint from NVIDIA to use -->

- **Retrieval:** Document chunking and vector similarity
- **Augmentation:** Critical fact context injection
- **Generation:** Focused omission-aware prompting

### 4.3 Critical Fact Categories

| Category | Examples | Priority |
|----------|----------|----------|
| Credit Score | CIBIL score, score band | P0 |
| Delinquencies | DPD history, write-offs | P0 |
| Debt-to-Income | Existing EMIs, obligations | P0 |
| Recent Inquiries | Hard pulls in last 6 months | P1 |
| Employment | Stability, income verification | P1 |
| Collateral | LTV ratio, valuation concerns | P1 |

---

## 5. Search and RAG Strategy

### 5.1 Document Processing

<!-- TODO: Chunking strategy -->

### 5.2 Embedding Model

<!-- TODO: Which embedding model for retrieval -->

### 5.3 Retrieval Configuration

<!-- TODO: Top-k, similarity threshold, reranking -->

---

## 6. Safety and Verification

### 6.1 Tamper Detection

- SHA-256 fingerprints for all source documents
- Chained hashes in evidence report
- Verification before any processing

### 6.2 Audit Trail

- Immutable log of all processing steps
- Timestamps and model versions recorded
- Reproducibility guarantee

### 6.3 Failure Modes

| Failure | Detection | Response |
|---------|-----------|----------|
| Tampered input | Hash mismatch | Reject processing |
| API timeout | Connection error | Retry with backoff |
| Missing critical fact | Omission check fail | Flag for human review |
| Confidence below threshold | Score check | Escalate to senior analyst |

---

## 7. Data Flow and Privacy

### 7.1 Data Classification

- **PII:** Applicant names, addresses, IDs → Masked in logs
- **Financial:** Account numbers, balances → Encrypted at rest
- **Scores:** Credit scores, ratings → Retained for audit

### 7.2 Data Retention

<!-- TODO: Define retention policy with Luca (regulatory) -->

---

## 8. Deployment Architecture

### 8.1 Week 1: Local Development

- Python CLI tool
- Local file-based case storage
- Direct NVIDIA API calls

### 8.2 Week 2+: Axis Portal

- See `deploy-axis.md` for deployment guide
- Target: `https://axis-raplabhackathon.axisportal.io/apps`

---

## 9. Open Questions

1. [ ] Which specific NVIDIA RAG blueprint to adopt?
2. [ ] Exact critical fact taxonomy (confirm with Sriram)
3. [ ] Confidence threshold for omission detection
4. [ ] Integration pattern with existing loan origination systems
5. [ ] Data retention requirements (confirm with Luca)

---

## 10. References

- NVIDIA Build: https://build.nvidia.com/
- Nemotron documentation: https://docs.nvidia.com/nemotron/
- RAG blueprints: <!-- TODO: Add specific blueprint URL -->

---

*This document is a living design note. Update as decisions are made.*
