# For an auditor — how to check this evidence pack

Assistant `nvidia/nemotron-3.5-lightning` (on-prem) · 60 briefings: 20 referred loan cases × 3 · pack `underwriter-de` v0.6.0 · run `2026-09-25-de` · model calls 2026-09-25

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
2. `evidence verify runs/<run> --recompute --pack packs/underwriter-de` — runs every deterministic check again from the transcripts (360 results) and rebuilds every derived file, naming the first value that differs. Someone who edits a number *and* re-seals the checksums still fails here.
3. The web UI's tamper demo does step 1 on a copy with one digit changed.

## What cannot be re-derived

- The transcripts: they are what the model returned. They can be shown unchanged, not reproduced — serving is not byte-deterministic.
- The judge's opinions: the same, and they never decide pass or fail.

## Model fingerprints

Which model, exactly, served each role: a SHA-256 over what the server reports about itself (serving version; for a NIM its build, active profile and every file's checksum) and what the node recorded (container image digest, serving arguments, Hugging Face commit and the SHA-256 of every weights file). The components are in `manifest.json` under `models`; the fingerprint is the SHA-256 of their JSON with sorted keys.

| role | fingerprint | level | pins |
|---|---|---|---|
| assistant | `1869632eafca897436984f33787f7a00bdb65e00462c86c6abb7ba9d15ee7e15` | weights | NIM 2.0.9-variant; build hf-3db7814; profile vllm-int4-tp1-pp1-32.0; 64 weight files hashed; engine 0.25.1; image sha256:c2b2138e056d… |
| judge | `50b3265fb2c0eb7584995d76d592e76ce0e5229dce108843ea016c3e3e35d074` | weights | NIM 2.0.13; build rl-030326-fp8; profile vllm-fp8-tp2-pp1-65.0; 39 weight files hashed; engine 0.28.0; image sha256:d56c72bdbb53… |
| embed | `ed2942bb7c71b8fbe8bb7fdf3946e96c714c475c1f7e8535afaca6d0645cc042` | weights | NIM 2.2.2; build nvidia/nemotron-3-embed-1b; HF commit 1d46dbbb2e; 18 weight files hashed; image sha256:16f49c13bc9e… |

## Identifiers

- Engine commit `8cfae73`; pack `underwriter-de` v0.6.0, items sha256 `f5a04a502d89ad875cfa82aa760eca7b914ec25878e2dca970d846756d471826`.
- SDD spec hash `5a827b5de979bad9`, seed 7.
- Regulation corpus sha256 `4a7d4f6c5717220557107a6cb7760a41e9cd2b2431e89bf76625fef44064b523`; rule pack `DE-CREDIT-LENDING` sha256 `e47e562381d65fbd945bfcf56fbc4e0b9554f87dd410b47b6566318ebaa4e5f7`. The embedder reproduced the index before the first call (cosine 1.0 on `ai-act-art-9#1`). 55/55 passages found verbatim in CELEX:02024R1689-20260727 + CELEX:32023L2225 (checked 2026-09-24).
- Model calls 2026-09-25T02:33:22+00:00 to 2026-09-25T02:46:06+00:00; checks scored 2026-09-25T02:46:06+00:00.

## The other reports

- **Business** (Head of lending, product owner): `evidence/readers/business.md`
- **Credit risk** (Model risk, second line): `evidence/readers/credit-risk.md`
- **Compliance** (Compliance and legal): `evidence/readers/compliance.md`
- **Underwriting operations** (Underwriters and team leads): `evidence/readers/operations.md`
- **Vendor** (Whoever supplies the assistant): `evidence/readers/vendor.md`
- **Everything**, by obligation: `evidence/report.md`
