# Next M5 experiments

These are researched candidates, not enabled features or measured new gains. Preserve fresh matched controls, independent confirmation, normal pressure, zero new swap and exact settings/output checks. Avoid unchanged retries of rejected candidates and adding isolated percentages.

| Priority | Candidate | Main target / prerequisite |
| --- | --- | --- |
| 1 | Varied-file editing coverage | Establish the lookup benefit across disjoint Python/JS/JSON edits in fresh and warmed processes; prior-reply replay remains diagnostic. |
| 2 | Prompt-local lookup with MTP | Native ngram-simple drafts from the current prompt; retain fallback and bound proposals to3tokens, then check exact output/EOS/cancel/reuse. |
| 3 | macOS lazy-table prefetch | Measure cold-prompt and first-token time only after proving actual eligible ranges, bounded advisory reads and cache provenance. |
| 4 | Optional startup warmup | Publish startup-to-ready and first real answer separately; warming kernels can shift waiting rather than remove work. |
| 5 | Separate MLX layerwise prefill | Reduce repeated SSD expert reads on long prompts; requires precision, output compatibility and bounded-memory qualification. |
| 6 | Bounded parallel lazy-table reads | Compare with advisory prefetch independently; require file-offset/lifetime proof and low warm-case overhead. |
| 7 | Loader mapping-range audit | Our split shards already separate the lazy table from Metal mapping, so prove a foreign span exists before benchmarking. |
| 8 | Helper maintenance during lookup | Complete actual helper/server state and lifecycle equivalence before skipping catch-up work. |

[llama.cpp PR30405](https://github.com/ggml-org/llama.cpp/pull/30405) adds macOS prefetch and narrower loader mappings. Its measurements use different hardware and file layout; no speed or RAM estimate is transferred to this Mac. [strata-mlx threaded PLE reads](https://github.com/yibie/strata-mlx/commit/a52821c1c18cc7b3194d71f7cc746da425969719) and [layerwise prompt reading](https://github.com/yibie/strata-mlx/commit/6a229aed70) motivate the separate paging track, not a direct native upgrade.

New embedding-only logits allocation, unrelated-model copy removal, image-MTP compatibility, AVX2 code and parent CUDA/HIP/SYCL changes do not establish a speed improvement for this text-only arm64 profile. W02, High Power, rejected cooperative kernels and blind draft-depth increases remain parked. Downloaded GitHub metadata and detailed research snapshots stay local.
