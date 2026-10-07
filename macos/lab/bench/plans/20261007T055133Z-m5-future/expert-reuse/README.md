# Measure real expert reuse

Status: prepared; testing is on hold.

Diagnostic entry point and capture/parser staged; native CPU self-test passes. No model or GPU run yet.

Hypothesis: Four/five verification tokens may reuse enough selected experts to justify sparse matrix work.

Only change: Install a read-only evaluation callback for ten expert IDs per token; preserve weight bytes and all launchers.

## Before testing

- Testing go-ahead
- Verified diagnostic build
- 34 GiB available RAM
- No full-model server running

## Required evidence

- Matched greedy text and token IDs including warmups
- All 48 main expert layers captured
- Ten distinct IDs per token in 0..511
- 2048-byte routing row stride
- Target/helper roles separate
- Zero new swap

## Stop conditions

- Missing or invalid IDs
- Greedy outputs differ
- New swap or low-RAM guard

## Record results

Use `result-template.json`; all numbers remain empty until measured.

TPS gain = 100*(candidate/control-1). Time reduction = 100*(1-candidate/control). Requires finite positive matched metrics. Do not add percentages from separate experiments.

At least 5 percent median complete-task improvement on the chosen workload, or useful capacity gain with an explicitly accepted speed tradeoff; no unexplained quality failure or new swap. Report control drift and all raw passes.

Historical results are reference only. Record a new complete matched baseline for a speed candidate.

## Limits

Callbacks split/synchronize graphs. Exclude their timing from TPS history. A high reuse rate alone does not prove a fast kernel.

Plan-only command:

```sh
.venv/bin/python scripts/profile_m5_routes.py
```

Future testing command, to be invoked only after the user's go-ahead:

```sh
.venv/bin/python scripts/profile_m5_routes.py --mode routes --depths 3 4 --run
```
