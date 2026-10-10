# Next M5 experiment: encoders0

Fresh bracketing controls; 256 output tokens per fresh response. These percentages use this suite only.
All tested fresh and cached token IDs and text match the control. Cached fixtures are separate.

| Workload | Control TPS | Candidate TPS | TPS gain | Reply quicker | Control drift |
| --- | ---: | ---: | ---: | ---: | ---: |
| chinese/56 | 40.669 | 38.390 | -5.60% | -5.75% | +0.04% |
| code/48 | 59.442 | 56.135 | -5.56% | -5.71% | +0.13% |
| prose/53 | 39.943 | 37.750 | -5.49% | -5.62% | -0.04% |
| synthetic/512 | 48.439 | 45.767 | -5.52% | -5.08% | -0.16% |
| synthetic/2048 | 49.812 | 47.270 | -5.10% | -3.28% | -0.14% |
| cached-ledger/512 | 69.755 | 66.551 | -4.59% | -3.56% | -0.45% |
| cached-ledger/2048 | 63.896 | 60.270 | -5.68% | -3.82% | +0.30% |

Passed 128 answer/cache checks; compared 84 fresh/cached outputs. Zero new swap.
Speed acceptance: False. Default launchers remain unchanged.

[Raw evidence](comparison.json)

Effective count and null callback verified for every target/helper initialization.
Stricter acceptance including reply-time drift: False.
