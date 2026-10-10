# Next M5 experiment: draftcap-tail

Fresh bracketing controls; 256 output tokens per fresh response. These percentages use this suite only.
All tested fresh and cached token IDs and text match the control. Cached fixtures are separate.

| Workload | Control TPS | Candidate TPS | TPS gain | Reply quicker | Control drift |
| --- | ---: | ---: | ---: | ---: | ---: |
| chinese/56 | 40.660 | 40.665 | +0.01% | -0.02% | +0.13% |
| code/48 | 59.482 | 59.464 | -0.03% | -0.03% | -0.13% |
| prose/53 | 39.931 | 40.007 | +0.19% | +0.16% | +0.23% |
| synthetic/512 | 48.474 | 48.459 | -0.03% | -0.16% | +0.01% |
| synthetic/2048 | 49.892 | 49.970 | +0.16% | -0.36% | -0.12% |
| cached-ledger/512 | 69.432 | 70.110 | +0.98% | +0.80% | +2.51% |
| cached-ledger/2048 | 64.191 | 63.929 | -0.41% | -0.47% | -0.39% |

Passed 128 answer/cache checks; compared 84 fresh/cached outputs. Zero new swap.
Speed acceptance: False. Default launchers remain unchanged.

[Raw evidence](comparison.json)

Same actual allocation/max3 and no diagnostic trace; report-path correction analyzes unchanged saved runs. Original rejection retained.
