# M5 experiment queue: measured progress and remaining work

Latest incremental update: card 9 now has [three measured copy experiments](results/20261009T112641Z-m5-copy-resume/REPORT.md). Direct convolution-state copy adds 1.33-1.62% fresh TPS with identical outputs and zero new swap. Wide scalar/vector copies give no useful fresh-writing gain. The normal-path shape inventory confirms large GDN copies are already fused away. All 94 offline tests pass; shared matrix and grouped expert-weight work remain candidates.

October 9 update: user-authorized testing has completed cards 1–7 below. [Accepted GPU/context/SSD results](results/20261009T085842Z-m5-next-batch/REPORT.md) retain the original raw-JSON formatting failure and the separate passing fixture-v2 context retry. The full model passes 8K/F16 with essentially unchanged fresh TPS and zero new swap. All 91 offline checks pass; separate attention/indexer KV buffers are now counted. T3 and WiFiman remain open, model servers are stopped, and no VM/Docker/Chrome was restarted. Cards 8–11 remain designs with the measurement dependencies listed below; no automatic work is scheduled.

Original preparation, October 7, 2026: the refreshed [11-card packet](plans/20261007T231811Z-m5-future/preparation.json) records the protocols. [Source plan](../config/m5_future_plan.json). [Complete recreation recipe](M5-PREPARATION-RECIPE.md). [Preparation evidence](M5-REST-PREPARATION.md).

That preparation passed **90 maintained offline tests** before the October 9 accounting regression was added. Its model/GPU/storage runs were held then; the update above is the current state. Native engine and diagnostic receipts remain unchanged.

| Order | Experiment | What is ready |
| --- | --- | --- |
| 1 | Clean baseline refresh | Two clean full-model launches completed; later candidate comparisons have their own fresh controls. |
| 2 | Upstream Metal residual correctness | 1,160 CPU-reference GPU cases and four full-model launches pass; no useful TPS gain, original Qwen graph exposure unproved. |
| 3 | Real expert reuse | Full Flash depth3/4 captures pass, all 48 target layers plus helper captured; dominant batch selections repeat about 31–35%. |
| 4 | Remaining GPU work | Full Flash depth3/4 split captures pass and match controls; shared matrices/state-copy work identified. Instrumentation prevents a normal-runtime cost/occupancy claim. |
| 5 | RAM accounting | Distinct attention/indexer cache logs retained; 4K/8K allocations and monitored headroom recorded. Component estimates remain separate from physical footprint. |
| 6 | 8K context | Full 4K/8K/8K/4K fixture-v2 trial passes all 134 checks and zero new swap; six exact-6144-token recall fixtures pass. Initial JSON-fence failure retained. |
| 7 | Lookup-file reads | 128 offsets / three passes / 6.09 MiB read-only probe passes. First-pass median123.7us, repeats1.7–1.8us; cache state uncontrolled and native wait time unmeasured. |
| 8 | Native Mac SSD prefetch | Bounded design; implementation awaits evidence of meaningful lookup stalls. |
| 9 | One targeted GPU kernel | Three isolated copy variants measured; direct convolution copy improves fresh TPS 1.33-1.62%. Wide copies offer no useful fresh-writing gain, and large GDN copies are already fused. Next validate shared matrix or grouped expert weight work in the normal path. |
| 10 | Larger-model expert paging | Capacity/eviction proof template; needs hot-set data, RAM/SSD budget and an agreed speed tradeoff. |
| 11 | Quantized KV follow-up | Separate later design after 8K allocations/quality; requires quantized-attention correctness fix first. |

The archived preparation templates remain `not-run`; current measured evidence is linked above. Speed candidates use fresh control/candidate/candidate/control passes, report TPS, first-token delay, complete reply time and control drift, and reject any new swap or quality/provenance failure. Percentages are checked for finite positive input metrics. Historical rates are references only.

The 8K speed comparison uses identical shorter inputs at both capacities. Its three larger recall cases test capacity separately and do not create a 4K TPS comparison. F16 cache, model, helper and workers remain fixed. The saved-data RAM report separates unique weight bytes, helper/repack/private buffers and the lazy file mapping; an accounting sum is not measured physical RAM or proof that 8K fits.

The lookup probe reads selected page-aligned ranges via `pread`, verifies bounds and repeated sampled digests, and never writes/purges/preloads the shard. It characterizes file-specific read latency with uncontrolled cache state; it cannot measure actual native mmap waits or establish a model TPS improvement. Native prefetch, kernels and paging remain dependency-gated designs, rather than runnable placeholders.

## Safe plan/preparation commands

```sh
.venv/bin/python scripts/validate_offline.py
.venv/bin/python scripts/prepare_m5_future.py --prepare
.venv/bin/python scripts/benchmark_m5_decision_baseline.py
.venv/bin/python scripts/benchmark_m5.py --experiment metal-residual-correctness
.venv/bin/python scripts/profile_m5_routes.py
.venv/bin/python scripts/benchmark_context.py
.venv/bin/python scripts/memory_budget.py
.venv/bin/python scripts/profile_lookup_io.py
```

Card preparation requires a passing offline receipt for the current scripts/tests/config. The explicit gate excludes real sockets and native self-tests/builds/GPU/model suites. A CPU build remains a separate action. Commands adding `--run` execute real work; the October 9 batch was explicitly authorized by the user. Each full-model launch checks normal pressure, a quiet CPU window and at least 34 GiB available RAM. The accepted batch also stops on any new swap and releases only idle owned model-file cache outside measurements when needed. It never stops unrelated work to create headroom.

## Diagnostic interpretation and earlier evidence

The diagnostic entry point reads ten expert IDs per token, including a padded 2048-byte routing stride, checks bounds/layer roles and records raw evidence. CPU self-test/fatal-stop cases and a bounded Qwen3.5-4B control/split smoke passed earlier; see [the audit preparation](M5-AUDIT-PREPARATION.md). The dense smoke establishes plumbing only, not Flash expert reuse.

Split callbacks remove fusion and add synchronization. GPU buffers are assigned by monotonic submission intervals; ambiguous, untimed computational or uncovered work is rejected. Those costs rank diagnostic paths; they are not original per-kernel costs, accelerator occupancy or ordinary TPS.

The [Astra source-level review](research/20261007-astra-macos-deepdive.md) explains the staged correctness fix and why other forks do not supply a proven current speed upgrade. Our graph already avoids the port's duplicate GDN recurrence. The [earlier six-card packet](plans/20261007T055133Z-m5-future/preparation.json) is retained as history. Larger models/higher precision may trade speed for capacity; unified memory on this Mac does not pool with another PC.
