# Astra: new runtime mechanisms

Independent `gpt-6-astra`, xhigh, read-only source/evidence/upstream research on October9,2026. No build, benchmark, model/GPU/SSD execution, edit or process change by the reviewer. Coordinator summary; all gains below are hypothetical and non-additive.

## Rank and scenarios

| Direction | Metric | Low/base/high |
| --- | --- | --- |
| All-visible QSA ranking bypass | Decode TPS | -1/+1/+3% |
| Confidence-zero helper winner-only sampling | Decode TPS | -0.5/+0.5/+2% |
| Deferred accepted-only helper catch-up | Decode TPS | -3/+2/+5% |
| Alternating llama/scheduler plan reuse | Decode TPS | -1/+0.5/+2% |
| Exact cooperative Q2 inputs | Prompt throughput | -3/+2/+8% |

## QSA shortcut

Stored indexer top_k is2048 and pool ratio4. `src/models/qwen4exp.cpp:744-875` always builds query projection/norm/RoPE, scoring, top-k, gathers and selection-mask construction. With all visible pools selected, ranking should not change surviving visible cells, under valid finite scores.

Use a conservative **padded n_pool <=512** guard, one ordinary causal sequence, no shared cells/sliding/position transformations. `src/llama-memory-hybrid-idx.cpp:386` pads `max(64,PAD(n_pool_real+1,64))`; prompt length<2048 alone is insufficient. Preserve raw/pool cache updates for future continuation across the boundary. Preserve `build_attn_qsa`, n_sel and attention dispatch rather than switching to dense attention/reduction.

First structural mask proof for complete pools, tails, padding and visibility; later normal callback-free dispatch proof plus exact masks/hidden/logits/outputs near padding changes and beyond the limit. N02 normal plans identify indexer nodes but are not kernel timings. [Current upstream source](https://github.com/ggml-org/llama.cpp/blob/79e2e74eb11022c1ba2e438df7f0ca2d4c10f8b6/src/models/qwen4exp.cpp).

## Helper winner-only

Helper backend sampling is already active: N02 normal log line38930. `common/speculative.cpp:1467,1728` requests top ten but greedy/confidence0 consumes candidate zero. `ggml-metal-ops.cpp:5854` dispatches helper248320x1 k10 via bitonic+merges, not radix. A new winner-only consumer avoids this ranking, retaining full vocabulary/head weights and target CPU sampling.

Generic lowest-ID argmax is not proven equal to bitonic ties. Use unique finite maxima only; route ties/nonfinite to original top ten. Preserve sampler/history/state and avoid accidental full-logit retrieval. Full-vocabulary fixtures must cover cross-block ties, signed zero, infinities and near ties, followed by complete head+consumer timing. New versus N01 target min-p, P08 getter consolidation and S04/S05 head geometry.

## Catch-up after acceptance

Server `server-context.cpp:4069` invokes full target-batch catch-up before acceptance at4235. `common/speculative.cpp:1571` feeds target hidden rows into helper, including rejected suffix work. Defer until acceptance and replay only committed rows using target verified hidden states. Combining bonus/first draft is a separate second axis.

Never reuse helper-autoregressive hidden/KV states solely because token IDs matched. Preserve target verify width; prove pending_h/verify_h/helper KV/indexer states across all prefix lengths, EOS/cache/cancel/restore and D02's228th-token fixture. Helper width changes may alter arithmetic. [MTP driver state PR #30141](https://github.com/ggml-org/llama.cpp/pull/30141) is an open prerequisite if checkpoint paths are exercised, not a speed patch.

## Alternating plan cache

Two arenas exist, but `llama-context.cpp:1428` requires active-arena identity in addition to reusable parameters; no-output catch-up/output draft switches rebuild/reset/allocate. Keys must include topology/pool shape, and cache ownership/scratch must stay bounded. Measure exposed critical-path build/reset/allocate/set-input gaps against normal GPU timestamps, with no callbacks/new sync. Stop below2% exposed reply cost.

[Metal encoded graph #14570](https://github.com/ggml-org/llama.cpp/pull/14570) reports no gain due CPU/GPU overlap; it does not establish this different llama/scheduler path. Existing shape plans or old unexplained phase-trace remainder are not overhead attribution.

## Current source and exclusions

llama master79e2e74eb11022c1ba2e438df7f0ca2d4c10f8b6 retains unconditional QSA top-k, helper top10 and active-arena condition. Native Mac head13da722 remains unchanged; parent headfb58e0d remains latest. CUDA [parent PR109](https://github.com/Niko1221/Strata/pull/109) is inspiration only, not transferable performance evidence.

Do not remove all-prompt logits based on stale source comments: need_embd() reflects the task, and actual dispatch proof is required. Cooperative Q2 prompt work is already queued; [Apple guidance](https://developer.apple.com/videos/play/wwdc2026/330/) supports the idea but not precision or measured gain.
