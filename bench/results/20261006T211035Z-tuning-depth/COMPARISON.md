# Helper tuning: depth

Status: passed

Full Flash-Next Q2_0, packed shared Q3 helper, mixed placement, 4K context, batch/ubatch 512, F16 cache, target CPU threads 8, temperature 0.6. Only the named helper setting changes. No kernel, vocabulary or GPU-limit change.

Control: depth 2, helper threads 8. Order: (2, 1, 3, 4, 4, 3, 1, 2). Each pass excludes one warmup and measures 2 repeats. Fresh replies use 128 output tokens; cached replies and answer checks stop normally. Previous suites are not pooled into these percentages.

Output tokens/second

| Workload / input | 2 | 1 | 3 | 4 |
| --- | ---: | ---: | ---: | ---: |
| chinese / 56 | 36.141 | 42.028 | 34.330 | 29.358 |
| code / 48 | 45.909 | 46.280 | 48.216 | 46.521 |
| prose / 53 | 39.895 | 40.988 | 36.576 | 34.356 |
| synthetic / 512 | 42.735 | 44.515 | 41.874 | 38.075 |
| synthetic / 2048 | 41.388 | 41.357 | 43.015 | 41.222 |
| cached-ledger / 512 | 51.453 | 47.889 | 55.340 | 54.380 |
| cached-ledger / 2048 | 48.135 | 44.323 | 54.361 | 56.409 |

Complete reply, seconds

| Workload / input | 2 | 1 | 3 | 4 |
| --- | ---: | ---: | ---: | ---: |
| chinese / 56 | 3.818 | 3.328 | 4.009 | 4.632 |
| code / 48 | 3.059 | 3.036 | 2.930 | 3.027 |
| prose / 53 | 3.485 | 3.403 | 3.777 | 4.002 |
| synthetic / 512 | 3.907 | 3.795 | 3.979 | 4.280 |
| synthetic / 2048 | 6.906 | 6.942 | 6.857 | 6.964 |
| cached-ledger / 512 | 0.752 | 0.786 | 0.725 | 0.734 |
| cached-ledger / 2048 | 0.788 | 0.817 | 0.725 | 0.715 |

First token, seconds

| Workload / input | 2 | 1 | 3 | 4 |
| --- | ---: | ---: | ---: | ---: |
| chinese / 56 | 0.305 | 0.308 | 0.309 | 0.306 |
| code / 48 | 0.293 | 0.293 | 0.296 | 0.294 |
| prose / 53 | 0.302 | 0.304 | 0.306 | 0.304 |
| synthetic / 512 | 0.935 | 0.943 | 0.951 | 0.942 |
| synthetic / 2048 | 3.837 | 3.871 | 3.884 | 3.866 |
| cached-ledger / 512 | 0.287 | 0.284 | 0.288 | 0.288 |
| cached-ledger / 2048 | 0.313 | 0.297 | 0.302 | 0.308 |

Input tokens/second

| Workload / input | 2 | 1 | 3 | 4 |
| --- | ---: | ---: | ---: | ---: |
| chinese / 56 | 183.965 | 182.238 | 181.820 | 183.067 |
| code / 48 | 164.365 | 164.092 | 162.617 | 163.805 |
| prose / 53 | 176.068 | 174.542 | 173.287 | 174.653 |
| synthetic / 512 | 548.105 | 543.338 | 538.919 | 543.808 |
| synthetic / 2048 | 533.895 | 529.206 | 527.398 | 529.835 |
| cached-ledger / 512 | 146.841 | 144.573 | 146.211 | 145.987 |
| cached-ledger / 2048 | 135.228 | 138.323 | 139.256 | 136.927 |

Draft acceptance, percent

| Workload / input | 2 | 1 | 3 | 4 |
| --- | ---: | ---: | ---: | ---: |
| chinese / 56 | 51.200 | 69.333 | 40.588 | 31.111 |
| code / 48 | 78.571 | 86.765 | 71.074 | 64.539 |
| prose / 53 | 61.404 | 65.789 | 45.625 | 40.625 |
| synthetic / 512 | 71.154 | 81.429 | 58.394 | 48.538 |
| synthetic / 2048 | 69.811 | 73.973 | 63.359 | 57.143 |
| cached-ledger / 512 | 100.000 | 100.000 | 89.744 | 86.364 |
| cached-ledger / 2048 | 100.000 | 100.000 | 100.000 | 92.500 |

Changes from this suite's control

| Workload / input | Setting | Output gain | Total reply quicker | First token quicker |
| --- | ---: | ---: | ---: | ---: |
| chinese / 56 | 1 | +16.29% | +12.84% | -1.01% |
| chinese / 56 | 3 | -5.01% | -4.98% | -1.17% |
| chinese / 56 | 4 | -18.77% | -21.30% | -0.48% |
| code / 48 | 1 | +0.81% | +0.77% | -0.17% |
| code / 48 | 3 | +5.02% | +4.23% | -1.10% |
| code / 48 | 4 | +1.33% | +1.06% | -0.36% |
| prose / 53 | 1 | +2.74% | +2.34% | -0.87% |
| prose / 53 | 3 | -8.32% | -8.39% | -1.59% |
| prose / 53 | 4 | -13.88% | -14.84% | -0.80% |
| synthetic / 512 | 1 | +4.17% | +2.88% | -0.84% |
| synthetic / 512 | 3 | -2.01% | -1.83% | -1.66% |
| synthetic / 512 | 4 | -10.90% | -9.55% | -0.75% |
| synthetic / 2048 | 1 | -0.08% | -0.53% | -0.88% |
| synthetic / 2048 | 3 | +3.93% | +0.70% | -1.23% |
| synthetic / 2048 | 4 | -0.40% | -0.84% | -0.76% |
| cached-ledger / 512 | 1 | -6.93% | -4.43% | +0.83% |
| cached-ledger / 512 | 3 | +7.55% | +3.67% | -0.45% |
| cached-ledger / 512 | 4 | +5.69% | +2.47% | -0.59% |
| cached-ledger / 2048 | 1 | -7.92% | -3.81% | +5.02% |
| cached-ledger / 2048 | 3 | +12.93% | +7.88% | +3.37% |
| cached-ledger / 2048 | 4 | +17.19% | +9.18% | +1.69% |

Raw runs

- [2 / 20261006T211035Z-tuning-depth-1-2](../20261006T211035Z-tuning-depth-1-2/result.json): passed, new swap 0.000 GiB
- [1 / 20261006T211229Z-tuning-depth-2-1](../20261006T211229Z-tuning-depth-2-1/result.json): passed, new swap 0.000 GiB
- [3 / 20261006T211405Z-tuning-depth-3-3](../20261006T211405Z-tuning-depth-3-3/result.json): passed, new swap 0.000 GiB
- [4 / 20261006T211545Z-tuning-depth-4-4](../20261006T211545Z-tuning-depth-4-4/result.json): passed, new swap 0.000 GiB
- [4 / 20261006T211729Z-tuning-depth-5-4](../20261006T211729Z-tuning-depth-5-4/result.json): passed, new swap 0.000 GiB
- [3 / 20261006T211913Z-tuning-depth-6-3](../20261006T211913Z-tuning-depth-6-3/result.json): passed, new swap 0.000 GiB
- [1 / 20261006T212052Z-tuning-depth-7-1](../20261006T212052Z-tuning-depth-7-1/result.json): passed, new swap 0.000 GiB
- [2 / 20261006T212228Z-tuning-depth-8-2](../20261006T212228Z-tuning-depth-8-2/result.json): passed, new swap 0.000 GiB
