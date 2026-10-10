# Native monitoring and baseline — October 10

The isolated `m5-observe` engine now measures where native inference spends time without changing the ordinary P07 launcher. The smaller-model baseline is complete. The full-model baseline is frozen and its first admission check stopped before loading weights: 33.462 GiB available against the unchanged 34 GiB requirement. No full-model diagnostic timings or new optimization gains are claimed.

| Area | Recorded metrics | Current evidence |
| --- | --- | --- |
| User response | Output tokens/sec, first streamed token, capped reply time, exact inputs/output IDs/text/finish | Four small-model launches pass; 24 measured answers and 8 excluded warmups |
| Graph setup | Memory-context application, reset, graph build, scheduler allocation, input setup, existing reuse synchronization; reuse/rebuild reasons | Validated on the small model; full-model helper exposure pending |
| Main model and helper | Separate prompt/generation GPU command-buffer intervals, original matrix shapes, helper catch-up/draft rows, accepted-draft histogram and helper outer-call wall time | Small model has no helper; helper markers compile but their full-model behavior is untested |
| Prompt checkpoints | Creation count, payload bytes and whole-operation wall interval | Does not cover every speculative state save/restore |
| Memory and safety | Every logged allocation reservation, sampled server RSS, host available low-water mark, swap growth and pressure | Zero new swap; normal pressure in all four small-model launches |
| Clock and observer validity | CPU/Mach clock calibration, record coverage, request boundaries, exact four-arm outputs and disabled/on timing difference | Clock mapping spread 34.791 microseconds; monitoring costs 2.10–2.35% TPS |

Command-buffer elapsed time is not active GPU utilization, individual-kernel cost or AI accelerator occupancy. CPU stages, GPU intervals and helper outer calls overlap. CPU setup outside recorded model GPU intervals is a diagnostic bound, not proven removable time. System disk counters include unrelated activity and do not establish model SSD bandwidth or wait time. Allocation reservations and RSS do not sum to unique physical RAM.

## Completed small-model baseline

Model: **Qwen3.5-4B Q4_K_M**, no prediction helper, 4K context, F16 KV, batch 512, temperature 0.6, seed 1234, fixed 128-token output cap. Four fresh processes run **P07 control / observer off / observer on / P07 control**, with one warmup and three measured answers per English code/prose workload. Baseline values average the two controls' per-workload medians. All 32 answers match exactly across arms. Capped outputs do not establish complete-answer quality or full internal tensor-state equality.

| Workload | Control output speed | First token | 128-token reply | Detailed monitoring TPS change |
| --- | ---: | ---: | ---: | ---: |
| English code | 77.886 TPS | 79.46 ms | 1.7102 s | -2.351% |
| English prose | 77.818 TPS | 80.21 ms | 1.7124 s | -2.099% |

Control TPS drift is 0.359%/0.236%. The observer build with monitoring disabled differs by -0.152%/-0.089%, within observed variation. Minimum host available is 30.132 GiB; maximum sampled server RSS is 2.973 GiB. Every launch has zero new swap, healthy monitors and clean owned-child shutdown.

The small model rebuilds once and reuses its graph 126 times during each measured 128-token generation phase. Median reset/build/allocation totals are 1.086 ms code and 1.058 ms prose, about 0.065%/0.063% of that generation phase. This leaves little graph-planning opportunity on this model. It does not tell us the full prediction helper's cost. Instrumented GPU-buffer intervals cover about 94% of the small model's generation phase; that is elapsed coverage, not hardware occupancy.

Use detailed monitoring for diagnosis, then disable it for speed comparisons. This small-model result does not replace the full-model P07 historical short English/256-output result of **60.0842 TPS code / 40.3755 TPS prose**. Model, output length and helper topology differ, so neither rates nor percentage gains can be combined.

[Detailed per-area medians](results/20261010-observe-small-v1/MONITORING.md), [machine-readable summary](results/20261010-observe-small-v1/MONITORING.json), [immutable protocol and source pins](results/20261010-observe-small-v1/frozen.json), [raw campaign](results/20261010-observe-small-v1/result.json).

## Full model and memory audit

The full P07 baseline preserves the existing Q2_0 target, mixed packed Q3 helper, eight helper workers, draft maximum three, Tensor API, F16 KV/4K and batch 512, with short English code/prose and 256-token outputs. Its four-arm protocol and complete source/native/model pins are frozen. Admission found normal pressure and low CPU load but only **33.462 GiB available**; no model child or answer was launched. The attempt is excluded as performance/helper evidence and cannot be retried or partially resumed under the same ID. There is no automatic retry.

After the small baseline, a single targeted read-only cache invalidation released only its freshly used model cache. Host availability gained **2.538 GiB** in a separate 60-second settle, with zero new swap and unchanged model identity. Visible mapping residency fell 2.553 GiB to zero; this is not a unique physical-memory measurement. No unrelated process was stopped, no service disabled and no model data modified. Availability still stayed below 34 GiB, so this cleanup does not qualify full native admission. It occurred outside all comparison launches.

The load-free allocation audit preserves all 19 historical startup reservations, including separate attention/indexer KV and repeated scratch reservations. Unique target tensor payload is **35.030 GiB**; mapped/shared/repacked reservations cannot be added as physical RAM. The helper-off 512/F32 numerical-screen KV estimate is 30 MiB, only 15 MiB more than F16 at that same context. Actual first-touch scratch, recurrent snapshots, overlap and startup peak remain unmeasured; the audit changes no admission rule and does not establish full-model fit.

[Held full-model campaign](results/20261010-observe-flash-v1/REPORT.md), [actual preflight receipt](results/20261010-observe-flash-v1/00-control/result.json), [cache cleanup receipt](results/20261010-observe-small-v1/post-run-cache-cleanup/receipt.json), [allocation audit](results/20261010-observe-budget-v1/REPORT.md).

## Next decision

1. Obtain stable full native admission with margin above 34 GiB, then freeze a new campaign retaining this refusal. Complete the same four-arm baseline; do not lower the guard or reuse this attempted ID.
2. Compare the full helper's exposed reset/build/allocation time against monitoring uncertainty and natural drift. Implement R08 reuse only if those measurements show meaningful avoidable cost. Small-model setup time is already too small to justify that optimization here.
3. Otherwise prioritize R09 exact-format Q2 cooperative-input prompt kernels: compile-only arithmetic/precision fixtures first, then focused GPU correctness, matched prompt/reply measurements and independent confirmation. Larger MLX expert-cache capacity remains a separate track.

The [Astra research](research/20261010-astra-next-priorities/ASTRA.md) ranks these conditional paths. Existing failures and retry conditions remain in the [experiment ledger](EXPERIMENT-LEDGER.md). No new optimization or default promotion occurs in this monitoring pass.

## Reproduce

Preparation builds only; default baseline invocation prints a plan and loads no model. Explicit `--run` is required after freezing a new unused campaign folder. Models and vendor binaries are provisioned locally and remain excluded from Git.

```sh
.venv/bin/python scripts/prepare_m5.py --engine m5-observe --build --jobs 1
.venv/bin/python scripts/validate_offline.py
.venv/bin/python scripts/baseline_m5_observe.py
.venv/bin/python scripts/baseline_m5_observe.py --freeze --model small --campaign bench/results/NEW-UNUSED-ID
# The following explicitly starts the guarded model baseline:
.venv/bin/python scripts/baseline_m5_observe.py --run --campaign bench/results/NEW-UNUSED-ID
```

The maintained offline gate passes **197 tests**, including corruption/clock/coverage rejection, allocation-row preservation, four-arm exactness and attempted-campaign refusal. The new engine compiles and passes this physical small-model output check; no new synthetic GPU math suite or full-model helper qualification ran on it.

[Final load-free verification](results/20261010-observe-small-v1/post-run-verification.json) checks all 29 native receipts, both frozen source/native/model closures, exact outputs and raw diagnostic recomputation; the ordinary launcher matches the preceding commit and no model server remains. An initial postcheck comparison rejected JSON string keys versus in-memory integer Counter keys; [the original analysis rejection](results/20261010-observe-small-v1/postcheck-initial-rejection.json) and [correction](results/20261010-observe-small-v1/postcheck-correction.json) are retained. JSON-normalized comparison passes without changing records or rerunning inference.
