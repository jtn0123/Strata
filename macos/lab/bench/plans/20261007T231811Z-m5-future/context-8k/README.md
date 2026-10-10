# Try more useful context

Status: prepared; testing is on hold.

Executable ABBA harness and three seeded exact-6144-token recall fixtures are staged. Offline geometry and comparison rejection tests pass; real tokenizer, recall, rollback and 8K memory remain untested.

Hypothesis: 8K context may fit with useful headroom and allow larger documents without unacceptable latency or quality loss.

Only change: Context capacity 4096 to 8192. Keep F16 cache, engine, helper depth and workers fixed.

## Before testing

- Testing go-ahead
- Offline gate passed for current sources
- Fresh controls and quiet host with 34 GiB available
- Saved allocation accounting reviewed; actual 8K fit remains unproved

## Required evidence

- ABBA timing on identical 512/2048-token inputs and 128-token outputs
- Separate 6144-token retrieval fixture at 8K with room for output
- Facts at beginning/middle/end and distractors; verify exact answers
- Target/helper KV, recurrent state, QSA and scratch allocations logged separately
- Zero new swap

## Stop conditions

- Memory guard
- Retrieval/rollback failure
- No useful headroom

## Record results

Use `result-template.json`; all numbers remain empty until measured.

TPS gain = 100*(candidate/control-1). Time reduction = 100*(1-candidate/control). Requires finite positive matched metrics. Do not add percentages from separate experiments.

At least 5 percent median complete-task improvement on the chosen workload, or useful capacity gain with an explicitly accepted speed tradeoff; no unexplained quality failure or new swap. Report control drift and all raw passes.

Historical results are reference only. Record a new complete matched baseline for a speed candidate.

## Limits

Higher configured capacity is not proof of long-input quality. The 6144-token case has no 4K TPS comparison. A separate quantized-cache trial may follow; do not combine it with this test.

Plan-only command:

```sh
.venv/bin/python scripts/benchmark_context.py
```

Future testing command, to be invoked only after the user's go-ahead:

```sh
.venv/bin/python scripts/benchmark_context.py --run
```
