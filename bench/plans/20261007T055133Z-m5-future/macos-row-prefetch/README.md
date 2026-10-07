# Overlap bounded SSD lookup reads

Status: prepared; testing is on hold.

Design template only. No prefetch code or candidate build exists.

Hypothesis: If model-specific lazy-row waits are material, bounded asynchronous page advice may hide part of them.

Only change: Add macOS handling for already-known lazy lookup rows; preserve shard bytes and mmap/lazy behavior.

## Before testing

- File-specific lookup/fault/wait evidence
- macOS API and offset/length validation
- Isolated engine manifest and real implementation
- Testing go-ahead

## Required evidence

- Exact output/data parity
- Bounds, alignment, shard lifetime, duplicate-row and failure-path checks
- Bounded resident pages and outstanding work
- Matched warm-request ABBA timing
- Label cold observations separately; no system cache purge
- Zero new swap

## Stop conditions

- Lookup waits insignificant
- Paging/advice increases memory pressure
- No repeatable complete-task gain after two narrow approaches

## Record results

Use `result-template.json`; all numbers remain empty until measured.

TPS gain = 100*(candidate/control-1). Time reduction = 100*(1-candidate/control). Requires finite positive matched metrics. Do not add percentages from separate experiments.

At least 5 percent median complete-task improvement on the chosen workload, or useful capacity gain with an explicitly accepted speed tradeoff; no unexplained quality failure or new swap. Report control drift and all raw passes.

Historical results are reference only. Record a new complete matched baseline for a speed candidate.

## Limits

System-wide disk reads cannot establish lookup wait. The 96 MiB cap is a proposed bound, not an implemented cache or established optimum.

No executable candidate/testing command exists yet. Implement and validate the stated prerequisites first.
