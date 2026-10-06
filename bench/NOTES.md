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

The next useful experiment is reducing the draft's additional memory, then comparing varied real prompts and answer quality. The current runtime does not borrow a shared MTP head's embeddings/output tensors; test a runtime that supports that before writing custom kernels. Higher-precision models and the AMD desktop remain separate future capacity experiments.

[Raw scoreboard and records](RESULTS.md)
