# For an auditor — how to check this evidence pack

Assistant `nvidia/nemotron-3.5-lightning` (on-prem) · 60 briefings: 20 referred loan cases × 3 · pack `underwriter-sample` v0.5.0 · run `2026-09-24-onprem-nims` · model calls 2026-09-24

## What is in the run

| file | what it is | how it is checked |
|---|---|---|
| `transcripts/*.json` | one model call each: prompts, parameters, output, tokens, latency | record — integrity only |
| `results.jsonl` | 360 deterministic check results and 60 judge opinions | checks re-derived from the transcripts; judge opinions integrity only |
| `manifest.json` | what ran: pack, models, endpoints, engine commit, times | record — integrity only |
| `regulations.json` | the lender's rule-pack assessment | integrity only |
| `evidence/obligations.yaml`, `evidence/thresholds.yaml` | the pack's claims and the bank's thresholds — inputs | integrity only |
| `evidence/*.json`, `evidence/report.md`, `evidence/readers/*.md` | everything derived from the above | rebuilt byte for byte |
| `checksums.sha256` | a SHA-256 for every file above | — |

## How to check it

1. `evidence verify runs/<run>` — every file hashes to its recorded value; nothing is missing and nothing has been added. One changed digit fails this and names the file.
2. `evidence verify runs/<run> --recompute --pack packs/underwriter-sample` — runs every deterministic check again from the transcripts (360 results) and rebuilds every derived file, naming the first value that differs. Someone who edits a number *and* re-seals the checksums still fails here.
3. The web UI's tamper demo does step 1 on a copy with one digit changed.

## What cannot be re-derived

- The transcripts: they are what the model returned. They can be shown unchanged, not reproduced — serving is not byte-deterministic.
- The judge's opinions: the same, and they never decide pass or fail.

## Model fingerprints

Which model, exactly, served each role: a SHA-256 over what the server reports about itself (serving version; for a NIM its build, active profile and every file's checksum) and what the node recorded (container image digest, serving arguments, Hugging Face commit and the SHA-256 of every weights file). The components are in `manifest.json` under `models`; the fingerprint is the SHA-256 of their JSON with sorted keys.

| role | fingerprint | level | pins |
|---|---|---|---|
| assistant | `1869632eafca897436984f33787f7a00bdb65e00462c86c6abb7ba9d15ee7e15` | weights | NIM 2.0.9-variant; build hf-3db7814; profile vllm-int4-tp1-pp1-32.0; 64 weight files hashed; engine 0.25.1; image sha256:c2b2138e056d… |
| judge | `2ce965d0466dc6382ab3556718f4f14c90e49da78282f25dcfa15bcfbefc2359` | weights | NIM 1.12.2; profile vllm-bf16-tp1-pp1-a145c9d12f9b03e9fc7df170aad8b83f6cb4806729318e76fd44c6a32215f8d5; 22 weight files hashed; image sha256:a2f4a5aefe7d… |
| embed | `ed2942bb7c71b8fbe8bb7fdf3946e96c714c475c1f7e8535afaca6d0645cc042` | weights | NIM 2.2.2; build nvidia/nemotron-3-embed-1b; HF commit 1d46dbbb2e; 18 weight files hashed; image sha256:16f49c13bc9e… |

## Identifiers

- Engine commit `0e40231`; pack `underwriter-sample` v0.5.0, items sha256 `79ecdc7a23fad846312effe17f94e62d23cec3c518281d4888b63ace17361beb`.
- SDD spec hash `5a827b5de979bad9`, seed 7.
- Regulation corpus sha256 `4cec98282f8332085eb68735dd75512f94be86fe648c21aac15ed9f34892d83b`; rule pack `IT-CREDIT-LENDING` sha256 `f547b8e333fed05408151120ec9279c062bf8b505915c9781e1854eeb3d02c63`.
- Model calls 2026-09-24T09:23:54+00:00 to 2026-09-24T09:37:03+00:00; checks scored 2026-09-24T09:37:03+00:00.

## The other reports

- **Business** (Head of lending, product owner): `evidence/readers/business.md`
- **Credit risk** (Model risk, second line): `evidence/readers/credit-risk.md`
- **Compliance** (Compliance and legal): `evidence/readers/compliance.md`
- **Underwriting operations** (Underwriters and team leads): `evidence/readers/operations.md`
- **Vendor** (Whoever supplies the assistant): `evidence/readers/vendor.md`
- **Everything**, by obligation: `evidence/report.md`
