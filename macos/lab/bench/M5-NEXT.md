# M5 experiments: completed settings and operation measurements

Prepared October 6, 2026 for the 48 GiB, 20-GPU-core M5 Pro. The user subsequently authorized testing after memory cleanup. [Tensor API and prediction-depth results](M5-RESULTS.md) cover the first four comparisons; [GPU matrix tuning results](M5-GPU-TUNING.md) cover build parity and four matrix comparisons. [Helper workers and confidence results](M5-HELPER-RESULTS.md) complete the final three comparisons. All twelve experiments are complete. Colima and Grafana remain stopped. No model server is left running, and there is no scheduled run or background waiter.

The isolated `m5-lab` server and operation tester were built with one compiler worker. All 40 offline workflow checks pass. Existing native engines, model files, model/runtime pins, GPU memory limits and the ordinary/writing/follow-up launchers are preserved. All stock and candidate GPU correctness checks, both timing profiles and all matrix comparisons now pass. Row-threshold and GPU-worker overrides do not improve speed. A two-tile limit gives a small generation gain and passed the real API checks; it has a separate optional trial launcher. The existing launchers keep their settings, including the earlier optional short structured depth-six trial.

[Final build/source receipt and saved-header weight inventory](features/20261007T002056Z-m5-preparation.json), [offline checks](features/20261006-m5-offline.log), [plan-only output](features/20261006-m5-plans.log). Receipt timestamps are UTC; preparation happened October 6 locally. The earlier preparation receipt is retained as build history.

## Completed comparison plan

The [plan](../config/m5_test_plan.json) defines twelve single-variable comparisons. Each brackets candidates with fresh controls, excludes one warmup per pass, measures two repeats and records raw token responses, prompt hashes, source/binary receipts, CPU/RAM snapshots, load time, input/output TPS, first-token delay, total reply time, acceptance and percentage changes. Fresh replies use 128 output tokens. Cached lookup replies stop normally and are much shorter; their TPS is not a general writing rate. Historical numbers are not pooled into new percentages.

| Experiment | Control | Candidates | Engine |
| --- | --- | --- | --- |
| GPU Tensor API, writing | on, depth 3 | off | current `mtp-mma` |
| GPU Tensor API, follow-ups | on, depth 4 | off | current `mtp-mma` |
| Prediction, writing | depth 3 | 5, 6 | current `mtp-mma` |
| Prediction, follow-ups | depth 4 | 5, 6 | current `mtp-mma` |
| Confidence, writing | 0.0, depth 3 | 0.2, 0.4 | current `mtp-mma` |
| Confidence, follow-ups | 0.0, depth 4 | 0.2, 0.4 | current `mtp-mma` |
| Helper CPU workers | 8, depth 3 | 6, 12 | current `mtp-mma` |
| Isolated build parity | current `mtp-mma` | `m5-lab`, controls disabled | both |
| BF16 few-row threshold | 4 rows | 3 rows | `m5-lab` |
| Q2_0 few-row threshold | 3 rows | 2 rows | `m5-lab` |
| Matrix tile width limit | existing choice, maximum 4 | maximum 1, 2 | `m5-lab` |
| Matrix worker split | existing choice | requested 4, 8 SIMD groups | `m5-lab` |

Each comparison changes only its named setting. Both prediction controls use today's faster GPU math. Larger predictions automatically allocate more recurrent rollback slots, so memory is recorded rather than assumed unchanged. Confidence filtering can reduce batch sizes enough to lose matrix efficiency. The tiling requests remain bounded by K length, threadgroup memory and hardware thread limits; actual choices may be smaller than the requested maximum.

GPU correctness checks against the CPU reference run before speed trials and verify the requested Tensor API mode. The selected weight formats include Q2_0, Q3_K, BF16, IQ4_NL, IQ4_XS and the Q5_K shared output head, with rows through 32. The operation tester loads synthetic tensors, not model weights. New speed comparisons stop if answers fail, source/binary changes, or any new swap is observed. The native memory guard stops at more than 128 MiB new system swap or less than 512 MiB available RAM for four seconds. A guard stop is recorded as a failed experiment, not a performance result.

The existing API checker accepts depth five/six, confidence and explicit tensor/tuning settings. Depth six passed nine real app checks and is exposed only by the optional short structured follow-up trial. Writing stays at depth three and the existing fast-follow-up launcher stays at four. The two-tile trial passed nine real API check groups with zero new swap. Confidence and helper CPU-worker comparisons are complete; the optional prose-confidence and twelve-worker trials each pass nine real API check groups. Matrix settings are not combined with depth six or other new presets.

## Completed diagnostics and next kernel comparison

The [phase/shape diagnostic results](M5-PHASE-PROFILE.md) add a separate `m5-trace` engine. Request phases and model roles are explicit; matrix shapes are inventoried once per llama graph call and inactive nodes are counted separately. Main-model GPU-buffer intervals cover 68-73% of generation wall time in four measured requests.

The [operation measurements](M5-OPERATION-PROFILE.md) now compare the recorded expert Q2_0 and output-head Q5_K shapes without editing any of the seven engines. All 23 full-size CPU-reference checks pass. Expert math is larger among these selected families, but their isolated latencies project to only 34-42% of the main GPU interval. Next capture actual expert reuse during verification and broaden cost coverage to the remaining shared matrices and attention/state work before choosing a shader. Accelerator occupancy remains unmeasured. The [Astra plan](research/20261006-astra-future-plan.md) ranks later candidates.

The unchanged writing control has one clean fresh launch at 47.6-48.9 synthetic TPS and 54.2 code TPS. Its second launch adds 60.3 MiB swap during overlapping build activity and is excluded. This incomplete refresh is not a candidate comparison or a new gain. A future shader needs a fresh complete matched control/candidate run while background builds are quiet.

`profile_m5.py` uses the isolated engine's disabled-by-default command-buffer completion timestamps. It records GPU intervals, graph/context IDs and original operation counts, alongside native cumulative helper wall-time statistics. Two prompt lengths, 512 and 2048, distinguish prompt processing from the short generation portion. All profiling timings remain separate from speed results.

This measures command-buffer elapsed intervals, not time per individual operation or AI-accelerator occupancy. Graph counts precede fusion. The older context IDs do not identify target/helper roles by themselves; the new trace labels roles from the native context type. Gaps outside recorded buffers can contain CPU work, scheduling or other GPU activity; they do not prove the GPU is idle. Helper wall time includes synchronization and overlaps GPU intervals, so it must not be added to GPU time. Full Instruments/kernel-counter profiling would need additional tooling; only Command Line Tools are installed, and no Xcode or toolchain download was started.

Tensor API on/off measures the contribution of the available tensor path. It does not disable all GPU matrix instructions, and it does not control the separate Neural Engine. The GPU/model tests now verify the available path and bounded matrix settings. Hardware accelerator occupancy remains unmeasured.

## Compressed-weight work staged for the following iteration

Preparation reads the saved GGUF header inventory and records weight-format byte counts and example shapes in the preparation receipt. It does not read, duplicate or requantize weight payloads. Byte counts indicate storage, not the time a calculation takes.

Apple's [macOS 27 tensor guidance](https://developer.apple.com/videos/play/wwdc2026/330/) describes dequantizing custom formats directly into cooperative tensor inputs, avoiding an intermediate threadgroup-memory round trip. The current dense tensor kernel still stages unpacked values in threadgroup memory. The Q2_0 and mixed GGUF formats are not automatically interchangeable with Apple's native quantized tensor layouts.

After profiling identifies a useful shape/format, implement one isolated cooperative-input kernel. Preserve GGUF bytes and lazy lookup behavior; start with synthetic CPU-reference tests, odd/aligned dimensions and fallback cases, then a matching end-to-end comparison. Register pressure, precision and dispatch thresholds need measurement. No compressed-weight shader has been implemented or performance gain claimed in this stage. The separate Neural Engine remains a conversion/runtime research task.

## Commands

These commands only display plans or record preparation:

```sh
.venv/bin/python scripts/prepare_m5.py
.venv/bin/python scripts/verify_m5.py
.venv/bin/python scripts/profile_m5.py
.venv/bin/python scripts/benchmark_m5.py
```

Double-click `M5 Experiment Plan.command` to display the comparisons without loading a model. Rebuilding, if needed, uses `scripts/prepare_m5.py --build --jobs 1` and does not run GPU tests.

The initial testing batch used diagnostics, Tensor API comparisons and prediction depth. These commands reproduce those tests and do execute GPU work and load the full model:

```sh
.venv/bin/python scripts/profile_m5.py --run
.venv/bin/python scripts/benchmark_m5.py --experiment tensor-writing tensor-followup --run
.venv/bin/python scripts/benchmark_m5.py --experiment depth-writing depth-followup --run
```

Choose later experiments explicitly, one at a time. All twelve prepared comparisons are complete. Choose explicit reproductions or add a new measured hypothesis. The settings runner refuses `--run` without an experiment selection. Operation diagnostics and the unchanged writing control also require their own `--run`; their default commands only show plans. They do not monitor VoltTracker, automatically resume, restart Colima or stop unrelated processes. Phase separation and selected matrix measurements are complete; broader cost and real-routing evidence remain before selecting a decoding kernel change.

[Isolated native patch manifest](../config/m5_lab_experiment.json). Preparation receipts and offline checks are under `bench/features/`; new measurements create new result directories.
