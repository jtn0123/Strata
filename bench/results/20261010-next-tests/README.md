# Next sequential tests — prepared, not run

The validated checkpoint is commit `c615d06`, submitted in [fork PR #1](https://github.com/jtn0123/Strata/pull/1). Its confirmed 256-output English results remain 60.084 TPS code and 40.375 TPS prose. This preparation adds no measured gain. The ordinary launcher still selects P07 and the packed shared Q3 helper. The original launcher's rollback remains available.

[Machine-readable sequence and stop rules](../../../config/next_tests_20261010.json). Only an explicit `--run` starts either executable test below. The default commands display their plans. Neither the MLX engine nor the helper-reuse design is ready for a model comparison.

## 1. Input tokenization cache on the existing smaller model

The candidate is implemented, opt-in and disabled by default. A cache lives in one tokenizer instance, keyed by the entire rendered input and its special-token mode. Returned IDs are copied; errors are not retained; clearing serializes with in-flight replies. The conservative retained-object budget is 2 MiB and 128 entries. This bound does not claim a 2 MiB total RSS change.

`scripts/benchmark_input_cache.py --run` owns four separate native processes running the pinned Qwen3.5-4B Q4_K_M. English code/prose cases compare cold, identical and unique whole inputs with one excluded warmup and three measured replies per case. It includes template rendering/tokenization in time to first content and complete Service reply. It records actual cache hits, exact input IDs, output IDs, parser events and finish, native timings, source/model/build pins and zero-new-swap monitoring. Incoming app HTTP overhead and browser rendering are outside this Service measurement.

This can reduce input-response latency on repeated inputs. It does not accelerate native generation. Cold/unique inputs and native TPS have regression guards. A passing screen needs independent confirmation, actual repeated-input exposure in normal app use and full-model/API state/cancellation/cache checks before adoption. The parked S06 output-piece cache stays disabled.

## 2. Expert prompt tile screen

The isolated `m5-tile16` native engine and paired probes are built. GPU correctness, pipeline specialization and timings are untested. The normal P07 engine and its binaries are unchanged.

The existing kernel already runs one or two 16x64 Tensor API products within its 32-row tile and skips the second product if unused. The new flag splits those halves into separate 16-row dispatches while retaining the product shape, K accumulation, scale, route map, 128 threads, barriers and 8192-byte scratch. It skips unused upper activation loads. It may improve occupancy or duplicate expensive weight reads; there is no estimated gain. Only bounded Q2_0/F32 shapes with 512 experts, ten selected and 32–512 prompt tokens on the Tensor API qualify. Unsupported cases retain the original path. W02/P11 remain disabled.

`scripts/benchmark_m5_tile16.py --run` first checks complete two-block byte parity and activation/fallback coverage on the original P07 engine, the new engine with its flag off, and its flag on. It then runs a fresh original/candidate/candidate/original synthetic prompt screen. Small gains can qualify above their own drift, with safety checks on the other cases. The unchanged probe route metadata describes 32-row control tile distribution; it is not a count of tile16 dispatches. Activation counters count encoded eligible matrix operations, not GPU shader frequency.

A pass licenses a later full-model English prompt/reply trial, not a default change or a decode TPS claim. The native correctness probe needs 8 GiB available and aborts on new swap. Its original output digests, warmup and same-graph A/B/A mutation checks are retained.

## 3. MLX feasibility, then helper reuse

[MLX preparation receipt](mlx/preparation.json) pins `yibie/strata-mlx` at `4b6ce302` and the custom mlx-lm port at `2097324e`. MLX 0.32.3 and its isolated dependency environment are installed; dependency consistency and source syntax checks pass. No engine import, model download/load, GPU operation or benchmark ran. The environment and vendor source are excluded from Git; the exact resolved requirements and installation report are retained here.

Before loading the full model, add a bounded protocol/resource supervisor and test device initialization. The proposed first experiment uses F32, no MTP or suffix guessing, a small input chunk/context and a 24 decimal-GB expert pager budget. This is a capacity/compatibility pilot; that budget is not a verified 48 GiB fit or a throughput prediction. Default MLX F16 changes some token choices, and original sampling/state equivalence is unresolved. Its reported larger-Mac speeds are outside this lab's metrics.

R08 helper graph/scheduler reuse remains a design. The current runtime already reuses matching graphs. The next useful measurement is actual helper rebuild/reset/allocation cost on the critical path; cumulative overlapping GPU/helper durations cannot establish that opportunity.

## Results and failures

[Result sheet](results.json) starts with empty metrics. Each runner preserves raw logs, source/build/model provenance, memory samples, failed/aborted outcomes and its frozen protocol. A prior `tracking.json` blocks automatic reruns or selective resumes. Source changes require a new campaign. No daemon or timer starts these tests.

The older 152-file keeper qualification remains evidence for its committed/frozen checkpoint. This preparation changes the lab source inventory and gets a new offline receipt and separate frozen campaigns; it does not re-label the old proof as qualification of new code. No candidate is promoted from a preparation or component result.

The first frozen campaigns were superseded before execution when PR review tightened the memory-report CLI path boundary. Their original files are retained. The current runners use [v2 campaigns](../20261010-next-tests-v2/README.md), with the source fix and three new regression tests included.
