# Architecture

## Purpose

Banks refer loan applications their rules cannot auto-decide to a human
underwriter. An AI assistant may draft the briefing that person relies on. The
assistant does not decide the loan; it shapes what the underwriter sees.

A briefing can be fluent, correct in its conclusion, and still dangerous if it
leaves out the fact the decision turns on or states a number that is not in the
file. This system is an instrument for catching those failures by name, without
asking another model to judge them, and for producing a record a second-line
reviewer can inspect and re-derive.

Cases are generated from a declared process so the material facts are known
before the assistant is asked anything. That sealed knowledge is what makes
omission and fidelity checking possible.

## Parts

| Part | Module | Responsibility |
|---|---|---|
| Case generation | `src/evidence/packs/`, `specs/` | Generate applications, decide them with a scorecard, attribute drivers and decoys, render documents, emit a pack |
| Contracts | `src/evidence/contracts/` | The item, the transcript, the check result, the regulatory context and assessment |
| Checks | `src/evidence/checks/` | Deterministic marking against the item's reference lists; no model in the verdict |
| Model access | `src/evidence/adapters/` | One client for NVIDIA Build and any OpenAI-compatible NIM; retrieval over the case file |
| Runner | `src/evidence/runner.py` | Items × repeats → transcripts; resumable; writes the run manifest |
| Judge | `src/evidence/judge.py` | Readability only; reported, not gated |
| Regulations | `src/evidence/regulations.py`, `regulations/` | Jurisdiction rule packs: evidence-presence checks selected by the pack's regulatory context |
| Evidence | `src/evidence/evidence/` | Aggregation by obligation, the report, checksums, the verifier |
| CLI | `src/evidence/cli.py` | `evidence run · report · verify · rules · checks · ui` |
| Web UI | `src/evidence/web/` | A thin FastAPI layer over the same functions; static HTML, no build step. Pack → cases → run → evidence → verify; packs can be built from a spec or uploaded; runs execute on a worker thread, are polled, and can be cancelled |

Generation never scores briefings. Marking never invents what "material"
means. Model access never sees scorecard internals — only the documents and the
task.

## Flows

### Build a pack

```
declared credit process (SDD spec)
    → synthetic applications
    → deterministic scorecard
    → keep the referred cases
    → attribute drivers / decoys / omission targets / flip levers
    → render application + bureau report + lending policy
    → items.jsonl + manifest + obligations map (+ regulatory context)
```

Each item carries the prompt, the documents, which checks apply, and the
reference lists those checks resolve against. Threshold maths, contributions
and margins stay in a gitignored answer key.

### The gate, no model

```
one item → its documents → what a briefing must surface
    → briefing A: every word true, deciding fact omitted
    → briefing B: deciding fact surfaced
    → material_omission on each → pass / fail, which refs were found
```

`scripts/demo_gate.py`. Nothing here calls a model; the catch is comparison
against known required facts.

### A run

```
pack × repeats
    → assistant call per (item, repeat), recorded as a transcript
    → every declared check on the output → results.jsonl
    → readability judge on the output → results.jsonl (not gated)
    → jurisdiction rule pack on the regulatory context → regulations.json
    → manifest: pack sha, model ids, endpoints, prompt hashes, seeds, git commit
    → evidence/: report by obligation, summary, obligations map
    → checksums.sha256 over everything
```

A transcript that already exists is reused, so a killed run continues and a
finished run re-scores without model calls. When retrieval is used, the
transcript records what was retrieved, so an omission after a missed paragraph
is attributable to retrieval rather than to the model.

### Verify

```
checksums.sha256 → every file re-hashed; missing, changed and unlisted files named
--recompute       → every deterministic check re-run from the transcripts and
                    compared with results.jsonl
```

## Marking a briefing

```
briefing text + item
    → for each named check
        → resolve against the item's reference lists
        → uniform result: passed, score, detail, evidence, needs_audit
```

| Check | Question | Passes when |
|---|---|---|
| `material_omission` | Did it state every fact the decision turned on? | All required facts found: exact, or by constrained similarity (flagged for audit) |
| `numeric_fidelity` | Is every number in the briefing in the file, or one arithmetic step from it? | No ungrounded number |
| `decoy_citation` | Did it cite a zero-weight field as a reason? | No decoy in a sentence with a reasoning cue |
| `flip_accuracy` | Did it name what would change the outcome, and which way? | Every flip lever named with its direction |

Further checks register the same way: name on the item → function → uniform
result.

## Design rules

1. Omission is arithmetic, not judgement.
2. Selection is observable: what the assistant read is part of the transcript.
3. Soft matches are counted and flagged, never hidden.
4. One instrument, two briefing sources: hand-written controls and live model
   output face the same checks.
5. Local and offline first: pack build, the gate, marking and verification run
   without a network; models are the one stage that needs one.
6. The judge never grades completeness or correctness.
