# Sol 6.1: serving and upstream research

Independent `gpt-6.1-sol`, high, read-only October9,2026 review. No edits, builds, model/GPU/SSD tests, process changes or external posts. Coordinator summary. No measured gains on this Mac.

## 1. Explicit stateless checkpoint suppression

`scripts/benchmark.py:315,349` uses cache_prompt=false, `scripts/lab.py:31` disables RAM cache. Nonetheless, accepted control `bench/results/20261009T194552Z-m5-draftcap-tail-4-conv-direct/server.log:442,706-710,737-741` executes112.571MiB context checkpoint saves and splits the48-token code prompt into44+4. Larger prompt checkpoints also execute.

[llama #30188](https://github.com/ggml-org/llama.cpp/pull/30188) is **open draft**, head d21082be681268216a8646527f67be2cf92400eb. It guards prompt-reuse checkpoint creation and automatic cache saves by task caching policy. Speculative rollback checkpoints are separate and must remain.

First suppress serialization while retaining current prompt split points. Second independent axis: remove extra splits, with D02 long English exactness fixture, seeded code/prose, cache-enabled behavior, cancellation/recovery. Split changes can alter arithmetic. Hypothesis: native decode0%; short-prompt TTFT0/3/15% faster, complete256-token reply0/0.2/1% faster. Those are scenarios, not measured or transferable from the PR's AMD machine.

## 2. Native stream text instead of repeated detokenization

`scripts/native_backend.py:21` POSTs /detokenize; generate at102 ignores native text and emits token IDs. `vendor/Strata-macOS/serve/server.py:415-428,648` re-decodes all emitted IDs after each token. N output tokens therefore cause N HTTP requests and quadratic total token-array serialization.

Use native text deltas or exact byte pieces with an incremental UTF8 decoder. Load-free fake native streams must match text/events, partial UTF8, reasoning delimiters, EOS, cancel/drain. Then measure native-ready versus app-emitted timestamps: network/parser work can overlap GPU generation, so fewer calls do not prove faster replies. Hypothesis: native TPS0%; app whole reply0/0.5/3% faster, with possible smoother display/lower CPU use. Different from P08 logits retrieval.

## 3. Exact preprocessing caches, conditional

[Parent f346dc6](https://github.com/Niko1221/Strata/commit/f346dc6b0c2fe5b87f34a570bd3a1f4760ef6595) adds a bounded200000-piece Python BPE cache. That path is not the lab's active native tokenizer. A native adaptation or bounded adapter cache needs vocabulary/template/parse-special identities and exact English/code ID tests. Current short prompt benefit near zero; repeated4K preprocessing0-30ms is only a hypothesis. Benchmark tokenization occurs outside timed completion, so no native TPS claim.

## 4. Immutable host-cache checkpoints, inactive today

[llama #30137](https://github.com/ggml-org/llama.cpp/pull/30137) is **open, unmerged**, head d2d35a3d80433db1b77f8b513768cac5a3e2c019. It shares immutable checkpoint objects, avoids zero-fill and checks complete state writes. Current --cache-ram0 means no unchanged-control benefit. Only investigate if an actual app history workload already incurs deep-copy cost; do not enable RAM cache on48GiB just to chase gain. Hypothesis for an affected cache-enabled switch: TTFT0/2/10% faster; native decode0%.

## 5. Recurrent checkpoint persistence, lower priority

[llama #26004](https://github.com/ggml-org/llama.cpp/pull/26004) merged October8 10:18:20UTC as033df86b69ec1a333eb241f0c16325a4d43dcff5. It preserves recurrent checkpoint state in slot save/restore. Useful only if restart/restore currently forces unnecessary shared-prefix replay. Potential avoided2K prefill0-3.5seconds is bounded by existing~3.8second fresh processing, not measured resume gain. Target+helper state/model/KV identity/corruption/continuation proof required. No SSD bandwidth or native decode claim. User does not prioritize cross-session chat, so defer without evidence of use.

## Fresh upstream/fork status

Read-only GitHub APIs on October9:

- llama master79e2e74eb11022c1ba2e438df7f0ca2d4c10f8b6, Oct9 17:59:50UTC; latest CUDA rounding fix.
- Parent Strata fb58e0dbc8399662c0e47c76578c6e878b14f6cf, Oct8; stage pinning made opt-in after corruption failure.
- Native metal-mac13da72298e0505bdcc4069bd87e96bc11e7b7aa5; Python Mac2cc4153409edb3f859187bdf10f13e34972d6ffb.
- [MLX thin-M #4654](https://github.com/ml-explore/mlx/pull/4654) merged Oct9 as a87691d; BF16/F16 geometry/formats do not establish Q2 model eligibility or gain.

Do not repeat N01/N02 or worker sweeps. [Metal encoded graph #14570](https://github.com/ggml-org/llama.cpp/pull/14570) reports no measured gain due overlap. Parent CPU-prefill share/residency-biased routing change arithmetic/output. No new SSD trial before attributed native lookup wait satisfies P06's gate.

Root independently verified selected PR statuses into [upstream-pr-status.json](upstream-pr-status.json). An open PR's merge_commit_sha is prospective, not merged proof.
