# Decisions from the first Mac experiment

October 6, 2026. Apple M5 Pro, 48 GiB, AC power, normal power mode. No GPU memory sysctl was changed. Source and model pins are in `config/`.

## Normal profile

Full Qwen3.8-Flash-Next GSQ-RCO Q2_0, all 512 experts per layer, lazy SSD lookup table, Metal, 4K context, one request at a time, processing batch 512, conversation caching enabled, no MTP. `Start Strata.command` and `Stop Strata.command` launch and stop this profile. `scripts/run.py flash --no-prompt-cache` restores the uncached v1 conversation behavior.

## What the measurements changed

- The small Qwen3.5 4B baseline ran at 76-78 output tokens/s. An A/B/A sequence confirmed the batch improvement without moving the generation baseline.
- Full Flash-Next ran at 37-39 output tokens/s. The 37.6 GB weight shard loaded on Metal; the separate 28.8 GB lookup shard was logged as lazy. Native logs reported 35,870 MiB of mapped GPU weights. Initial full-model baseline swap growth was 14.6 MB.
- Processing batch 512 improved the full model's 2048-token prompt rate from 414 to 658 tokens/s. Median first response fell from 4.94 to 3.11 seconds, about 37% less waiting. Output speed stayed around 37-39 tokens/s. This is the adopted change.
- Full-GPU MTP loaded but failed on its first request with `kIOGPUCommandBufferCallbackErrorOutOfMemory`. Both the native error and failed run are saved.
- CPU MTP ran at 43-45 output tokens/s with 71-72.5% draft acceptance, but added 1.85 GiB of swap and raised first-response time for the long prompt from 3.11 to 4.15 seconds. It is an optional experiment, not the normal profile.
- MTP's 2048-token workload matched the non-MTP output token-for-token. The 512-token workload diverged after token 92. Batch arithmetic is a possible explanation, but the divergence has not been diagnosed. Do not claim exact greedy equivalence for this configuration.
- Full-model 8K context passed 1024- and 4096-token input workloads and two answer checks, at 37-38 output tokens/s, with no new swap growth. Its approximately 1.93 GiB of pre-existing swap came from the earlier CPU MTP experiment. The launcher stays at 4K; use `scripts/run.py flash --context 8192` for the tested larger context.

## Application proof

Both the small and full models passed nine real API/adapter checks: Unicode, native/adapter token parity, OpenAI streamed and non-streamed chat, Anthropic chat, explicit tool/overflow rejection, cancellation and client disconnect recovery. Strata's real browser chat returned 391 for 17 x 23 with each model. Preview screenshot capture failed; browser evidence is DOM-based.

A separate 2831-token prompt with 128 distinct records correctly retrieved the requested label. Its complete request and response are saved as a context probe. This exercises varied lookup keys beyond the repeated text used for timing.

## Optimization 1: reuse conversation history

The only inference behavior changed is the adapter's `cache_prompt` setting. This reuses a matching prefix in the existing native engine slot. It does not add a separate multi-conversation RAM cache, change model precision, enable MTP or change GPU memory limits. The adapter reports its configured cache setting through Strata's `/metrics` engine information.

The [full-model paired comparison](results/20261006T141016Z-flash-conversation-cache/comparison.json) uses five measured pairs at each history size, plus excluded warm-ups. Each mode starts from an identical uncached first turn, then receives exactly the same follow-up tokens. Pair order alternates. Settings match the working v1 profile: batch 512, 4K, F16, full Metal, no MTP. These matched follow-ups are the baseline for the percentages; the earlier synthetic fresh-prompt benchmark is a different workload and remains unchanged.

- Short history (545-token follow-up): median first token 0.951 -> 0.259 seconds, 72.8% less waiting. Total answer time 1.581 -> 0.883 seconds, 44.1% less time. Reused 503 prompt tokens.
- Longer history (2069-token follow-up): median first token 3.351 -> 0.272 seconds, 91.9% less waiting. Total answer time 3.972 -> 0.898 seconds, 77.4% less time. Reused 2027 prompt tokens.
- Output speed changed +1.0% on the short workload and -0.7% on the longer one, about 37-38 tokens/s overall. This is a startup improvement, not evidence of faster token generation.
- All 15 paired/changed/new-conversation checks passed. All sampled outputs matched the uncached token IDs exactly. This limited check does not prove general answer quality or bit-for-bit equivalence on every prompt.
- Swap growth was zero; approximately 1.04 GiB was already swapped at the start. The memory guard did not fire. Memory samples cover both modes in one process; equal paired RSS is not an isolated proof that cache allocations cost zero memory.
- [Nine API/adapter checks](results/20261006T141248Z-flash-integration.json) passed with caching enabled, including cancellation and disconnect recovery.
- [Real Strata HTTP API proof](results/20261006T141353Z-flash-cache-api.json) confirmed correct streamed follow-up answers and native metric deltas of 503 and 2027 reused tokens. These two extra timings are functional evidence, not paired benchmark medians.

Keep conversation caching enabled. The gain applies when conversation history matches the engine's current slot; fresh or interleaved unrelated chats may have little reusable history. Longer answers receive a smaller percentage reduction in total time because generation speed is unchanged. The next isolated experiment is reducing the prediction helper's extra memory.

## Limits and next experiment

These are local single-user timing and sanity checks, not a broad quality evaluation. Fixed-length generation ignores EOS for timing. OS file cache is uncontrolled and background applications were left running. The Mac's SSD speed was tested separately with a short uncached file test; it is not a sustained inference bandwidth guarantee.

The smaller-helper experiment is complete; see optimization 2 below. The current runtime does not borrow a shared MTP head's embeddings/output tensors. A runtime supporting that or profiling the remaining CPU/GPU work is a possible next speed experiment. Higher-precision main models and the AMD desktop remain separate future capacity experiments.

## Optimization 2: a smaller prediction helper

[Percentage comparison and all source records](PREDICTION.md). The full main model, runtime pin, batch 512, 4K context and conversation-cache behavior remain the same. Only the helper and its draft/placement settings vary.

Three helpers were quantized from the SHA256-verified, revision-pinned BF16 MTP source: Q2_K (1.491 GB), Q2_0 (1.110 GB) and Q3_K_S (1.798 GB). The selected Q3 file is 35.5% smaller than the original 2.786 GB Q4 helper. Preparation receipts, compatible tensor fallbacks, inventories and hashes are saved. Helper file size is not total runtime memory: CPU repacking, target rollback state and temporary buffers also consume RAM.

The all-GPU Q2_K attempt failed on its first request with a Metal out-of-memory error. Q2_0 on GPU accepted fewer than 2% of draft tokens, slowed to 12-16 tokens/s and then failed. Both failed records stay in the scoreboard. Splitting the helper's body onto CPU and its output projection onto GPU avoided the GPU limit. Q3 split placement was faster than Q2 split or Q3 CPU-only placement. No GPU memory sysctl or engine-source patch was applied.

At greedy sampling, the selected Q3/two-token helper wrote 43.15 and 42.53 tokens/s versus 38.97 and 37.59, gains of 10.7% and 13.1%. First-token waiting grew 38-43%. At temperature 0.6, fixed-length writing changed -1.6% and -0.5%, while total response time increased 10.1% and 20.0%. These compare identical 512/2048-token synthetic prompts and fixed 128-token outputs.

Matched, cached ledger follow-ups at temperature 0.6 gave a narrower benefit: output rates rose 35.1% and 25.6%, and complete answers finished 10.1% and 3.9% sooner. The first token arrived 28.1% and 32.6% later. All 11 conversation/changed-label checks passed. This does not establish the same gain for open-ended conversation.

Selected native helper runs passed 18 focused answer checks each, including structured output and a small code function at temperatures 0 and 0.6. [Nine real app API/adapter checks](results/20261006T155222Z-flash-integration.json) passed with the selected helper active, including cancellation and disconnect recovery. [The app proof](results/20261006T155345Z-prediction-app-proof.json) binds that suite to the exact helper/placement command. Greedy timing output still diverges after token 92 on the 512-token input, while the 2048-token input matches; general exact-token equivalence is not claimed.

No additional swap grew in the selected runs, though about 1 GiB of pre-existing system swap remained. Keep the normal launcher on caching with prediction off. `Start Strata - Prediction Test.command` provides the tested optional profile; stop the current app before switching. The ordinary profile was restored after checking the helper app.

[Raw scoreboard and records](RESULTS.md)
