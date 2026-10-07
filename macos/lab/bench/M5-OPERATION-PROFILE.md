# M5 expert and vocabulary-head measurements

Measured October 6, 2026 on the 48 GiB M5 Pro, 18 CPU / 20 GPU cores, macOS 27.2. UTC artifacts fall on October 7. This implements the first measurement step from the [Astra future plan](research/20261006-astra-future-plan.md), following the [request-phase trace](M5-PHASE-PROFILE.md).

## Finding

Expert calculations cost more than the vocabulary output table among the three matrix families tested. For the usual four-token verification, multiplying the isolated matrix measurements by 48 blocks estimates **12.81–14.33 ms of expert math**, versus **2.16 ms for the main output table**. Those are synthetic routing scenarios, not measured in-model kernel times or guaranteed bounds.

The larger finding is a measurement gap: projecting these operations onto the saved generation inventories accounts for only **33.6–42.0% of the main model's GPU-buffer interval**. Other matrices, attention/state operations, memory access, graph scheduling and synchronization still need investigation. This result does not justify calling expert math the whole-model bottleneck or interpreting the remaining time as SSD wait.

No optimization, new TPS gain or increased model capacity is claimed in this stage. The full model already works on this Mac with the existing Q2_0 compression and lazy lookup. Existing launchers and all seven native engines remain unchanged.

## What was measured

A new diagnostic executable includes the pinned native backend tester and links the existing `m5-lab` libraries. It performs CPU-reference correctness checks and then times graphs containing one matrix operation each, using the existing Metal command-buffer timestamps. No vendor engine or shader was edited.

The geometry matches the actual captured model graphs, including the ten-expert view's **2048-byte routing row stride**:

| Family | Weight type and shape | Input for four token rows | Output |
| --- | --- | --- | --- |
| Expert projection to 2560 | Q2_0 `[640,2560,512,1]` | `[640,10,4,1]` | `[2560,10,4,1]` |
| Expert projections to 640, two per block | Q2_0 `[2560,640,512,1]` | `[2560,1,4,1]` | `[640,10,4,1]` |
| Vocabulary output table | Q5_K `[2560,248320,1,1]` | `[2560,4,1,1]` | `[248320,4,1,1]` |

Weights and inputs are deterministically initialized synthetic values, not copied model payloads. Every token selects ten distinct experts from all 512. Two scenarios use independently selected sets across token rows or the same ten experts across all rows. IDs change between samples. Neither scenario measures the real model's expert reuse.

Each scenario has three excluded warmups and forty measured samples. Three passes alternate family and row order: **5520 measured matrix buffers** in nine performance processes. Each runs an unflushed condition and a separate condition preceded by a square operation reading 128 MiB of input and writing 128 MiB of output. Scratch and warmup timings are excluded.

The explicit pressure condition has at most **1.66% spread between pass medians**. Some unflushed expert cases are unstable: single-row down/up spreads are 343%/297%, and independent five-row up is 242%. Preceding GPU work changes the measurement conditions; these results do not establish why, prove a cold cache, or show that clearing cache improves model speed. The table below uses the more repeatable pressure condition and labels it accordingly.

## GPU elapsed latency under explicit cache pressure

Values are the median of three pass medians, in milliseconds. Rows are tokens processed together, not batch-size settings.

| Operation | Rows | Independent expert sets | Shared expert sets |
| --- | ---: | ---: | ---: |
| Expert to 2560 | 1 | 0.0383 | — |
| Expert to 2560 | 4 | 0.1226 | 0.1201 |
| Expert to 2560 | 5 | 0.1509 | 0.1475 |
| Expert to 640 | 1 | 0.0306 | — |
| Expert to 640 | 4 | 0.0880 | 0.0734 |
| Expert to 640 | 5 | 0.1063 | 0.0890 |
| Vocabulary output | 1 | 1.5332 | — |
| Vocabulary output | 4 | 2.1556 | — |
| Vocabulary output | 5 | 2.1636 | — |

All row counts 1–5 are present in the raw summary. Actual compilation logs confirm that expert operations use `kernel_mul_mv_id_q2_0_f32_nsg=2_split=0`. The vocabulary table uses ordinary quantized matrix-vector math at one row and the existing few-row `kernel_mul_mv_mma_q5_K_f32` path at rows 2–5. Weight sharing saves memory but does not remove the helper's repeated vocabulary calculation.

For four-row verification, `48 × (down + 2 × up)` gives the 12.81/14.33 ms scenario estimates. Expert math is **85.6–86.9% of these selected main-model matrix costs**, not that percentage of total generation. Five-row verification estimates 15.63–17.45 ms of expert math plus 2.16 ms for its output head. A helper's single-token vocabulary call costs about 1.53 ms in this test; its CPU experts were not benchmarked here.

## Comparison with recorded full-model GPU intervals

The [offline projection](features/20261007T052314Z-m5-operations/projection.json) multiplies these isolated latencies by original graph-node appearances from the preceding trace. It excludes prompt processing, warmups and CPU matrices. Original counts precede fusion and are not execution-time attribution. The trace and isolated tests also differ in synchronization, cache state and routing.

| Depth / input | Projected selected main matrices | Recorded main GPU interval | Projected / recorded |
| --- | ---: | ---: | ---: |
| 3 / 512 | 715.6–788.1 ms | 2025.8 ms | 35.3–38.9% |
| 3 / 2048 | 724.9–798.3 ms | 2156.8 ms | 33.6–37.0% |
| 4 / 512 | 777.3–856.6 ms | 2041.3 ms | 38.1–42.0% |
| 4 / 2048 | 792.2–873.0 ms | 2162.3 ms | 36.6–40.4% |

The helper's projected output-table cost is 57.8–62.2% of its recorded GPU interval, but that is still a cross-test estimate. Helper CPU work and waits are outside that GPU interval. These ratios cannot predict a whole-model TPS gain.

## Fresh writing baseline: one clean launch, refresh incomplete

The unchanged writing preset was launched twice: `mtp-mma`, depth three, eight helper workers, confidence zero, Tensor API on, F16 cache, 4K context, batch/ubatch 512, temperature 0.6 and seed 1234. Each launch has one excluded warmup and two measured repeats per writing workload. Writing timings force 128 output tokens and ignore EOS; separate answer checks use normal stopping.

The **first launch** passed all 30 answer checks and recorded zero new swap. Its medians are:

| Workload / input | Output TPS | First token | Complete 128-token reply |
| --- | ---: | ---: | ---: |
| Synthetic / 512 | 47.61 | 0.934 s | 3.602 s |
| Synthetic / 2048 | 48.91 | 3.835 s | 6.432 s |
| Code / 48 | 54.19 | 0.313 s | 2.657 s |
| Prose / 53 | 41.68 | 0.297 s | 3.345 s |
| Chinese / 56 | 38.99 | 0.302 s | 3.560 s |

This is a single-launch status refresh, not a completed two-launch baseline or a comparison with a candidate. Minimum available RAM in this launch was 1.98 GiB. No performance-increase percentage is defined because the runtime/settings did not change.

The **second launch is excluded**: it passed its 30 answer checks but added **63,242,240 bytes (60.31 MiB)** of system swap. That is below the emergency 128 MiB stop threshold, but violates this runner's stricter zero-growth acceptance requirement. One code repeat also fell to 38.96 TPS while the other measured 53.01. Resource samples show `swift-package` build activity peaking at 166.5% of one core at 05:28:18 UTC; swap growth first appears at 05:28:24. Those observations overlap this launch but do not establish causation. Other agents' builds were left running.

The original [failed refresh receipt](features/20261007T052606Z-m5-decision-baseline/baseline.json), both raw runs and a separate [acceptance review](features/20261007T052606Z-m5-decision-baseline/review.json) are preserved. The failed batch was not relabeled as passing, averaged into the clean reference or used to replace historical benchmarks. A fresh complete control/candidate comparison is required for any later gain claim.

## Validation and next experiment

- **23/23 full-size CPU-reference GPU checks** cover every measured row count and both expert routing scenarios where applicable; the vocabulary table covers rows 1–5. Native sentinel checks and normalized mean-square error tolerance `5e-4` apply. The first batch ran 13 checks; the supplemental batch ran the ten row-2/3 checks.
- Native self-test passes 1000 deterministic routing fixtures without initializing a backend. Operation diagnostics record zero new swap. Minimum available RAM in the original batch is 19.21 GiB. These are synthetic math checks, not new end-to-end model-quality proof.
- All **51 offline tests pass**. They verify operation/buffer joins independent of callback order, reject ambiguous or incomplete samples, check geometry/stride, exclude scratch/warmup/CPU/prompt work, reject unmeasured projection shapes, and prevent even small swap growth from becoming an accepted baseline.
- Diagnostic build/source/native-test/library hashes are saved, and all seven existing engine receipts verify unchanged. No previous 1144-check/API suite is represented as rerun for this measurement-only executable.

The next useful gate is **real expert reuse during four/five-token verification plus broader cost attribution**, before choosing a custom expert shader. Capture selected IDs in a diagnostic-only run, check that its greedy output still matches the control, and exclude instrumented timings from TPS results. Extend timing coverage to the remaining shared matrices and attention/state work, or use deliberately split family intervals with measured instrumentation overhead. Four/five tokens spread over 512 experts do not automatically give a matrix accelerator enough work per expert.

Choose one kernel hypothesis only after that evidence. Test it in an isolated engine against CPU reference, then use fresh repeated controls for output TPS, first-token and complete-task time. The earlier cooperative-input shader and Mac lazy-row prefetch ideas remain candidates, not implementations or promised gains. The latter needs file-specific lookup/wait evidence first. A separate Neural Engine runtime is still research. Colima and Grafana remain stopped; no service was restarted.

## Reproduce deliberately

Default commands only display plans. Building the operation executable does not modify the existing engine:

```sh
.venv/bin/python scripts/benchmark_m5_ops.py
.venv/bin/python scripts/benchmark_m5_ops.py --build
.venv/bin/python scripts/benchmark_m5_ops.py --run
.venv/bin/python scripts/benchmark_m5_ops.py --run --checks-only --rows 2 3
.venv/bin/python scripts/benchmark_m5_decision_baseline.py
```

Adding `--run` to the last command loads the full model and attempts two unchanged-control launches. It does not start any service or stop background builds. The projection command is offline:

```sh
.venv/bin/python scripts/analyze_m5_operations.py \
  --operations bench/features/20261007T052314Z-m5-operations/operations.json \
  --trace bench/features/20261007T044842Z-m5-phases-3-trace/profile.json \
          bench/features/20261007T044911Z-m5-phases-4-trace/profile.json \
  --output /tmp/m5-operation-projection.json
```

## Evidence

- [Original operation batch](features/20261007T052314Z-m5-operations/operations.json), adjacent native logs and memory/resource records.
- [Supplemental correctness batch](features/20261007T053356Z-m5-operations/operations.json).
- [Diagnostic build receipt](features/20261007T052314Z-m5-operations/build.json) and [build log](features/20261007T052314Z-m5-operations/build.log).
- [Clean single writing launch](results/20261007T052606Z-m5-decision-baseline-1/result.json) and [excluded second launch](results/20261007T052745Z-m5-decision-baseline-2/result.json).
- [Offline checks](features/20261006-m5-operations-offline-final.log) and [final verification](features/20261006-m5-operation-validation.json).
- [Diagnostic source](../native/m5_operation_probe.cpp), [runner](../scripts/benchmark_m5_ops.py), [offline projection](../scripts/analyze_m5_operations.py), [writing-control runner](../scripts/benchmark_m5_decision_baseline.py).
