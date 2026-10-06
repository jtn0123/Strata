# Mac source review — October 6, 2026

This source review initially selected Meld's focused Q2_0 Metal kernel change, then prediction overhead, for isolated testing. The review itself applied no inference changes. Subsequent measured work is documented separately: [Q2 Metal](Q2-METAL.md), [draft vocabulary](DRAFT-VOCAB.md) and [shared helper/layout](SHARED-HELPER.md). The source screening and external results below describe the checked October 6 revisions, not a continuing claim that those experiments are pending.

Our measured everyday baseline remains full Qwen3.8-Flash-Next GSQ-RCO Q2_0, all experts, all main-model layers on Metal, lazy SSD lookup, 4K context, batch 512, conversation caching and no prediction: about 37–39 output tokens/s. The separate prediction profile remains optional. Earlier raw benchmarks are retained.

## What was checked

Screened 1,277 public fork listings by repository name/description, then used README searches and inspected relevant source, patches and raw benchmark documentation. This is not a code audit of every fork. Two important Mac forks were found by supplementary search even though they were absent from the listing returned by GitHub. Also reviewed parent releases/issues, llama.cpp changes since our pin, and selected open/merged runtime PRs.

[Exact repository heads, checks and candidate states](research/20261006-upstream-scan.json) and [fork-list metadata](research/20261006-fork-screening.json) record the scope. External timings below are their authors' results, not measurements on Justin's Mac.

## Useful sources

| Source | Finding | Fit for this lab |
| --- | --- | --- |
| [Meld Turbo](https://github.com/MeldlabsAI/meld-turbo) | Optimized Q2 expert math, draft-vocabulary subset, shared-head branch, dense-weight conversion and GPU timing tools. Their full setup reports around 40–47 tok/s on an M2 Max with 96 GB. | Strong source of isolated engine experiments. Their recommended full setup needs 64 GB or more; its 64 GB test was simulated on a 96 GB Mac. Do not install the whole recipe on our 48 GB machine. |
| [shruxx/StrataForMac](https://github.com/shruxx/StrataForMac/blob/c57a31fe7b5dca115896b239811b592fc847197b/bench/results/2026-10-05-macos-qwen-q2_0/README.md) | Real 48 GB M5 Pro results: Q2_0 around 34 tok/s with all 49 layers on GPU and 64K context, versus 11.8 tok/s with 24 GPU layers and 128K context. | Supports our existing all-GPU choice. Longer context with carefully measured cache settings is a worthwhile separate capacity experiment. These are different workloads and runtime versions from ours. |
| [liangxiwei/Strata-for-mac](https://github.com/liangxiwei/Strata-for-mac/tree/56075e03265f7be44e65d6c9de0574eaa0b7e13d) | Actual CUDA/HIP-to-Metal engine port, including image support and long-context tests. README reports 27 Q2_0 / 29 IQ2_XS tok/s on an M2 Max with 96 GB. | A functional comparison engine and a source of kernel-parity methods, not a proven faster replacement for our llama.cpp path. Requires full Xcode/Metal tools. |
| [tierpack](https://github.com/vamzi/tierpack) | Separates GPU, expert and lookup tensors without changing tensor bytes. M3 Max 48 GB Q2_0 reports 34–36 tok/s. Larger IQ3 weights still suffered heavy paging, around 0.2 tok/s in one real-text test. | Useful for future layout/capacity work; our lookup table is already in its own lazy shard. Repacking does not supply additional physical RAM. |
| [metalfit](https://github.com/shruxx/metalfit) | Computes weight/cache budgets from GGUF headers and prioritizes fitting whole models on GPU. | Borrow architecture-aware capacity accounting as contexts grow. Its small process-footprint readings exclude the full meaning of GPU residency; do not treat a 1 GiB footprint as total model memory. |

Reviewed the popular [architectds](https://github.com/architectds/Strata), [mach10x](https://github.com/mach10x/strata), [lighttransport](https://github.com/lighttransport/Strata), and newer [Strata-Hetero](https://github.com/xdcgh/Strata-Hetero) forks as well. Their inspected default branches did not provide a direct new Metal optimization. Architectds' dual-GPU/CUDA gains are ideas to study, not settings our Metal engine understands. Strata-Hetero's default head matched the parent at the checked time; its name alone establishes no working Mac/AMD distributed path.

## Ranked experiments

1. **Sustained baseline, then Q2 expert math.** [Meld's first patch](https://github.com/MeldlabsAI/meld-turbo/blob/ef2101f5f2517204e1d755522d0b84346c4c9f0a/patches/0001-metal-Q2_0-matvec-via-masked-pre-scaled-y-one-FMA-pe.patch) changes one Metal file and reuses the existing weights. Our later numerical/answer checks passed, but confirmed writing gains were only +0.3% / +3.7%, input processing slowed, and whole replies changed little. The normal launcher keeps the original engine; the isolated candidate and measurements remain available.
2. **Reduce prediction overhead.** Investigate sharing the main model's embeddings/output head, then the [106K draft-vocabulary path](https://github.com/MeldlabsAI/meld-turbo/blob/ef2101f5f2517204e1d755522d0b84346c4c9f0a/patches/0008-qwen4exp-MTP-draft-vocabulary-subset-MELD_DRAFT_VOCA.patch). Target verification remains full-vocabulary, but limiting draft choices can affect acceptance. Test code, prose and multilingual answers at the normal sampling setting; avoid adopting an English-only vocabulary.
3. **Checkpoint changes are lower priority for our current profile.** [llama.cpp PR 28118](https://github.com/ggml-org/llama.cpp/pull/28118) remains open and removes host round trips where full recurrent-state checkpoints are taken. Source review found our two-token Qwen MTP profile already fits its two native recurrent rollback snapshots. The separate draft has no recurrent state. Those full-checkpoint call sites therefore do not establish a missing optimization in the profile we are benchmarking. Reconsider only if draft depth exceeds the available snapshots or profiling shows an actual copy.
4. **Longer context with measured memory budgets.** The M5 fork's 64K Q2 results make 16K/32K trials reasonable after speed work. We have only tested up to 8K in our own engine so far. Expand one size at a time, measuring resident allocations, swap growth, first-token time and varied-record recall. Do not import their 128K settings or raise GPU limits merely because their run loaded.
5. **Dense Q8 conversion only if headroom and profiling support it.** [Meld's measurements](https://github.com/MeldlabsAI/meld-turbo/blob/ef2101f5f2517204e1d755522d0b84346c4c9f0a/docs/PERFORMANCE.md) increased dense weights from 1.77 to 3.46 GB and helped multi-token verification, while a single-token pass became slower. This changes weight values and uses about 1.7 GB more memory; it is not our first trial on 48 GB.

Unmerged [llama.cpp PR 30047](https://github.com/ggml-org/llama.cpp/pull/30047) extends few-row kernels to Q2/BF16/IQ expert operations. Most evidence is from M3 Ultra and the path without the tensor API. Its dispatch conditions must be checked on M5; no whole-model gain should be inferred from its kernel speedups.

## Avoid duplicating work already present

Our llama.cpp v0.6.0 pin is still the latest release. GitHub ancestry checks confirmed it includes [MoE/SSM fusion](https://github.com/ggml-org/llama.cpp/pull/28948), [M5 F16 attention](https://github.com/ggml-org/llama.cpp/pull/29570), [native Qwen MTP](https://github.com/ggml-org/llama.cpp/pull/29761), and [few-row Metal kernels](https://github.com/ggml-org/llama.cpp/pull/29869). The checked source also sets Metal language version 4.0 and contains incremental QSA pooled-key caching. Do not treat old issue titles or still-open proposals as proof that these features are missing.

The reviewed master was 21 commits ahead of our pin. It includes a QSA shared-sequence data-race correction, MTP scheduler-reservation fixes, quantized-attention threadgroup memory fixes, and tensor-split RPC. Test a new runtime separately; our normal profile uses one slot and F16 cache, so some fixes address paths it does not currently exercise. RPC is a later Mac/AMD experiment, not automatically pooled memory or a speed guarantee.

Only Command Line Tools are selected here. `xcrun --find xctrace` and `xcrun --find metal` are unavailable. The current embedded-source build runs successfully without them. Kernel timing instrumentation and paired server benchmarks are available approaches; full Instruments tracing would require Xcode/toolchain installation. No toolchain was installed during this scan.

## Fork and checkpoint layout

Use a personal fork of [Niko1221/Strata](https://github.com/Niko1221/Strata), with a `mac-m5-lab` branch and the current lab under `macos/lab/`. Preserve the lab's commits and raw results through a Git subtree import. Keep source/model revision pins and the existing launchers reproducible; model files, the virtual environment and generated runtime directories stay ignored.

The parent is now v0.1.40.1; our UI/API dependency remains the tested v0.1.13-derived Mac fork. The [parent release](https://github.com/Niko1221/Strata/releases/tag/v0.1.40.1) says its history was rewritten on October 6. Start the fork from current parent history and import our lab, rather than resetting our work or trying a blind merge with old fork history.

The parent also has newer server failure/restart, browser-origin and tool-parsing fixes. Bringing these into the Mac adapter is a separate integration change with its own API checks; CUDA/HIP speed switches do not transfer directly. Keep the present server pin during the first kernel comparison.

Each subsequent experiment keeps an unchanged control, independent source/binary receipts, focused checks and identical workloads. Reports include output TPS, input throughput, first-token delay, complete reply time, swap growth and percentages against the matched control. Cache-only stays the normal profile until a candidate demonstrates an everyday benefit. Cross-session caching remains deferred.
