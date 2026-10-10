# Next M5 experiment: parallel-top10

Fresh bracketing controls; 256 output tokens per fresh response. These percentages use this suite only.
All tested fresh and cached token IDs and text match the control. Cached fixtures are separate.

| Workload | Control TPS | Candidate TPS | TPS gain | Reply quicker | Control drift |
| --- | ---: | ---: | ---: | ---: | ---: |
| code/48 | 59.379 | 60.028 | +1.09% | +0.96% | +0.28% |
| prose/53 | 39.938 | 40.314 | +0.94% | +0.83% | +0.15% |
| synthetic/512 | 48.432 | 48.886 | +0.94% | +0.71% | -0.31% |
| synthetic/2048 | 49.868 | 50.287 | +0.84% | -0.20% | +0.07% |
| cached-ledger/512 | 70.840 | 70.647 | -0.27% | -0.19% | -0.20% |
| cached-ledger/2048 | 63.868 | 63.969 | +0.16% | +0.62% | +0.97% |

Passed 104 answer/cache checks; compared 72 fresh/cached outputs. Zero new swap.
Speed acceptance: False. Default launchers remain unchanged.

[Raw evidence](comparison.json)

Original m5-copy control; eligible variant entry confirmed on candidate launches.
Stricter TPS and reply drift acceptance: False.
