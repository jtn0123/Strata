# Monitoring baseline: Qwen3.5-4B Q4_K_M

Four fresh processes: P07 control, observer build with monitoring off, monitoring on, then P07 control. Each runs one excluded warmup and three measured answers per English workload. All 32 capped answers have identical input/output IDs, text, finish type and helper counters. No helper is enabled on this model.

| Workload | Uninstrumented TPS | First token | 128-token reply | Monitoring TPS cost | Control TPS drift |
| --- | ---: | ---: | ---: | ---: | ---: |
| code | 77.886 | 79.46 ms | 1.7102 s | 2.351% | 0.359% |
| prose | 77.818 | 80.21 ms | 1.7124 s | 2.099% | 0.236% |

The observer build with monitoring off differs by only -0.152%/-0.089% in code/prose TPS, inside the controls’ observed variation. Detailed monitoring stays off during optimization speed comparisons. This small-model rate does not replace the full-model P07 baseline.

| Workload / phase | Phase wall | Recorded GPU interval coverage | Graph rebuilds / reuses | Reset + build + allocate |
| --- | ---: | ---: | ---: | ---: |
| code / prompt | 79.696 ms | 92.23% | 2 / 0 | 2.312 ms |
| code / generation | 1669.853 ms | 93.96% | 1 / 126 | 1.086 ms |
| prose / prompt | 80.231 ms | 92.51% | 2 / 0 | 2.201 ms |
| prose / generation | 1667.006 ms | 94.01% | 1 / 126 | 1.058 ms |

| Workload / phase | CPU area | Calls | Wall interval union | Outside recorded GPU |
| --- | --- | ---: | ---: | ---: |
| code / prompt | target/allocate | 2 | 1.755 ms | 1.755 ms |
| code / prompt | target/build | 2 | 0.529 ms | 0.529 ms |
| code / prompt | target/inputs | 2 | 0.008 ms | 0.008 ms |
| code / prompt | target/memory_apply | 2 | 0.005 ms | 0.005 ms |
| code / prompt | target/reset | 2 | 0.025 ms | 0.025 ms |
| code / generation | target/allocate | 1 | 0.827 ms | 0.827 ms |
| code / generation | target/build | 1 | 0.248 ms | 0.248 ms |
| code / generation | target/inputs | 127 | 0.132 ms | 0.132 ms |
| code / generation | target/memory_apply | 127 | 0.053 ms | 0.053 ms |
| code / generation | target/reset | 1 | 0.011 ms | 0.011 ms |
| prose / prompt | target/allocate | 2 | 1.670 ms | 1.670 ms |
| prose / prompt | target/build | 2 | 0.506 ms | 0.506 ms |
| prose / prompt | target/inputs | 2 | 0.010 ms | 0.010 ms |
| prose / prompt | target/memory_apply | 2 | 0.005 ms | 0.005 ms |
| prose / prompt | target/reset | 2 | 0.025 ms | 0.025 ms |
| prose / generation | target/allocate | 1 | 0.817 ms | 0.817 ms |
| prose / generation | target/build | 1 | 0.233 ms | 0.233 ms |
| prose / generation | target/inputs | 127 | 0.131 ms | 0.131 ms |
| prose / generation | target/memory_apply | 127 | 0.056 ms | 0.056 ms |
| prose / generation | target/reset | 1 | 0.010 ms | 0.010 ms |

All phase values are medians of three measured requests in the instrumented process. Setup stages, helper work and GPU intervals may overlap; do not add overlapping totals. The uncovered intervals are a diagnostic bound, not measured GPU idle time, SSD wait or a causal speedup budget.

Minimum host available: **30.132 GiB**. Maximum sampled server RSS: **2.973 GiB**; this is not total Metal or unique physical memory. **Zero new swap**, normal pressure, healthy monitors and owned children shut down. Clock mapping spread: **34.791 microseconds**; widest calibration bracket: **1.000 microseconds**.

This model has no prediction helper, so helper planning, replay, drafting and acceptance bottlenecks remain unmeasured. Prompt-checkpoint creation markers cover that operation only; they do not cover all speculative state saves/restores. Complete-answer quality, long prompts, cached continuations and full internal tensor-state equivalence remain outside this baseline.

[Reproducible summary](MONITORING.json), [raw campaign](result.json), [frozen protocol](frozen.json), [summary generator](summarize_monitoring.py).
