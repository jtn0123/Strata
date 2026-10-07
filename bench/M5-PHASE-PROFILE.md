# M5 request-phase and tensor-shape profiling

Measured October 6, 2026 on the 48 GiB, 18-CPU-core, 20-GPU-core M5 Pro. UTC artifacts fall on October 7. This follows the [twelve completed settings comparisons](M5-HELPER-RESULTS.md). The full Qwen3.8-Flash-Next GSQ-RCO Q2_0 model, packed mixed Q3 prediction helper, lazy lookup, F16 cache and 4K context are preserved.

## Finding and next decision

The main-model GPU path is the largest measured generation interval. Its command buffers cover 68.44-73.29% of server generation wall time in these four requests; helper GPU buffers cover 12.63-14.79%. This points the next experiment toward the main model's GPU work. It does not establish whether the work is limited by arithmetic, memory bandwidth or page access, and it does not identify the slowest individual kernel.

The next controlled test should compare the recorded routed-expert Q2_0 shapes with dense/shared-output-head shapes. Routed-expert operations use `MUL_MAT_ID`, a separate Metal path from the dense few-row tile knobs already tested. Time those shapes and validate CPU-reference math before choosing a compressed-weight or dequantization shader. Node counts and weight storage sizes alone cannot rank the kernels.

This stage adds diagnostics; it claims no new TPS gain and changes no existing launcher. The separate `m5-trace` engine preserves all six previously built source/binary receipts exactly. Logging is disabled by default and runs only under explicit profiling flags.

## Generation, measured separately from prompt processing

| Depth / input | Phase wall | Main-model GPU buffers | Share of phase wall | Helper GPU buffers | Helper draft wall |
| --- | ---: | ---: | ---: | ---: | ---: |
| 3 / 512 | 2.8914 s | 2.0258 s | 70.06% | 0.3653 s | 0.5895 s |
| 3 / 2048 | 2.9427 s | 2.1568 s | 73.29% | 0.3901 s | 0.5456 s |
| 4 / 512 | 2.9825 s | 2.0413 s | 68.44% | 0.4339 s | 0.6851 s |
| 4 / 2048 | 3.1501 s | 2.1623 s | 68.64% | 0.4659 s | 0.6847 s |

Main/helper GPU columns are unions of command-buffer elapsed intervals within each role, not sums of overlapping buffers. Their overlap is zero in these requests; the parser supports and subtracts overlap when computing the combined union. Across the four requests, combined GPU-buffer intervals cover about 82.7-86.5% of generation wall time. This is elapsed interval coverage, not hardware utilization or AI-accelerator occupancy.

The helper's actual `draft` function spans roughly 0.546-0.685 seconds, or 18.5-23.0% of generation wall time. That span includes its GPU work, CPU expert calculations, sampling and synchronization. Do not add it to GPU time. The separate `process` hook can wait for the target's embeddings; its apparent cost includes waiting for main-model GPU work. The profiler does not label that wait as CPU-only helper calculation.

## Prompt processing

| Depth / input | Phase wall | Main-model GPU buffers | Share of phase wall | Helper GPU buffers | Helper draft wall |
| --- | ---: | ---: | ---: | ---: | ---: |
| 3 / 512 | 0.9201 s | 0.7541 s | 81.96% | 0.0325 s | 0.0000 s |
| 3 / 2048 | 3.7920 s | 3.1909 s | 84.15% | 0.1559 s | 0.0000 s |
| 4 / 512 | 0.9134 s | 0.7632 s | 83.56% | 0.0320 s | 0.0000 s |
| 4 / 2048 | 3.8494 s | 3.2081 s | 83.34% | 0.1548 s | 0.0000 s |

The long-input main-model GPU interval is roughly 3.2 seconds, compared with 2.0-2.2 seconds during the subsequent 128-token generation. Separating the phases removes the earlier problem where long prompt graphs dominated an aggregate profile. During long prompt processing, the helper `process` wall interval is roughly 3.7 seconds although its own GPU buffers total only 0.155 seconds: most of that wall interval cannot be attributed to helper math. Its source reads target embeddings and can synchronize the target.

## Captured generation shapes

Shape arrays are `[K, M, experts, batch]` for the expert weights as stored by GGML. Input/output dimensions in raw records establish routing and token rows; this table lists the recurring weight shapes.

| Candidate family | Weight type | Stored weight shape | Observed generation token rows | Placement |
| --- | --- | --- | --- | --- |
| Routed expert projection to 2560 | Q2_0 | `[640, 2560, 512, 1]` | chiefly 4 at depth three, 5 at depth four; occasional 2/3 | Main-model Metal |
| Routed expert projections to 640 | Q2_0 | `[2560, 640, 512, 1]` | chiefly 4/5; occasional 2/3 | Main-model Metal |
| Shared vocabulary output head | Q5_K | `[2560, 248320, 1, 1]` | recorded per call in raw inventory | Main/helper Metal |
| Helper routed experts | Q3_K/Q4_0 | recorded per call in raw inventory | generally single-token generation | CPU |

The main expert output has a ten-expert routing axis. Shape records are emitted once per llama graph call, so command-buffer partitions no longer repeat the same graph inventory. Counts still represent original graph-node appearances before fusion, not executed kernel counts or time shares. Inactive zero-sized matrix nodes are counted separately and are excluded from active matrix shapes, matching the Metal encoder's empty-node filtering.

The M5 capability probe reports stage-boundary timestamp counters and no dispatch-boundary counter support. The probe source is [saved here](features/20261006-metal-capabilities.m). Apple's [counter-sampling documentation](https://developer.apple.com/documentation/metal/sampling-gpu-data-into-counter-sample-buffers) explains the boundary distinction. This stage uses command-buffer completion timestamps; it does not split encoders or force per-operation synchronization to manufacture kernel timings. Full per-kernel/occupancy evidence remains outstanding.

## Matched outputs, instrumentation and disk limits

The untouched `m5-lab` control and labeled `m5-trace` run use the same prompts, temperature zero, seed 1234, helper workers eight, confidence zero, Tensor API on, and batch/ubatch 512. Both depths use a 512-token/16-output warmup, then 512/2048 input and 128 output tokens. All six paired output texts and token-ID sequences match, including warmups. Four measured request pairs are available; this is not a broad model-quality test or an ABBA speed comparison.

| Depth / input | Control generation interval | Traced generation interval | Difference | System reads during traced whole request |
| --- | ---: | ---: | ---: | ---: |
| 3 / 512 | 2.8759 s | 2.8913 s | +0.54% | 99.82 MiB |
| 3 / 2048 | 3.0246 s | 2.9427 s | -2.71% | 70.84 MiB |
| 4 / 512 | 2.8864 s | 2.9825 s | +3.33% | 118.59 MiB |
| 4 / 2048 | 3.0682 s | 3.1500 s | +2.66% | 251.12 MiB |

The small interval differences mix logging overhead and run variation; one control/trace pair per input cannot establish an exact overhead percentage. These timings are excluded from the TPS benchmark history. Temperature, filler prompt and output choices differ from the previous speed suite, so these diagnostic rates must not replace its roughly 50 TPS synthetic/57 TPS code results.

Disk columns cover the entire request and all system activity. They are neither the model's read bandwidth nor an SSD-wait measurement. No cold-cache sweep, file-specific I/O trace or model write-speed test was performed. GPU-buffer intervals can also include memory access or stalls; the uncovered wall time must not be relabeled as SSD time or GPU idleness.

## Validation and resource use

- Four final diagnostic model launches; four measured request pairs plus two warmup pairs; all six paired text/token outputs match the untouched control.
- 1144/1144 CPU-reference GPU math checks on final control/trace builds; nine real app/API check groups pass for the new engine with profiling disabled; all 44 offline workflow/parser tests pass.
- Lowest available RAM in final diagnostics: 2.414 GiB. Peak process RSS: 37.898 GiB. All final diagnostics and the app check record zero new swap and no memory-guard stop. RSS is not total Metal memory.
- Parser tests reject missing completions, overlapping slots, missing/duplicate graph identifiers, inconsistent roles, invalid GPU times, unattributed request buffers and helper intervals crossing phase boundaries. Valid raw logs recompute the saved summaries exactly, independent of callback order.
- Existing six engine receipts verify unchanged. The new combined diagnostic patch, component hash, source diff and binary receipt verify. Original launchers, model files, runtime pins and GPU memory limits are preserved.
- Resource logs show no sampled Java build load. Peak other named groups range 20.3-64.5% of one core; these top-eight samples are not a complete CPU/GPU trace.
- [Final batch receipt](features/20261006-m5-phase-batch.json), [runner batch](features/20261007T044827Z-m5-phase-profile-batch.json), [offline checks](features/20261006-m5-phase-offline.log), [preflight](features/20261006-m5-phase-preflight.json), [build log](features/20261006-m5-trace-build.log), [preparation](features/20261007T044748Z-m5-preparation.json).

The [first diagnostic attempt](features/20261007T044619Z-m5-phase-profile-batch.json) stopped at its parser check because original graphs contained zero-sized inactive matrices. Its [trace](features/20261007T044647Z-m5-phases-3-trace/profile.json) and native log are preserved and excluded. The native inventory was corrected to match the existing Metal empty-node filter, a regression test failed before and passed after that fix, and both depths were rerun. Those model runs also recorded zero new swap; the failure was interpretation validation, not a model memory failure. Initial prerequisite receipts remain separate from the final 1144 checks above.

All model servers, Colima and Grafana are stopped after testing. No service was restarted. No new compressed-weight shader, hardware occupancy measurement or separate Neural Engine runtime is introduced.

## Reproduce deliberately

```sh
.venv/bin/python scripts/prepare_m5.py --engine m5-trace --build --jobs 1
.venv/bin/python scripts/profile_m5_phases.py
.venv/bin/python scripts/profile_m5_phases.py --run
```

The middle command displays a plan without GPU work or model loading. The last command loads the full model and runs the matched diagnostics with the 128 MiB new-swap guard. The new [manifest](../config/m5_trace_experiment.json) and [combined native patch](../patches/mtp-m5-trace.patch) reproduce the isolated build without modifying older engines.

## Raw evidence

- [Depth 3 control](features/20261007T044827Z-m5-phases-3-control/profile.json); adjacent `native.log`, `memory.jsonl` and `resources.jsonl` retain the raw evidence.
- [Depth 3 trace](features/20261007T044842Z-m5-phases-3-trace/profile.json); adjacent `native.log`, `memory.jsonl` and `resources.jsonl` retain the raw evidence.
- [Depth 4 control](features/20261007T044857Z-m5-phases-4-control/profile.json); adjacent `native.log`, `memory.jsonl` and `resources.jsonl` retain the raw evidence.
- [Depth 4 trace](features/20261007T044911Z-m5-phases-4-trace/profile.json); adjacent `native.log`, `memory.jsonl` and `resources.jsonl` retain the raw evidence.
- [GPU math receipt](features/20261007T044813Z-m5-math-m5-lab-on-stock/checks.json).
- [GPU math receipt](features/20261007T044820Z-m5-math-m5-trace-on-stock/checks.json).
- [App proof](results/20261007T045029Z-mma-app-3-8.json) and [integration checks](results/20261007T045035Z-flash-integration.json).
