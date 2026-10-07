# Strata on M5 Pro: independent future plan

Research review completed October 6, 2026. Requested Astra subagent: `gpt-6-astra`, xhigh reasoning; findings reviewed and synthesized by the primary agent. Hardware: M5 Pro, 18 CPU cores, 20 GPU cores, 48 GiB unified memory. This pass ran no models, benchmarks, builds or services and changed no runtime settings. This document is a research plan, not a performance result.

## Recommendation

Stop broad settings sweeps. Measure the expensive executed operation, then improve one operation with an isolated change. In parallel, decide how much longer context and better task reliability matter. Treat larger-model capacity as a separate expert-paging project with an explicit speed tradeoff.

Further speed improvement is plausible, but this research does not establish a new TPS forecast or promise 60 TPS across ordinary writing. At an illustrative 50 TPS, a 10% generation improvement saves 0.23 seconds on 128 output tokens and 2.73 seconds on 1,500 tokens. Avoiding several seconds of repeated prompt work can matter more for some requests. These are arithmetic examples, not new measurements.

## What we have actually established

The lab uses pinned llama.cpp Metal behind Strata's macOS API shell. It does not run the parent CUDA/HIP expert scheduler. It runs the full Flash-Next GSQ-RCO Q2_0 model, with the lookup shard lazy on SSD and a packed mixed CPU/GPU MTP helper. The GPU Tensor API is already enabled; the separate Neural Engine is not.

The current writing trial has measured roughly 49–50 TPS on synthetic writing, 56–57 TPS on code, 43 TPS on prose and 40 TPS on Chinese. The roughly 69 TPS cached-ledger result covers short answers and is not a long-writing rate. Ordinary prediction-off and optional writing/follow-up profiles remain separate. See [helper results](../M5-HELPER-RESULTS.md), [M5 settings](../M5-RESULTS.md) and [MMA results](../METAL-MMA.md).

[Phase diagnostics](../M5-PHASE-PROFILE.md) show main-model GPU command-buffer intervals covering 68–73% of generation wall time in four measured requests. This is not proof of arithmetic limitation, accelerator occupancy or expert-kernel time. The helper draft span includes computation and synchronization. The six paired diagnostic outputs matched; these runs were excluded from speed history.

The phase runs reached only 2.414 GiB available RAM at the minimum, with zero new swap. That is historical test headroom, not today's free RAM. Current context is 4K, with F16 cache. The focused math/API checks establish implementation correctness, not broad model quality. The original goals of longer context, normal tool calling, vision and an upstream submission remain separate work.

Research starting points: lab `760957e60688118cedf458e089871e82db8919ca`; fork `cce68f36b1f70794537e3192241ce48ef88134f2`; llama.cpp `d81235049384534c167caea52b85a694f6103d14`. The primary agent verified clean repositories before this document was added. Colima and Grafana were not touched or restarted.

## Three findings that change the next decision

**The latest routed-expert MMA proposal is not a direct decode upgrade for our workload.** [llama.cpp PR #30047](https://github.com/ggml-org/llama.cpp/pull/30047), draft head `c1d2e51` when reviewed, chooses its path by average tokens per expert. Our 4–5 verification rows and ten selected experts out of 512 give about 0.078–0.098 tokens per expert, below its roughly two-token threshold for our K dimensions. The author reports unchanged serial decoding and eight-token verification on another model. We must verify dispatch and actual expert reuse before adapting it; a custom sparse kernel remains a separate hypothesis.

**The vocabulary head deserves equal investigation with experts.** Our shared Q5_K output head has shape `[2560, 248320]`, about 416.8 MiB of weights. The current MTP graph computes it for each helper draft step. Sharing its allocation saves memory, but does not remove those calculations. A full-vocabulary kernel improvement differs from restricting draft choices. The [previous fixed subset](../DRAFT-VOCAB.md) improved synthetic generation roughly 4% versus its then-control, but slowed code/cached replies, added memory and recorded some swap. It was not tested with today's shared/MMA combination and is not a demonstrated new gain.

**A real macOS lookup-prefetch gap exists.** In the [pinned implementation](https://github.com/ggml-org/llama.cpp/blob/d81235049384534c167caea52b85a694f6103d14/src/llama-mmap.cpp#L837), `llama_prefetch()` is enabled for Linux/supported Windows, while macOS falls through to `GGML_UNUSED(mr)`. Qwen's graph supplies the known lazy lookup rows. The primary agent verified the platform guard, graph call and saved native log independently. General startup mapping advice is separate. This gap justifies investigation, but system-wide request read totals do not establish a lookup bottleneck.

## Ranked ideas

Rank reflects value, evidence and cost, not the largest hypothetical percentage. Cross-session caching is below the more relevant Mac work because Justin previously expressed limited interest in it. Conditional examples are not expected gains and must not be added together.

| Priority | Idea | Possible value and confidence | Effort and main constraint |
| --- | --- | --- | --- |
| 1 | Real-task quality, sustained generation and executed head/expert attribution | No direct TPS gain. High confidence that better evidence prevents wasted optimization. Distinguish prompt time, generation, helper work, expert reuse and output quality. | Small to medium. Instrumented timings stay outside speed comparisons. Stage-only counters cannot prove per-kernel occupancy. [Apple profiling tools](https://developer.apple.com/metal/tools/) explain the available analysis. |
| 2 | Optimize the measured GPU winner with the existing weight bytes | Medium confidence in an opportunity, low confidence in its size. If a family occupies 30% of wall time and becomes 1.5× faster, total TPS rises 11.1%; at a 10% share, only 3.45%. | High. Compare exact routed Q2_0 shapes and the full Q5_K head first. Register pressure, memory traffic and sparse reuse can erase a shader win. |
| 3 | Longer useful context: 8K first, then larger only if proven | More document/code capacity, rather than a promised TPS gain. Medium confidence in an 8K trial; 32K feasibility remains unproven here. | Medium. Measure target/helper KV, QSA, recurrent state, rollback and scratch separately. Quantized KV changes only eligible cache allocations and may affect quality. |
| 4 | Bounded macOS lazy-row/page prefetch | High confidence the source path is missing; low confidence it matters to speed. If lookup waits are 10% of wall time and half disappear, TPS improves 5.3%. Warm or overlapped reads can yield zero. | Medium. Requires file-specific fault/wait evidence. Extra resident pages compete with scarce headroom; avoid preloading the whole 26.82 GiB lookup shard. |
| 5 | Reduce measured avoidable helper work; adapt draft length to accepted tokens per time | Low to medium confidence. Removing half of a genuine 5% exclusive overhead yields only 2.56% TPS. A faster head, CPU expert path or adaptive depth must earn its cost. | Medium to high. Full-GPU helper placement already failed or became slow. The helper's wall span includes necessary work and waits; it is not all removable overhead. |
| 6 | An isolated newer-runtime branch for specific correctness/feature fixes | No credible general TPS forecast. Useful before shared-state, quantized-cache or distributed experiments. | Medium integration work. Reconcile local sharing/MMA patches and retain the exact successful control. Live upstream was 30 commits ahead of the pin during this review; that count is a snapshot. |
| 7 | Exact bounded prompt-state reuse across interruptions, if it matches actual use | No intrinsic decode gain. A hypothetical 0.3-second restore replacing 3.8 seconds of prompt processing saves 3.5 seconds. Benefit depends on reuse frequency. | Medium; optional due user preference. Preserve complete target/helper/recurrent state and model/tokenizer/source identity. Prefer bounded snapshots to unbounded RAM caching. |
| 8 | Explicit expert paging to fit larger or higher-precision models | A credible capacity direction with likely speed loss. A different Metal PoC saved 11.1 GiB while falling 38.1→27.5 TPS. This is external evidence, not our forecast. | High, likely weeks. Correct resident-slot mapping, miss handling, prefill capacity and synchronization are essential. Set a minimum acceptable TPS before developing it. |
| 9 | Use the AMD PC independently; split a model later for a demonstrated capacity need | Separate services can improve aggregate capacity. Single-answer TPS has no defensible estimate without the exact GPU, drivers and network. | Standalone validation is moderate; heterogeneous splitting is high effort. Unified memory is within the Mac, not a pool automatically shared with the PC. |

For priority 2, Apple's [macOS 27 TensorOps guidance](https://developer.apple.com/videos/play/wwdc2026/330/) offers custom dequantization directly into cooperative tensor inputs, avoiding an intermediate threadgroup-memory round trip. This is a concrete mechanism for sufficiently dense work. GGUF Q2_0/Q5_K do not become compatible with native quantized tensors just because their nominal bit widths resemble Apple's formats. Start with one selected shape and fallback path; avoid whole-model dequantized caches.

For priority 3, another [48 GB M5 Pro configuration reports longer-context operation](https://github.com/shruxx/StrataForMac/blob/c57a31fe7b5dca115896b239811b592fc847197b/bench/results/2026-10-05-macos-qwen-q2_0/README.md). That supports a controlled trial, not adoption: weights, helper, allocations and workload need matching. A configured 4K capacity is not a test with 4K input. Such a test needs additional context room for the answer.

For priority 6, relevant recent work includes [MTP scheduler reservation #30020](https://github.com/ggml-org/llama.cpp/pull/30020), [shared QSA state #29994](https://github.com/ggml-org/llama.cpp/pull/29994) and [quantized attention memory #29340](https://github.com/ggml-org/llama.cpp/pull/29340). These are reasons to evaluate a newer isolated branch when needed; they do not establish an improvement in today's single-slot/F16 profile.

For priority 7, [native server cache mechanisms](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) exist. Immediate conversation reuse is already enabled in the lab; interrupted-session or restart reuse would be additional work. Cache integrity, cancellation and restart behavior matter as much as hit speed.

For priority 8, the [Metal expert-paging proof of concept](https://github.com/ggml-org/llama.cpp/discussions/23324) uses compact slots, exact disk reads and shared-event synchronization. Its author measured lower memory and lower speed on Qwen3-30B-A3B Q6_K/M3 Pro, including overhead even when all slots were available. It provides a starting architecture, not a drop-in backend for our model. Our current SSD path pages lookup rows, not the main experts.

For priority 9, [RPC](https://github.com/ggml-org/llama.cpp/blob/master/tools/rpc/README.md) exposes remote compute capacity. [New tensor splitting #26610](https://github.com/ggml-org/llama.cpp/pull/26610) adds options, but network coordination can outweigh a small machine's contribution. Start with independent services, then evaluate supported contiguous-layer partitioning before fine-grained splitting. MLX's [JACCL documentation](https://ml-explore.github.io/mlx/build/html/usage/distributed.html) describes supported Mac connections; it does not establish that route for the Windows AMD PC.

## First three controlled experiments

1. **Build a decision baseline.** Select about 15–20 representative coding, prose, Chinese, structured-output and document-recall tasks. Keep the existing short speed suite and add naturally stopped answers plus two 30–60-second generation cases. Record task correctness, first-token delay, complete reply time, sustained TPS, accepted drafts by position, RAM/swap and actual expert reuse. Attribute executed head/expert work with supported profiling or realistic isolated measurements. Gate: usable answers and reproducible controls before optimizing.

2. **Improve one proven operation.** Compare the two recorded expert geometries, ten-expert routing, realistic reuse and actual verification rows with the full Q5_K head. Confirm the selected GPU pipeline. Use attribution and the cost fraction to choose either a sparse expert change or a dense/head dequantization change. Gate: CPU-reference math and dispatch/fallback checks pass, then the uninstrumented full application improves on intended tasks. A synthetic kernel win without application benefit is a stop.

3. **Test usefulness and latency separately.** Start with 8K F16 and the current helper, measuring real allocation and recall. Then choose bounded lazy prefetch if file-specific waits matter, or exact state reuse if repeated prompt processing matters. Review relevant runtime fixes before quantized KV/shared-state work. Gate: zero new swap, no memory guard trips, correct recall/state and a noticeable complete-task benefit. Combine candidates only after each wins separately.

Predeclare acceptance criteria before running: for example, at least 5% median complete-task improvement on the intended workload, or a substantial useful capability, with no material quality regression or recurring tail-latency/memory failure. Keep narrow gains in named optional profiles. Stop a kernel branch after two failed approaches or repeated improvements below roughly 2–3% without a clear user benefit. These are proposed research gates, not changes to existing benchmark rules.

## Watch or defer

**MLX:** Watch [text support PR #1788](https://github.com/ml-explore/mlx-lm/pull/1788), which remained open during this review. Recent discussion supersedes some older third-party bug claims. [PipeNetwork's separate implementation](https://github.com/PipeNetwork/qwen38-flash-next-mlx) documents a 106.2 GB mixed 4/8-bit build that drops MTP; it is not a comparable 48 GiB replacement. Require compatible architecture, lazy lookup, quantization, bounded memory and correct output before timing a migration.

**Separate Neural Engine:** A conversion/backend project with no demonstrated path here for the whole architecture and lazy lookup. It is not an unused performance flag. The GPU Tensor API is already on.

**Blind memory-limit increases, dense dequantization or larger quantizations:** Observed headroom is too small to assume they fit. Model capacity depends on its resident working set and precision, not advertised parameter count. Expert paging or another machine would change the architecture and tradeoffs.

**Tools and vision:** Potentially useful capabilities, but separate from TPS optimization. The current API explicitly rejects unsupported tools. Establish user-task quality before deciding whether feature work has greater value than a small speed gain.

No implementation or benchmark is scheduled by this document. The next action should be chosen from the three experiments above.
