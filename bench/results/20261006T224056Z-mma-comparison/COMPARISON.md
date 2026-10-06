# Few-row Metal comparison

Status: passed

Full Flash-Next Q2_0, unchanged packed shared Q3 helper, mixed placement, 4K context, batch/ubatch 512, F16 cache, eight target and helper workers, temperature 0.6. Only the dense few-row Metal dispatch/kernel patch differs between paired engines.

Order: [(1, 'control'), (1, 'candidate'), (1, 'candidate'), (1, 'control'), (3, 'control'), (3, 'candidate'), (3, 'candidate'), (3, 'control'), (4, 'control'), (4, 'candidate'), (4, 'candidate'), (4, 'control')]. Each pass excludes one warmup and measures 2 repeats. Fresh replies use 128 tokens; cached replies stop normally. Percentages use fresh, matching-depth controls.

| Depth | Workload / input | Control TPS | Patch TPS | Output gain | Total reply quicker | First token quicker | Control TPS drift |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | chinese / 56 | 40.661 | 40.340 | -0.79% | -0.52% | +3.19% | -4.37% |
| 1 | code / 48 | 44.633 | 44.686 | +0.12% | +0.03% | +0.43% | -3.85% |
| 1 | prose / 53 | 39.851 | 39.719 | -0.33% | -0.08% | +1.67% | -4.05% |
| 1 | synthetic / 512 | 43.853 | 44.253 | +0.91% | +0.44% | -0.78% | -1.59% |
| 1 | synthetic / 2048 | 40.459 | 39.876 | -1.44% | -1.08% | -1.07% | -3.51% |
| 1 | cached-ledger / 512 | 47.711 | 47.955 | +0.51% | +1.43% | +2.37% | +0.41% |
| 1 | cached-ledger / 2048 | 43.847 | 43.472 | -0.86% | -0.24% | +0.43% | +0.74% |
| 3 | chinese / 56 | 34.322 | 40.104 | +16.85% | +13.57% | +3.44% | +0.04% |
| 3 | code / 48 | 48.124 | 56.213 | +16.81% | +13.30% | +3.35% | +1.00% |
| 3 | prose / 53 | 36.642 | 42.783 | +16.76% | +13.48% | +3.37% | +0.98% |
| 3 | synthetic / 512 | 41.828 | 48.908 | +16.93% | +11.07% | +0.02% | +1.72% |
| 3 | synthetic / 2048 | 43.084 | 49.852 | +15.71% | +6.64% | +1.39% | +0.85% |
| 3 | cached-ledger / 512 | 56.245 | 66.260 | +17.81% | +10.48% | +3.73% | +1.95% |
| 3 | cached-ledger / 2048 | 55.499 | 65.679 | +18.34% | +10.72% | +3.86% | +5.27% |
| 4 | chinese / 56 | 29.469 | 35.870 | +21.72% | +16.88% | +3.39% | +0.09% |
| 4 | code / 48 | 46.643 | 56.681 | +21.52% | +16.30% | +3.20% | -0.02% |
| 4 | prose / 53 | 34.453 | 41.897 | +21.61% | +16.67% | +3.19% | +0.18% |
| 4 | synthetic / 512 | 38.148 | 46.234 | +21.20% | +14.12% | +2.03% | +0.11% |
| 4 | synthetic / 2048 | 41.254 | 49.658 | +20.37% | +8.08% | +0.98% | -0.08% |
| 4 | cached-ledger / 512 | 56.658 | 68.914 | +21.63% | +12.23% | +3.50% | +0.64% |
| 4 | cached-ledger / 2048 | 57.701 | 69.240 | +20.00% | +11.09% | +3.55% | +0.11% |

wall_s

| Depth | Workload / input | Control | Patch |
| ---: | --- | ---: | ---: |
| 1 | chinese / 56 | 3.4347 | 3.4526 |
| 1 | code / 48 | 3.1418 | 3.1409 |
| 1 | prose / 53 | 3.4933 | 3.4959 |
| 1 | synthetic / 512 | 3.8241 | 3.8074 |
| 1 | synthetic / 2048 | 7.0927 | 7.1694 |
| 1 | cached-ledger / 512 | 0.7876 | 0.7763 |
| 1 | cached-ledger / 2048 | 0.8223 | 0.8242 |
| 3 | chinese / 56 | 4.0067 | 3.4629 |
| 3 | code / 48 | 2.9340 | 2.5436 |
| 3 | prose / 53 | 3.7689 | 3.2610 |
| 3 | synthetic / 512 | 3.9703 | 3.5307 |
| 3 | synthetic / 2048 | 6.8253 | 6.3723 |
| 3 | cached-ledger / 512 | 0.7146 | 0.6397 |
| 3 | cached-ledger / 2048 | 0.7161 | 0.6393 |
| 4 | chinese / 56 | 4.6142 | 3.8352 |
| 4 | code / 48 | 3.0150 | 2.5236 |
| 4 | prose / 53 | 3.9883 | 3.3233 |
| 4 | synthetic / 512 | 4.2564 | 3.6555 |
| 4 | synthetic / 2048 | 6.8927 | 6.3354 |
| 4 | cached-ledger / 512 | 0.7140 | 0.6267 |
| 4 | cached-ledger / 2048 | 0.6992 | 0.6217 |

ttft_s

| Depth | Workload / input | Control | Patch |
| ---: | --- | ---: | ---: |
| 1 | chinese / 56 | 0.3150 | 0.3050 |
| 1 | code / 48 | 0.2959 | 0.2946 |
| 1 | prose / 53 | 0.3048 | 0.2997 |
| 1 | synthetic / 512 | 0.9278 | 0.9350 |
| 1 | synthetic / 2048 | 3.9323 | 3.9743 |
| 1 | cached-ledger / 512 | 0.2836 | 0.2769 |
| 1 | cached-ledger / 2048 | 0.2978 | 0.2965 |
| 3 | chinese / 56 | 0.3064 | 0.2959 |
| 3 | code / 48 | 0.2941 | 0.2842 |
| 3 | prose / 53 | 0.3031 | 0.2928 |
| 3 | synthetic / 512 | 0.9340 | 0.9338 |
| 3 | synthetic / 2048 | 3.8775 | 3.8235 |
| 3 | cached-ledger / 512 | 0.2859 | 0.2752 |
| 3 | cached-ledger / 2048 | 0.3008 | 0.2892 |
| 4 | chinese / 56 | 0.3048 | 0.2945 |
| 4 | code / 48 | 0.2921 | 0.2827 |
| 4 | prose / 53 | 0.3021 | 0.2925 |
| 4 | synthetic / 512 | 0.9276 | 0.9088 |
| 4 | synthetic / 2048 | 3.8155 | 3.7781 |
| 4 | cached-ledger / 512 | 0.2855 | 0.2755 |
| 4 | cached-ledger / 2048 | 0.3000 | 0.2893 |

prompt_tok_s

| Depth | Workload / input | Control | Patch |
| ---: | --- | ---: | ---: |
| 1 | chinese / 56 | 178.0881 | 183.9324 |
| 1 | code / 48 | 162.5483 | 163.2478 |
| 1 | prose / 53 | 174.2133 | 177.1650 |
| 1 | synthetic / 512 | 552.1718 | 547.9778 |
| 1 | synthetic / 2048 | 521.0818 | 515.6169 |
| 1 | cached-ledger / 512 | 144.8346 | 148.3382 |
| 1 | cached-ledger / 2048 | 137.9831 | 138.6004 |
| 3 | chinese / 56 | 183.0646 | 189.6021 |
| 3 | code / 48 | 163.5241 | 169.2065 |
| 3 | prose / 53 | 175.2985 | 181.3015 |
| 3 | synthetic / 512 | 548.5159 | 548.6334 |
| 3 | synthetic / 2048 | 528.3064 | 535.7583 |
| 3 | cached-ledger / 512 | 147.1465 | 152.8451 |
| 3 | cached-ledger / 2048 | 139.9142 | 145.5660 |
| 4 | chinese / 56 | 184.0789 | 190.4982 |
| 4 | code / 48 | 164.6034 | 170.0678 |
| 4 | prose / 53 | 175.7050 | 181.4897 |
| 4 | synthetic / 512 | 552.2878 | 563.7455 |
| 4 | synthetic / 2048 | 536.8680 | 542.1760 |
| 4 | cached-ledger / 512 | 147.3672 | 152.7193 |
| 4 | cached-ledger / 2048 | 140.3003 | 145.4934 |

draft_acceptance_percent

| Depth | Workload / input | Control | Patch |
| ---: | --- | ---: | ---: |
| 1 | chinese / 56 | 69.3333 | 69.3333 |
| 1 | code / 48 | 86.7647 | 86.7647 |
| 1 | prose / 53 | 65.7895 | 65.7895 |
| 1 | synthetic / 512 | 81.4286 | 81.4286 |
| 1 | synthetic / 2048 | 73.9726 | 73.9726 |
| 1 | cached-ledger / 512 | 100.0000 | 100.0000 |
| 1 | cached-ledger / 2048 | 100.0000 | 100.0000 |
| 3 | chinese / 56 | 40.5882 | 40.5882 |
| 3 | code / 48 | 71.0744 | 71.0744 |
| 3 | prose / 53 | 45.6250 | 45.6250 |
| 3 | synthetic / 512 | 58.3942 | 58.3942 |
| 3 | synthetic / 2048 | 63.3588 | 63.3588 |
| 3 | cached-ledger / 512 | 89.7436 | 89.7436 |
| 3 | cached-ledger / 2048 | 100.0000 | 100.0000 |
| 4 | chinese / 56 | 31.1111 | 31.1111 |
| 4 | code / 48 | 64.5390 | 64.5390 |
| 4 | prose / 53 | 40.6250 | 40.6250 |
| 4 | synthetic / 512 | 48.5380 | 48.5380 |
| 4 | synthetic / 2048 | 57.1429 | 57.1429 |
| 4 | cached-ledger / 512 | 86.3636 | 86.3636 |
| 4 | cached-ledger / 2048 | 92.5000 | 92.5000 |

Raw runs

- [1 / control / 20261006T224056Z-mma-1-1-control](../20261006T224056Z-mma-1-1-control/result.json): passed, new swap 0.000 GiB
- [1 / candidate / 20261006T224232Z-mma-2-1-candidate](../20261006T224232Z-mma-2-1-candidate/result.json): passed, new swap 0.000 GiB
- [1 / candidate / 20261006T224409Z-mma-3-1-candidate](../20261006T224409Z-mma-3-1-candidate/result.json): passed, new swap 0.000 GiB
- [1 / control / 20261006T224547Z-mma-4-1-control](../20261006T224547Z-mma-4-1-control/result.json): passed, new swap 0.000 GiB
- [3 / control / 20261006T224726Z-mma-5-3-control](../20261006T224726Z-mma-5-3-control/result.json): passed, new swap 0.000 GiB
- [3 / candidate / 20261006T224905Z-mma-6-3-candidate](../20261006T224905Z-mma-6-3-candidate/result.json): passed, new swap 0.000 GiB
- [3 / candidate / 20261006T225034Z-mma-7-3-candidate](../20261006T225034Z-mma-7-3-candidate/result.json): passed, new swap 0.000 GiB
- [3 / control / 20261006T225203Z-mma-8-3-control](../20261006T225203Z-mma-8-3-control/result.json): passed, new swap 0.000 GiB
- [4 / control / 20261006T225339Z-mma-9-4-control](../20261006T225339Z-mma-9-4-control/result.json): passed, new swap 0.000 GiB
- [4 / candidate / 20261006T225521Z-mma-10-4-candidate](../20261006T225521Z-mma-10-4-candidate/result.json): passed, new swap 0.000 GiB
- [4 / candidate / 20261006T225651Z-mma-11-4-candidate](../20261006T225651Z-mma-11-4-candidate/result.json): passed, new swap 0.000 GiB
- [4 / control / 20261006T225822Z-mma-12-4-control](../20261006T225822Z-mma-12-4-control/result.json): passed, new swap 0.000 GiB
