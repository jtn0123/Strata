# M5 experiments: completed settings and operation measurements

Latest pass, October 9: [compact GPU scheduling](results/20261009-compact-tiles/REPORT.md) tested in two isolated variants. V1 gives 4.677% / 3.596% shorter two-block time at uniform T508/T512; V2 takes 0.456% / 2.226% longer than its own matched controls. Both preserve checked outputs but fail the fixed >10% component gate; no model trial or new TPS gain. Twelve accepted launches have zero new swap, 148 offline checks pass, 26 engines verify and all 24 originals are unchanged. [P11/P12/X22](EXPERIMENT-LEDGER.md) retain evidence and retry conditions. Next unimplemented compute area: exact-format quantized cooperative prompt input. The [R05 checkpoint card](research/20261009-astra-stateless-checkpoint-plan.md) identifies a cache-lifetime blocker and is held. Existing launchers remain unchanged.

Read the [experiment decision ledger](EXPERIMENT-LEDGER.md) before scheduling another test; retries must cite the prior ID and explain what changed. The [machine-readable index](experiment-ledger.json) supports future-session lookup.

Earlier pass, October 9: [backend sampling and embedding ordering](results/20261009-sampling-embedding/REPORT.md) are screened and parked. GPU min-p eligibility differs in four boundary cases; the embedding backport preserves target CPU→Metal stages but increases planned Metal inputs27→30. Six paired requests/192 tokens and cache checks match, zero new swap; no TPS gain measured.120 offline tests passed,20 engine receipts verified,all19 preexisting engines unchanged. Next: cost-aware depth within three, requiring actual helper early stop, then quantized prompt cooperative-input work. [Decisions N01/N02](EXPERIMENT-LEDGER.md), [research queue](research/20261009-astra-future-queue.md).

Previous pass, October 9: [Astra-ranked sequential experiments](results/20261009-sequential-pass/REPORT.md) screened parallel activation, zero/two extra Metal encoding workers and two/four-row Q5_K heads. No candidate qualified. Zero extra workers lost about 5.5% TPS, two were flat, activation was below drift, and head tiling took 1–3% longer. Eight accepted model launches had exact tested outputs and zero new swap; 120 offline tests passed and 19 engine receipts verified.

Earlier incremental pass, October 9: [repeated-expert grouping](results/20261009T153117Z-m5-expert-pair-group/REPORT.md) passes 9,446,400-value exact output comparison and 336 CPU projection references, but takes 27.31% more time on real R4 and 24.16% more on R5 in the final sequential operator ABBA. All-distinct cases also take 8.65-8.78% more time. Grouping stays off, and no full-model benchmark or new TPS gain is claimed. Six final native launches add zero swap; all 12 existing engines are unchanged and 107 offline checks pass. Astra's [next gate/up fusion card](research/20261009-astra-gate-up-plan.md) is prepared, with graph/allocator/consumer safeguards and no promised gain. No commit or push; ordinary launchers remain unchanged.

Earlier research implementation, October 9: [three independent experiments and tracked results](results/20261009-next-three/REPORT.md). Ten-expert reduction adds 0.90-1.05% fresh writing TPS beyond conv-direct; sampling consolidation supplies no sustained gain. Correct mixed F32/BF16 TensorOps projection kernels and exact-K specialization fail the operator speed gate, so remain off. Eight clean full-model launches give 256 answer/cache checks, exact tested output parity and zero new swap. Matrix correctness/fallback tests pass, 103 offline tests pass, nine original engines are unchanged, and ordinary launchers remain unchanged. No commit or push. Next prioritize real repeated-expert grouping or gate/up work.

Latest incremental update, October 9: [three isolated copy changes](results/20261009T112641Z-m5-copy-resume/REPORT.md) were compared in eight full-model launches, three measured repeats per workload. Removing the intermediate CONT before the existing convolution-state copy adds 1.33-1.62% fresh TPS: synthetic 2048 goes from 50.016 to 50.737, code from 56.501 to 57.258, prose from 42.877 to 43.448. All 256 answer/cache checks pass; every measured fresh/cached output matches stock token for token; zero new swap, minimum 2.14 GiB available. Scalar/vector row-copy changes give no useful fresh-writing gain. The lighter normal-dispatch inventory has 123 shapes and no unfused large GDN state CPY: native GDN-cache fusion already removes it. The earlier split trace interrupted that fusion and cannot assign those CPY costs to ordinary generation. A quiet-CPU deferral launched no model; the exact accepted protocol prefix was resumed with unchanged source/model/guards. [Optional direct-copy launcher](../Start%20Strata%20-%20Direct%20Copy%20Trial.command) is prepared; ordinary defaults remain. Prioritize shared matrix or grouped expert-weight work next, with normal-path measurements before another kernel.

Latest update, October 9: the [full-model GPU/context/SSD batch](results/20261009T085842Z-m5-next-batch/REPORT.md) completes the prepared residual-fix comparison, depth3/4 expert routing and split captures, bounded lookup reads, and a strict 4K/8K/8K/4K retry. Sixteen accepted launches provide 262 answer/cache/recall checks and 12 matching diagnostic response pairs, with zero new swap. The full model handles 8K/F16 at 49.03–50.07 synthetic TPS and 56.46 code TPS; fresh speed differs from matched 4K by at most 0.21%. The correctness fix supplies no useful TPS gain. The initial 8K raw-JSON formatting failure is retained; explicit fixture-v2 instructions pass the unchanged strict grader in both 8K launches. Separate attention/indexer KV accounting is fixed, and all 91 offline tests pass. Expert weight selection repeats about 31–35%; shared matrices and large state-copy nodes are additional measured investigation targets. Model servers are stopped, about 39.85 GiB was available after releasing idle owned model pages, and T3/WiFiman remain open. Normal launcher defaults are unchanged. Next validate the identified shapes and compare one isolated optimization; prefetch/paging still need native-wait/hot-set evidence.

Earlier update, October 8 locally (October 9 UTC): the [full-model writing baseline](results/20261009T042329Z-heavy-guarded-trial/REPORT.md) completed two clean launches, six measured samples per workload and 64/64 answer/cache checks. Synthetic generation is 48.48–49.87 TPS, code 56.14, prose 42.60 and Chinese 39.99, with zero new swap during both successful launches. A read-only model-cache reset recovered enough RAM to satisfy the normal 34 GiB admission requirement. The initial guard-stopped attempt is retained and excluded. T3 and WiFiman remained running; the benchmark's model server is stopped. This refresh changes no native preset and claims no new optimization gain. [Acceptance receipt](features/20261009-heavy-baseline-acceptance.json). At that point, full-model residual-candidate comparisons, expert routing/split captures and 8K trials remained pending; the October 9 update above completes them.

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

[The refreshed experiment queue](M5-FUTURE-TEMPLATES.md) stage the next diagnostics and later capacity/shader/prefetch ideas. The [October 7 preparation update](M5-AUDIT-PREPARATION.md) records the audit safeguards, 72 passing offline tests and an accepted bounded 4B control/split smoke: all three paired outputs match with zero new swap. Full Flash expert routing and split costs remain untested. Keep OpenTaskManager's VM/builds running as requested; wait for the user's full-model testing go-ahead and fresh RAM/quiet-host checks. Preparation has no automatic testing trigger.

The [October 7 parent/fork refresh and pending-work list](research/20261007-macos-upstream-review.md) screens 1,458 public fork listings and checks targeted Mac sources. The parent explicitly excludes Apple Silicon; Mac forks provide useful state/mapping/MLX ideas. The broader few-row matrix patch merged into llama.cpp today is already included in our M5 engine. No runtime update or benchmark ran during this review.

The subsequent [Astra source-level deep dive](research/20261007-astra-macos-deepdive.md) finds no additional fork with a proven speed upgrade for our current setup. Our graph already avoids the native port's duplicate GDN recurrence and reuses execution graphs. The missing #30100 correctness fix now has a separate compiled candidate and held reproducer; use the held full-model captures to select any state-copy or expert-kernel work. Memory-fit accounting, numerical audits and bounded SSD measurements are useful adaptations, with gains still unmeasured.

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

Choose later experiments explicitly, one at a time. The original twelve comparisons are complete. A separate residual-correctness comparison is now staged; the refreshed diagnostics/capacity queue is documented above. Choose explicit reproductions or add a new measured hypothesis. The settings runner refuses `--run` without an experiment selection. Operation diagnostics and the unchanged writing control also require their own `--run`; their default commands only show plans. They do not monitor VoltTracker, automatically resume, restart Colima or stop unrelated processes. Phase separation and selected matrix measurements are complete; broader cost and real-routing evidence remain before selecting a decoding kernel change.

[Isolated native patch manifest](../config/m5_lab_experiment.json). Preparation receipts and offline checks are under `bench/features/`; new measurements create new result directories.

## October 7 remaining preparation

[The completed preparation](M5-REST-PREPARATION.md) adds the isolated upstream correctness candidate, executable 8K recall/capacity harness, saved-data RAM accounting, a bounded lookup-file probe and the maintained 90-test offline gate. All seven original engines remain unchanged. [Eleven refreshed cards](M5-FUTURE-TEMPLATES.md) distinguish executable trials from the kernel/prefetch/paging designs that still depend on measurements. No new model/GPU/SSD benchmark ran and no TPS gain is claimed.

## October9 sequential experiments

[Three new isolated experiments, five variants](results/20261009-sequential-pass/REPORT.md) are complete. None improved practical speed: lane activation did not clear its operator gate, zero extra encoding workers lost about5.5% TPS, two were flat, and Q5_K head tiles were1–3% slower in full-head/consumer tests. Default one extra encoding worker and the existing copy/conv-direct setup remain. Exact outputs, fresh controls, zero new swap,120 offline tests and all19 current receipts passed; all16 previous engines were preserved. [Astra's updated seven-idea queue](research/20261009-astra-future-queue.md) records sampling, embedding ordering, cost-aware drafting and cooperative-input prompt work still ahead.

## October9 draft-cap execution

[The actual early-stop and fixed-two pass](results/20261009-draftcap/REPORT.md) is complete. Early stop skips18 discarded helper decodes in the diagnostic set, with exact outputs/target widths; its independent256-tokenABBA shows code -0.030% and English prose +0.191%, below drift. Fixed2 passes the initial633-token diagnostic set but changes the228th emitted token in all three longer synthetic512 repetitions, so its bracket stopped and the controller is parked. All attempted model launches have zero new swap and clean owned-model exit.121 load-free checks and21 engine receipts validate; all20 previous engines are unchanged.

Future benchmark/capture prompts and adoption focus on English prose and code only, as requested. Keep three guesses and the practical copy/conv-direct control. Next independent research is an exact-format cooperative-input prompt kernel; any adaptive revisit must first repair the recorded extended-output fixture. [D01/D02/X14/X15 and retry conditions](EXPERIMENT-LEDGER.md) retain successes, limitations and parser/report corrections without rerunning or overwriting original evidence.

Latest completed pass: [S06/Q02/P10 results](results/20261009-next-speed-pass/REPORT.md). All three are parked below their speed gates; read the [decision ledger](EXPERIMENT-LEDGER.md) before repeating them. Next queued is R03 compact expert/token tile launches, with a >10% complete-block screen before a model trial.
