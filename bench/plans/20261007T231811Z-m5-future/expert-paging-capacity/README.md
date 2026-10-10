# Explore larger-model capacity

Status: prepared; testing is on hold.

Feasibility template only; pager, precision upgrade and larger model downloads are absent.

Hypothesis: A bounded expert residency map could trade SSD traffic and speed for larger or higher-precision weights.

Only change: Expert residency/paging policy in a separate prototype after a complete capacity budget.

## Before testing

- User-selected capacity goal and acceptable minimum speed
- Measured expert hot set/miss curve
- Storage and OS headroom budget
- Correctness-tested resident-slot map
- Testing go-ahead before downloads or model runs

## Required evidence

- Mapping, eviction, in-flight references and fallback correctness
- Prefill and verification miss handling
- Read bytes/latency and resident-set peak
- Zero OS swap growth
- Actual quality/precision benefit and sustained response speed

## Stop conditions

- Memory accounting depends on OS swap
- Resident mapping race or corruption
- Minimum useful speed cannot be met

## Record results

Use `result-template.json`; all numbers remain empty until measured.

TPS gain = 100*(candidate/control-1). Time reduction = 100*(1-candidate/control). Requires finite positive matched metrics. Do not add percentages from separate experiments.

At least 5 percent median complete-task improvement on the chosen workload, or useful capacity gain with an explicitly accepted speed tradeoff; no unexplained quality failure or new swap. Report control drift and all raw passes.

Historical results are reference only. Record a new complete matched baseline for a speed candidate.

## Limits

Capacity may improve while TPS falls. Mac unified memory does not pool with another PC. This plan does not allocate, download or page model weights.

No executable candidate/testing command exists yet. Implement and validate the stated prerequisites first.
