# Few-row GPU math on the 48 GiB M5 Pro

October 6, 2026. Full Qwen3.8-Flash-Next GSQ-RCO Q2_0, unchanged packed shared Q3 helper, mixed CPU/GPU helper placement, all target layers on Metal, 4K context, F16 cache, batch/ubatch 512, eight target and helper workers, temperature 0.6.

## Decision

Keep the patch in the optional writing and fast follow-up launchers. Writing now uses `mtp-mma` with three predicted tokens; fast follow-ups use that engine with four. The ordinary launcher retains its existing prediction-off engine, and the original balanced shared launcher remains on the unpatched two-token profile.

Three-token prediction is the stronger general writing/prose profile. Four reaches 56.7 TPS in this code test, less than 1% above the three-token result, but is slower for short writing, prose and Chinese. Four remains the cached follow-up choice. One-token prediction gains less than 1% on short writing and has no convincing overall benefit from this patch.

## Upgrading the previous optional profiles

These controls were freshly remeasured in this suite. They are not the earlier historical 44.5, 48.2 and 56.4 TPS samples. Writing changes both the kernel and prediction depth from one to three. Code and cached follow-ups isolate the kernel at unchanged depth. These profile changes must not be added to the kernel-only percentages below.

| Workload | Prior depth | New depth | Prior TPS | New TPS | Output gain | Prior complete reply | New complete reply | Reply quicker |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Short writing | 1 | 3 | 43.85 | 48.91 | +11.53% | 3.8241 s | 3.5307 s | +7.67% |
| Code | 3 | 3 | 48.12 | 56.21 | +16.81% | 2.9340 s | 2.5436 s | +13.30% |
| Long cached follow-up | 4 | 4 | 57.70 | 69.24 | +20.00% | 0.6992 s | 0.6217 s | +11.09% |

[Machine-readable profile upgrades](features/20261006-mma-profile-upgrades.json). The short-writing upgrade finishes 7.7% sooner; code finishes 13.3% sooner; the longer cached follow-up finishes 11.1% sooner. Cached replies contain only about 24-25 output tokens. Their 69 TPS result is not a general writing rate.

## Kernel alone, matching prediction depth

| Depth | Workload / input | Control TPS | Patch TPS | Output gain | Reply quicker | Control TPS drift |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 3 | chinese / 56 | 34.32 | 40.10 | +16.85% | +13.57% | +0.04% |
| 3 | code / 48 | 48.12 | 56.21 | +16.81% | +13.30% | +1.00% |
| 3 | prose / 53 | 36.64 | 42.78 | +16.76% | +13.48% | +0.98% |
| 3 | synthetic / 512 | 41.83 | 48.91 | +16.93% | +11.07% | +1.72% |
| 3 | synthetic / 2048 | 43.08 | 49.85 | +15.71% | +6.64% | +0.85% |
| 3 | cached-ledger / 512 | 56.25 | 66.26 | +17.81% | +10.48% | +1.95% |
| 3 | cached-ledger / 2048 | 55.50 | 65.68 | +18.34% | +10.72% | +5.27% |
| 4 | chinese / 56 | 29.47 | 35.87 | +21.72% | +16.88% | +0.09% |
| 4 | code / 48 | 46.64 | 56.68 | +21.52% | +16.30% | -0.02% |
| 4 | prose / 53 | 34.45 | 41.90 | +21.61% | +16.67% | +0.18% |
| 4 | synthetic / 512 | 38.15 | 46.23 | +21.20% | +14.12% | +0.11% |
| 4 | synthetic / 2048 | 41.25 | 49.66 | +20.37% | +8.08% | -0.08% |
| 4 | cached-ledger / 512 | 56.66 | 68.91 | +21.63% | +12.23% | +0.64% |
| 4 | cached-ledger / 2048 | 57.70 | 69.24 | +20.00% | +11.09% | +0.11% |

The three-token fresh workloads improve 15.7-16.9% TPS; four-token fresh workloads improve 20.4-21.7%. Draft acceptance is identical between control and candidate on every compared workload, so the measured gain is not from more successful guesses. The patch mainly speeds output generation; long-input throughput/first-token changes are small. It makes no model-file compression or SSD bandwidth improvement.

Three-token fresh control drift ranges from 0.04% to 1.72%; four-token control drift is at most 0.64% across all workloads. The three-token longer cached control drifts 5.27%, so its exact percentage deserves more caution. The selected four-token longer cached control drifts only 0.11%. One-token fresh controls drift up to 4.37%; its sub-1% apparent improvements are not grounds for adoption. OS temperature and file cache are not controlled, and the cause of the earlier drift was not isolated.

## What changed

The new build applies the unchanged dense portion of [llama.cpp PR #30065](https://github.com/ggml-org/llama.cpp/pull/30065), commit `b0cb151326e6b436c265c641f23235864f7de090`, on top of our existing shared-helper patch and the same v0.6.0 runtime pin. The PR was open and draft when inspected for this run. Only three Metal/test files differ from the shared control; the three shared-helper source files are byte-identical.

The patch adds few-row MMA dispatch and kernel instantiations for additional weight formats. Real-model diagnostics show 13 new-format pipeline variants for BF16, Q2_0, Q3_K, IQ4_NL and IQ4_XS in the candidate, and none in the control. The 16-token greedy diagnostic sample matches exactly. That sample does not establish general exact-token equivalence. Pipeline selection is proved; hardware utilization and per-operation GPU timing have not been profiled. This result does not establish new use of dedicated M5 AI accelerators.

Routed expert MUL_MAT_ID kernels, the stored model/helper weights, lazy SSD lookup mechanism and GPU memory limit are unchanged. This is still the native Metal lab, not a port of the parent Strata CUDA/HIP expert SSD scheduler. The patch improves speed in the existing capacity envelope; no larger model was loaded in this experiment.

[Patch/build manifest](../config/mtp_mma_experiment.json), [unchanged upstream patch](../patches/metal-mma-types-upstream.patch), [combined patch](../patches/mtp-shared-mma.patch), [source identity and all build receipts](features/20261006-mma-source-proof.json), [real-model dispatch proof](features/20261006-mma-dispatch-proof.json). Native checkouts and binaries remain separate.

## Validation and memory

Each depth uses control, candidate, candidate, control. Every pass excludes one warmup and measures two repeats per workload: four measured samples per engine/depth/workload. Fresh replies produce 128 tokens with EOS ignored for timing; answer checks and cached replies stop normally. Prompt token hashes, fixed output counts, sampling settings, model/helper pins and per-engine source/binary receipts must match before percentages are calculated. Prior suites are not pooled into these results.

- All 12 speed passes pass 360 answer checks. Every pass has zero new system swap and no memory-guard stop. The minimum sampled available RAM is 2.42 GiB.
- All 1,076 synthetic Metal math cases pass against CPU reference, 538 with the M5 tensor API enabled and 538 disabled. They cover the affected formats used here plus a Q5_K control and include small/odd/fallback/broadcast shapes. No model weights are loaded for these checks.
- All 30 offline workflow checks pass, including rejection of comparisons with changed prompts, models, engines, helper settings or failed checks.
- All 27 real Strata API checks pass across depths one, three and four, including Unicode, native/adapter parity, OpenAI/Anthropic, streaming/EOS, explicit unsupported requests, cancellation and disconnect recovery. Each app trial records zero new swap and stops its servers. These functional timings are excluded from the speed comparison.

These are focused sanity and API checks, not a broad model-quality evaluation. Floating-point accumulation changes can still change generated tokens on other prompts. Colima was stopped with the user's authorization before the full-model trials and was left stopped. Existing swap is separate from new swap growth.

[Full tables, first-token/input/acceptance values and links to every raw run](results/20261006T224056Z-mma-comparison/COMPARISON.md). [Machine-readable comparison](results/20261006T224056Z-mma-comparison/comparison.json).
[Small GPU math checks](features/20261006T223935Z-mma-math/checks.json), [offline checks](features/20261006-mma-offline.log), [VM stop record](features/20261006-mma-vm-stop.json).

- [App proof: 20261006T230008Z-mma-app-1-8.json](results/20261006T230008Z-mma-app-1-8.json)
- [App proof: 20261006T230013Z-mma-app-3-8.json](results/20261006T230013Z-mma-app-3-8.json)
- [App proof: 20261006T230018Z-mma-app-4-8.json](results/20261006T230018Z-mma-app-4-8.json)

## Reproduce

Provision the pinned baseline and packed shared helper first. Preparation builds the isolated candidate and a separate control operation tester without loading a model. The math check uses synthetic tensors. The trace, app checks and benchmark with --run load the full model. Stop the active app before switching profiles.

```sh
.venv/bin/python scripts/prepare_mma.py --jobs 2
.venv/bin/python scripts/verify_mma.py
.venv/bin/python scripts/trace_mma.py --engine mtp-shared
.venv/bin/python scripts/trace_mma.py --engine mtp-mma
.venv/bin/python scripts/benchmark_mma.py
.venv/bin/python scripts/benchmark_mma.py --run
.venv/bin/python scripts/verify_helper_tuning.py --engine mtp-mma
```

Use `Start Strata - Writing Test.command` for the three-token profile and `Start Strata - Fast Follow-ups Test.command` for four tokens. Both keep conversation caching and eight helper workers. The old one-token profile remains available by running the original shared launcher with `--draft 1 --draft-threads 8`. No cross-session cache or two-device work is added.
