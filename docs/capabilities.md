# The capability checker (NVIDIA NeMo Evaluator)

A credit memo test shows how the assistant does at its job. Before a changed or fine-tuned
assistant replaces the current one, two more questions need answers:

1. **Did the change break anything else?** A model tuned on credit memos could get worse at
   arithmetic or at German.
2. **Is the improvement real, or run-to-run noise?**

The capability checker answers both with NVIDIA's open-source
[NeMo Evaluator](https://github.com/NVIDIA-NeMo/Evaluator) (`nel`), and keeps each result in a
sealed, anchored folder. It is standalone: the engine does not depend on it, and NeMo
Evaluator runs in its own Python environment.

## What it measures

| Capability | Benchmark | Why |
|---|---|---|
| Arithmetic | `gsm8k` | The assistant's main weakness in our tests |
| Maths in eleven languages, German included | `mgsm` | Our cases are German; the report gives German alone |
| Knowledge and reasoning | `mmlu-pro` | General ability across 14 subjects |
| Credit memos | `credit-memo` | Our case set: the six checks decide each memo; a judge (Nemotron 3 Super) scores its usefulness to an underwriter, 1–5, beside them |

The model is measured as the engine runs it: temperature 0 and, for Nemotron models, thinking
switched off.

**The judge never decides.** It's recorded next to the checks, and the report counts where the
two disagree:
- **Fooled:** a memo with a proven mistake that the judge rated 4 or 5.
- **Doubted:** a memo that passed every check but that the judge rated 1 or 2. That one is
  for a person to look at.

In our first run, the judge rated 11 of 16 memos with a proven mistake as good (4 or 5). Its
average was 4.5 where the checks passed and 4.0 where they failed. A judge alone can't tell
these memos apart; the checks can.

## Setting it up

NeMo Evaluator has its own dependencies, so give it its own environment:

```bash
python3 -m venv ~/venvs/nel
```

```bash
~/venvs/nel/bin/pip install "nemo-evaluator[all]"
```

Then tell the engine where `nel` is (or put it on the PATH):

```bash
export EVIDENCE_NEL=~/venvs/nel/bin/nel
```

The engine passes its own code to `nel` (on `PYTHONPATH`), so the credit memo benchmark runs
our checks without installing the engine there. API keys are never written into the config
file: it holds `${NVIDIA_API_KEY}`, which `nel` expands from the environment.

## Using it

Measure the assistant (the endpoint in `.env`), judged by the judge endpoint:

```bash
.venv/bin/evidence capabilities run --suite quick --pack packs/underwriter-de-s80534 --name lightning
```

| Suite | Size | Time (Lightning on the team's node) | For |
|---|---|---|---|
| `quick` | about 20 problems per benchmark, 10 credit cases, 2 repeats | about 2 minutes | trying things out |
| `standard` | about 100 per benchmark, the whole case set, 2 repeats | about 10–15 minutes | a release decision |
| `general` | the three general benchmarks only | | a model with no credit-memo task |

Other options:
- `--setup with_figures`: the credit memos with the bank's figures.
- `--model-url` and `--model-id`: another model, such as a fine-tuned one.
- `--no-judge`: skip the judge.
- `--thinking`: leave the model's thinking on.

Each run writes a folder in `capabilities/` holding:
- `report.md`, in plain words;
- `capabilities.json`;
- the NeMo Evaluator config and its raw output;
- the seal, and the Bitcoin anchor when anchoring is on.

Set a candidate against a baseline:

```bash
.venv/bin/evidence capabilities gate capabilities/<baseline> capabilities/<candidate>
```

This runs `nel compare` and `nel gate`, and writes `gate.md`, `gate.json` and `compare.json`
into the candidate's folder, sealed. The default policy:
- **Credit memos are critical** and may not drop.
- **The rest are supporting** and may drop at most 5 points.

`--policy` takes your own policy (NeMo Evaluator's format).

The verdict is one of:
- **GO:** the candidate may replace the baseline.
- **NO-GO:** something got worse beyond the limit.
- **INCONCLUSIVE:** too few problems to tell either way. Measure with the standard suite or
  more repeats.

Example, from the quick suite: Lightning with the bank's figures against Lightning without.
The credit memos went from 20% to 75% passing every check, which is significant even on 10
cases. The general benchmarks moved by 5–9 points although the model was the same, so that
was run-to-run noise. The gate rightly said INCONCLUSIVE for them.

## What we learned about NeMo Evaluator 0.3.0

We tried every part of it against Nemotron 3.5 Lightning and Nemotron 3 Super.

**Works well:**
- **Custom benchmarks:** our six checks ran inside it unchanged.
- **Bootstrap confidence intervals.**
- **`nel compare`:** pairs each problem across two runs, lists what flipped, and tests
  whether a change is significant.
- **`nel gate`:** tiered release policies. It honestly says INCONCLUSIVE rather than passing
  noise.
- **The rest:** reports (Markdown, HTML, LaTeX, CSV), export to MLflow and Weights & Biases,
  packaging a benchmark as a container, running on SLURM, and a bridge to lm-eval-harness
  (14,683 tasks).

**Traps, and how the checker avoids them:**

| Trap | Effect | The checker |
|---|---|---|
| Lightning's reasoning comes back without an opening `<think>` tag; NeMo Evaluator's reasoning filter only strips it when the tag is there | The answer extractor reads the reasoning: arithmetic scored 25% instead of 85% | Thinking off, as the engine runs the model |
| MMLU-Pro's prompt asks for `Answer: $LETTER`; models copy the dollar signs, and the extractor's pattern doesn't read `$D$` | Knowledge scored 15% where the answers given were about 65% right | `mmlu-pro` is the same dataset and prompt with a reader that takes `$D$`, `(D)`, `**D**` and `\boxed{D}` |
| A judge's score replaces the benchmark's score by default, and the `rubric` setting of a judge metric is not read anywhere | A judge would silently overrule the checks | Our benchmark supplies its own judge function (the route NVIDIA's PinchBench uses) and keeps the checks' score |
| The normal-approximation interval can go below 0 or above 100% on small samples | Impossible intervals | The report uses the bootstrap interval |
| `xstest`'s dataset URL is out of date upstream | The benchmark fails | Left out, and listed under "Not measured" |
| `lm-eval://ifeval` needs `langdetect` and NLTK's `punkt_tab` data, which `[all]` does not install | The benchmark fails | Left out, and listed |
| `mgsm` drops its per-language breakdown when repeated | No German score | Computed from the per-problem results |
| NeMo Evaluator records the configuration but not model fingerprints, and seals nothing | Its output can't serve as audit evidence on its own | Each result folder is sealed and anchored like a test |
