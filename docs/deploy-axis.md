# Deploying to Axis Portal

**Target Environment:** `https://axis-raplabhackathon.axisportal.io/apps`  
**Status:** Stub — Week 2+ implementation

---

## Overview

This document describes deployment of OpenCredit Evidence to the Axis hackathon portal.

---

## Prerequisites

<!-- TODO: Confirm requirements with Axis portal team -->

- [ ] Axis portal account and API credentials
- [ ] Application registration in portal
- [ ] Network access from portal to NVIDIA Build API
- [ ] SSL certificates (if required)

---

## Deployment Steps

### 1. Package Application

```bash
# Build distribution
python -m build

# Or create container
docker build -t open-credit-evidence:latest .
```

### 2. Configure Environment

```bash
# Set production environment variables
export NEMOTRON_BASE_URL=https://integrate.api.nvidia.com/v1
export NEMOTRON_API_KEY=<production-key>
export EVIDENCE_VERIFICATION_MODE=strict
```

### 3. Deploy to Portal

<!-- TODO: Axis-specific deployment commands -->

```bash
# Placeholder for Axis deployment CLI
# axis deploy --app open-credit-evidence --env production
```

### 4. Verify Deployment

```bash
# Health check
curl https://axis-raplabhackathon.axisportal.io/apps/open-credit-evidence/health

# Smoke test
curl -X POST https://axis-raplabhackathon.axisportal.io/apps/open-credit-evidence/verify \
  -H "Content-Type: application/json" \
  -d '{"case_id": "test_001"}'
```

---

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `NEMOTRON_BASE_URL` | Yes | NVIDIA API endpoint |
| `NEMOTRON_API_KEY` | Yes | API authentication |
| `EVIDENCE_VERIFICATION_MODE` | No | `strict` or `permissive` |
| `LOG_LEVEL` | No | Logging verbosity |

### Secrets Management

<!-- TODO: How does Axis handle secrets? -->

---

## Monitoring

### Health Endpoints

- `/health` — Basic liveness check
- `/ready` — Readiness with dependency checks
- `/metrics` — Prometheus metrics (if enabled)

### Logging

<!-- TODO: Axis logging integration -->

---

## Rollback Procedure

<!-- TODO: Document rollback steps -->

---

## Troubleshooting

### Common Issues

| Issue | Cause | Resolution |
|-------|-------|------------|
| 502 Bad Gateway | App not running | Check container logs |
| API timeout | NVIDIA rate limit | Implement backoff |
| Auth failure | Invalid API key | Rotate credentials |

---

## Contact

- **Axis Portal Support:** <!-- TODO: Contact info -->
- **Team Lead:** Clyde (Backend/Deploy)

---

*This document will be completed during Week 2 deployment phase.*
