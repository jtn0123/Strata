# N00: what a prompt chunk costs on the kept M5 engine

October 14, 2026. MacBook Pro M5 Pro (20 GPU cores), 48 GiB, AC power, Automatic power mode. Kept `m5-small-stack` engine with the full Qwen3.8-Flash-Next GSQ-RCO Q2_0 model (61.85 GiB file, 48 layers, 512 experts, 10 per token), packed shared Q3 MTP helper in mixed placement with eight helper CPU workers, depth 3, 4K context, F16 KV cache. No engine, kernel, weight or setting was changed. Prompts are the four balanced cases from [E05](../20261013-prompt-chunks/REPORT.md): long-retrieval (2,332 tokens), long-prose (2,346), python-client (307) and short-prose (48). Each request reads its prompt fresh and samples one token.

**Result:** this pass attributes prompt-reading time. It changes no setting and claims no speed gain.

- Every target prompt chunk encodes the same Metal operations whatever its size: 3,322 dispatches for 512 tokens and for 1,532. Cost differences between chunk sizes come from tensor shapes, not from different operations.
- Target GPU time per chunk fits **about 171 ms per chunk + 1.02 ms per token + 0.21 ms per token for every 1,000 earlier tokens**. The fit covers 13 chunk measurements from 284 to 1,532 tokens at positions 0–1,834 and is within ±3.3% of each. Larger chunks win on long prompts because they pay the per-chunk cost fewer times. With 1,536-token chunks, the long prompts take 3,335–3,348 ms of target GPU time, against 3,817–3,818 ms with 512 (12.3–12.6% less).
- **The GPU sits idle for 427–463 ms of each long prompt while the MTP helper runs its experts on the CPU.** That is 9.5–11.5% of prompt time, more than double the helper's own GPU time (175–184 ms).
- The server always reads the last 4 prompt tokens as their own chunk, so it can save a recurrent-state checkpoint there. That chunk costs 39.6–50.8 ms of GPU time: 15.3% of the 48-token prompt's target GPU time and 8.7% of the 307-token prompt's.
- The engine's launch-wide fusion counter counts each MoE-reduce fusion twice. It reports 25,312 fused nodes where the per-dispatch lines show 17,815. The per-dispatch lines are the count used here.

## Method

- **Inventory launches** (one at 512, one at 1,536): Metal graph debug level 2 at verbosity 5, plus fusion statistics. These log every encoded dispatch with its tensor types and shapes. Fusion statistics force single-thread, single-buffer encoding, so timings from these launches are not used.
- **Timing launches** in the order 512 / 1,536 / 1,536 / 512, three requests per prompt per launch. Only the engine's existing command-buffer GPU timestamps are on. Each graph is two command buffers, and this GPU timestamps only stage boundaries, so time is measured per graph (one chunk), not per kernel.
- **Requests:** `/completion` with token prompts, one output token, temperature 0, seed 1234, prompt cache off. The server must report reading the whole prompt.
- **Guards** on every launch, as in earlier campaigns:
  - 34 GiB available before loading, a 1 GiB running floor and normal memory pressure;
  - zero new swap, a quiet CPU and AC power;
  - the owned server stopped before the next launch.
- **Launch outcomes:** all six launches passed. Minimum available RAM was 1.96–3.58 GiB and peak process RSS 37.04–38.22 GiB. Swap grew by 0; the 160 MiB that existed before stayed unchanged.
- **Held first attempt:** the first inventory attempt was held at 33.7–33.9 GiB available. With the user's permission I quit System Settings and four background helpers (mediaanalysisd, NewsTag, WeatherWidget, amsengagementd); macOS restarts them on demand. The 34 GiB threshold was not lowered.

## How the server cuts a prompt into chunks

This model has recurrent layers, which cannot roll back to an earlier position, so the pinned server saves state checkpoints near the end of each prompt. Batches fill up to the batch size, but a batch also ends where `min(batch, 4 + ubatch)` or `min(batch, 4)` tokens of the prompt remain.

| Prompt | 512 profile | 1,536 profile |
| --- | --- | --- |
| long-retrieval (2,332) | 512, 512, 512, 284, 508, 4 | 796, 1,532, 4 |
| long-prose (2,346) | 512, 512, 512, 298, 508, 4 | 810, 1,532, 4 |
| python-client (307) | 303, 4 | 303, 4 |
| short-prose (48) | 44, 4 | 44, 4 |

Every one of these chunks matches a logged target graph in both inventory launches. An earlier draft of the tool assumed whole batches followed by the remainder. That assumption was wrong, and the tool now uses the server's rule.

## What one chunk encodes

From the inventory launches. The counts are the same at 512 and 1,536 except where noted.

- **Target graph:** 3,322 dispatches.
  - The first chunk of each request has 3,395: 73 more SCALE dispatches, 72 of them on the recurrent-state tensors (consistent with clearing state at position 0).
  - The 4-token chunk has 3,334.
  - The op counts for a 512-token and a 1,532-token chunk are identical.
- **Layers:**
  - 36 gated-delta-net layers at 60 dispatches each;
  - 12 attention layers (lightning indexer, top-k and flash attention) at 93 each;
  - 6 dispatches before the first layer.
- **Barriers:** 1,923–2,033 dispatches per prompt chunk (57–61%) start behind a memory barrier rather than running concurrently.
- **Fusion:** 1,023 graph nodes per chunk are fused into other dispatches (1,026 in the 4-token chunk). No node is skipped without compute.
- **Largest op groups per chunk:**
  - MUL_MAT 782, of which 481 use bf16 weights;
  - UNARY 364, SCALE 337, RMS_NORM 255, MUL 199, CPY 188;
  - MUL_MAT_ID 144: the Q2_0 expert gate, up and down matrices in each layer.
- **Helper (MTP):** two GPU graphs per chunk, 80 dispatches before its experts and 14 after. Its experts run on the CPU in between.

## What chunks cost

Median target GPU time per chunk across the timing launches. The position is the number of prompt tokens before the chunk.

| Profile | Chunk tokens | Position | Samples | Target GPU ms | ms per token | Helper GPU ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 512 | 512 | 0 | 12 | 710.2 | 1.387 | 31.8 |
| 512 | 512 | 512 | 12 | 762.5 | 1.489 | 36.2 |
| 512 | 512 | 1,024 | 12 | 821.3 | 1.604 | 40.9 |
| 512 | 284 | 1,536 | 6 | 578.4 | 2.037 | 25.3 |
| 512 | 298 | 1,536 | 6 | 591.0 | 1.983 | 26.6 |
| 512 | 508 | 1,820 | 6 | 891.6 | 1.755 | 46.9 |
| 512 | 508 | 1,834 | 6 | 889.8 | 1.752 | 47.2 |
| 1,536 | 796 | 0 | 6 | 1,056.4 | 1.327 | 50.8 |
| 1,536 | 810 | 0 | 6 | 1,043.9 | 1.289 | 51.8 |
| 1,536 | 1,532 | 796 | 6 | 2,242.0 | 1.463 | 123.2 |
| 1,536 | 1,532 | 810 | 6 | 2,244.6 | 1.465 | 123.8 |
| both | 303 | 0 | 12 | 504.9–505.4 | 1.666 | 19.2–20.9 |
| both | 44 | 0 | 12 | 218.4–219.6 | 4.96–4.99 | 4.8 |
| both | 4 | 44 | 12 | 39.6 | 9.9 | 0.7 |
| both | 4 | 303 | 12 | 48.1–48.5 | 12.0–12.1 | 0.7 |
| 512 | 4 | 2,328–2,342 | 12 | 50.8 | 12.7 | 0.9 |
| 1,536 | 4 | 2,328–2,342 | 12 | 47.5–47.9 | 11.9–12.0 | 0.9 |

The per-chunk cost does not hold for very small chunks: 4 tokens cost 40–51 ms, not 171. It is already in place by 44 tokens, where the fit gives 215.7 ms against 218.4 measured. Content also matters slightly: 796 long-retrieval tokens took 1,056 ms, while 810 long-prose tokens took 1,044 ms.

Where prompt time goes, as medians of six requests per profile:
- **Helper CPU experts** is GPU idle time between the helper's two graphs, where its CPU experts run.
- **Other gaps** is any other GPU idle time inside the request.

| Prompt | Profile | Prompt time ms | Prompt tok/s | Target GPU ms | Helper GPU ms | Helper CPU experts ms | Other gaps ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| long-retrieval | 512 | 4,486.7 | 519.8 | 3,817.3 | 182.0 | 426.7 | 42.3 |
| long-retrieval | 1,536 | 4,064.2 | 573.8 | 3,347.6 | 174.9 | 462.1 | 60.0 |
| long-prose | 512 | 4,472.1 | 524.6 | 3,818.3 | 183.7 | 428.4 | 33.9 |
| long-prose | 1,536 | 4,025.9 | 582.7 | 3,335.3 | 176.5 | 464.2 | 39.3 |
| python-client | 512 | 644.0 | 476.7 | 552.7 | 19.9 | 59.0 | 8.1 |
| python-client | 1,536 | 651.4 | 471.3 | 554.1 | 21.6 | 61.3 | 9.0 |
| short-prose | 512 | 284.2 | 168.9 | 257.9 | 5.5 | 11.1 | 6.0 |
| short-prose | 1,536 | 285.4 | 168.2 | 259.1 | 5.5 | 11.0 | 6.2 |

How much the results moved between repeated launches of the same profile:
- **512 launches (first and last):** long-retrieval went from 524.5 to 519.4 tok/s (−1.0%) and long-prose from 529.1 to 520.0 (−1.7%).
- **The two 1,536 launches:** within 0.5% of each other.
- **1,536 against 512:** reads the long prompts 10.4–11.1% faster, in line with E05. Short prompts use the same chunks in both profiles.

## Limitations

- GPU times are per graph, not per kernel. The fit describes these chunk shapes. It does not say what makes up the roughly 171 ms per-chunk cost.
- The helper-expert gap is attributed by its place in the GPU timeline. It is where the helper's CPU experts run (`--spec-draft-cpu-moe`), but CPU work was not traced directly.
- One machine with a warm file cache: launches after the first were ready in 2.1–2.3 s. These are not cold-SSD measurements.
- Prompt reading only. Generation speed was not measured.

## Next

1. **Helper experts during prompt reading:** up to 427–463 ms per long prompt with the GPU idle. Two options:
   - run the helper's next chunk alongside the target's next chunk;
   - compute the helper's prompt-batch experts on the GPU.

   Either option must keep decode speed and memory where the mixed placement put them.
2. **N01 (expert routing, isolated clone)** now has a measured target: the per-chunk cost.
   - Before porting, check whether that cost is in the expert matrices. Use a segment-timed diagnostic build: the same kernels, with command-buffer boundaries around the expert matrix and attention blocks.
3. **4-token checkpoint chunk:** 40–51 ms of GPU time per request. Before changing it, check whether the app's multi-turn prompt reuse depends on that checkpoint.

## Tool corrections in this pass

- **Prompt chunk rule:** the driver at first assumed whole batches followed by the remainder. It now uses the server's checkpoint rule, checked against every logged graph.
- **Token counts:** hidden states here are [width, 4 streams, tokens], so a graph's first norm does not give its token count. Graphs are now labelled from the chunk schedule, and each label is checked against the first dispatch's shape.
- **Fusion:** the launch-wide counter is kept as printed, but fused nodes now come from the per-dispatch `fuse N ops` lines. The pinned encoder records each MoE-reduce fusion in both the binary-op path and the MoE-reduce kernel: 833 fusions × 9 nodes = 7,497 extra nodes in the 512 launch. The vendor source stays unchanged.
- **Re-analysis:** both inventory launches were re-analysed offline from their original native logs after these fixes.

## Reproduce

Each command is a plan only until `--run` is added. Use a new output directory each time.

```sh
.venv/bin/python scripts/profile_prompt_ops.py --mode inventory --profile 512 --profile 1536 --output bench/features/<new-name> --run
.venv/bin/python scripts/profile_prompt_ops.py --mode timing --profile 512 --profile 1536 --profile 1536 --profile 512 --output bench/features/<new-name> --run
```

Native logs, per-request rows, memory samples and the inventory files stay local and ignored under `bench/features/20261014-n00/`. This report contains only aggregate numbers and synthetic workload names.
