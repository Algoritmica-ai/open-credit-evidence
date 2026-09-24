# For an auditor — how to check this evidence pack

Assistant `nvidia/nemotron-3.5-lightning` (on-prem) · 60 briefings: 20 referred loan cases × 3 · pack `underwriter-sample` v0.3.0 · run `2026-09-20-onprem` · model calls 2026-09-20

## What is in the run

| file | what it is | how it is checked |
|---|---|---|
| `transcripts/*.json` | one model call each: prompts, parameters, output, tokens, latency | record — integrity only |
| `results.jsonl` | 300 deterministic check results and 60 judge opinions | checks re-derived from the transcripts; judge opinions integrity only |
| `manifest.json` | what ran: pack, models, endpoints, engine commit, times | record — integrity only |
| `regulations.json` | the lender's rule-pack assessment | integrity only |
| `evidence/obligations.yaml`, `evidence/thresholds.yaml` | the pack's claims and the bank's thresholds — inputs | integrity only |
| `evidence/*.json`, `evidence/report.md`, `evidence/readers/*.md` | everything derived from the above | rebuilt byte for byte |
| `checksums.sha256` | a SHA-256 for every file above | — |

## How to check it

1. `evidence verify runs/<run>` — every file hashes to its recorded value; nothing is missing and nothing has been added. One changed digit fails this and names the file.
2. `evidence verify runs/<run> --recompute --pack packs/underwriter-sample` — runs every deterministic check again from the transcripts (300 results) and rebuilds every derived file, naming the first value that differs. Someone who edits a number *and* re-seals the checksums still fails here.
3. The web UI's tamper demo does step 1 on a copy with one digit changed.

## What cannot be re-derived

- The transcripts: they are what the model returned. They can be shown unchanged, not reproduced — serving is not byte-deterministic.
- The judge's opinions: the same, and they never decide pass or fail.

## Identifiers

- Engine commit `3f8c89d`; pack `underwriter-sample` v0.3.0, items sha256 `d249c1f217beb7e73bb4687f6e2304639c4940369f6262b856461c8545fed710`.
- SDD spec hash `5a827b5de979bad9`, seed 7.
- Regulation corpus sha256 `—`; rule pack `IT-CREDIT-LENDING` sha256 `f547b8e333fed05408151120ec9279c062bf8b505915c9781e1854eeb3d02c63`.
- Model calls 2026-09-20T09:01:32+00:00 to 2026-09-20T09:32:03+00:00; checks scored 2026-09-24T01:36:53+00:00.

## The other reports

- **Business** (Head of lending, product owner): `evidence/readers/business.md`
- **Credit risk** (Model risk, second line): `evidence/readers/credit-risk.md`
- **Compliance** (Compliance and legal): `evidence/readers/compliance.md`
- **Underwriting operations** (Underwriters and team leads): `evidence/readers/operations.md`
- **Vendor** (Whoever supplies the assistant): `evidence/readers/vendor.md`
- **Everything**, by obligation: `evidence/report.md`
