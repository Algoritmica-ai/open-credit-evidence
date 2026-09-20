# Running the pack under NeMo Evaluator

[NeMo Evaluator](https://github.com/NVIDIA-NeMo/Evaluator) is NVIDIA's open-source
harness for running benchmarks against any OpenAI-compatible endpoint with repeats,
confidence intervals, run-to-run comparison and pass/fail gates.
`credit_evidence_bench.py` registers the sample pack as a benchmark whose scorer is
this repository's check battery. Nothing in the checks changes; the harness supplies
scheduling, statistics and reporting.

```bash
pip install nemo-evaluator
export NVIDIA_API_KEY=...
nel validate -b examples/nemo_evaluator/credit_evidence_bench.py --samples 2
nel eval run -b examples/nemo_evaluator/credit_evidence_bench.py --repeats 3 \
    --model-url https://integrate.api.nvidia.com/v1/chat/completions \
    --model-id nvidia/nemotron-3.5-lightning-30b-a3b --api-key $NVIDIA_API_KEY \
    --output-dir results/credit-evidence
nel eval report results/credit-evidence -f markdown
nel gate --policy examples/nemo_evaluator/gate.yaml results/credit-evidence
```

Point `--model-url` at a NIM on your own hardware to run the same benchmark on-prem.

The reward per problem is the share of gated checks passed; each check's pass flag,
score and detail are in `scoring_details`, so the per-problem `results.jsonl` the
harness writes carries the same evidence as `evidence run`. The evidence pack itself —
the report by obligation, the checksums, the verifier — is produced by `evidence run`,
not by the harness.
