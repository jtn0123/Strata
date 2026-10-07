# Locate the remaining GPU work

Status: prepared; testing is on hold.

Split callback, buffer attribution and parser staged; real GPU behavior untested.

Hypothesis: Shared matrices, attention/state or other operations account for the gap left by isolated matrix timings.

Only change: Deliberately split scheduled computational nodes into diagnostic intervals; never enable this in app launchers.

## Before testing

- Testing go-ahead
- Small-model plumbing smoke first
- 34 GiB available RAM

## Required evidence

- Matched greedy text/token output
- CPU monotonic boundaries assign every computational GPU buffer once
- Main/helper and prompt/generation separated
- No additional math op in an isolated interval
- Explicit instrumentation overhead versus fresh control
- Zero new swap

## Stop conditions

- Output mismatch
- Unattributed computational buffers
- Callback event cap or excessive logs
- Memory guard

## Record results

Use `result-template.json`; all numbers remain empty until measured.

TPS gain = 100*(candidate/control-1). Time reduction = 100*(1-candidate/control). Requires finite positive matched metrics. Do not add percentages from separate experiments.

At least 5 percent median complete-task improvement on the chosen workload, or useful capacity gain with an explicitly accepted speed tradeoff; no unexplained quality failure or new swap. Report control drift and all raw passes.

Historical results are reference only. Record a new complete matched baseline for a speed candidate.

## Limits

Splitting removes fusion and adds synchronization/command-buffer overhead. Costs rank diagnostic paths, not original kernel time or accelerator occupancy.

Plan-only command:

```sh
.venv/bin/python scripts/profile_m5_routes.py --mode split
```

Future testing command, to be invoked only after the user's go-ahead:

```sh
.venv/bin/python scripts/profile_m5_routes.py --mode split --depths 3 --run
```
