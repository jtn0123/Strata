# Try more useful context

Status: prepared; testing is on hold.

Protocol and fixture design prepared. Native context setting exists; long-context harness and quality checks still require implementation/validation.

Hypothesis: 8K context may fit with useful headroom and allow larger documents without unacceptable latency or quality loss.

Only change: Context capacity 4096 to 8192. Keep F16 cache, engine, helper depth and workers fixed.

## Before testing

- Testing go-ahead
- Capacity fixture implemented
- Quiet host and verified sources
- Memory budget derived from actual allocation logs

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

No executable candidate/testing command exists yet. Implement and validate the stated prerequisites first.
