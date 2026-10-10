# Next M5 experiment: ten-expert-reduction

Fresh bracketing controls; 256 output tokens per fresh response. These percentages use this suite only.
All tested fresh and cached token IDs and text match the control. Cached fixtures are separate.

| Workload | Control TPS | Candidate TPS | TPS gain | Reply quicker | Control drift |
| --- | ---: | ---: | ---: | ---: | ---: |
| chinese/56 | 40.636 | 41.007 | +0.91% | +0.89% | +0.09% |
| code/48 | 59.415 | 59.948 | +0.90% | +0.94% | -0.03% |
| prose/53 | 39.845 | 40.262 | +1.05% | +1.02% | +0.04% |
| synthetic/512 | 48.462 | 48.880 | +0.86% | +0.87% | -0.26% |
| synthetic/2048 | 49.813 | 50.246 | +0.87% | +0.90% | -0.12% |
| cached-ledger/512 | 70.050 | 70.630 | +0.83% | +1.01% | +2.55% |
| cached-ledger/2048 | 63.697 | 63.846 | +0.23% | +0.77% | +0.72% |

Passed 128 answer/cache checks; compared 84 fresh/cached outputs. Zero new swap.
Speed acceptance: False. Default launchers remain unchanged.

[Raw evidence](comparison.json)
