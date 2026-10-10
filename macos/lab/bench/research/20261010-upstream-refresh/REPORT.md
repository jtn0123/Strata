# Upstream and fork refresh — October 10, 2026

The strongest new lead is **[yibie/strata-mlx](https://github.com/yibie/strata-mlx)**, an independent engine for the full Flash model. It offers useful source and a working expert pager, but it is not a proven upgrade for this 48 GiB M5 Pro. There is no newly merged Mac speed patch to install from the parent or the established native Mac fork.

This pass committed the accumulated lab work as `3a8d168ab429b17b6d81cadda72aa81534c392a5`, including the promoted P07 launcher, raw qualification evidence, benchmark reports and failed-experiment ledger. That tree was imported exactly into the local `mac-m5-lab` fork branch as `781710c`. Research and later documentation commits follow those checkpoints. Nothing was pushed, merged into the parent, installed or benchmarked during this research pass.

## Verified local checkpoint

The no-argument launcher now selects P07 exact ten-expert reduction in `m5-small-stack` / `small-reduce`. The target remains full Qwen3.8-Flash-Next GSQ-RCO Q2_0, packed shared Q3 helper, mixed placement, eight CPU workers, draft maximum three, confidence zero, Tensor API on, F16 KV, 4K context and batch/ubatch 512.

The previously measured short-prompt/256-output confirmation is **60.084163 TPS for English code** and **40.375465 TPS for English prose**. These are existing results, not new timings. Longer prompts measured 46.187239 / 47.143565 TPS in a separate safety bracket. Do not pool those workloads, sum historical percentage gains, or compare another engine's marketing numbers against these results.

P07 passed two independent short-prompt brackets and the later long-prompt/short-answer safety checks. W02's new screen fails the prospective 10 ms worst launch-pair first-token ceiling on prose (12.659958 ms), so it remains a possible tradeoff, disabled in the normal launcher. P11 remains parked. All raw failures and exclusions are committed.

Current verification: 156 load-free tests and five campaign protocol tests pass in the working lab. The 152-file frozen source closure, three engine/source/binary receipts and all 27 native qualification records were rechecked against their saved raw hashes without model/GPU execution. A fresh export of committed `3a8d168` initially failed three imports because intentionally ignored vendor source was absent. Adding only Git archives of the pinned Strata `serve` source and llama.cpp `gguf-py` dependency resolved it: **156 tests pass on the committed export**, without copying models, builds or dirty vendor files. [Initial failure](committed-export-validation.json), [successful dependency-qualified check](committed-export-with-pinned-deps.json). This verifies committed lab code with provisioned source dependencies; it is not a full cold-machine installer/build test. The preceding rollout's 12 benchmark launches, 312 answer/cache checks, 192 exact output signatures, zero new swap, 16 real API checks and streaming check remain historical measured evidence in [the rollout report](../../results/20261010-small-gains-stack/REPORT.md).

## What was checked

GitHub REST evidence was refreshed at approximately 11:10–11:13 UTC on October 10. The [head snapshot](summary.json), [coverage receipt](fork-coverage.json), saved PR descriptions/diffs and pinned MLX source receipt make the findings reviewable.

- Enumerated **1,811 unique publicly accessible direct-fork listings** across 19 API pages. GitHub reported 1,846 forks; the endpoint does not expose every counted repository, and the list is not an atomic snapshot. This is metadata screening, **not a source audit of all forks**.
- Checked names/descriptions plus four focused Mac/Metal/Apple/MLX searches. Inspected the relevant existing Mac branches, the additional Mac-named candidate and the newly published independent MLX engine. Metadata keywords can miss unnamed work; no claim of exhaustive Mac code coverage.
- Inspected the 100 most recently updated parent PRs, 100 issues and 100 recently updated llama.cpp PRs, then fetched focused PR descriptions and file diffs. Targeted refresh covered the parent, established Mac ports, MetalFit, Meld Turbo, Tierpack, architectds, lighttransport and llama.cpp. `xdcgh/Strata` returned HTTP 404 in this session; no assumption that it was deleted or contains no work.
- An initial overly broad repository search returned unrelated projects. Its response is retained as `mac-search.json` but excluded from coverage. The corrected focused searches and full direct-fork listing supply the screening evidence.

The parent main head is still [`fb58e0d`](https://github.com/Niko1221/Strata/commit/fb58e0dbc8399662c0e47c76578c6e878b14f6cf). The native Mac `metal-mac` branch remains [`13da722`](https://github.com/liangxiwei/Strata-for-mac/commit/13da72298e0505bdcc4069bd87e96bc11e7b7aa5), and its canonical expert-down branch remains `56075e0`, already reviewed on October 7. Shruxx, the 16 GB MLX port, the pinned jinzy adapter, Meld and Tierpack have no newer captured head than the existing review. `Godatplay/Strata-macOS-optimized` has exactly the parent's head on main and the same two branches; its name does not indicate an implemented Mac optimization.

## Ranked paths worth keeping

These are source-backed investigations. **No gain is budgeted until a matched local comparison passes.** The [queue](NEXT-EXPERIMENTS.json) records prerequisites and keeps every item not run.

| Priority | Path | What it could improve | Decision for this Mac |
| --- | --- | --- | --- |
| 1 | Full-model MLX engine feasibility, `U10-01` | Generation speed; independent runtime alternative | Strong new lead. Check exactness, sampling, peak memory and helper format first; isolate it from the working app. |
| 2 | A smaller expert prompt tile, `U10-02` | Prompt TPS and first-token time | Study its 16-token tiles as a new axis. Keep our Q2 unpacking/math and test all overhead. Tensor API itself is already enabled. |
| 3 | Helper graph/scheduler plan reuse, existing `R08` | Small cumulative generation gain | Still unimplemented. First measure exposed CPU planning/waits without disabling normal fusion. |
| 4 | Bounded repeated-input token cache, `U10-03` | App response latency on repeated long messages | Inspired by new parent PR #1823. Our adapter calls native `/tokenize`, so it requires a separate implementation and actual exposure measurement. |
| 5 | Explicit expert paging, `U10-04` | Capacity for a higher-precision model | MLX now has an implemented LRU pager to study. Treat this as a slower capacity experiment, not a promise of more Q2 TPS. |
| Later | Remote layer stages, `U10-05` | Capacity and possibly throughput with another PC | New working PC-side proposal. No Mac Metal worker or AMD-specific proof for this mixed pair. |
| Later | PC prefill and Mac answer handoff, `U10-06` | First-token time for large new prompts | Existing converter demonstrates another architecture. Requires different engines/state conversion; not exact output equivalence or shared physical RAM. |

### U10-01: a new full-model MLX engine

Pinned engine head: [`4b6ce302ef41d9cab54985e4aa99fe52f4fd89f2`](https://github.com/yibie/strata-mlx/tree/4b6ce302ef41d9cab54985e4aa99fe52f4fd89f2), published October 10. Fifteen selected source/report/license files were saved with Git blob and SHA-256 receipts in [yibie-source-receipt.json](yibie-source-receipt.json); none was executed.

Its own README reports full Q2_0 generation at 68–111 TPS with its draft head, on **one 128 GB M4 Max**, greedy decoding. Its comparison is against stock llama.cpp 0.4.1 rather than our tuned native engine. Those figures do not establish an improvement over our 60.08 code result. Its prompt comparison also spans separate sessions, and short prompts can start later, including an unexplained idle-related slowdown; both are disclosed in its `ISSUES.md`.

It reads the original GGUF expert blocks, keeps the large n-gram table on disk, implements its own draft/verify loop and speaks Strata's line protocol. These are relevant to our full model, unlike the earlier small-model MLX port. However, activation precision and sampling behavior are part of the engine, not just its weight-file identity. Its float16 default reportedly changes about one token in 250 near ties. Float32 matched eight tested answers according to its README, which is useful preliminary evidence rather than proof of parity with our temperature-0.6 target sampler and all cache/rollback histories.

The claimed speeds therefore cannot enter our exact-output keeper track. First inspect F32 memory, the dependency pin, draft-format requirements, sampler and state semantics. Its draft fetch is 4.9 GB on disk, while its memory notes estimate 1.6 GB resident draft arrays; neither is our shared packed Q3 helper. Its 41 GB resident Q2 process measurement and additional prompt workspace were on the larger Mac. Automatic fit logic is an estimate, especially under F32 and long context. A 48 GiB M5 result remains unknown. Prepare in a separate environment, reuse the existing target files, and do not fetch more weights or load it until the budget and comparison scope are concrete.

### U10-02: use the kernel source as a reference

`strata_mlx/blocks.py` uses 16-token × 64-output × 64-column expert tiles, unpacking weights into bounded threadgroup memory and invoking Apple's `matmul2d`. Its recorded Q2 complete expert block changes 22.1452 → 16.2729 ms in **its own MLX experiment on an M4 Max**. Its different numerical ordering and reported output differences prevent treating that kernel as an exact drop-in.

Our existing `mul_mm.metal` already uses Metal TensorOps, Q2 unpacking and compressed-weight expert math. This is not discovery of an unused accelerator or elimination of a full expanded expert stack in our runtime. Its active-tile compaction overlaps tested P11, and grouping overlaps P10/P12. Do not repeat those unchanged experiments.

A genuinely new bounded axis would be **16-token expert tiles instead of our 32-token tiles**, preserving the existing column loop, precision, reduction order and routing. An expert often has fewer than 16 useful prompt rows; a smaller tile may reduce padded work but increase scheduling overhead. It needs an isolated implementation, exact complete-block fixtures and normal fused-path evidence before English code/prose TTFT/reply comparisons. It does not inherently accelerate our four-row decode path. R09's proposed direct cooperative-input dequantization remains separate and unimplemented; this source still stages weights through threadgroup memory.

### U10-03: cache repeated input, not generated token pieces

[Parent PR #1823](https://github.com/Niko1221/Strata/pull/1823) caches whole long text spans before pre-tokenization. It is open. Its impressive 1.06 s → 0.042 s example compares against an older tokenizer without the current piece cache, on a Xeon and a 190K-token conversation. The incremental gain over current upstream was not measured, and our 4K-context/native C++ tokenizer is different.

Our `NativeTokenizer.encode()` still calls `/tokenize` on every invocation. A bounded cache could avoid repeated HTTP/tokenizer work on identical inputs, particularly prompt-counting/retry paths; whether normal app traffic repeats an identical whole render must be measured first. This is distinct from parked S06 **output detokenization** caching and from disk-persisted cross-session model state. Use a tokenizer/model-instance identity plus text and special-token flags, return fresh ID lists, limit retained bytes and reject oversized entries. Do not assume separately encoding messages equals encoding a combined prompt. The likely benefit is latency, with zero native generation-TPS attribution.

### U10-04: implemented SSD paging source

The new MLX engine has a shared byte-bounded expert LRU, parallel expert reads, per-layer prompt reads and routing counters. Its smaller-machine experiments cap memory on the same 128 GB Mac: Q2 generation at 6–7 TPS as 16 GB, 19–23 as 24 GB and 28–47 as 32 GB. These are simulated capacity budgets, not physical small-Mac measurements. Its resident path should avoid per-layer router readback; even without misses, its paged path adds waits. IQ3_S loads resident, but its capped-memory measurements were Q2 only.

This finally supplies runnable paging code to inspect for the earlier capacity template. It does not prove higher-precision throughput on our SSD or make SSD bandwidth equal unified RAM bandwidth. Require actual budget accounting, eviction/publication correctness, zero new swap, physical-I/O/page-cache evidence and fresh English workloads before using it to support a larger model claim.

[Parent PR #1838](https://github.com/Niko1221/Strata/pull/1838), also open, makes a partial RAM expert copy follow the conversation. Its author measures +11.9–17.3% decode on a CUDA PC with a genuine file tier. It explicitly does nothing when every expert is already in RAM/VRAM. Our current full-resident Q2 expert path cannot inherit that gain; it is a later paging design reference. Its blocking reads and absent HIP/Windows testing matter for the future AMD PC.

### U10-05 / U10-06: the later second computer

[Parent PR #1748](https://github.com/Niko1221/Strata/pull/1748) is a new, open remote-layer-stage implementation: each PC owns only its layers' experts/state, and activation rows cross TCP. The author reports two-PC decode gains on NVIDIA machines, with single runs per table row and non-matched starting-state limitations. Linux and Windows socket paths exist. The reviewed files provide no Mac Metal integration or benchmark on our AMD GPU. Use its stage timing and ranged-weight loading ideas when designing a bridge; do not sum 48 GiB unified RAM, 32 GB PC RAM and 16 GB VRAM as one zero-copy pool.

[kv-baton](https://github.com/datanerdie/kv-baton) instead has a PC read a large prompt and transfers converted state to a Mac to generate. It measured substantial long-prompt first-token savings on two RTX 3090s and a 128 GB M4 Max. Its Sushi/Strata quantizations and KV layouts differ, open-ended outputs are not bit-identical, and restored MTP state has known limitations. This is relevant to our earlier two-device question, but not a ready adapter for this 48 GiB M5 + 16 GB AMD pair. It changes first-token latency rather than the Mac's decode TPS.

## Changes screened out or still held

- [llama.cpp #30255](https://github.com/ggml-org/llama.cpp/pull/30255) saves logits buffers for embedding/reranking graphs without logits. Our target and helper require logits; it provides no relevant model-memory saving here.
- [llama.cpp #27478](https://github.com/ggml-org/llama.cpp/pull/27478) optimizes CPU flash attention and Linux allocation alignment. Our attention runs on Metal, the helper CPU work is expert computation, and its allocation change excludes macOS. Do not transplant its CPU-only gains.
- [Parent #1822](https://github.com/Niko1221/Strata/pull/1822) avoids CUDA gate/up group copies. Our resident Metal matrices already read their weights directly; no equivalent group-copy removal was identified. It does not remove an existing Mac bottleneck.
- [Parent #1779](https://github.com/Niko1221/Strata/pull/1779) concerns distinct-GPU pipelined adaptive caches; its eligibility excludes this single unified-memory Metal runtime.
- [llama.cpp #30047](https://github.com/ggml-org/llama.cpp/pull/30047) remains open and unchanged at captured head `c1d2e51`. Its tokens-per-expert MMA threshold still excludes our normal four/five-row verification. Earlier screening remains valid.
- [llama.cpp #30188](https://github.com/ggml-org/llama.cpp/pull/30188) remains open; captured head `d21082b` and restore test do **not** resolve our exact mixed-cache-policy/prompt-split requirements. R05 stays held under its existing card. Do not relabel it a new safe fix.
- [llama.cpp #30141](https://github.com/ggml-org/llama.cpp/pull/30141) remains an MTP hidden-state checkpoint correctness proposal, not a proven speed improvement.
- The latest captured llama.cpp head [`781dbc5`](https://github.com/ggml-org/llama.cpp/commit/781dbc5ac98921dbdb5e5b2ec5b7a50960e937d4) fixes multimodal MTP. This verified text-only profile does not use that path. Previously merged dense few-row math is already included locally; sampler/embedding changes keep their N01/N02 exclusions.

## Next order

1. Inspect MLX feasibility and numerical/sampling/memory boundaries without changing the working engine. Prefer borrowing a distinct exact kernel mechanism over claiming an unsupported whole-engine comparison.
2. Prepare the 16-token expert-tile axis only if it can preserve required arithmetic; otherwise park it with the reason. Retain P11/P12/P10's failures.
3. Measure helper graph-planning exposure for R08 and app input-tokenization exposure for U10-03. Implement one only if it has exposed work to remove.
4. Keep SSD paging and both PC architectures in a separate capacity/future queue.

Any future measured keeper uses fresh matched controls, English code/prose, fixed prompts/output caps, temperature/seed/sampler controls, warmups, independent ABBA brackets, exact output/state checks, cached safety, healthy memory monitoring and zero new swap. Positive 1% and sub-1% gains are eligible when they exceed twice their own control drift and independently confirm. No automatic benchmark trigger or speculative gain is installed by these research notes.
