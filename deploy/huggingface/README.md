---
title: Credit Evidence Engine
emoji: 🧾
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
short_description: Evidence that an AI assistant told the underwriter what mattered
---

# Credit Evidence Engine

Tests an AI assistant that compiles a loan case file for a human underwriter,
and produces the evidence a validator or supervisor needs to approve it: did the
briefing state the facts the decision turned on, are its numbers in the file,
did it lean on an irrelevant field, did it say what would change the outcome.
The right answer is known before the model runs, because the cases are
generated; every check is a comparison, not an opinion. A judge model grades
readability against the EU AI Act passage it retrieves and must cite — and is
reported, not gated.

**This is a hosted, shared demo.** The models run on NVIDIA Build, not on your
hardware; runs are capped at 5 cases × 2 repeats; anything you upload or run is
visible to other visitors and wiped when the Space restarts. Two committed runs
of the sample pack — one on NVIDIA Build, one on the team's own GPU node — are
included, sealed, and verifiable here: open one under **Evidence**, then
**Verify** re-hashes every file and re-derives every check from the transcripts,
and the tamper demo changes one digit in a copy and shows the verifier reject it.

To evaluate an assistant on your own GPU, install it locally:

```bash
git clone https://github.com/Algoritmica-ai/open-credit-evidence.git
cd open-credit-evidence && python3 -m venv .venv && .venv/bin/pip install -e ".[web]"
.venv/bin/evidence ui
```

Source, documentation and the evidence packs: <https://github.com/Algoritmica-ai/open-credit-evidence>.
Built for the NVIDIA Open Models Codefest by Sriram Krishnan, Clyde Tedrick and
Luca Borella (Algoritmica). Apache 2.0.
