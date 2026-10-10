# Repeated-expert grouping: accurate, slower, parked

Astra designed and audited an isolated Q2_0 grouping experiment for the 48 GiB M5 Pro. The final version groups repeated selections in pairs, keeps the original singleton kernel, and uses bounded scratch already reserved by the backend. No additional model-memory allocation, quantization change, model download or default-launcher change.

The final four fresh operator launches run control/candidate/candidate/control. Each case times 60 measured graphs after four warmups; each graph contains eight sequential gate/up/SwiGLU/down blocks, weighted ten-expert reduction and residual per block. Two distinct full-512-expert weight sets exceed a tiny hot-weight working set. Real routing uses eight captured target events stratified across reuse counts at R4/R5. The times include every per-projection GPU map, barrier and compute dispatch. No callbacks or diagnostic route logging are active during timing.

| Rows | Route | Control per block | Candidate per block | Extra time | Bracket control drift |
| ---: | --- | ---: | ---: | ---: | ---: |
| 4 | real | 301.839 us | 384.266 us | +27.31% | +0.71% |
| 4 | distinct | 311.302 us | 338.646 us | +8.78% | +0.35% |
| 4 | shared | 295.104 us | 362.919 us | +22.98% | +0.51% |
| 5 | real | 362.391 us | 449.932 us | +24.16% | -0.08% |
| 5 | distinct | 373.430 us | 405.742 us | +8.65% | +0.43% |
| 5 | shared | 354.255 us | 447.234 us | +26.25% | +0.03% |

The predeclared gate required at least 10% less time on real R4, a gain above control drift, no more than 2% real-R5 slowdown, and no more than 5% all-distinct slowdown. It fails. Grouping remains off; full-model testing was skipped. These are component times, not tokens/second. The graphs omit the full model shared-expert branch and its scheduling; do not transfer these loss percentages to model TPS.

Final correctness: 42 graph cases per control/candidate launch, 336 CPU projection references, 9,446,400 output values bit-identical between modes, and 750 candidate route markers with exact fallback inventory. Actual and adversarial routes, duplicates within one token, one-to-six rows, activation/ID/weight strides, cancellation and wider values pass. Input, ID/padding and all synthetic weight bytes remain unchanged. Strict NMSE <1e-8 and max absolute error <1e-4 are retained.

Zero new swap in all six accepted final correctness/performance launches; minimum available RAM 32.03 GiB, peak process RSS 4.48 GiB. Model servers and native probes exited. All 12 existing engines are unchanged and 107 maintained offline tests pass. All work is local/uncommitted.

Development evidence is retained: V1 output parity passed, but its independent graphs allowed cross-block concurrency and its combined 2..5 kernel had severe high-reuse regression; those timings are throughput-only and excluded from final sequential comparison. Streamed V2/V3 passed CPU error thresholds but failed exact bit parity; both are rejected. V4 restores the known-exact ordered two-assignment body in a separate kernel and passes the unchanged bit gate. Large register working sets are a plausible performance explanation, not a measured hardware-counter diagnosis.

[Raw final evidence](comparison.json) · [Correctness comparison](../../features/20261009T152947347619Z-m5-group-check-expert-group/comparison.json) · [Predeclared plan](../../../config/m5_group_plan.json) · [Next bounded Astra card](../../research/20261009-astra-gate-up-plan.md)

Next: independently investigate combining the gate/up calculations with their SwiGLU step, so fewer GPU dispatches and intermediate values are needed. Keep down separate and grouping disabled. The card describes graph-consumer/allocator/alias guards and normal-graph accuracy/speed gates; it is preparation, not an implemented or measured speed upgrade.

[Current upstream PR30047](https://github.com/ggml-org/llama.cpp/pull/30047) still selects matvec below two tokens per expert (0.5 at K<=512). Our R4/R5 batches have 0.078125/0.09765625 per expert, so its documented MMA gate does not cover this case. This is a source-based inference, not a benchmark result.
