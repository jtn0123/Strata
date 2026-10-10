# Validate the isolated upstream Metal correctness fix

Status: prepared; testing is on hold.

Separate m5-correctness source, manifest, server and operation tester are built. GPU math and model comparisons are held.

Hypothesis: The fused matrix-plus-residual operation must select the correct input; no TPS improvement is assumed.

Only change: Apply upstream residual-source identity fix #30100 to m5-lab; no changed model or launch defaults.

## Before testing

- Explicit testing go-ahead for any --run command
- Offline validation receipt matches current sources
- Quiet host; leave unrelated VM/build work alone

## Required evidence

- MUL_MAT_ADD mm2+mm CPU-reference GPU check, plus existing math checks
- Fresh m5-lab/correctness/correctness/m5-lab controls
- Quality and zero-swap gates; report speed/latency without assuming a gain

## Stop conditions

- Invalid evidence or source drift
- Unexpected quality failure or new swap

## Record results

Use `result-template.json`; all numbers remain empty until measured.

TPS gain = 100*(candidate/control-1). Time reduction = 100*(1-candidate/control). Requires finite positive matched metrics. Do not add percentages from separate experiments.

At least 5 percent median complete-task improvement on the chosen workload, or useful capacity gain with an explicitly accepted speed tradeoff; no unexplained quality failure or new swap. Report control drift and all raw passes.

Historical results are reference only. Record a new complete matched baseline for a speed candidate.

## Limits

Fix is absent locally and staged, but the current Qwen graph has not been proven to trigger the faulty fusion.

Plan-only command:

```sh
.venv/bin/python scripts/benchmark_m5.py --experiment metal-residual-correctness
```

Future testing command, to be invoked only after the user's go-ahead:

```sh
.venv/bin/python scripts/benchmark_m5.py --experiment metal-residual-correctness --run
```
