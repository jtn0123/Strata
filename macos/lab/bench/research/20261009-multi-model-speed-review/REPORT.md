# New speed paths: multi-model research, October9,2026

**Result: there are credible new mechanisms to screen, but no new measured performance gain.** The most useful next generation-speed probes are an exact winner-only helper sampler and a guarded all-visible attention-selection shortcut. Prompt expert-route map reuse/active-tile dispatch are separate first-response-speed opportunities. Improving native streaming can reduce app overhead without changing model TPS.

Research only: no implementation/build, model load, benchmark, GPU/SSD test, process shutdown, commit or push during this pass. Existing dirty work and runtime settings were preserved. Workloads are English prose and code only; completed historical evidence remains untouched.

## Reviewers and evidence

- Two independent `gpt-6.1-sol` agents: [Metal/kernel findings](sol61-kernel-review.md), [serving/upstream findings](sol61-serving-review.md).
- One independent `gpt-6-astra` agent: [runtime findings](astra-runtime-review.md).
- Two independent `claude-opus-5-5` reviews, called programmatically through the installed Claude CLI with tools/customizations disabled and supplied source/evidence dossiers: [A raw review](opus-a-review.md), [A corrections](opus-a-adjudication.md), [A model receipt](opus-a-receipt.json); [B raw review](opus-b-review.md), [B corrections](opus-b-adjudication.md), [B model receipt](opus-b-receipt.json). Both completed successfully with Opus usage verified. These reviewers did not browse or run hardware work. Claude CLI auxiliary Haiku usage is disclosed in the receipts; it is not counted as another requested reviewer.

The43-decision/15-excluded-attempt [ledger](../../EXPERIMENT-LEDGER.md) was supplied first. Native base is d81235049384534c167caea52b85a694f6103d14 with existing local patches; actual source file hashes are in [source-pins.json](source-pins.json). Normal historical records were inspected, not rerun. Shape/topology records are not timings or execution counts.

Latest qualified256-token matched baseline: **59.482TPS code,39.931TPS English prose**. These are prior measured controls, not new measurements this turn. Preserve Q2_0 target, packed shared Q3 helper, maximum draft3, confidence0, greedy helper, target CPU sampler, current mixed placement/workers, F16KV,4096context,512batch/ubatch and already-enabled TensorAPI. No comparison with old128-token rates and no sum of hypothetical gains.

## Ranked investigation cards

Order balances distinctness, source evidence, inexpensive qualification and exactness risk; it is not a forecast of successful gains. Percentage triplets are investigator **low/base/high hypothetical scenarios**, not measurements or confidence intervals. A negative value means a regression; every card can yield zero useful gain. Planning assumption remains zero until measured. IDs below identify proposals, not executed ledger decisions.

| Order / card | Plain-language change | Metric and hypothetical low/base/high | Main limit |
| --- | --- | --- | --- |
| 1 / R02 | Pick the helper's winning token without ranking ten when probabilities are unused | Native decode TPS -0.5/+0.5/+2% | Helper is already GPU sampled; exact tie fallback and no hidden readback required |
| 2 / R01 | Skip attention-block ranking when every visible block already fits | Native decode TPS -1/+1/+3% | Prove masks/caches/finite-score predicate; preserve current sparse attention arithmetic |
| 3 / R04 | Build one expert-routing map per prompt layer instead of several | Prompt throughput -1/+1/+4%; decode0 | Scratch ownership, compatible strides and actual map cost |
| 4 / R03 | Launch only expert/token prompt tiles that contain work | Prompt throughput -3/+5/+12%; decode0 | GPU scheduling/indirect-dispatch overhead; empty groups already exit quickly |
| 5 / R05 | Avoid prompt-reuse state saves when request explicitly disables caching | Short-prompt TTFT reduction0/+3/+15%; complete256-token reply reduction0/+0.2/+1%; decode0 | Separate serialization suppression from changed prompt splits |
| 6 / R06 | Stop asking localhost to decode the entire growing answer after every token | App whole-reply reduction0/+0.5/+3%; native TPS0 | Real display/tail lag may be hidden by concurrent generation |
| 7 / R08 | Reuse helper graph/scheduler plans that alternate every cycle | Native decode TPS -1/+0.5/+2% | Rebuilds are not necessarily exposed critical-path cost |
| 8 / R07 | Replay only the accepted target prefix into the helper | Native decode TPS -3/+2/+5% | High hidden-state/KV and batch-width exactness risk |
| 9 / R09 | Keep exact Q2 prompt dequantization in cooperative registers | Prompt throughput -3/+2/+8%; decode base0 | Compiler/layout/precision/register pressure; not a new TensorAPI switch |
| 10 / R11 | Let grouped query heads share sparse K/V loads | Native decode TPS -3/0/+3% | Current masked T1-4 path is ineligible for MLX's ready no-mask q1 kernel |
| Later / R10 | Cache repeated preprocessing or preserve recurrent restart state | Current native TPS0; affected app/resume latency only | Low priority without evidence the user's workload uses these paths |

Full machine-readable mechanisms, evidence, prerequisites and gates: [candidate-cards.json](candidate-cards.json).

## Important source proofs and boundaries

### R02: a smaller helper consumer

`common/speculative.cpp:1467,1728` requests backend top10 but confidence0/non-probabilistic mode consumes candidate0. Normal logs confirm backend_sampling=1. `ggml-metal-ops.cpp:5854` uses bitonic+merges for248320x1,k10. Remove those ranking/merge operations only when the helper needs a winner and no probabilities/list. Keep target sampling unchanged.

Generic lowest-ID argmax is not equivalent to existing unstable top-k ties. Proposed unique-finite-maximum reduction must fall back to old top10 on ties/nonfinite values and preserve common-sampler state/consumer behavior. Count total head+consumer work, not argmax alone. No evidence yet that this saves enough time.

### R01: selection that becomes redundant

Stored indexer top_k2048 and pooling4 are in the model inventory. `qwen4exp.cpp:744-875` always computes query/scoring/ranking/selection-mask work. Conservative initial eligibility is padded n_pool<=512, one ordinary causal sequence and no unsupported position/sharing/sliding cases. `llama-memory-hybrid-idx.cpp:386` pads pools with an unused sentinel; token count<2048 alone is insufficient.

Retain raw/pool key writes and the original `build_attn_qsa`, n_sel and dispatch. Do not substitute dense attention. Require **by_order=false and contiguous positions** initially; rank-based duplicate positions/holes can break mask equivalence. Include fast-path eligibility in graph-reuse topology keys and test crossing the boundary on a reused graph. Complete pools/tails must yield the same visible-cell mask; signed zero, infinity/nonfinite score behavior and cache continuation crossing the budget need proof. Historical N02 plans show indexer nodes, not their actual removable time. Scope must exclude any regime where equivalence cannot be proved.

### R04/R03: prompt metadata and empty tile work

`llama-graph.cpp:2241,2254,2355` passes the same selected experts to prompt up/gate/down. `ggml-metal-ops.cpp:2890,2929` rebuilds output-local route metadata for each projection; the mapper at `kernels/mul_mm.metal:363-414` does not depend on weights/activations. Reuse only compatible mappings; independent activation scaling still runs.

Prompt dispatch at ops.cpp3009 launches ceil(T/32)*ceil(output_channels/64)*E. The kernel at mul_mm.metal536-547 returns for empty expert/token tiles. With T512,E512,top10, there are8192 expert/token tiles per channel tile but at most `floor((5120+31*512)/32)=656` useful ones. This is a combinatorial launch-count bound, **not a92% runtime prediction**. Keep each existing64x32 tile's arithmetic/order intact, generate scheduling metadata on GPU, and account for its full cost. Opus B proposes a simpler first prototype: dispatch the static proven upper bound, derive expert/tile from GPU prefix metadata and early-exit surplus groups. That avoids CPU readback and may avoid indirect-dispatch plumbing; its full overhead still needs proof. [MLX #4567](https://github.com/ml-explore/mlx/pull/4567) and [#4572](https://github.com/ml-explore/mlx/pull/4572) provide merged scheduling precedents, not compatible GGUF math or local gains.

### R05/R06: responsiveness outside decode TPS

The accepted control log executes112.571MiB context saves despite cache_prompt=false/RAMcache0;48-token prompt is split44+4. [llama #30188](https://github.com/ggml-org/llama.cpp/pull/30188) addresses this but remains an open draft. Suppressing serialization while retaining split points is the first axis; removing splits is a second arithmetic-sensitive axis. Speculative rollback and cache-enabled requests must remain correct.

NativeEngine currently emits IDs while ignoring native text, and the Python service re-decodes all accumulated IDs through /detokenize every token. This is N HTTP calls and quadratic total serialized ID traffic. Native-ready versus app-emitted timestamps are needed before claiming shorter displayed-response time.

### Higher-risk paths

Two helper graph arenas already exist, but active-arena equality blocks reuse after switching output topology. One shared scheduler still resets/reallocates, so merely keeping two graph pointers does not retain two execution plans. Full plan caching may duplicate scratch; a graph-build-only cache would retain allocation cost. Separate those mechanisms, include target tail-width changes in the census, and bound memory. A cache needs exposed CPU/GPU timeline evidence and bounded allocation lifetime; [encoded Metal graph reuse #14570](https://github.com/ggml-org/llama.cpp/pull/14570) reported no gain due overlap.

Accepted-only catch-up must use verified target hidden rows, never assume accepted helper hidden states are equivalent. D02's228th-token failure fixture is mandatory. Helper batch-width changes can still change arithmetic even with unchanged target width. MTP driver checkpoint save/restore eligibility is another prerequisite.

[Apple cooperative-input TensorOps guidance](https://developer.apple.com/videos/play/wwdc2026/330/) is relevant to exact Q2 prompts. Q2_0 is not automatically native MX, and macOS27.2/SDK27.0 metadata does not prove compiler/layout/precision compatibility. TensorAPI is already enabled. Current QSA sparse hint forces vector attention, so an off-the-shelf Tensor FlashAttention or MLX unmasked q1 GQA kernel is not eligible.

## Proposed sequential qualification

1. **Before hardware work:** static mask/visibility/cache-lifecycle proof for R01; exact winner/tie/fallback specification for R02; compatible route-map ownership proof for R04; callback-free normal-shape evidence audit. Reject incorrect premises now.
2. **First bounded generation probe:** R02 full-vocabulary unique/tie/nonfinite fixtures, then complete head+consumer timing. Stop unless removed exposed work could plausibly clear the native1% gate; preserve helper IDs/widths/state and target sampler.
3. **Second bounded generation probe:** R01 exact mask/cache/hidden/logit equivalence at padding/selection boundaries and continuation beyond the fast limit. Confirm actual removed dispatches and unchanged attention dispatch. Stop at any unhandled equivalence failure or insufficient complete-operation gain.
4. **Prompt branch:** R04 alone first; R03 alone next, including scheduling overhead. They share routing infrastructure but their percentages are not additive. Use actual T32/33/64/127/508/512 and changing/skewed routes. Target complete-block improvement gates: R04>3%, R03>10%, both above twice component drift and exact outputs.
5. **Responsiveness branch:** fake native streams for R06; explicit stateless checkpoint suppression with splitpoints preserved for R05. Test display/cancel/UTF8/event identity and cache-enabled behavior before timing. Removing prompt splits waits for independent long exactness qualification.
6. **Only after qualification:** fresh uninstrumented model comparisons. Native decode adoption remains >=1% TPS **and** whole-reply improvement on both English real workloads above respective control drift, with zero new swap and exact output/cache/continuation gates. Prompt-only or app-only gains are separately labeled and cannot be credited as decodeTPS. Use matched long-prompt/app workloads and full-reply time for those metrics.
7. R08 receives critical-path profiling before any cache implementation; stop below~2% exposed reply cost. R07 waits for state/width equivalence. R09/R11 wait for format/dispatch eligibility and meaningful component gains. Do not spend effort on cross-session cache paths without demonstrated use.

One mechanism at a time; preserve immutable baseline controls, source/build/model/settings pins, raw responses, attempts including failures, counters and memory samples. No new experiment decision was appended to the ledger because no experiment ran.

## Upstream refresh and what stays parked

Root independently verified [fork heads](fork-heads.json) and [selected PR statuses](upstream-pr-status.json). Parent remains fb58e0d (Oct8); native metal-mac remains13da722 (Oct8). No ready native Mac upgrade replaces our queue. MLX row-tile changes are merged; checkpoint policy/shared-checkpoint proposals are not.

D01 had no useful gain; D02 fixed2/adaptive remains parked after exactness failure; N01 target backend min-p remains parked without a semantic repair; N02 gather ordering removes no current handoff. No repeated worker sweeps, wide-copy/head tile sweeps, already-enabled accelerator toggle or SSD-prefetch trial without its ledger revisit evidence. Parent CPU-prefill/residency routing changes arithmetic or output and are outside this exact speed-only pass.


## October9 execution update

R02's raw-winner premise was corrected for model token suppression. W02 implements exact parallel top10: complete component8.1% quicker, full-model code+1.092%TPS/prose+0.942%, whole replies+0.959%/+0.829%; below default adoption, optional trial. R01's original guard is unreachable and numerical equivalence is unproved; the corrected synthetic qualification fixture is next, followed by exact-format cooperative-input prompt work. [Measured outcomes and retry rules](../../EXPERIMENT-LEDGER.md), [QSA qualification](../20261009-qsa-qualification.md).
