# M5 helper workers and confidence results

Measured October 6, 2026 on the 48 GiB, 18-CPU-core, 20-GPU-core M5 Pro. UTC artifact names fall on October 7. This follows the [Tensor API/depth batch](M5-RESULTS.md) and [GPU matrix batch](M5-GPU-TUNING.md). All twelve prepared comparisons are now complete.

## Decision

- Keep the existing ordinary, writing and follow-up settings. These are small workload-dependent gains, with four measured samples per setting.
- Offer `Start Strata - Twelve Helper Workers Trial.command`: depth three, twelve CPU helper workers, confidence 0.0 and Tensor API on, using the current `mtp-mma` engine. Code increases 56.33 to 56.85 TPS (+0.94%). The long fresh-input reply falls from 6.3427 to 6.2025 seconds (+2.21% quicker).
- Offer `Start Strata - Prose Confidence Trial.command`: depth three, eight helper workers and confidence 0.4. This one prose prompt increases 42.83 to 43.61 TPS (+1.83%); reply time falls 3.2575 to 3.2060 seconds (+1.58% quicker). Other workloads regress, so it is a narrow trial.
- Neither optional setting is combined with the two-tile or depth-six trials, or with each other. No additional model capacity is established. Model/helper bytes, lazy SSD lookup, native engines, expert kernels and GPU memory limits are preserved.

## Confidence for writing, depth three

| Workload / input | Control TPS | 0.2 TPS | Gain | 0.4 TPS | Gain |
| --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | 40.07 | 40.27 | +0.48% | 39.54 | -1.33% |
| code / 48 | 56.36 | 56.34 | -0.03% | 56.04 | -0.57% |
| prose / 53 | 42.83 | 43.18 | +0.83% | 43.61 | +1.83% |
| synthetic / 512 | 49.02 | 48.94 | -0.16% | 45.84 | -6.50% |
| synthetic / 2048 | 49.95 | 49.93 | -0.05% | 48.10 | -3.72% |
| cached-ledger / 512 | 65.01 | 66.00 | +1.53% | 66.12 | +1.71% |
| cached-ledger / 2048 | 64.09 | 65.74 | +2.59% | 65.80 | +2.67% |

Confidence skips helper guesses below the selected probability; it does not skip the target model's answer verification. On the prose test the helper proposes 160 tokens and accepts 73 at confidence 0.0, versus 127 proposed and 72 accepted at 0.4. Acceptance rises from 45.63% to 56.69% mainly because fewer guesses are made. Both candidate launches reproduce the control's prose, code, Chinese and long synthetic outputs. The short synthetic output changes in both measured repeats at 0.4: eight of ten paired fresh outputs match, so that short synthetic difference is not a pure speed comparison on identical token choices. Answer checks still pass; this is not a broad quality evaluation.

The cached writing-control TPS drifts +4.37%/+5.73% for 512/2048 history, more than the reported candidate gains. Those cached gains are inconclusive. The prose control drifts only +0.23%, while all four confidence-0.4 prose samples are faster, approximately 43.5-43.7 TPS. This supports a small gain on this prompt, not a general writing upgrade.

## Confidence for follow-ups, depth four

| Workload / input | Control TPS | 0.2 TPS | Gain | 0.4 TPS | Gain |
| --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | 35.79 | 36.02 | +0.63% | 37.30 | +4.22% |
| code / 48 | 56.58 | 56.60 | +0.05% | 54.99 | -2.80% |
| prose / 53 | 41.84 | 42.40 | +1.34% | 41.80 | -0.08% |
| synthetic / 512 | 46.22 | 46.20 | -0.04% | 44.36 | -4.03% |
| synthetic / 2048 | 49.63 | 49.67 | +0.07% | 46.27 | -6.76% |
| cached-ledger / 512 | 68.97 | 68.94 | -0.05% | 68.88 | -0.14% |
| cached-ledger / 2048 | 69.42 | 69.42 | +0.00% | 63.55 | -8.46% |

Confidence 0.2 leaves the cached generation rate essentially unchanged. Confidence 0.4 reduces long cached generation from 69.42 to 63.55 TPS (-8.46%) and makes that complete reply 5.46% slower. The apparent Chinese gain does not justify changing the follow-up profile. Candidate 0.4 changes three of ten paired fresh outputs; candidate 0.2 reproduces all ten. Keep confidence 0.0 for the existing follow-up launcher.

## CPU helper workers, depth three

| Workload / input | 8 workers TPS | 6 TPS | Gain | 12 TPS | Gain |
| --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | 40.06 | 40.50 | +1.09% | 40.28 | +0.56% |
| code / 48 | 56.33 | 56.76 | +0.77% | 56.85 | +0.94% |
| prose / 53 | 42.80 | 43.29 | +1.16% | 43.12 | +0.76% |
| synthetic / 512 | 48.91 | 49.49 | +1.19% | 49.31 | +0.81% |
| synthetic / 2048 | 49.93 | 50.45 | +1.05% | 50.34 | +0.82% |
| cached-ledger / 512 | 66.06 | 66.76 | +1.06% | 66.42 | +0.54% |
| cached-ledger / 2048 | 65.76 | 66.39 | +0.97% | 66.26 | +0.76% |

Six workers slightly improve generation but process the 2048-token input at 521.92 rather than 539.26 input tokens/s (-3.21%). First token increases from 3.7986 to 3.9247 seconds, and the complete reply is 1.56% slower. Code samples at six workers vary roughly 56.21-57.05 TPS. Twelve workers are the more balanced optional trial: input processing reaches 556.75 tokens/s (+3.24%), first token is 3.14% quicker, and all measured complete-reply medians improve. Every worker candidate reproduces all ten paired fresh outputs in both launches.

| Workload / input | Stock reply | 12-worker reply | Reply quicker | Stock first token | 12-worker first token |
| --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | 3.4670 s | 3.4464 s | +0.59% | 0.2963 s | 0.2939 s |
| code / 48 | 2.5387 s | 2.5164 s | +0.88% | 0.2834 s | 0.2825 s |
| prose / 53 | 3.2603 s | 3.2363 s | +0.74% | 0.2929 s | 0.2913 s |
| synthetic / 512 | 3.5136 s | 3.4563 s | +1.63% | 0.9174 s | 0.8830 s |
| synthetic / 2048 | 6.3427 s | 6.2025 s | +2.21% | 3.7986 s | 3.6792 s |
| cached-ledger / 512 | 0.6415 s | 0.6385 s | +0.47% | 0.2762 s | 0.2750 s |
| cached-ledger / 2048 | 0.6395 s | 0.6355 s | +0.63% | 0.2895 s | 0.2882 s |

Cached outputs are short 25/24-token ledger answers. Their 66 TPS rate is not a general writing rate. The twelve-worker trial keeps depth three; it does not replace the depth-four long-follow-up or depth-six short-structured trials.

## Method and validation

Each comparison runs control/A/B/B/A/control. Each setting has two model launches, an excluded warmup for each workload, and two measured repeats per launch. Tables use the median of four samples. Comparisons keep the packed mixed Q3 helper, F16 cache, 4K context, batch/ubatch 512, eight target CPU workers, temperature 0.6, seed 1234 and Tensor API on. Only the named axis changes. Profiling callbacks remain disabled. Fresh replies are fixed at 128 output tokens; cached replies stop naturally. Percentages use each suite's own fresh controls, without stacking historical gains.

- Clean retry: 18 full-model speed passes, 540/540 answer checks, 1716/1716 CPU-reference GPU math checks; zero observed new swap and no guard stops.
- Lowest available RAM during clean speed trials: 3.344 GiB. Peak process RSS: 38.488 GiB. RSS includes shared mappings and is not total Metal memory.
- Both optional launchers pass nine real app/API check groups each: Unicode, greedy native/adapter parity, OpenAI streaming/non-streaming, Anthropic, explicit tool/overflow rejection, cancellation and disconnect recovery. Both app trials record zero new swap; minimum available RAM is 3.418 GiB. Functional timings are excluded from speed results.
- All 40 offline checks and both launcher shell syntax checks pass. All six native source/binary receipts verify after testing; comparison summaries were recomputed from immutable raw results.
- [Batch receipt](features/20261006-m5-helper-batch.json), [offline checks](features/20261006-m5-helper-offline.log), [quiet retry preflight](features/20261007T034427Z-m5-helper-retry-preflight.json).

## Excluded first attempt and background work

The first writing comparison overlapped unrelated VoltTracker Android builds. Java CPU usage reached 397% during writing and 1531% during the next follow-up attempt. The follow-up model load crossed its 128 MiB new-swap guard (138.18 MiB sampled growth) and was stopped. A later Metal assertion occurred during forced shutdown after the guard; it is not counted as an inference result. Other agents' builds were not killed, and no native or harness source was changed to fix an environmental failure.

Those original records are preserved and excluded from adoption; [interruption receipt](features/20261006-m5-helper-resource-interruption.json), [excluded writing comparison](results/20261007T032352Z-m5-confidence-writing/comparison.json), [failed follow-up comparison](results/20261007T033300Z-m5-confidence-followup/comparison.json), [failed run](results/20261007T033307Z-m5-confidence-followup-1-0.0/result.json). The whole session did incur new swap in that failed attempt. Zero-growth claims above apply only to the clean retry and the subsequent app checks.

After four quiet CPU probes, the whole three-comparison batch was restarted. In retry resource samples, maximum observed Java CPU was 2.4%, 0.3% and 0.6%; no heavy Android build load was observed. Other background activity remained: mediaanalysisd reached 40.7%/63.5%, and duetexpertd reached 78.9% during workers, each less than one core. These are top-eight process-name groups sampled every two seconds, not a complete CPU/GPU trace. Small gains still need broader workloads before becoming defaults.

## Control variation

| Comparison | Largest absolute fresh TPS control drift | Largest absolute cached TPS control drift |
| --- | ---: | ---: |
| confidence-writing | 0.621% | 5.731% |
| confidence-followup | 0.534% | 0.432% |
| helper-workers | 0.081% | 0.162% |

The worker controls are stable, while short cached replies still have large repeat-to-repeat rate differences. Four samples and two launches per setting are useful evidence for optional trials, not proof of a universal one-percent improvement.

## Next work

All twelve prepared comparisons are complete. Larger GPU work should first add request-phase and tensor-shape timing evidence, separating prompt processing from generation and dense from routed-expert operations. Then choose one compressed-weight/dequantization kernel with a measured decoding cost. Hardware AI-accelerator occupancy is still unmeasured; no new compressed-weight shader or separate Neural Engine runtime is implemented. All model servers, Colima and Grafana are stopped after this batch. No VM or service was restarted.

## Raw evidence

- [confidence-writing](results/20261007T034515Z-m5-confidence-writing/comparison.json) and [comparison table](results/20261007T034515Z-m5-confidence-writing/COMPARISON.md); the record links every full-model pass.
- [confidence-followup](results/20261007T035416Z-m5-confidence-followup/comparison.json) and [comparison table](results/20261007T035416Z-m5-confidence-followup/COMPARISON.md); the record links every full-model pass.
- [helper-workers](results/20261007T040326Z-m5-helper-workers/comparison.json) and [comparison table](results/20261007T040326Z-m5-helper-workers/COMPARISON.md); the record links every full-model pass.
- [prose-confidence app proof](results/20261007T041229Z-mma-app-3-8.json) and [integration checks](results/20261007T041233Z-flash-integration.json).
- [twelve-workers app proof](results/20261007T041255Z-mma-app-3-12.json) and [integration checks](results/20261007T041300Z-flash-integration.json).
- [GPU math receipt](features/20261007T034515Z-m5-math-mtp-mma-on-stock/checks.json).
- [GPU math receipt](features/20261007T035416Z-m5-math-mtp-mma-on-stock/checks.json).
- [GPU math receipt](features/20261007T040326Z-m5-math-mtp-mma-on-stock/checks.json).
