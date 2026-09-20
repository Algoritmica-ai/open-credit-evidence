# Model selection

Three models: the assistant under test, the judge, and the embedder. Exact ids are
in `src/evidence/adapters/nvidia_build.py`. Each is served from NVIDIA Build by
default; any role can be moved to a self-hosted NIM with two environment variables
(`EVIDENCE_<ROLE>_BASE_URL`, `EVIDENCE_<ROLE>_MODEL`). Nemotron 3 Super is
excluded because its free endpoint is deprecated on 2 October 2026.

## Assistant under test — Nemotron 3.5 Lightning (`nvidia/nemotron-3.5-lightning-30b-a3b`)

- 30B total, 3B active, 1M context, released August 2026. Cheap enough per call that we
  can run the full pack many times in a Codefest afternoon, which matters more than peak
  quality for an instrument we are calibrating.
- Catalogue description: "leading domain accuracy for specialized agentic tasks". The
  assistant is exactly that shape: retrieve from the case file, reason over it, produce
  a structured briefing.
- Not Super. Super's free endpoint carries a deprecation notice for 2 October 2026. Building
  the demo on a model that disappears five days before we present it is not a risk worth
  taking, and Lightning is the newer model anyway.

## Judge — Nemotron 3 Ultra (`nvidia/nemotron-3-ultra-550b-a55b`)

- **Must not be the model under test.** A model grading its own output is the first
  objection a validator raises, and it is a free objection to remove.
- 550B mixture-of-experts reasoning model. A larger model judging a smaller one is
  the defensible direction; the reverse invites "the judge is worse than the thing
  it grades".
- Same family as the assistant, which keeps the whole stack on Nemotron for the
  event without compromising independence — different weights, different scale,
  different training run.

The judge grades only what exact comparison cannot reach: whether the briefing is
intelligible to an underwriter and whether the underwriter can tell what would need
to change. Everything else is a deterministic check. The judge ships with its
agreement study or it does not ship.

## Embedding model — for retrieval over the case file

- `nvidia/nemotron-3-embed-1b` — the Nemotron Retriever line, free endpoint. It requires
  an `input_type` of `passage` when indexing and `query` when searching; the catalogue
  warns that getting this wrong costs retrieval accuracy badly, so the adapter refuses
  anything else.
- The case file is two short documents. Retrieval is not a hard problem here; the
  point of RAG is that the assistant *selects* what to read rather than being handed
  everything, because that is how it fails in production.
- Log what was retrieved for every item from day one. If retrieval drops the
  paragraph with the debt-service ratio, the assistant omits it for a reason that
  has nothing to do with the model, and we have to be able to tell the two apart.

## What this is not

Not a model comparison. One assistant, one judge, one embedder. A second
assistant is a configuration change, not a code change.
