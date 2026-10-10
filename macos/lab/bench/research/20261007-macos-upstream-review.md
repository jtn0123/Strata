# Pending M5 work and macOS upstream review — October 7, 2026

Mac support is progressing in forks. The parent maintainer explicitly excludes Apple Silicon from the official engine. Our existing M5 matrix extension has now landed upstream in llama.cpp; it is already in our experimental engine and is not a new performance gain to add.

This review ran no builds, models, GPU tests or benchmarks and changed no runtime settings. OpenTaskManager's VM/build work was left alone. The [existing preparation status](../M5-AUDIT-PREPARATION.md) remains the local testing baseline.

The subsequent [Astra source-level deep dive](20261007-astra-macos-deepdive.md) narrows the candidate list and corrects the native-port comparison below. In particular, its duplicate-recurrence optimization fixes work our llama.cpp graph already avoids. No new fork establishes a speed gain for our current configuration.

## Work waiting for testing

| Order | Work | What it will tell us |
| --- | --- | --- |
| 1 | Full Flash expert-route capture, depth three, then depth four | Whether predicted tokens actually reuse experts enough to justify a new matrix path. The completed dense 4B smoke cannot answer this. |
| 2 | Full Flash split-operation capture | Which shared matrices, attention/state operations and other GPU work deserve optimization. Capture output must match its control; instrumented timing stays outside TPS history. |
| 3 | Complete a fresh speed baseline and compare each candidate separately | Actual TPS gain, prompt/read speed, first-token delay and complete-reply time, with fresh controls and zero new swap. The prior two-launch refresh remains incomplete. |
| 4 | One targeted kernel or state/graph optimization | Whether the measured bottleneck can be improved without unexplained output changes or extra RAM pressure. No new target has been selected yet. |
| 5 | File-specific SSD lookup measurements, then bounded prefetch if justified | Whether waiting for the lazy table is significant and can be overlapped. A fast sequential SSD or aggregate disk counter does not establish this. |
| 6 | 8K context, with long-input recall and allocation checks | Useful document capacity, quality, prompt latency and memory headroom. Cache precision would be a separate follow-up. |
| 7 | Expert paging / larger or higher-precision model | A measured capacity-versus-speed tradeoff, based on hot experts, cache misses and SSD bytes per token. No larger-model download or pager exists yet. |
| Later | Mac plus the Windows/Linux AMD machine | A separate distributed-inference experiment; the two machines do not share a coherent unified-memory pool. |

Full-model commands remain gated by user authorization, at least 34 GiB available, normal memory pressure and a quiet CPU window. There is no automatic testing trigger.

## Preparation that does not need the full-model RAM budget

- Finish F1: verified baseline provisioning receipt and Python/source checks.
- Finish G3: reject NaN, infinity and invalid timing values before reporting percentage gains.
- Finish H1/I1: one complete recreation recipe and an explicit maintained offline validation command.
- Finish F2's portable dependency policy and later validate recreation in a fresh directory.
- Review, commit and mirror the recent local safeguards/results into our fork; the current fork mirror still predates them.
- Inspect candidate source and prepare isolated patches without loading a model. Startup warmup and memory accounting are useful new preparation candidates, with runtime validation held.

These remain queued; this request performed research rather than implementing another batch.

## Review coverage

GitHub reported 1,485 forks. The paginated API returned **1,458 unique public fork listings**, screened by metadata; the counts are not identical. This is not an audit of every fork's code or every branch. Targeted inspection covered eight direct forks, the parent, three related Apple inference projects and one unrelated same-name project, plus branch listings for two additional Mac-named forks. Thirteen selected source/document files and five llama.cpp PRs were refreshed.

Exact heads, dates and scope are saved in [target/source review](20261007-upstream-targets.json), [fork screening](20261007-fork-screening.json) and [branch listings](20261007-upstream-branches.json). Cached downloaded source is under ignored `bench/runtime/upstream-review/20261007/`.

## Parent repository

Current main: `d5ea7133741e67743c0e886bb426c0ce8d69cf6c`. Latest release: **v0.1.40.3**, published October 7 at 18:01 UTC. Its fixes target Intel Arc, Windows/Linux AMD, deployment and server reliability; it adds no Mac engine. The Windows AMD memory-reserve fix is relevant to the user's later 16 GB VRAM PC, not a demonstrated Mac speed improvement. [Release notes](https://github.com/Niko1221/Strata/releases/tag/v0.1.40.3).

On October 7, Niko1221 closed the Apple Silicon milestone and stated that the project has CUDA, HIP and SYCL backends, lacks a Metal backend, and treats Apple Silicon as out of scope. Closing that issue was not completion of a Mac port. [Maintainer's comment](https://github.com/Niko1221/Strata/issues/836#issuecomment-6037821451). The inspected CMake backend options agree with this position.

## Relevant forks and projects

| Project | Current evidence | Value for our setup |
| --- | --- | --- |
| [liangxiwei/Strata-for-mac](https://github.com/liangxiwei/Strata-for-mac) | Actual native Strata-to-Metal engine, with full Flash runs and numerical/state comparisons. Head `56075e0326` is unchanged since our October 6 scan. | Study resident graph execution, direct quantized kernels, avoiding repeated state updates, and prompt processing. This is a different engine, so changes require adaptation and local controls. |
| [shruxx/StrataForMac](https://github.com/shruxx/StrataForMac) | llama.cpp/Metal integration with measured 48 GB M5 Pro mapping/layer/context trials. Head `c57a31fe7b` is unchanged. | Improve capacity planning and validation in the complete app. Its large mapping/layer gain starts from partial offload; our target already uses full GPU offload and mmap. |
| [migueldevops-real/Strata-Apple-Silicon-16GB](https://github.com/migueldevops-real/Strata-Apple-Silicon-16GB) | New since the prior review: MLX backend, optional startup warmup, quantized KV, retained conversation prefix, PDF/tool/API integration and MLX memory reporting. Head `f0c54b04ef`, October 7. | Startup latency and memory-readout ideas; optionally a separate small-model MLX baseline. It explicitly does not implement the full Flash expert-cache/MTP/ngram path. |
| [jinzy0623/Strata-macOS](https://github.com/jinzy0623/Strata-macOS) | Existing small-GGUF Metal/API port. Head `2cc4153409` still matches our pinned checkout. | No new changes to import from this fork. Its installer/recovery approach remains useful for reproducible setup. |
| [shruxx/metalfit](https://github.com/shruxx/metalfit) | Related standalone tool, now at `6354857a3f`, changed from the prior scan. Reads model headers to plan full-model fit, architecture-specific KV and working-set headroom. | Better model-fit planning and an explicit policy for leaving RAM to other apps. Plans must include mapped weight pages, GPU allocations and macOS. It is not an expert-paging implementation. |
| [MeldlabsAI/meld-turbo](https://github.com/MeldlabsAI/meld-turbo) | Head `ef2101f5f2` unchanged. Existing Metal/MTP/draft-vocabulary and dense-requantization work. | Continue referencing kernel/scheduling ideas. Its dense re-encoding uses a larger memory budget and changes weights; its published hardware results do not establish a gain on our 48 GB Mac. |
| [vamzi/tierpack](https://github.com/vamzi/tierpack) | Head `bd397562c0` unchanged. Lossless file-layout work and candid 48 GB capacity tests. | File-layout and paging evidence. Its report says packing did not make larger quantizations fast on 48 GB; it is not a capacity shortcut. |

### Particularly useful native-port finding

The native Metal port reports reducing GDN commit work by avoiding a second recurrence for a one-token window. Its M2 Max/96 GB, IQ2_XS, MTP-off comparison improved warm decode from 21.78 to 22.55 tok/s while preserving the compared outputs/state. Astra's later source inspection found that our llama.cpp graph already computes output and new state once, so that specific recurrence fix is not a missing optimization here. Canonical expert-shape specialization and measured snapshot/copy costs remain research candidates. [Native port handoff](https://github.com/liangxiwei/Strata-for-mac/blob/56075e03265f7be44e65d6c9de0574eaa0b7e13d/docs/PORT_METAL/HANDOFF.md), [source-level applicability and benchmark corrections](20261007-astra-macos-deepdive.md).

The shruxx M5 report is also useful because it measures through the actual server: partial-offload results changed substantially when the surrounding app occupied RAM. Its Qwen mapping comparison reports 34 tok/s at full offload, on a 16-GPU-core M5 Pro with different context/cache settings and no tested MTP. Those rates are not comparable speed controls for our 20-GPU-core M5 Pro. [Qwen mapping measurements](https://github.com/shruxx/StrataForMac/blob/c57a31fe7b5dca115896b239811b592fc847197b/bench/results/2026-10-05-macos-qwen-q2_0/README.md).

The new MLX fork's warmup explicitly moves initial Metal compilation into startup. Its monitor exposes GPU name and MLX active/cache/peak memory, not measured accelerator utilization. Temperature, power and GPU load are unavailable in that implementation without additional tooling. [MLX backend limits and measurements](https://github.com/migueldevops-real/Strata-Apple-Silicon-16GB/blob/f0c54b04efb4e0fcd1e5a15732e8e2960145b379/docs/MACOS_MLX.md). Reusing conversation prefixes is already supported in our app; it is not a new cross-session cache gain.

Other targeted forks were mainly PC work: architectds' current `best` branch focuses on pipelined decode/lookup/CPU assist; lighttransport's `glm53f` focuses on GLM and CUDA/CPU/distributed experiments; xdcgh has storage, memory-tier and CPU-scheduler branches. These are later design references, not validated Apple engine updates. JiaJunDeng's Mac-named default head matches an older parent commit. 4EverBuilder targets an Intel Mac Pro running Linux with an NVIDIA P40. Ikaikaalika's same-name `strata` belongs to the oLLM fork network, so it was excluded from the Strata-fork conclusions.

## Fresh llama.cpp findings

| Work | Current state | Decision |
| --- | --- | --- |
| [#30065: broader few-row matrix types](https://github.com/ggml-org/llama.cpp/pull/30065) | Merged October 7, 13:49 UTC; merge `988190680d5a89fce97de3c20df2c2813731fd61`. | **Already included locally.** The fetched PR diff and `patches/metal-mma-types-upstream.patch` have identical stable patch IDs: `6e250e9eea58cfc199aec56e85daa7d3046e8fa8`. Our `m5-lab` patch includes those types/default thresholds and `m5-trace` inherits them. No second gain or duplicate application. |
| [#30047: few-row routed-expert matrix kernels](https://github.com/ggml-org/llama.cpp/pull/30047) | Still open; updated October 7 to `c1d2e51bbeca8cb1d5b0e2cd312e1a3c23bda614`. | Watch for larger expert batches. Author reports unchanged serial decode and short speculative verification. With our usual 4–5 rows, ten selected experts and 512 total, its average-density dispatch is below the new path's threshold. This is an inference from the dispatch, not a local benchmark. |
| [#28118: on-device recurrent checkpoints](https://github.com/ggml-org/llama.cpp/pull/28118) | Open, head unchanged. | Measure our checkpoint/restore cost first. AMD-reported gains are not Mac measurements; its fragmented-state limitation also needs a correctness guard before adopting. |
| [#27441: skinny-batch/split-K matrices](https://github.com/ggml-org/llama.cpp/pull/27441) | Draft/open, head unchanged. | Lower priority for this machine: its current description keeps the stock path on M5 tensor-API devices. |
| [#28699: incremental QSA pooled cache](https://github.com/ggml-org/llama.cpp/pull/28699) | Open, head unchanged. | The prior/current pinned source already has incremental pooled-key cache support. Review implementation differences before treating it as an additional improvement. |

## Recommended next use of this research

Keep the full-model route/cost diagnostics first. Then examine measured state/snapshot copies or a specific expert shape, using the native port as a reference rather than assuming its duplicate work exists here. Our graph already reuses execution graphs, and short drafts generally avoid target speculative checkpoints. Add better memory-fit accounting and optional startup warmup as separate preparation proposals. Investigate SSD prefetch only after file-specific waits justify it. The newly merged matrix patch is already present; the open routed-expert patch is not a demonstrated boost for our short verification batches. The [Astra follow-up](20261007-astra-macos-deepdive.md) also identifies the missing #30100 correctness fix and a quantized-KV prerequisite for later experiments.

No external performance figure above is a gain on this Mac. No patch, dependency update, model download or service change was applied by this review.
