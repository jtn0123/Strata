# Next M5 experiments: prepared, testing on hold

Prepared October 6, 2026 for the 48 GiB M5 Pro. The user will give the testing go-ahead later. **No model loading, GPU tests or benchmarks were performed in this preparation stage.** No VM, service, model download or app launcher was started or changed.

The [six experiment cards](plans/20261007T055133Z-m5-future/preparation.json) contain a protocol, stop conditions and an empty result template. [Source plan](../config/m5_future_plan.json). These follow the [expert/output-table measurements](M5-OPERATION-PROFILE.md) and [Astra research plan](research/20261006-astra-future-plan.md).

| Experiment | Purpose | Ready now |
| --- | --- | --- |
| [Real expert reuse](plans/20261007T055133Z-m5-future/expert-reuse/README.md) | See how many predicted tokens select the same experts, separately for each layer | Diagnostic executable, matched-control runner and parser staged; native CPU self-test passed. Model behavior untested. |
| [Remaining GPU work](plans/20261007T055133Z-m5-future/split-gpu-cost/README.md) | Separate expert, vocabulary, shared matrix, attention/state and other work | Deliberately split diagnostic callback and timestamp attribution staged. Real GPU behavior and output parity untested. |
| [8K context](plans/20261007T055133Z-m5-future/context-8k/README.md) | Fit larger documents while checking recall, memory and latency | Protocol/fixture design. Existing native setting; long-input harness and quality fixture still need implementation. |
| [Bounded Mac SSD prefetch](plans/20261007T055133Z-m5-future/macos-row-prefetch/README.md) | Overlap useful lookup reads if file-specific waits are significant | Design only. No prefetch implementation or candidate engine. |
| [One targeted GPU kernel](plans/20261007T055133Z-m5-future/targeted-gpu-kernel/README.md) | Improve the measured expensive operation with current weight bytes | Design only. Kernel target stays unset until diagnostics establish it. |
| [Expert paging capacity](plans/20261007T055133Z-m5-future/expert-paging-capacity/README.md) | Investigate larger/higher-precision weights with a defined speed tradeoff | Feasibility design only. No pager, larger-model download or memory allocation. |

Each result template starts `not-run`, with every measurement and gain empty. The speed protocol brackets candidates with fresh controls in **control/candidate/candidate/control** order, measures first-token and complete-reply time alongside TPS, and requires zero new swap. Historical rates are references, not substitute controls. Diagnostics use matched greedy outputs and their timing stays outside speed history.

## Diagnostic implementation and limits

[The new entry point](../native/m5_eval_server.cpp) links existing `m5-trace` libraries; all seven existing engine receipts remain unchanged. It reads selected IDs through the native evaluation callback and checks the padded 2048-byte row stride, ten unique IDs per token, layer names and ID bounds. An independent CPU-only self-test checks padded reads and six invalid-input cases. It initializes no backend.

The split mode requests a synchronization boundary after each computational node. The parser joins GPU buffers to monotonic CPU intervals by submission time, independent of completion-log order; it rejects ambiguous/missing IDs, extra computational operations and uncovered computational buffers. Splitting changes fusion and adds synchronization/command-buffer overhead. Its costs are diagnostic observations, not uninstrumented per-kernel cost, accelerator occupancy or a TPS gain.

The [runner](../scripts/profile_m5_routes.py) uses an unchanged native control, checks paired greedy text/token output, separates prompt/generation and main/helper roles, saves raw evidence and rejects new swap. It requires at least 34 GiB available before a full-model run and a verified diagnostic build. The `--small-smoke` option is prepared for initial plumbing verification; **it has not run**. It cannot establish Flash expert reuse. No end-to-end GPU/model behavior is represented as proven yet.

## Safe preparation commands

These show plans or create cards; they do not run a model:

```sh
.venv/bin/python scripts/prepare_m5_future.py
.venv/bin/python scripts/prepare_m5_future.py --prepare
.venv/bin/python scripts/profile_m5_routes.py
```

`profile_m5_routes.py --build` compiles the diagnostic entry point and runs only its CPU self-test. It preserves existing engines. Commands that add `--run` do execute GPU/model work and must wait for the user's go-ahead. There is no background waiter, trigger, VM cleanup or auto-resume mechanism.

The first later test should be a small-model split-mode smoke, followed by full-model expert capture and then bounded split profiling. Stop and preserve evidence if output parity or attribution fails. Use those findings to choose which of the later templates earns implementation.

## Preparation evidence

- [Preparation receipt](plans/20261007T055133Z-m5-future/preparation.json), all six protocol/result-template files alongside their cards.
- [Build and final verification](features/20261006-m5-future-preparation.json), adjacent build/self-test logs.
- [Offline test log](features/20261006-m5-future-offline.log).
- [Packet generator](../scripts/prepare_m5_future.py) and [offline parser/template tests](../tests/test_m5_future.py).
