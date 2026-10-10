# October 9: three researched speed experiments

Implemented and tested independently. All reported model percentages use fresh controls within the same suite, beyond the previous conv-direct improvement. Historical TPS suites are not pooled or compounded.

Full model: Qwen3.8-Flash-Next GSQ-RCO Q2_0, depth-three MTP, packed shared Q3 helper, mixed placement with eight CPU workers, Tensor API on, F16 4K cache. Four launches per experiment, control/candidate/candidate/control, three measured repeats plus excluded warmup per workload, 256 fresh output tokens. Cached short responses are separate.

| Experiment | Workload | Control TPS | Candidate TPS | TPS change | Full reply time reduction |
| --- | --- | ---: | ---: | ---: | ---: |
| reduce10 | chinese/56 | 40.636 | 41.007 | +0.91% | +0.89% |
| reduce10 | code/48 | 59.415 | 59.948 | +0.90% | +0.94% |
| reduce10 | prose/53 | 39.845 | 40.262 | +1.05% | +1.02% |
| reduce10 | synthetic/512 | 48.462 | 48.880 | +0.86% | +0.87% |
| reduce10 | synthetic/2048 | 49.813 | 50.246 | +0.87% | +0.90% |
| sampling-view | chinese/56 | 40.687 | 40.651 | -0.09% | -0.08% |
| sampling-view | code/48 | 59.523 | 59.481 | -0.07% | -0.10% |
| sampling-view | prose/53 | 39.983 | 39.977 | -0.01% | +0.01% |
| sampling-view | synthetic/512 | 48.471 | 48.391 | -0.17% | -0.32% |
| sampling-view | synthetic/2048 | 49.904 | 49.881 | -0.05% | -0.24% |

## Decisions

1. **Ten-expert reduction:** preserves non-NaN output bits in the operator checks and exact tested model tokens/text. Fresh writing rises 0.90-1.05%, with 0.89-1.02% quicker full replies. This is a small measured benefit; it narrowly misses the preset requirement for at least 1% TPS and reply-time benefit on two real workloads. Keep the opt-in engine; ordinary launchers stay unchanged.
2. **Sampling-output view:** small-model first-read checks cover five backend/CPU modes, multiple rows and negative indexing. Actual common sampling checks cover greedy/stochastic sampling and both grammar paths, with identical 18 token selections. Already-ready retrieval saves only 0.067141 microseconds per row (0.097706 to 0.030565 us). Matched full-model writing changes -0.01 to -0.09%, within bracket drift. Keep off as a speed feature. The initial 0.5MiB new-swap control is excluded completely.
3. **Exact BF16 projections:** adapted the new MLX register-input/split-K design to BF16 stored weights, F32 activations and outputs. Relaxed precision was rejected after an API probe showed greater rounding error; the accepted design uses relaxed_precision=false. Shape/type/stride/batch/availability guards limit TensorOps to exact four/five-row projections, preserve existing residual fusion and retain all other paths. Explicit scratch is at most 15KiB; no new runtime weight cache. The operator fixture deliberately uses 20 distinct copies (125MiB working set) to test complete graphs under normal fusion, without per-op callbacks.
   Both directions, five long-K splits, and a conservative exact-K MMA specialization were screened. Twelve small operator-check processes provide 864 CPU-reference shape/layout cases; every unaffected fallback comparison is bit-identical. Eight broader GPU math/residual configurations also pass. After screening, fresh independent ABBA operator repeats still qualify no variant for the preset >=10% operator win. No full-model kernel TPS benefit is claimed.

| Kernel confirmation | Shape K x M | Rows | Control us/op | Candidate us/op | Time reduction | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| hc-special | 10240 x 320 | 4 | 35.580 | 35.417 | +0.46% | -3.21% |
| hc-special | 10240 x 320 | 5 | 35.719 | 36.041 | -0.90% | -0.23% |
| hc-special | 320 x 10240 | 4 | 36.174 | 35.613 | +1.55% | +2.36% |
| hc-special | 320 x 10240 | 5 | 35.642 | 35.920 | -0.78% | -1.12% |
| hc-down-ks8 | 10240 x 320 | 4 | 36.001 | 40.075 | -11.32% | -0.80% |
| hc-down-ks8 | 10240 x 320 | 5 | 35.554 | 40.853 | -14.90% | -3.47% |
| hc-up | 320 x 10240 | 4 | 33.774 | 36.964 | -9.44% | -8.13% |
| hc-up | 320 x 10240 | 5 | 33.866 | 36.931 | -9.05% | -7.27% |

Negative time reduction means slower. The long-K TensorOps variant takes 11-16% longer across plain/residual cases. The short-K variant shows no gain and substantial bracket drift in some cases; its exact slowdown is uncertain. Conservative specialization is mixed (roughly -1.4 to +3.0% across affected cases), below the gate. These operator numbers are not model TPS or hardware accelerator-utilization measurements.

## Validation and provenance

The two accepted full-model suites provide 256 answer/cache checks and 168 fresh/cached output comparisons, with identical token IDs and text. Zero new swap in all eight accepted launches; minimum available memory 2.452GiB, peak process RSS 38.280GiB. RSS omits some Metal/shared/compressed accounting and is not total model residency.
103 maintained offline tests pass. Nine original engines and their native artifacts match the snapshot taken before implementation. All new paths are isolated experimental engines; default launchers are unchanged. Model servers are stopped. No commit, push, PR or deployment was performed.
The ten-expert suite retained its passing first control after a preflight-only rejection. Resume support and bounded between-launch memory waiting were added before continuing. Native source/artifacts, model, tuning, workload/settings and response measurement stayed unchanged; pre-change and resumed offline receipts are retained. No guard was relaxed.
Failed compile/API/inventory/logging attempts are retained under bench/runtime/m5-next and bench/features. They are excluded from accepted speed evidence. The first matrix probe exposed stdout/stderr interleaving; line-buffered JSON markers now make malformed evidence fail clearly. Actual route checks corrected an initial assumption that three-row BF16 batches used MMA.

## Evidence

- [Ten-expert full-model comparison](../20261009T130146Z-m5-ten-expert-reduction/REPORT.md)
- [Sampling full-model comparison](../20261009T132908Z-m5-sampling-view-clean-retry/REPORT.md)
- [Sampling small-model and CPU-overhead checks](../../features/20261009T132329116485Z-m5-sampling-read_cost-conv-direct/comparison.json)
- [Kernel confirmation](../20261009T135603Z-m5-hc-operator-confirmation/comparison.json)
- [Complete receipts and decisions](results.json)
- [Astra source research and next candidates](../../research/20261009-astra-next-speed-ideas.md)

The next higher-value investigation is grouped repeated-expert work or fused gate/up projections, using the recorded real routing distribution. These remain ideas, not implemented speed gains.
