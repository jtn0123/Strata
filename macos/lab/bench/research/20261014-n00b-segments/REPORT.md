# N00b: where a prompt chunk's fixed GPU cost goes

October 14, 2026. MacBook Pro M5 Pro (20 GPU cores), 48 GiB, AC power, Automatic power mode. Same model, helper, settings and prompts as [N00](../20261014-n00-prompt-ops/REPORT.md): the full Qwen3.8-Flash-Next GSQ-RCO Q2_0 model (61.85 GiB file, 48 layers, 512 experts, 10 per token), packed shared Q3 MTP helper in mixed placement with eight helper CPU workers, depth 3, 4K context, F16 KV cache, and the four balanced prompts from [E05](../20261013-prompt-chunks/REPORT.md). Each request reads its prompt fresh and samples one token.

The engine is `m5-segments`, an isolated diagnostic clone: the kept `m5-small-stack` patch plus a segment timer that is off unless `GGML_M5_LAB_SEGMENTS` is set. The kept engine and its build were not touched.

**Result:** this pass attributes prompt-reading time. It changes no setting and claims no speed gain.

- N00 measured about 171 ms of fixed GPU cost per prompt chunk. With the timer on, the fixed cost is 164.0 ms and splits into:
  - the routed expert matrices: 89.4 ms (55%);
  - the router: 42.4 ms (26%);
  - the 36 recurrent mixers: 27.9 ms (17%);
  - the 12 attention mixers: 7.5 ms (5%);
  - the expert combine: about zero (−3.0 ms).

  These fits cover 12 chunk medians of 284–1,532 tokens at positions 0–1,834. The busy-time fit is within ±4.5% of each.
- The router's fixed cost is large for its size. It is 42.4 of the router's 86.4 ms in a 512-token chunk (49%), while the router's per-token cost is only 0.079 ms.
- Per token, the recurrent mixers cost most (0.470 ms), then the experts (0.309 ms), attention (0.119 ms plus 0.205 ms per 1,000 tokens of context), the router (0.079 ms) and the combine (0.049 ms).
- The timer does not distort what it measures:
  - The segment sums are within −1.2% to +0.4% of the same engine's chunk time with the timer off, for chunks of 284 tokens and more, and within +0.6% to +3.0% for 4- and 44-token chunks.
  - The timer starts 192–193 command buffers per chunk instead of 2. In chunks of 44 tokens or more, that left at most 0.18 ms of GPU idle time per chunk between them.
  - 5 of the 24 timed 4-token chunks had 61–75 ms of GPU idle time between segments. The others had 0.13–0.16 ms. Busy time leaves idle time out, so the part times are unaffected.
  - All 48 requests returned the same token and the same top-8 probabilities for their prompt, with the timer on or off.
- With the timer off, this engine reproduces N00's kept-engine fit: 170.7 ms per chunk + 1.016 ms per token + 0.212 ms per token per 1,000 tokens of context, within ±3.4%.

## Method

- **Timer:** with `GGML_M5_LAB_SEGMENTS` set, the engine encodes each graph on one thread into one Metal command buffer per segment. Each segment's time is the GPU start-to-end time of its command buffer. A new command buffer starts at the next node that dispatches GPU work:
  - after each hyper-connection merge (`DSV4_HC_POST`);
  - at a layer's first routed expert matrix (`MUL_MAT_ID`);
  - after its `ffn_moe_down` matrix.

  Fusion and the dispatches themselves are unchanged. A new command buffer is a full barrier, so the segment sum also pays for overlap lost at each boundary. That is why each pair below compares the timer with the same engine with the timer off.
- **Parts:** a target chunk gets four segments per layer, plus an output segment when the chunk samples a token. The tool checks every segment against this pattern and refuses graphs that do not match.
  - **recurrent / attention:** the layer's gated-delta-net or attention block with its hyper-connection mix. From layer 1 on it also holds the per-layer embedding work that follows the previous layer.
  - **router:** the feed-forward hyper-connection mix, the router and the shared expert's gate and up matrices.
  - **experts:** the routed gate, up and down matrices, plus the shared expert's activation and down matrix, which the graph places between them.
  - **combine:** the weighted expert sum, the feed-forward output and the hyper-connection merge.
  - **output:** everything after the last merge. Only the final 4-token chunk samples a token here, so the fits leave the output out. That chunk's output costs 1.6 ms.
- **Launches:** timer on and off at 512, then off and on at 1,536, alternating which variant runs first. Each launch made three requests per prompt with the N00 request settings, plus the top 8 probabilities of the sampled token for the parity check.
- **Fit:** chunk GPU time = per-chunk + per-token × tokens + context term × tokens × (position + tokens / 2) / 1,000, over chunk medians of 256 tokens or more. Position + tokens / 2 is the average number of earlier tokens each token of the chunk sees. N00 used the same form.
- **Guards** on every launch, as in earlier campaigns:
  - 34 GiB available before loading, a 1 GiB running floor and normal memory pressure;
  - zero new swap, a quiet CPU and AC power;
  - the owned server stopped before the next launch.
- **Launch outcomes:** all four launches passed.
  - Minimum available RAM was 2.25–3.05 GiB and peak process RSS 37.65–38.23 GiB.
  - Swap grew by 0; the 160 MiB that existed before stayed unchanged.
  - The server was ready 2.05–2.08 s after each start (warm file cache).

## Where the fixed cost sits

Fits of segment GPU time, timer on, over the same 12 chunk medians.

| Part | Per chunk ms | Per token ms | Per token per 1,000 context ms | Max residual |
| --- | ---: | ---: | ---: | ---: |
| All parts (busy) | 164.0 | 1.026 | 0.210 | 4.5% |
| Experts | 89.4 | 0.309 | −0.005 | 4.1% |
| Router | 42.4 | 0.079 | 0.004 | 3.5% |
| Recurrent mixers | 27.9 | 0.470 | 0.005 | 8.9% |
| Attention mixers | 7.5 | 0.119 | 0.205 | 7.9% |
| Combine | −3.0 | 0.049 | 0.000 | 3.6% |
| Timer off (whole chunk) | 170.7 | 1.016 | 0.212 | 3.4% |

The parts add up to the busy fit (164.1 ms per chunk). The mixer fits are looser (±8–9%) than the others. The first chunk of each request carries 72 extra recurrent dispatches (consistent with clearing state at position 0, as in N00), which the fit does not model.

The fixed cost is 23% of a 512-token chunk's GPU time (164.0 of 708.7 ms at position 0) and 7% of a 1,532-token chunk's (164.0 of 2,246.9 ms at position 796).

## Part times by chunk

Medians of segment GPU time in ms, timer on. Samples are requests across both timer-on launches.

| Chunk tokens | Position | Samples | Busy | Recurrent | Attention | Router | Experts | Combine | Output |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1,532 | 796 | 3 | 2,246.9 | 764.5 | 682.2 | 173.4 | 553.9 | 72.9 | 0 |
| 796 | 0 | 3 | 1,059.3 | 413.3 | 167.5 | 105.1 | 336.3 | 36.8 | 0 |
| 508 | 1,834 | 3 | 891.5 | 265.0 | 276.4 | 86.7 | 241.3 | 21.9 | 0 |
| 512 | 1,024 | 6 | 818.4 | 263.2 | 203.9 | 86.5 | 242.7 | 22.0 | 0 |
| 512 | 0 | 6 | 708.7 | 259.0 | 92.6 | 86.4 | 248.6 | 22.1 | 0 |
| 303 | 0 | 6 | 507.3 | 179.6 | 57.4 | 67.7 | 190.6 | 12.3 | 0 |
| 44 | 0 | 6 | 220.8 | 73.2 | 23.3 | 47.4 | 75.4 | 1.6 | 0 |
| 4 | 44 | 6 | 40.0 | 14.2 | 5.1 | 5.8 | 12.7 | 0.7 | 1.6 |

Below 256 tokens the parts do not follow their fits. At 44 tokens the experts take 75.4 ms, less than their 89.4 ms fixed term. The recurrent and attention mixers take more than their fits.

Dispatches per chunk are the same at every chunk size and match N00's 3,322 in total:
- recurrent mixers: 1,265 (1,337 in a request's first chunk);
- attention mixers: 804;
- router: 628–629;
- experts: 433;
- combine: 192.

The sampling chunk adds 12 output dispatches.

## Timer cost and parity

Segment sum against the same engine with the timer off, by chunk (medians):

| Chunks | Timer-on sum vs timer-off chunk time |
| --- | --- |
| 284–1,532 tokens (12 chunk shapes) | −1.2% to +0.4% |
| 44 tokens | +0.9% |
| 4 tokens | +0.6% to +3.0% |

- **Parity:** 48 requests (4 prompts × 3 repeats × 4 launches) returned, per prompt, the same token and the same top-8 probabilities.
- **Wall-clock prompt speed:** the first launch of each pair was faster, whichever variant it was.

  | Pair | Long prompts, first launch (tok/s) | Long prompts, second launch (tok/s) |
  | --- | --- | --- |
  | 512 | timer on: 524.0 and 526.3 | timer off: 518.4 and 517.5 |
  | 1,536 | timer off: 576.5 and 575.7 | timer on: 562.1 and 565.7 |

  The gap is 1.1–2.6%. This order effect is larger than any wall-time cost of the timer, so this run does not measure one. GPU time is the comparison used above.

## Engine checks

- **Source:** a separate clone at the pinned revision with the kept stack's patch and the timer. The timer patch is bound by hash in `config/m5_segments_experiment.json`. The kept engine and the vendor checkout are unchanged.
- **Build:** no compiler warnings.
- **GPU math on the final build** (Tensor API on, kept tuning): 572/572 matrix checks and 16/16 fused-residual checks pass.
- **Segment path:** with the timer on, the Metal backend-op tests pass for MUL_MAT_ID (867/867), DSV4_HC_POST (9/9) and DSV4_HC_PRE (18/18).

## Held and corrected attempts

Every attempt keeps its own folder of evidence. None of them is used in the numbers above.

1. **Attempts 1–2:** held by the zero-new-swap guard, at 320 KiB and 64 KiB of swap growth during model load.
   - With the user's earlier permission I quit three background helpers (mediaanalysisd, NewsTag, WeatherWidget). macOS restarts them on demand.
   - The guard was not changed.
2. **Attempt 3:** the launch passed its memory gates, but the analysis refused 25 helper command buffers with no GPU time.
   - Cause: on prompt chunks the helper's output-head nodes carry no compute flag, so the encoder skips them. The timer still opened a command buffer for them.
   - Fix: the timer now starts segments, and counts dispatches, only at nodes that dispatch. Skipped nodes join the open segment.
   - The engine was rebuilt, and the GPU math and segment-path tests were rerun.
3. **Attempt 4:** the first launch's analysis refused target chunks with 192 segments.
   - After the attempt-3 fix, a chunk that samples no token has no output segment, which is correct.
   - The parser now accepts target chunks with or without the output segment, and leaves the output out of the fits.
4. **Fit correction after attempt 5:** the tool first fitted the context term on position alone. That ignores the earlier tokens inside the chunk, and gave the timer-off control 102.6 ms per chunk within ±7.5%.
   - The tool now uses position + tokens / 2, the form N00 used.
   - The comparison was recomputed offline from the four saved launch results. The summary keeps the first output beside it.

## Limitations

- Segment times are per command buffer, not per kernel. The router's 42.4 ms fixed cost is located to the router segment. Which dispatch in that segment carries it was not measured.
- The timer adds a full barrier at each boundary. The sums match the timer-off chunk times within −1.2% to +0.4% for large chunks, but a part's time can include waiting that the unsegmented engine overlaps with a neighbouring part.
- The 61–75 ms idle gaps in five 4-token chunks were not traced. With the timer on, one thread encodes each graph. Whether these gaps also happen with the timer off is not known, because the timer-off engine times each graph as a whole.
- Memory bandwidth was not measured. For scale only: the routed expert tensors total 31.6 GiB. Reading them once in the experts' 89.4 ms fixed term would take 380 GB/s. Whether that term is weight reading is not established.
- One machine with a warm file cache. Prompt reading only; generation speed was not measured.

## Next

1. **Helper experts during prompt reading:** the GPU still sits idle for 427–463 ms per long prompt (N00).
   - The memory-neutral option is to overlap the helper's CPU experts with the next target chunk.
   - Running them on the GPU conflicts with [L03](../../EXPERIMENT-LEDGER.md#l03--put-complete-helper-on-gpu): the full-GPU helper failed against the Metal working-set budget.
2. **Router fixed cost (42.4 ms per chunk):** split the router segment further, for example before the expert sort and before the shared expert's matrices, to find the dispatch that carries it.
3. **N01 (compact expert routing):** the experts' fixed term (89.4 ms per chunk, about 1.9 ms per layer) is the largest single item. Before porting, measure whether it is weight reading. Compact routing can only help prompt reading if it lowers that term or the 0.309 ms per-token term.

## Reproduce

Each command is a plan only until `--run` is added. Use a new output directory each time.

```sh
.venv/bin/python scripts/prepare_m5.py --engine m5-segments --build --jobs 2
.venv/bin/python scripts/verify_m5.py --engine m5-segments --tensor-api on --tuning small-reduce --run
.venv/bin/python scripts/profile_prompt_ops.py --mode segments --profile 512 --profile 1536 --output bench/features/<new-name> --run
```

Native logs, per-request rows, memory samples and the held attempts stay local and ignored under `bench/features/20261014-n00b-segments*` and `bench/features/20261014-n00b-smoke/`. This report contains only aggregate numbers and synthetic workload names.
