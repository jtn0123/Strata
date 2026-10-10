# First native/MLX English greedy-output screen

This is a correctness screen, not a speed benchmark. It compares the full-model native engine with the existing qualified MLX 6/12 GB campaign's exact capped English answer IDs. The MLX reference, runtime, dependency, source/archive and model hashes are pinned before execution. No new MLX model is loaded.

Four native requests alternate code/prose twice, using exact 44/53 input IDs, temperature zero, a temperature-only sampler and 128 output tokens. Each request disables prompt caching. Prediction helpers and speculative lookup are disabled. Native F32 KV, 512 context and 32-token batches are intentional for this screen; they do not change the normal F16 KV/4K/MTP launcher. Greedy token/finish matching is required, with divergences retained individually.

The 188-test offline gate passed before freezing. Frozen inputs and the 168-file source/config/test archive are immutable. Execution status is in result.json, which retains every attempted request, raw response, native log, memory/pressure samples and guard failure. No automatic retry or partial resume is supported.

Native admission remains 34 GiB available, with normal pressure throughout, a 1 GiB sustained floor and zero new swap. A 900-second owned-process deadline bounds the screen. Only the owned model process is stopped. This screen does not compare logits or internal state tensors and does not establish answer quality, sampled output, conversation continuation, long-context or app/API compatibility. No performance percentages, adoption or default changes follow from it.
