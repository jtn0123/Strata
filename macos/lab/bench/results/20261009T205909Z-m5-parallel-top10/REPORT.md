# Exact parallel top10: matched model result

Original m5-copy/conv-direct control versus isolated m5-top10/top10. Qwen3.8-Flash-Next Q2_0, packed shared Q3 helper, mixed placement, eight helper workers, depth3/confidence0, Tensor API on, F16/4K/batch512.

Fresh ABBA,256 output tokens, excluded warmup plus three measured repetitions. Historical results are not pooled.

| Workload / input | Control TPS | Candidate TPS | TPS gain | Reply quicker | TPS control drift | Reply control drift |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| code/48 | 59.379 | 60.028 | +1.092% | +0.959% | +0.283% | +0.207% |
| prose/53 | 39.938 | 40.314 | +0.942% | +0.829% | +0.152% | +0.162% |
| synthetic/512 | 48.432 | 48.886 | +0.938% | +0.709% | -0.311% | -0.539% |
| synthetic/2048 | 49.868 | 50.287 | +0.840% | -0.198% | +0.066% | -0.452% |
| cached-ledger/512 | 70.840 | 70.647 | -0.272% | -0.186% | -0.200% | -0.064% |
| cached-ledger/2048 | 63.868 | 63.969 | +0.159% | +0.621% | +0.972% | -0.021% |

Strict speed acceptance: False. At least1% TPS and whole-reply gain on both English code/prose, each above its own absolute control drift; exact tested outputs and zero new swap.
Only measured fresh English code/prose determine adoption. Cached replies and synthetic tasks are reported separately.

Eligible variant entry confirmed on both candidate launches. This marker does not prove fast-branch frequency. Exact fresh/cache tokens and text match; accepted launches have zero new swap allocation, with existing system swap accounted separately.

code reply: 4.574689 -> 4.530796s.
prose reply: 6.675852 -> 6.620488s.

| Fresh workload / input | First-token change | Prompt TPS change |
| --- | ---: | ---: |
| code/48 | -0.972% quicker | -0.965% |
| prose/53 | -1.012% quicker | -1.015% |
| synthetic/512 | -0.965% quicker | -0.970% |
| synthetic/2048 | -1.503% quicker | -1.466% |

Default launchers remain unchanged.

[Raw comparison](comparison.json). Development, component results and the excluded cold load are recorded in [the experiment report](../20261009-top10/REPORT.md).
