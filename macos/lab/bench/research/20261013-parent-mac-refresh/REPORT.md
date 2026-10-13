# Long-prompt lookup screen and newly maintained parent Mac engine

Checked on 2026-10-13. Parent source is pinned at
`ed4773eb7c8f1f1531ba2bc70e0e1987de2661af`; thirteen source files and their Git blob identities
are saved locally. No parent installer, model preparation, model download or new engine inference was run.
The existing maintained balanced/editing defaults remain in place.

## E03: a different workload now justifies a narrow prefetch investigation

`scripts/capture_lookup_long.py` runs two synthetic English review documents of 2337/2346 input tokens.
There is no inference warmup. Each document gets its first encounter and one exact replay, with prompt
cache disabled. The diagnostic engine is `m5-lookup` over the earlier `m5-copy` engine; P07 is absent.
Both launches use the existing Q2 target/shared Q3 helper, MTP3, mixed placement, eight helper workers,
4K/F16 and batch/ubatch512. Native fusion stays enabled. Tracing is excluded from speed comparisons.

| Document / encounter | Full reply | First text | Lookup envelope | Envelope / reply | Envelope before first text |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 / first | 4.942 s | 4.765 s | 145.288 ms | 2.940% | 144.335 ms |
| 1 / replay | 4.662 s | 4.488 s | 1.527 ms | 0.0328% | 1.507 ms |
| 2 / first | 4.740 s | 4.566 s | 21.096 ms | 0.4450% | 21.077 ms |
| 2 / replay | 4.684 s | 4.510 s | 1.654 ms | 0.0353% | 1.631 ms |

The first document's earlier envelope is 3.029% of observed first-text delay. These are conservative
gather envelopes, including CPU dequantization, scheduling and possibly overlapping target/helper work.
They do **not** measure physical SSD wait or a prefetch gain. First text is observed by the client,
not an internal prompt-phase callback. Cache residency is unknown; no cache purge, forced eviction,
whole-shard preload, memory wiring or precision change occurred. Replaying a document is not a matched
optimization comparison.

The trace identifies the exact lazy host-backed lookup tensor in shard1, file offset192, 90-byte rows
and 16KiB pages. The loader confirms prefetch eligibility, but the pinned platform guard makes the
prefetch function a no-op on Apple. Nine lookup invocations cover each request. The summed page sizes
of 203.5/208.2 MB deduplicate within each invocation only; they are not unique resident bytes or SSD reads.
The following control launch returns identical complete text/token/prompt signatures for all four
requests. All eight requests end normally, with no capped output. Both owned processes exit cleanly,
continuous pressure is normal and new swap is zero. Minimum available RAM is 2.98/3.38GiB; peak process
RSS is 37.65/37.74GiB, which is not unique GPU allocation. Postflight has 38.47GiB available and swap0.

**Decision:** retain P06's rejection of unchanged warm-only prefetch trials. E03 crosses the screening
threshold on one first encounter and permits a bounded prefetch-only investigation. Its roughly145ms
envelope sets the scale of this opportunity on that request; it does not predict a general TPS increase.
Require page-residency evidence on the actual demand path, bounded advice/call-result evidence, unchanged
model outputs and a fresh repeatable latency comparison before keeping it. Unknown-cache observations
must not be called cold-cache benchmarks. Raw evidence and original source are local in
`bench/features/20261013-lookup-long-v1`.

## The parent now contains a Mac engine

The earlier statement that Apple Silicon was out of scope is superseded by the current parent tree.
[The parent Mac guide](https://github.com/Niko1221/Strata/blob/ed4773eb7c8f1f1531ba2bc70e0e1987de2661af/docs/MAC.md)
documents a native Metal port in `metal/`, source builds through `setup.sh`, and streaming on32–48GB Macs.
Its reported inference machines are an M5 Max128GB and M4 mini32GB; neither is our M5 Pro48GiB.

The installer conservatively budgets75% of48GiB, or36GiB, for a resident pack. Its Q2 estimate is
37.6GB plus8GB overhead, about42.47GiB, so it recommends SSD streaming and omits MTP at this size.
The runtime independently checks real device working-set limits and tensor bytes with a12GiB reserve.
The installer estimate is not a measured allocation, and its streaming throughput cannot be transferred
to our resident target + smaller shared-helper arrangement. Source inspection also finds the default
Q8 hyper-connection read; BF16 is available through `STRATA_HC_Q8=0`. This is a numerical change that
must be separated from architectural gains.

The unchanged upstream `arena_budget_test.cpp` compiled locally and passed47 CPU arithmetic checks.
No GPU was initialized and no weights were read for those tests. This validates its arithmetic fixtures,
not a48GiB model load, an allocation cap in practice, or an inference improvement. Local receipt:
`bench/features/20261013-parent-mac-budget/proof.json`.

## Next work, in order

1. **Native prefetch-only candidate:** use the existing row-range interface and keep loader mapping changes
   separate. Establish residency and useful overlap first. Gate on first-text/full-reply improvements and
   zero new swap; generation speed may stay unchanged. A small repeatable gain is still worth retaining.
2. **Parent engine compatibility and memory plan:** keep it isolated, reuse verified target files, account
   for pack/host/helper/workspace bytes and establish guarded ownership before any load. Start with4K,
   explicit BF16 HC and matched numerical settings. Compare actual prompts, full replies and cancellation;
   do not run its installer against this lab or force its resident/arena overrides.
3. **GPU draft-round chaining:** the parent's `Window::mtp_draft` keeps token selection, probability and
   next-step embedding on the GPU across one submitted round. Check whether avoidable per-step waits
   exist in our normal helper path before porting that architecture. Our helper backend sampling is
   **already enabled** in source defaults and the actual native log; enabling that same flag is no new
   optimization. Preserve target verification, tie handling, cache rollback and seeded output gates.
4. **Separate MLX comparison:** `yibie/strata-mlx` remains at `e9cf9b70695d3021c087054b78a78fb92d3c039b`.
   Audit its complete48GiB budget and current helper formats before loading. Default float16 results
   cannot be claimed as an exact replacement; float32/M5 precision controls need independent validation.
5. **Contiguous expert storage for larger models:** the parent's one-read-per-expert layout is useful
   only when experts actually stream. Our current target is resident, so it is a future capacity experiment,
   not a promised current TPS boost. Account for extra disk space, pack identity and repack lifecycle first.

The whole-model adapter and engine comparison are not prepared yet. These are bounded next gates with
source evidence, not enabled features or estimated percentages to add to existing results.
