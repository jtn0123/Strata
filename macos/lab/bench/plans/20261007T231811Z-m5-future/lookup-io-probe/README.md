# Stage bounded file-specific lookup reads

Status: prepared; testing is on hold.

Read-only pread runner and offset/bounds/failure tests are staged; no real model payload read performed.

Hypothesis: A bounded lookup-file fixture can characterize cached read latency before choosing native prefetch work.

Only change: Sample up to 128 page-aligned lookup offsets in three passes, with at most 8 MiB total reads.

## Before testing

- Explicit testing go-ahead for any --run command
- Offline validation receipt matches current sources
- Quiet host; leave unrelated VM/build work alone

## Required evidence

- Known tensor row geometry and shard bounds
- Read sizes, per-offset latencies and matching sampled digests
- No writes, cache purge, whole-shard preload or inference

## Stop conditions

- Invalid evidence or source drift
- Unexpected quality failure or new swap

## Record results

Use `result-template.json`; all numbers remain empty until measured.

TPS gain = 100*(candidate/control-1). Time reduction = 100*(1-candidate/control). Requires finite positive matched metrics. Do not add percentages from separate experiments.

At least 5 percent median complete-task improvement on the chosen workload, or useful capacity gain with an explicitly accepted speed tradeoff; no unexplained quality failure or new swap. Report control drift and all raw passes.

Historical results are reference only. Record a new complete matched baseline for a speed candidate.

## Limits

pread latency does not establish native mmap-fault time or model lookup stalls. First-pass cache state is unknown. No TPS gain can be inferred.

Plan-only command:

```sh
.venv/bin/python scripts/profile_lookup_io.py
```

Future testing command, to be invoked only after the user's go-ahead:

```sh
.venv/bin/python scripts/profile_lookup_io.py --run
```
