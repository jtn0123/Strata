# Complete the clean baseline refresh

Status: prepared; testing is on hold.

Two-launch writing baseline runner exists; prior second launch was rejected for new swap. Refresh remains incomplete.

Hypothesis: A clean repeat establishes current comparison conditions.

Only change: No settings change: depth 3, eight helper workers, Tensor API on, F16 4K cache.

## Before testing

- Explicit testing go-ahead for any --run command
- Offline validation receipt matches current sources
- Quiet host; leave unrelated VM/build work alone

## Required evidence

- Two accepted launches with identical prompts/settings/hashes
- Monitor healthy; owned server exits; zero new swap
- 128-token synthetic/code/prose/Chinese replies and cached task checks

## Stop conditions

- Invalid evidence or source drift
- Unexpected quality failure or new swap

## Record results

Use `result-template.json`; all numbers remain empty until measured.

TPS gain = 100*(candidate/control-1). Time reduction = 100*(1-candidate/control). Requires finite positive matched metrics. Do not add percentages from separate experiments.

At least 5 percent median complete-task improvement on the chosen workload, or useful capacity gain with an explicitly accepted speed tradeoff; no unexplained quality failure or new swap. Report control drift and all raw passes.

Historical results are reference only. Record a new complete matched baseline for a speed candidate.

## Limits

Historical single-launch numbers are references. A refresh provides no optimization gain by itself.

Plan-only command:

```sh
.venv/bin/python scripts/benchmark_m5_decision_baseline.py
```

Future testing command, to be invoked only after the user's go-ahead:

```sh
.venv/bin/python scripts/benchmark_m5_decision_baseline.py --run
```
