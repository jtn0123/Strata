# All-pool QSA ranking removal: matched model result

Original m5-copy/conv-direct versus isolated m5-qsa/qsa-all-pools. Qwen3.8-Flash-Next Q2_0, shared Q3 helper, mixed placement, eight helper workers, depth3/confidence0, Tensor API on, F16/4K/batch512.

Fresh ABBA,256 output tokens, excluded warmup and three repetitions. Exact token/text parity includes warmups and cached continuations. Scores, cache writes and attention dispatch remain unchanged.

| Workload/input | Control TPS | Candidate TPS | TPS gain | Reply quicker | First token quicker | TPS drift | Reply drift |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| code/48 | 59.388 | 59.402 | +0.023% | +0.028% | -0.957% | -0.613% | -0.522% |
| prose/53 | 39.872 | 39.758 | -0.284% | -0.379% | -1.180% | -0.070% | -0.025% |
| synthetic/512 | 48.416 | 48.406 | -0.020% | -0.164% | -1.052% | -0.191% | -0.527% |
| synthetic/2048 | 49.857 | 49.770 | -0.174% | +0.067% | +0.522% | +0.072% | +0.116% |
| cached-ledger/512 | 70.063 | 70.319 | +0.366% | +0.031% | -0.361% | +0.134% | +0.290% |
| cached-ledger/2048 | 63.723 | 63.973 | +0.393% | -1.527% | -4.171% | +0.651% | +0.115% |

Strict speed acceptance: False. At least1% TPS and reply gain on both English code/prose, each above its own absolute control drift; exact tested outputs and zero new swap.

The once-per-process marker proves an eligible input was prepared, not shader execution frequency. Successful graph completion and exact tested answers qualify the run. No new swap; original launchers remain unchanged.

[Raw comparison](comparison.json).
