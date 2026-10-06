# Decisions from the first Mac experiment

October 6, 2026. Apple M5 Pro, 48 GiB, AC power, normal power mode. No GPU memory sysctl was changed. Source and model pins are in `config/`.

## Normal profile

Full Qwen3.8-Flash-Next GSQ-RCO Q2_0, all 512 experts per layer, lazy SSD lookup table, Metal, 4K context, one request at a time, processing batch 512, no MTP. `Start Strata.command` and `Stop Strata.command` launch and stop this profile.

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

## Limits and next experiment

These are local single-user timing and sanity checks, not a broad quality evaluation. Fixed-length generation ignores EOS for timing. OS file cache is uncontrolled and background applications were left running. The Mac's SSD speed was tested separately with a short uncached file test; it is not a sustained inference bandwidth guarantee.

The next useful experiment is reducing the draft's additional memory, then comparing varied real prompts and answer quality. The current runtime does not borrow a shared MTP head's embeddings/output tensors; test a runtime that supports that before writing custom kernels. Higher-precision models and the AMD desktop remain separate future capacity experiments.

[Raw scoreboard and records](RESULTS.md)
