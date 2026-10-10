# Strata Mac Lab

Local, measured experiments for an Apple M5 Pro with 48 GiB unified memory. This workspace keeps Strata's existing Mac interface and uses a revision-pinned native llama.cpp Metal server behind it. All inference stays on the Mac.

Latest: [P07 is validated and installed in the normal launcher](bench/results/20261010-small-gains-stack/REPORT.md). Its prior independent confirmation adds +0.61% code/+0.79% prose generation over the direct-copy profile. New longer-prompt and 32-token answer safety checks pass; 12 full-model launches, 312 answer/cache checks and 192 exact output signatures have zero new swap. The actual Strata API passes 16 English answer checks plus streaming and clean shutdown. W02 adds +0.58–0.71% TPS but exceeds the declared 10 ms startup ceiling on prose, so stacking remains untested. Double-click `Start Strata.command` for P07; `Start Strata - Original Baseline.command` restores the earlier profile. No model server is left running.

Current measured short-prompt/256-output result: **60.08 TPS English code / 40.38 TPS English prose**. Longer-prompt safety results are a separate workload. [October 10 upstream and fork refresh](bench/research/20261010-upstream-refresh/REPORT.md) screens 1,811 public fork listings and records seven future investigations. The new full-model MLX engine is the strongest source lead; its 128 GB M4 measurements and F16 numerical changes are not a verified upgrade for this 48 GiB M5. [Next queue and prerequisites](bench/research/20261010-upstream-refresh/NEXT-EXPERIMENTS.json). No new model benchmark ran during that review.

[Next sequential tests are prepared and held](bench/results/20261010-next-tests/README.md): an opt-in bounded input cache on the existing 4B model, then a private sixteen-row expert prompt-tile screen. Both have [fresh v2 frozen campaigns](bench/results/20261010-next-tests-v2/README.md), exact-output/resource gates and empty metrics. 177 offline tests pass and all 28 native build receipts verify. MLX source/dependencies are isolated and installed; its supervised memory/device pilot is still pending. The ordinary launcher enables neither new candidate. No model/GPU benchmark ran during preparation.

Earlier pass: [actual draft-cap early stopping and fixed two guesses](bench/results/20261009-draftcap/REPORT.md) are complete. The tail repair removes discarded helper work but has no useful measured gain: code59.482→59.464TPS (-0.030%), English prose39.931→40.007 (+0.191%), both below control drift. Fixed two passes short checks but changes the228th token in a longer English writing fixture and is parked; no controller added. All attempted launches have zero new swap;121 load-free checks pass,21 engine receipts validate and all20 preexisting engines/ordinary launcher defaults remain unchanged. Future benchmarks and native diagnostic prompts use English prose and code only. [Decisions and retry conditions](bench/EXPERIMENT-LEDGER.md), [remaining queue](bench/research/20261009-astra-future-queue.md).

[The first M5 measurements are complete](bench/M5-RESULTS.md). Twenty full-model benchmark passes record zero swap growth. Keep Tensor API enabled and writing at depth three. Depth six raises the short cached-ledger result from 68.98 to 75.50 TPS (+9.44%) over a fresh depth-four control, with complete replies 4.88% quicker; long cached replies are essentially tied and fresh writing is slower.

The subsequent [M5 GPU tuning batch](bench/M5-GPU-TUNING.md) completes another 24 passes with zero new swap: two-tile limits add only +0.39% code TPS and about +0.59% synthetic TPS; threshold and worker overrides do not help.

The [helper/confidence batch](bench/M5-HELPER-RESULTS.md) completes all twelve comparisons: twelve helper workers add +0.94% code TPS and finish the long fresh-input reply 2.21% sooner; confidence 0.4 adds +1.83% on one prose prompt but regresses other tasks. Both have separate optional launchers; existing defaults remain. The [M5 plan](bench/M5-NEXT.md) records the completed tests and next diagnostics. `M5 Experiment Plan.command` displays the plan without starting inference. The [phase/shape diagnostic](bench/M5-PHASE-PROFILE.md) separates prompt and generation: main-model GPU-buffer intervals cover 68-73% of generation wall time on four diagnostic requests. All matched control/trace outputs agree, and the six prior engines remain unchanged.

The [expert/output-table measurement](bench/M5-OPERATION-PROFILE.md) passes 23 full-size CPU-reference checks and measures 5520 matrix buffers. Expert math is the larger tested matrix family, but the selected operations project to only 34-42% of the recorded main GPU interval. Actual expert reuse and the remaining work need evidence before choosing a shader. One clean unchanged writing launch measures 47.6-48.9 synthetic TPS and 54.2 code TPS; the second launch is excluded for 60.3 MiB new swap during overlapping build activity. This is an incomplete baseline refresh and no new speed gain. All seven engines and launchers remain unchanged. The [Astra research plan](bench/research/20261006-astra-future-plan.md) records later candidates.

[Six future experiment templates](bench/M5-FUTURE-TEMPLATES.md) are prepared: expert reuse, broader GPU timing, 8K context, bounded Mac SSD prefetch, one measured GPU kernel and larger-model paging. The [October 7 preparation update](bench/M5-AUDIT-PREPARATION.md) adds launch/monitor/provenance safeguards, 72 passing offline tests and a bounded 4B split smoke with three matching response pairs and zero new swap. Full Flash routing/split behavior remains untested; full-model testing waits while OpenTaskManager's VM and builds continue. Later templates label remaining implementation work. Empty result sheets track matched TPS/latency percentages, quality and memory. No background trigger resumes testing.

## Run

From this folder:

```sh
"./Start Strata.command"
```

Open **http://127.0.0.1:8095**. OpenAI-compatible clients use **http://127.0.0.1:8095/v1**; the native engine is on **http://127.0.0.1:8096/v1**. Ctrl-C stops both processes. Double-click `Start Strata.command` to launch the full model, or `Stop Strata.command` to release its memory. The normal no-argument launcher uses P07 with the packed shared Q3 helper, depth-three MTP, mixed placement, eight helper CPU workers, Tensor API enabled, F16 KV, 4K context, processing batch 512 and conversation caching. Explicit arguments retain the generic `scripts/run.py` behavior. The rollback launcher retains the original prediction-off profile. To use the small development model:

```sh
.venv/bin/python scripts/run.py small
```

Use `scripts/run.py flash --no-prompt-cache` to restore v1's uncached conversation behavior. Caching reuses the common prefix in one engine slot; switching to a different conversation may replace it. It adds no separate multi-chat RAM cache. It can change rounding and generated token choices, so semantic answer checks accompany the timing comparison.

The optional `Start Strata - Prediction Test.command` uses the measured smaller Q3 helper, with its body on CPU and output projection on GPU. Stop the current app before switching profiles. This is an experiment: at temperature 0 it wrote 11-13% faster, but at temperature 0.6 the fixed-length writing gain disappeared. Cached record-lookup replies finished 4-10% sooner, while fresh replies took longer. The current normal-launcher validation is recorded above. [Exact comparisons](bench/PREDICTION.md).

`Start Strata - Shared Prediction Test.command` selects the isolated shared-weight engine and packed helper layout. It removes 521 MiB of duplicated helper tables and keeps helper experts on CPU while placing small dense operations on GPU. [Sharing, layout and comparison evidence](bench/SHARED-HELPER.md) records its scope. The separate [smaller word-list experiment](bench/DRAFT-VOCAB.md) stays optional: it helps some writing generation but slows cached replies compared with the full helper.

The packed mixed comparison measured writing generation 7.7-11.6% faster and cached complete replies 7.0-11.0% sooner than the old helper. All eight passes completed 240 answer checks with no new swap; the actual Strata app passed nine API checks. Fresh long-input replies still take longer than ordinary prediction-off operation, which is a limitation of those historical comparisons; the current normal-launcher configuration has separate validation above.

No login service or system-wide Python packages are installed. Native and Strata source checkouts are under `vendor/`; model files and virtual environment stay outside git.

## Recreate the environment

For the complete optional M5 engine/helper/diagnostic chain, use [the ordered preparation recipe](bench/M5-PREPARATION-RECIPE.md). It distinguishes CPU builds and saved-data checks from model/GPU execution, and documents the current external-library policy and remaining fresh-directory validation.

Prerequisites: native ARM64 macOS, Apple's Command Line Tools, Python 3 and `uv`. The build embeds Metal source for runtime compilation, so the standalone Metal compiler is not required for this initial path. This does not establish that every optional Metal 4 tensor optimization is enabled.

```sh
uv run --python 3.12 --no-project python scripts/provision.py --jobs 1
.venv/bin/python scripts/download_models.py small
.venv/bin/python scripts/download_models.py flash
.venv/bin/python scripts/download_models.py mtp
.venv/bin/python scripts/download_models.py mtp_bf16
.venv/bin/python scripts/prepare_draft.py q3
```

Sources, dependencies and model revisions are pinned in `config/` and `requirements.txt`. Downloads resume and verify exact byte count and SHA256 before a model becomes available. The original three downloads use about 72 GB. Recreating the optional Q3 helper adds a 7.77 GB BF16 source and 1.80 GB derived file; leave another 20 GiB spare. Smaller helpers are quantized from verified BF16, not re-quantized from the compressed Q4 file. `prepare_draft.py` records source/tool pins, output SHA256 and native quantization logs. The experiments also retain Q2_K and Q2_0 variants; they are not the chosen profile.

Saved derived-model entries do not require the local files to exist already: the preparation tools regenerate missing outputs and check them against the registered byte count/SHA256 before accepting them. Recreated files preserve the registry and its original pins. Existing corrupted or unexpected partial files still require review; a mismatch is not silently re-pinned.

## Test and track

Before proposing or rerunning a speed experiment, read the [experiment decision ledger](bench/EXPERIMENT-LEDGER.md). It records settings, matched results, accuracy and memory evidence, rejection reasons and specific revisit conditions, including older failed helper layouts and interrupted runs. [Machine-readable index](bench/experiment-ledger.json). New results append to this history; previous failures stay preserved.

```sh
.venv/bin/python scripts/benchmark.py small --label small-baseline
.venv/bin/python scripts/benchmark.py small --label small-ubatch512 --ubatch 512
.venv/bin/python scripts/benchmark.py flash --label flash-baseline
.venv/bin/python scripts/benchmark.py flash --label flash-mtp-cpu --ubatch 512 --spec draft-mtp --draft 3 --draft-placement cpu
.venv/bin/python scripts/benchmark_cache.py flash
.venv/bin/python scripts/benchmark.py flash --label prediction-q3 --ubatch 512 --spec draft-mtp --draft-model mtp_q3 --draft 2 --draft-placement output --extended-checks
.venv/bin/python scripts/report.py
```

Run one configuration at a time on AC power, with no downloads during speed measurements. Each run starts and stops its own engine on an unused local port. Results include exact commands, model hashes/revisions, hardware/power snapshots, load time, first-token delay, input/output token speeds, raw responses, memory/swap samples, native logs and CSV. A failed attempt also leaves a result record. Existing records are never replaced. [Scoreboard](bench/RESULTS.md).

Stop the web app with `Stop Strata.command` before benchmarking. The conversation benchmark refuses to start a second lab model. It compares caching off and on through the real adapter, using identical follow-up prompts. It alternates pair order, excludes warm-up pairs, checks ledger recall and changed/new conversations, and records percentage changes. Its baseline uses the same working v1 settings: full Metal, 4K context, batch 512, F16 cache and no MTP. These results are separate from the synthetic fresh-prompt benchmark, which continues to disable prompt reuse.

With the web app running, verify the real API and adapter:

```sh
.venv/bin/python scripts/verify_integration.py
# With Flash-Next running instead:
.venv/bin/python scripts/verify_integration.py --model flash
```

Checks cover greedy native/adapter token parity, Unicode, streaming, OpenAI and Anthropic answers, EOS, overflow rejection, cancellation and disconnect recovery. Text chat is the verified interface scope. Tool calls and vision require their own validation and are rejected by this adapter.

## Why the full model can exceed RAM on disk

The selected full Flash-Next Q2_0 files contain 37.6 GB of model weights and a separate 28.8 GB lookup table. The table is read lazily from SSD; the entire 66.4 GB download does not need to stay in RAM. That does not make SSD equivalent to RAM: model weights, working buffers, context and macOS still need memory. [Header inventory](bench/results/flash-gguf-inventory.json).

This experiment preserves all 512 experts per layer in the selected compressed model. It does not use the separate Coder variant that drops experts. It also does not port the upstream CUDA expert scheduler: Metal reads resident weights through unified memory, while the existing lazy lookup path uses SSD.

The full files do not include an MTP block. The original optional 2.79 GB self-contained Q4_K_M draft head is downloaded separately; the selected Q3 helper is 1.80 GB. The untouched pinned runtime requires the helper's own embeddings/output projection. A separate weight-sharing build now tests borrowing these tables from the main model; it does not change the normal engine.

The original self-contained Q4 GPU draft exceeded the default GPU memory budget on this Mac. Its CPU variant produced 43-45 output tokens/s but added 1.85 GiB of swap and longer startup. The later selected Q3 split profile avoided new swap; its measured tradeoffs are in [PREDICTION.md](bench/PREDICTION.md). No system GPU memory limit was changed.

## Isolated prediction experiments

Build and prepare without loading the main model:

```sh
.venv/bin/python scripts/prepare_vocab.py --jobs 2
.venv/bin/python scripts/prepare_shared.py --jobs 2
.venv/bin/python scripts/prepare_shared_layout.py
```

The vocabulary build keeps a multilingual 106K helper word list, while the main model still verifies against all 248K tokens. The compact head adds about 111.5 MiB and is explicitly marked as weights so a CPU helper body can retain GPU output placement. The sharing build derives a helper with two duplicated tables removed, validates every retained byte, and borrows the main model's existing tables. It keeps its own conversation state. The layout preparation groups CPU experts ahead of GPU dense tensors, reducing the mixed helper's mapped GPU-weight span from 1,183 MiB to 45.6 MiB without changing its weights. Each engine uses a separate checkout, binary, source hash and build receipt.

The comparison commands below print a RAM snapshot and plan without loading models. Add `--run` to execute them. Feature checks do load the full model and terminate it afterward.

```sh
.venv/bin/python scripts/verify_vocab.py
.venv/bin/python scripts/benchmark_vocab.py --predict 128
.venv/bin/python scripts/verify_shared.py --mixed-only
.venv/bin/python scripts/benchmark_shared.py --include-mixed
```

To manually try the compact vocabulary in the web app, after stopping the current model:

```sh
.venv/bin/python scripts/run.py flash --engine draft-vocab --draft-vocab 106k --spec draft-mtp --draft-model mtp_q3 --draft 2 --draft-placement output
```

Full-GPU helper placement failed at batch 512 and was very slow at batch 128. It is not the recommended path. The mixed profile keeps helper expert tables on CPU and disables automatic CPU-op offload. Cross-session caching remains deferred.

To run the packed mixed profile manually:

```sh
.venv/bin/python scripts/run.py flash --engine mtp-shared --spec draft-mtp --draft-model mtp_shared_packed_q3 --draft 2 --draft-placement mixed
```

The [helper tuning results](bench/HELPER-TUNING.md) compare prediction depth and CPU workers against fresh controls in the earlier shared engine. The later [few-row GPU math comparison](bench/METAL-MMA.md) upgraded the optional writing launcher to the `mtp-mma` engine and three predicted tokens: about 49 TPS for synthetic writing and 56 TPS for code. The fast follow-up launcher uses that engine with four predicted tokens: about 69 TPS on the longer cached-ledger test. At that earlier checkpoint the ordinary launcher retained prediction off; it now selects the P07 profile described above. The original shared launcher remains at two tokens. Stop the active model before switching launchers.

`Start Strata - Short Structured Follow-ups Test.command` is an optional depth-six trial for short cached structured answers. It passed nine real API checks. Its 75.50 TPS result comes from 25-token ledger answers with 512 tokens of cached history; it is not a general chat or writing rate. The ordinary, writing and existing fast-follow-up launchers keep their settings. [Matched comparisons and limits](bench/M5-RESULTS.md).

`Start Strata - M5 Two-Tile Trial.command` is a separate optional depth-three writing trial using the isolated engine. Its matched code result is 56.46 to 56.68 TPS (+0.39%); synthetic generation improves about +0.59%. It passed nine real API check groups. The gain is small, so existing launchers keep their settings. [GPU tuning results](bench/M5-GPU-TUNING.md).

`Start Strata - Twelve Helper Workers Trial.command` and `Start Strata - Prose Confidence Trial.command` expose separate depth-three trials using the current `mtp-mma` engine. Each passed nine real API check groups with zero new swap. Their settings have not been tested together or combined with other trials. [Matched results and interruption history](bench/M5-HELPER-RESULTS.md).

To reproduce the separate tuning sweeps, first print their plans, then add `--run` to benchmark:

```sh
.venv/bin/python scripts/benchmark_tuning.py --axis depth
.venv/bin/python scripts/benchmark_tuning.py --axis threads
# Functional app checks load the model; these timings are not speed results:
.venv/bin/python scripts/verify_helper_tuning.py
```

`--draft-threads N` changes the helper's generation and input-processing workers; the main model stays at eight CPU threads. The measured depth profiles use eight helper workers. Thread and depth gains are separate experiments and must not be added together.

The separate few-row dense Metal experiment combines the existing shared helper with the pinned patch from llama.cpp PR #30065. It uses the same model/helper files and its own native build. Preparation compiles code without loading weights; math checks use synthetic tensors. The trace and app checks load the full model. The comparison prints its plan unless `--run` is supplied.

```sh
.venv/bin/python scripts/prepare_mma.py --jobs 2
.venv/bin/python scripts/verify_mma.py
.venv/bin/python scripts/trace_mma.py
.venv/bin/python scripts/benchmark_mma.py
.venv/bin/python scripts/verify_helper_tuning.py --engine mtp-mma
```

The writing upgrade improves short synthetic generation 11.5% over this suite's freshly remeasured prior one-token profile; it changes both the kernel and prediction depth. The kernel alone improves three-token writing/code roughly 17%. The four-token cached comparison improves output speed 20.0% and complete reply time 11.1%. Twelve speed passes pass 360 answer checks with zero new swap; all 27 real app checks and 1,076 synthetic GPU math checks pass. These are focused checks, not a broad model-quality evaluation. [Full measurements and limits](bench/METAL-MMA.md).

## Next steps

The [October 6 parent/fork review](bench/UPSTREAM-SCAN.md) ranks specific Mac experiments and records which improvements are already in this runtime. The isolated Q2_0 Metal candidate passed 124 small GPU correctness checks and 54 full-model answer checks; six baseline/candidate benchmark passes completed. Final writing gains were +0.3% / +3.7% for short/long prompts, while input processing slowed 6-7% and full replies changed little. Background work affected earlier passes. The normal launcher keeps the original engine. [Measured results, evidence and commands](bench/Q2-METAL.md).

1. Conversation caching is implemented, benchmarked and enabled. Its matched follow-up results are in [the scoreboard](bench/RESULTS.md) and [experiment notes](bench/NOTES.md).
2. The smaller prediction helper is implemented and benchmarked. Keep it optional: its benefit depends on sampling and workload. [Prediction results](bench/PREDICTION.md).
   The later [draft vocabulary](bench/DRAFT-VOCAB.md) and [shared helper/layout](bench/SHARED-HELPER.md) experiments use independent controls and retain the normal engine.
   [Helper depth and worker tuning](bench/HELPER-TUNING.md) adds optional writing and cached-follow-up profiles.
3. Treat larger contexts and higher-precision full models as separate capacity experiments. Porting Strata's expert scheduler to Metal is a larger engineering project.
4. Investigate two-device execution later. The AMD desktop's memory does not automatically merge with Mac unified memory; networking and GPU support must be tested separately.

The attached port plan predates native MTP support in the runtime pinned here. Avoid rebuilding those kernels or a custom draft loop until current upstream behavior has been tested. References: [Strata Mac fork](https://github.com/jinzy0623/Strata-macOS), [llama.cpp v0.6.0](https://github.com/ggml-org/llama.cpp/releases/tag/v0.6.0), [full model](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF), [draft files](https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF/tree/main/MTP).
