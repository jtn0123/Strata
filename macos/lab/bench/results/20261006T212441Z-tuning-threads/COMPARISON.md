# Helper tuning: threads

Status: passed

Full Flash-Next Q2_0, packed shared Q3 helper, mixed placement, 4K context, batch/ubatch 512, F16 cache, target CPU threads 8, temperature 0.6. Only the named helper setting changes. No kernel, vocabulary or GPU-limit change.

Control: depth 2, helper threads 8. Order: (8, 6, 12, 12, 6, 8). Each pass excludes one warmup and measures 2 repeats. Fresh replies use 128 output tokens; cached replies and answer checks stop normally. Previous suites are not pooled into these percentages.

Output tokens/second

| Workload / input | 8 | 6 | 12 |
| --- | ---: | ---: | ---: |
| chinese / 56 | 36.090 | 36.269 | 36.140 |
| code / 48 | 45.644 | 46.090 | 45.817 |
| prose / 53 | 39.740 | 40.103 | 39.879 |
| synthetic / 512 | 42.882 | 43.062 | 42.950 |
| synthetic / 2048 | 41.335 | 41.637 | 41.386 |
| cached-ledger / 512 | 51.588 | 51.788 | 51.438 |
| cached-ledger / 2048 | 48.233 | 48.413 | 48.426 |

Complete reply, seconds

| Workload / input | 8 | 6 | 12 |
| --- | ---: | ---: | ---: |
| chinese / 56 | 3.828 | 3.809 | 3.821 |
| code / 48 | 3.076 | 3.056 | 3.064 |
| prose / 53 | 3.500 | 3.472 | 3.486 |
| synthetic / 512 | 3.902 | 3.916 | 3.868 |
| synthetic / 2048 | 6.913 | 7.021 | 6.800 |
| cached-ledger / 512 | 0.751 | 0.752 | 0.751 |
| cached-ledger / 2048 | 0.779 | 0.776 | 0.781 |

First token, seconds

| Workload / input | 8 | 6 | 12 |
| --- | ---: | ---: | ---: |
| chinese / 56 | 0.309 | 0.309 | 0.306 |
| code / 48 | 0.295 | 0.298 | 0.292 |
| prose / 53 | 0.302 | 0.305 | 0.301 |
| synthetic / 512 | 0.942 | 0.963 | 0.911 |
| synthetic / 2048 | 3.841 | 3.969 | 3.733 |
| cached-ledger / 512 | 0.285 | 0.288 | 0.285 |
| cached-ledger / 2048 | 0.301 | 0.301 | 0.304 |

Input tokens/second

| Workload / input | 8 | 6 | 12 |
| --- | ---: | ---: | ---: |
| chinese / 56 | 181.626 | 181.815 | 183.227 |
| code / 48 | 163.103 | 161.639 | 164.741 |
| prose / 53 | 175.597 | 174.372 | 176.437 |
| synthetic / 512 | 544.234 | 531.927 | 562.618 |
| synthetic / 2048 | 533.240 | 516.097 | 548.775 |
| cached-ledger / 512 | 147.411 | 145.876 | 147.528 |
| cached-ledger / 2048 | 139.974 | 140.011 | 138.419 |

Draft acceptance, percent

| Workload / input | 8 | 6 | 12 |
| --- | ---: | ---: | ---: |
| chinese / 56 | 51.200 | 51.200 | 51.200 |
| code / 48 | 78.571 | 78.571 | 78.571 |
| prose / 53 | 61.404 | 61.404 | 61.404 |
| synthetic / 512 | 71.154 | 71.154 | 71.154 |
| synthetic / 2048 | 69.811 | 69.811 | 69.811 |
| cached-ledger / 512 | 100.000 | 100.000 | 100.000 |
| cached-ledger / 2048 | 100.000 | 100.000 | 100.000 |

Changes from this suite's control

| Workload / input | Setting | Output gain | Total reply quicker | First token quicker |
| --- | ---: | ---: | ---: | ---: |
| chinese / 56 | 6 | +0.50% | +0.48% | +0.10% |
| chinese / 56 | 12 | +0.14% | +0.18% | +0.88% |
| code / 48 | 6 | +0.98% | +0.63% | -0.91% |
| code / 48 | 12 | +0.38% | +0.39% | +0.99% |
| prose / 53 | 6 | +0.91% | +0.81% | -0.70% |
| prose / 53 | 12 | +0.35% | +0.42% | +0.48% |
| synthetic / 512 | 6 | +0.42% | -0.35% | -2.30% |
| synthetic / 512 | 12 | +0.16% | +0.89% | +3.27% |
| synthetic / 2048 | 6 | +0.73% | -1.55% | -3.33% |
| synthetic / 2048 | 12 | +0.12% | +1.64% | +2.83% |
| cached-ledger / 512 | 6 | +0.39% | -0.04% | -1.05% |
| cached-ledger / 512 | 12 | -0.29% | +0.07% | +0.09% |
| cached-ledger / 2048 | 6 | +0.37% | +0.35% | +0.03% |
| cached-ledger / 2048 | 12 | +0.40% | -0.24% | -1.16% |

Raw runs

- [8 / 20261006T212441Z-tuning-threads-1-8](../20261006T212441Z-tuning-threads-1-8/result.json): passed, new swap 0.000 GiB
- [6 / 20261006T212620Z-tuning-threads-2-6](../20261006T212620Z-tuning-threads-2-6/result.json): passed, new swap 0.000 GiB
- [12 / 20261006T212759Z-tuning-threads-3-12](../20261006T212759Z-tuning-threads-3-12/result.json): passed, new swap 0.000 GiB
- [12 / 20261006T212936Z-tuning-threads-4-12](../20261006T212936Z-tuning-threads-4-12/result.json): passed, new swap 0.000 GiB
- [6 / 20261006T213114Z-tuning-threads-5-6](../20261006T213114Z-tuning-threads-5-6/result.json): passed, new swap 0.000 GiB
- [8 / 20261006T213253Z-tuning-threads-6-8](../20261006T213253Z-tuning-threads-6-8/result.json): passed, new swap 0.000 GiB
