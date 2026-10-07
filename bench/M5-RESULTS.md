# M5 Tensor API and prediction-depth measurements

Measured October 6, 2026 on the 48 GiB, 20-GPU-core M5 Pro. Artifact timestamps use UTC and fall on October 7. The user authorized this batch after an idle media-analysis process exited and Grafana was unloaded; Colima remained stopped. About 36.1 GiB was available before testing.

## Decision

- Keep Tensor API enabled. It was already enabled in the working baseline; this is confirmation of its contribution, not a newly added gain.
- Keep the optional writing profile at depth three and existing fast-follow-up profile at depth four.
- Offer depth six only as a short structured follow-up trial: the matched 512-token cached-ledger case improves 68.98 to 75.50 TPS (+9.44%), and total reply time falls 0.6252 to 0.5947 seconds (+4.88% quicker). Long cached replies are effectively tied. Fresh code/prose/Chinese writing slows.
- The ordinary prediction-off launcher, existing launchers, model bytes, native binaries, routed-expert kernels, lazy SSD lookup and GPU memory limit are preserved. The separate short trial passed the real API checks.

## Method and validation

Controls bracket candidates: on/off/off/on for each Tensor API comparison; 3/5/6/6/5/3 and 4/5/6/6/5/4 for prediction depth. Each setting has two model launches, one excluded warmup per workload and two measured repeats per launch. Tables use medians of four measured samples per setting/workload. Percentages use fresh matched controls, without pooling historical suites.

All comparisons use the current `mtp-mma` engine, packed mixed Q3 helper, F16 cache, 4K context, batch/ubatch 512, eight target/helper workers, temperature 0.6, seed 1234 and confidence threshold 0.0. Fresh workloads produce 128 output tokens with EOS ignored for timing. Cached answers stop naturally and are checked for correctness.

The cached output counts observed here were [25] tokens at history budget 512 and [24] at 2048. Those short-answer rates do not establish the speed of long chat replies.

- 20 benchmark passes; 600/600 answer checks; zero observed swap growth and no RAM-guard stops.
- 4004/4004 CPU-reference GPU math checks across 7 prerequisite launches. Repeated prerequisites are counted separately.
- Minimum available RAM during speed tests: 2.448 GiB; peak process RSS: 38.788 GiB. RSS includes shared mappings and is not total Metal memory.
- Nine real app/API check groups pass at depth six: Unicode, greedy native/adapter token parity, OpenAI streaming/non-streaming, Anthropic, explicit tool/overflow rejection, cancellation and client-disconnect recovery. Functional-check timings are excluded from speed results.
- All 40 offline workflow checks pass again, the new launcher passes shell syntax checking, all report evidence links exist, and all six native engine/source receipts verify after the batch. [Batch receipt](features/20261006-m5-first-batch.json), [offline checks](features/20261006-m5-first-batch-offline.log).

## Tensor API contribution

This compares the Metal Tensor API path with it disabled; it is not a hardware AI-utilization counter and does not enable the separate Neural Engine. Fixed prompts and seeds still can produce different tokens and helper acceptance because floating-point paths differ. End-to-end generation differences include that effect; they are not a pure kernel-speed measurement.

| Profile / workload | On TPS | Off TPS | On vs off TPS | On first token | Off first token | On complete reply | Off complete reply |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| tensor-writing / synthetic 512 | 48.01 | 48.35 | -0.70% | 0.9136 s | 1.6353 s | 3.5699 s | 4.2617 s |
| tensor-writing / synthetic 2048 | 49.75 | 47.62 | +4.46% | 3.8283 s | 6.5633 s | 6.3823 s | 9.2263 s |
| tensor-writing / code 48 | 56.07 | 52.29 | +7.23% | 0.2844 s | 0.3817 s | 2.5497 s | 2.8105 s |
| tensor-writing / prose 53 | 42.50 | 42.50 | +0.01% | 0.2936 s | 0.3969 s | 3.2812 s | 3.3850 s |
| tensor-writing / chinese 56 | 39.83 | 35.52 | +12.16% | 0.2973 s | 0.4014 s | 3.4860 s | 3.9773 s |
| tensor-writing / cached-ledger 512 | 64.93 | 64.64 | +0.45% | 0.2773 s | 0.3682 s | 0.6489 s | 0.7416 s |
| tensor-writing / cached-ledger 2048 | 63.87 | 63.58 | +0.45% | 0.2952 s | 0.3820 s | 0.6561 s | 0.7436 s |
| tensor-followup / synthetic 512 | 45.79 | 50.35 | -9.05% | 0.9118 s | 1.6183 s | 3.6831 s | 4.1406 s |
| tensor-followup / synthetic 2048 | 49.54 | 43.82 | +13.04% | 3.7894 s | 6.4823 s | 6.3573 s | 9.3797 s |
| tensor-followup / code 48 | 56.54 | 52.13 | +8.45% | 0.2824 s | 0.3808 s | 2.5289 s | 2.8174 s |
| tensor-followup / prose 53 | 41.84 | 40.55 | +3.18% | 0.2917 s | 0.3956 s | 3.3286 s | 3.5278 s |
| tensor-followup / chinese 56 | 35.67 | 30.81 | +15.80% | 0.2931 s | 0.4003 s | 3.8534 s | 4.5278 s |
| tensor-followup / cached-ledger 512 | 67.39 | 68.53 | -1.66% | 0.2791 s | 0.3680 s | 0.6372 s | 0.7208 s |
| tensor-followup / cached-ledger 2048 | 67.78 | 69.37 | -2.29% | 0.2946 s | 0.3811 s | 0.6353 s | 0.7130 s |

For the writing-profile 2048-token input, enabling the path improves input processing 312.08 to 535.07 input TPS (+71.46%), reduces first-token wait 41.67% and completes the full reply 30.83% sooner. This path was already enabled before this batch.

## Prediction depth for fresh writing

| Workload / input | Depth 3 TPS | Depth 5 TPS | Gain vs 3 | Depth 6 TPS | Gain vs 3 |
| --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | 40.16 | 33.26 | -17.19% | 29.91 | -25.52% |
| code / 48 | 56.43 | 53.54 | -5.12% | 50.38 | -10.72% |
| prose / 53 | 42.84 | 36.70 | -14.34% | 34.47 | -19.53% |
| synthetic / 512 | 49.01 | 41.23 | -15.87% | 37.31 | -23.88% |
| synthetic / 2048 | 50.03 | 45.57 | -8.90% | 43.40 | -13.25% |

Increasing depth reduces the helper acceptance fraction and adds work. This batch establishes the end-to-end slowdown; it does not isolate its GPU, CPU or rollback-copy components.

## Prediction depth for cached follow-ups

| Cached history | Depth | TPS | Gain vs depth 4 | Complete reply | Reply quicker vs 4 | First token |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 512 | 4 | 68.98 | +0.00% | 0.6252 s | +0.00% | 0.2750 s |
| 512 | 5 | 67.03 | -2.82% | 0.6337 s | -1.36% | 0.2755 s |
| 512 | 6 | 75.50 | +9.44% | 0.5947 s | +4.88% | 0.2769 s |
| 2048 | 4 | 69.40 | +0.00% | 0.6203 s | +0.00% | 0.2881 s |
| 2048 | 5 | 62.16 | -10.43% | 0.6629 s | -6.87% | 0.2928 s |
| 2048 | 6 | 69.73 | +0.48% | 0.6200 s | +0.04% | 0.2897 s |

At depth six the short gain is about 30 milliseconds per complete answer. The long case gains only 0.48% generation speed and 0.04% total reply time, so it does not justify replacing the existing long-follow-up setting. This is one structured ledger task; other short-answer workloads still need measurements.

## Variation

| Comparison | Largest absolute fresh TPS control drift | Largest absolute cached TPS control drift |
| --- | ---: | ---: |
| tensor-writing | 0.276% | 5.197% |
| tensor-followup | 1.906% | 3.496% |
| depth-writing | 0.080% | 0.515% |
| depth-followup | 0.163% | 0.166% |

The direct depth-four/six follow-up controls drift less than 0.17% in generation speed. Earlier Tensor API cached controls drift up to 5.20%; their sub-3% generation differences are not convincing gains. The input/first-token effect is much larger and repeated.

## GPU timing diagnostics

The isolated `m5-lab` stock engine passed GPU correctness and recorded usable command-buffer timestamps at depths three and four. Its timing callbacks were enabled only for diagnostics and were absent from speed comparisons.

| Depth | Timed buffers | GPU interval union | First-to-last interval span | Uncovered interval gaps | Cumulative helper draft wall time | Minimum available RAM |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 391 | 6.2058 s | 7.9000 s | 1.6942 s | 262.912 ms | 2.934 GiB |
| 4 | 463 | 6.3160 s | 7.6286 s | 1.3125 s | 330.559 ms | 3.408 GiB |

Both diagnostics record zero swap growth. Their totals include warmup, prompt processing and generation. Long prompt graphs dominate the aggregate; this does not establish the helper share during decoding. Context roles and request phases are not explicitly tagged. Original graph node counts repeat across command-buffer partitions and precede fusion; they are not unique executed-kernel counts. GPU interval gaps do not prove GPU idleness, and overlapping helper wall time must not be added to GPU intervals. Hardware accelerator occupancy and per-kernel time remain unmeasured.

## Next experiments

At the end of this first batch, eight comparisons remained. The subsequent [M5 GPU tuning batch](M5-GPU-TUNING.md) completes build parity, BF16/Q2 row thresholds, tile width and matrix worker split. The later [helper/confidence batch](M5-HELPER-RESULTS.md) completes writing/follow-up confidence and helper CPU workers; all twelve prepared comparisons are now complete. A future diagnostic should tag request phases and relevant tensor shapes/types before implementing compressed-weight cooperative-input kernels. No compressed-weight shader or separate Neural Engine runtime was implemented or tested in this batch.

## Raw evidence

- [tensor-writing](results/20261007T004003Z-m5-tensor-writing/comparison.json) and [table](results/20261007T004003Z-m5-tensor-writing/COMPARISON.md); the record links all individual passes.
- [tensor-followup](results/20261007T004710Z-m5-tensor-followup/comparison.json) and [table](results/20261007T004710Z-m5-tensor-followup/COMPARISON.md); the record links all individual passes.
- [depth-writing](results/20261007T005423Z-m5-depth-writing/comparison.json) and [table](results/20261007T005423Z-m5-depth-writing/COMPARISON.md); the record links all individual passes.
- [depth-followup](results/20261007T010359Z-m5-depth-followup/comparison.json) and [table](results/20261007T010359Z-m5-depth-followup/COMPARISON.md); the record links all individual passes.
- [Stock timing profile](features/20261007T003927Z-m5-profile-3-on/profile.json).
- [Stock timing profile](features/20261007T003945Z-m5-profile-4-on/profile.json).
- [Depth-six real app proof](results/20261007T011338Z-mma-app-6-8.json); [integration checks](results/20261007T011343Z-flash-integration.json).
- [GPU math receipt](features/20261007T003917Z-m5-math-m5-lab-on-stock/checks.json).
- [GPU math receipt](features/20261007T004003Z-m5-math-mtp-mma-off-stock/checks.json).
- [GPU math receipt](features/20261007T004010Z-m5-math-mtp-mma-on-stock/checks.json).
- [GPU math receipt](features/20261007T004710Z-m5-math-mtp-mma-off-stock/checks.json).
- [GPU math receipt](features/20261007T004717Z-m5-math-mtp-mma-on-stock/checks.json).
- [GPU math receipt](features/20261007T005424Z-m5-math-mtp-mma-on-stock/checks.json).
- [GPU math receipt](features/20261007T010359Z-m5-math-mtp-mma-on-stock/checks.json).
