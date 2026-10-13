# Performance tracking and next experiments

Researched 2026-10-13 against current GitHub API state and the local experiment ledger. The UI now records
timings and settings, but this pass did not load a model, compile a candidate engine or establish a new TPS gain.
The maintained balanced/editing settings and model bytes remain unchanged. This opening describes the initial
research snapshot; later real-model checks and a fresh parent update are recorded below.

## What is measured

- **Generation:** native final `predicted_per_second` when supplied; otherwise the shell's generation rate.
- **First token (server):** from leaving the queue to the shell's first generated token, including prompt
  processing and detokenization. This can precede visible text and does not include queuing or browser work.
- **Full response (server):** the server request lifecycle at millisecond resolution, including thinking and
  cleanup; queue admission is the start. Canceled/limited/disconnected requests retain their status.
- **Browser first text / full request:** observed in the web chat, including frontend, transport and queue
  time. Thinking counts as text. A very short response can first paint only when completion is received.
- **Prompt processing, helper acceptance and reuse:** native timing/counters if reported. Unknown values stay
  unknown. Acceptance is accepted proposals divided by all proposals, not accepted tokens / output tokens.
- **Resources:** available RAM and total system swap; owned model RSS, pressure and new-swap baseline from the
  existing launch guard when available. RSS can overlap shared/Metal memory; it is not a second RAM pool.
- **History/export:** up to 200 records in this browser, with numerical request data and a settings whitelist.
  Prompts, replies, model paths and API keys are excluded. Resource export is a current snapshot, not a
  per-request peak. The latest 30 server requests are visible. Mock measurements are marked as test data.

Ordinary chat is observational telemetry. Controlled comparisons still require the same exact input, output
budget, cache condition, sampling, engine/model/profile, fresh matched controls and independent confirmation.
The UI does not turn unrelated chat requests into claimed percentage gains.

## Ranked research queue

| Priority | Path | Main benefit | Current evidence and next gate |
| --- | --- | --- | --- |
| 1 | macOS native lazy-table prefetch | Cold first token, prompt reading, startup/reply delay | [llama.cpp #30405](https://github.com/ggml-org/llama.cpp/pull/30405) merged Oct 13 at 14:28 UTC, merge `b9f3599fb1c429e89248f042699ea2e062a32e57`. It enables `MADV_WILLNEED` on macOS. Qualify a prefetch-only candidate on the actual split Q2 layout, separate cold and warm results, preserve normal pressure/zero new swap. |
| 2 | Varied editing lookup + prompt-local lookup/MTP | Generation TPS on supplied-file editing | The dedicated profile already has a confirmed single-file result. Check disjoint Python/JavaScript/JSON edits and first/warmed requests. [Native speculative docs](https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md) describe prompt-local strategies; qualify bounded proposals and exact reply/lifecycle behavior before changing defaults. |
| 3 | Layer-at-a-time prefill in a separate MLX backend | Long-prompt throughput when experts are read from SSD | [strata-mlx 6a229aed70](https://github.com/yibie/strata-mlx/commit/6a229aed70) changes the paging/prompt path. This is a separate architecture, not a drop-in Metal kernel. Verify target/helper compatibility, output quality, memory, cold/warm behavior and cancellation before timing. |
| 4 | Bounded parallel lookup-table reads | Hide SSD latency in cold/under-resident workloads | [strata-mlx a52821c1c1](https://github.com/yibie/strata-mlx/commit/a52821c1c18cc7b3194d71f7cc746da425969719) supplies a mechanism. Its subsequent report explicitly corrects cache-contaminated measurements. First prove attributed lookup wait in our current native path; do not transfer its percentages. |
| 5 | Loader mapping-range audit | RAM headroom / accidental pinning | The other half of #30405 excludes foreign spans from Metal buffers. Our weights and lazy tables already live in split shards, so it may offer little here. Inspect actual spans before adopting or timing it. |
| 6 | Startup warmup | More predictable first interaction | Measure launch-to-ready and first real request separately; warmup can merely move the wait. Keep explicit, bounded and optional until whole-workflow latency is better. |
| 7 | Current Metal correctness/dispatch refresh | Correctness and possibly relevant native operations | Recent [Metal history](https://github.com/ggml-org/llama.cpp/commits/master/ggml/src/ggml-metal) includes duplicate-ID and large-tensor fixes. Their existence does not prove a speed gain for our shapes. The Q2 few-row MMA benefit is already in our kept engine, not a new opportunity to count again. |
| 8 | Probabilistic/adaptive MTP policies | Potential sampled-code/prose TPS | [#27694](https://github.com/ggml-org/llama.cpp/pull/27694) is already present in the inspected source and exposes draft sampling; this is not a new port. [Adaptive #27210](https://github.com/ggml-org/llama.cpp/pull/27210) remains open and its author recommends maximum depths at least 7. A 48 GiB memory budget and prior depth/cap divergence make this a lower-priority independent correctness project. |

For #30405 the fresh REST API confirms the merge; the fetched HTML still showed a cached Open state.
Its reported M2 Ultra/192 GB/IQ4 measurements are neither M5 Pro results nor predictions for our Q2 model.
No new kernel, paging, sampling, power or helper policy was enabled by this research.

Later same-day validation used the real maintained full-model editing app. It reproduced the backend losing
the final native timing packet when the shell closed at EOS. The bounded EOS-only counter handoff now preserves
generation/prompt rates, draft acceptance and cache reuse; cancellation and missing-final data remain separate.
Two complete-file API checks, all nine API/lifecycle groups, the actual browser timing badges/Monitor, and export
privacy passed with normal pressure and zero new swap. These are functional observations, not a new speedup.
The browser request included thinking; controlled editing comparisons disabled it. See the decision ledger's
E01/E02 and real-monitor entries for measured scopes, rejected attempts and local evidence locations.

## Avoid unchanged retries

The subsequent long-English diagnostic crosses the lookup screen on its first document (145.288ms,2.940% of
reply time), while its replay is0.0328%. Cache state stays unknown and no prefetch gain is measured. The parent
now also has its own native Mac Metal engine; previous out-of-scope statements are historical. Its48GiB
defaults stream experts and omit MTP, so there is no basis for transferring its larger-Mac TPS to this lab.
See the [updated source/budget evidence and next gates](../20261013-parent-mac-refresh/REPORT.md).

The ledger already parks stream-piece conversion caching (correct, no qualified whole-reply gain), W02 helper
selection (unconfirmed or outside latency gates), fixed depth/cap variants with divergence, route-map reuse,
cooperative scheduling and the power-mode experiment. They need a material mechanism/workload change and a
new frozen protocol before another test. Small confirmed gains remain worthwhile when above control drift;
independent percentages are not added together.

## First planned comparison

Use the maintained full Flash-Next Q2_0 + packed shared Q3/P07/4K/F16/MTP3/mixed/eight-worker configuration as
the matched control. Introduce only the macOS prefetch enablement first; keep loader-map changes separate.
Capture exact source/model/settings identities, cache-state evidence, actual eligible ranges, first token,
prefill TPS, generation TPS, full reply time, draft acceptance, available-memory floor and new swap. Use an
alternating control/candidate bracket and a separate confirmation, checking exact replies, EOS, cancel/reuse
and guard health. Unknown file-cache state cannot be advertised as a cold-cache result. Preparation and
performance tracking are complete here; that native experiment is not implemented or run in this pass.
