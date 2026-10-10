# Astra independent read-only review

October 9, 2026. Existing user-authorized Astra agents reviewed source, protocol and completed evidence. Neither agent edited files, built code or ran model/GPU work.

## Sampling review: astra_future_queue

The eight-case probe validly identifies the bounded min-p eligibility difference on the actual Metal path: four boundary mismatches, four separated controls matching, including production p=0.05. Source/binary/runner hashes and raw completion receipt agree. Equality is retained by CPU and excluded by Metal STEP. No finding invalidates parking complete backend sampling under exact-semantic rules; no rerun is required for that decision.

Do not extrapolate this stage to a complete default chain, actual generated-token divergence or quality loss. The logits were already ordered under both CPU sorted-flag settings. The complete chain also has potential F32 probability/RNG differences requiring separate proof; those concerns are source-informed, not executed failures. The upstream static graph change does not alter arithmetic. Grammar/reasoning gating already exists; do not report an absent safeguard incorrectly.

## Embedding review: astra_gdn_next

The upstream common/Qwen4exp hunks match exactly and existing `ggml_build_forward_order` is available. The separate MTP helper graph does not use the changed common embedding builder. Host placement of embeddings does not by itself make the patch redundant, so a bounded normal scheduler capture was warranted.

The accepted pair has identical per-request/shape plan inventories: 23 target and 139 helper dumps per engine. Every target remains CPU→Metal, with Metal input count increasing 27→30; every helper remains CPU→Metal→CPU→Metal, input counts0/14/2/2. Active token/PLE gathers remain CPU in both. The three added inputs belong to inactive mixed-input branches; compute flags do not erase scheduler input-copy obligations. No evidence qualifies a TPS trial. Park for this baseline, without claiming a measured slowdown.

All six requests/192 token IDs/text, draft counts and cached/fresh comparisons match. Both accepted launches have zero new swap. This is sampled output/cache parity, not exact hidden/recurrent-state or logit equality.

Protocol safeguards are sound for an untimed screen: exclusive lease, verified engines/models/offline gate, prelaunch baseline, zero-swap guard, bounded log cap, owned-child cleanup, separate greedy/cached checks, no evaluation callback, excluded diagnostics timings. Parse byte offsets against raw bytes before UTF-8 decoding. Debug2 emits plans on rebuild/reallocation, not every graph execution. Sizes/names are truncated. Startup reserve plans must not qualify a candidate. Known asynchronous HTTP debug notices can interleave native log-line fragments; keep raw evidence unchanged when reconstructing those lines.

The first pair was incomplete because candidate preflight deferred before loading; use only the independently completed retry as comparative evidence.
