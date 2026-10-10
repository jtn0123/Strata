# Next M5 experiment: encoders2

Fresh bracketing controls; 256 output tokens per fresh response. These percentages use this suite only.
All tested fresh and cached token IDs and text match the control. Cached fixtures are separate.

| Workload | Control TPS | Candidate TPS | TPS gain | Reply quicker | Control drift |
| --- | ---: | ---: | ---: | ---: | ---: |
| chinese/56 | 40.607 | 40.583 | -0.06% | -0.06% | +0.03% |
| code/48 | 59.467 | 59.325 | -0.24% | -0.21% | -0.06% |
| prose/53 | 39.949 | 39.882 | -0.17% | -0.12% | +0.05% |
| synthetic/512 | 48.449 | 48.342 | -0.22% | -0.37% | +0.04% |
| synthetic/2048 | 49.818 | 49.860 | +0.08% | -0.32% | -0.28% |
| cached-ledger/512 | 69.985 | 70.119 | +0.19% | +0.33% | +0.03% |
| cached-ledger/2048 | 64.145 | 63.317 | -1.29% | -0.61% | -0.26% |

Passed 128 answer/cache checks; compared 84 fresh/cached outputs. Zero new swap.
Speed acceptance: False. Default launchers remain unchanged.

[Raw evidence](comparison.json)

Effective count and null callback verified for every target/helper initialization.
Stricter acceptance including reply-time drift: False.
