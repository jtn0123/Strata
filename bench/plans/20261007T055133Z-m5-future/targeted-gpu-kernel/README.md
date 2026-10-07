# Optimize one measured GPU operation

Status: prepared; testing is on hold.

Design template only; target family is intentionally unset until diagnostic evidence is available.

Hypothesis: One demonstrated expensive shape can use less dequantization/memory work or better cooperative matrix input.

Only change: One dispatch/kernel in an isolated engine, keeping GGUF bytes and fallback behavior.

## Before testing

- Measured family/shape and real routing
- CPU-reference/fallback test inventory
- Actual candidate patch, manifest and build receipt
- Testing go-ahead

## Required evidence

- CPU-reference math, odd/aligned shapes and inactive-expert cases
- Actual dispatch proof
- Original controls preserved
- Fresh ABBA model comparisons and semantic checks
- Matched TPS, first-token and full-reply percentages
- Zero new swap

## Stop conditions

- Math/quality failure
- Gain disappears end to end
- Two narrow approaches repeatedly under 2-3 percent

## Record results

Use `result-template.json`; all numbers remain empty until measured.

TPS gain = 100*(candidate/control-1). Time reduction = 100*(1-candidate/control). Requires finite positive matched metrics. Do not add percentages from separate experiments.

At least 5 percent median complete-task improvement on the chosen workload, or useful capacity gain with an explicitly accepted speed tradeoff; no unexplained quality failure or new swap. Report control drift and all raw passes.

Historical results are reference only. Record a new complete matched baseline for a speed candidate.

## Limits

A synthetic kernel win is not a model TPS win. Do not force a sparse few-row workload into MMA merely because the hardware supports matrix acceleration.

No executable candidate/testing command exists yet. Implement and validate the stated prerequisites first.
