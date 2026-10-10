# Next M5 experiment: sampling-view-clean-retry

Fresh bracketing controls; 256 output tokens per fresh response. These percentages use this suite only.
All tested fresh and cached token IDs and text match the control. Cached fixtures are separate.

| Workload | Control TPS | Candidate TPS | TPS gain | Reply quicker | Control drift |
| --- | ---: | ---: | ---: | ---: | ---: |
| chinese/56 | 40.687 | 40.651 | -0.09% | -0.08% | -0.14% |
| code/48 | 59.523 | 59.481 | -0.07% | -0.10% | -0.23% |
| prose/53 | 39.983 | 39.977 | -0.01% | +0.01% | -0.09% |
| synthetic/512 | 48.471 | 48.391 | -0.17% | -0.32% | -0.33% |
| synthetic/2048 | 49.904 | 49.881 | -0.05% | -0.24% | -0.29% |
| cached-ledger/512 | 69.783 | 70.152 | +0.53% | +1.61% | +0.62% |
| cached-ledger/2048 | 63.519 | 63.758 | +0.38% | +0.12% | +0.62% |

Passed 128 answer/cache checks; compared 84 fresh/cached outputs. Zero new swap.
Speed acceptance: False. Default launchers remain unchanged.

[Raw evidence](comparison.json)
