# Strata Mac Lab

Local, measured experiments for an Apple M5 Pro with 48 GiB unified memory. This workspace keeps Strata's existing Mac interface and uses a revision-pinned native llama.cpp Metal server behind it. All inference stays on the Mac.

## Run

From this folder:

```sh
.venv/bin/python scripts/run.py flash
```

Open **http://127.0.0.1:8095**. OpenAI-compatible clients use **http://127.0.0.1:8095/v1**; the native engine is on **http://127.0.0.1:8096/v1**. Ctrl-C stops both processes. Double-click `Start Strata.command` to launch the full model, or `Stop Strata.command` to release its memory. The normal profile uses 4K context, processing batch 512, conversation caching and no MTP. To use the small development model:

```sh
.venv/bin/python scripts/run.py small
```

Use `scripts/run.py flash --no-prompt-cache` to restore v1's uncached conversation behavior. Caching reuses the common prefix in one engine slot; switching to a different conversation may replace it. It adds no separate multi-chat RAM cache. It can change rounding and generated token choices, so semantic answer checks accompany the timing comparison.

The optional `Start Strata - Prediction Test.command` uses the measured smaller Q3 helper, with its body on CPU and output projection on GPU. Stop the current app before switching profiles. This is an experiment: at temperature 0 it wrote 11-13% faster, but at temperature 0.6 the fixed-length writing gain disappeared. Cached record-lookup replies finished 4-10% sooner, while fresh replies took longer. The normal launcher keeps prediction off. [Exact comparisons](bench/PREDICTION.md).

`Start Strata - Shared Prediction Test.command` selects the isolated shared-weight engine and packed helper layout. It removes 521 MiB of duplicated helper tables and keeps helper experts on CPU while placing small dense operations on GPU. [Sharing, layout and comparison evidence](bench/SHARED-HELPER.md) records its scope. The separate [smaller word-list experiment](bench/DRAFT-VOCAB.md) stays optional: it helps some writing generation but slows cached replies compared with the full helper.

The packed mixed comparison measured writing generation 7.7-11.6% faster and cached complete replies 7.0-11.0% sooner than the old helper. All eight passes completed 240 answer checks with no new swap; the actual Strata app passed nine API checks. Fresh long-input replies still take longer than ordinary prediction-off operation, so this is an optional workload choice and the normal launcher retains its original engine/settings.

No login service or system-wide Python packages are installed. Native and Strata source checkouts are under `vendor/`; model files and virtual environment stay outside git.

## Recreate the environment

Prerequisites: native ARM64 macOS, Apple's Command Line Tools, Python 3 and `uv`. The build embeds Metal source for runtime compilation, so the standalone Metal compiler is not required for this initial path. This does not establish that every optional Metal 4 tensor optimization is enabled.

```sh
python3 scripts/provision.py
.venv/bin/python scripts/download_models.py small
.venv/bin/python scripts/download_models.py flash
.venv/bin/python scripts/download_models.py mtp
.venv/bin/python scripts/download_models.py mtp_bf16
.venv/bin/python scripts/prepare_draft.py q3
```

Sources, dependencies and model revisions are pinned in `config/` and `requirements.txt`. Downloads resume and verify exact byte count and SHA256 before a model becomes available. The original three downloads use about 72 GB. Recreating the optional Q3 helper adds a 7.77 GB BF16 source and 1.80 GB derived file; leave another 20 GiB spare. Smaller helpers are quantized from verified BF16, not re-quantized from the compressed Q4 file. `prepare_draft.py` records source/tool pins, output SHA256 and native quantization logs. The experiments also retain Q2_K and Q2_0 variants; they are not the chosen profile.

Saved derived-model entries do not require the local files to exist already: the preparation tools regenerate missing outputs and check them against the registered byte count/SHA256 before accepting them. Recreated files preserve the registry and its original pins. Existing corrupted or unexpected partial files still require review; a mismatch is not silently re-pinned.

## Test and track

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

The [helper tuning results](bench/HELPER-TUNING.md) compare prediction depth and CPU workers against fresh controls. `Start Strata - Writing Test.command` uses one predicted token; it helped the short writing workloads, especially the Chinese test, but slowed cached replies. `Start Strata - Fast Follow-ups Test.command` uses four predicted tokens; it helped longer cached ledger replies but slowed prose and Chinese writing. The original shared launcher remains at two tokens. Stop the active model before switching launchers.

To reproduce the separate tuning sweeps, first print their plans, then add `--run` to benchmark:

```sh
.venv/bin/python scripts/benchmark_tuning.py --axis depth
.venv/bin/python scripts/benchmark_tuning.py --axis threads
# Functional app checks load the model; these timings are not speed results:
.venv/bin/python scripts/verify_helper_tuning.py
```

`--draft-threads N` changes the helper's generation and input-processing workers; the main model stays at eight CPU threads. The measured depth profiles use eight helper workers. Thread and depth gains are separate experiments and must not be added together.

## Next steps

The [October 6 parent/fork review](bench/UPSTREAM-SCAN.md) ranks specific Mac experiments and records which improvements are already in this runtime. The isolated Q2_0 Metal candidate passed 124 small GPU correctness checks and 54 full-model answer checks; six baseline/candidate benchmark passes completed. Final writing gains were +0.3% / +3.7% for short/long prompts, while input processing slowed 6-7% and full replies changed little. Background work affected earlier passes. The normal launcher keeps the original engine. [Measured results, evidence and commands](bench/Q2-METAL.md).

1. Conversation caching is implemented, benchmarked and enabled. Its matched follow-up results are in [the scoreboard](bench/RESULTS.md) and [experiment notes](bench/NOTES.md).
2. The smaller prediction helper is implemented and benchmarked. Keep it optional: its benefit depends on sampling and workload. [Prediction results](bench/PREDICTION.md).
   The later [draft vocabulary](bench/DRAFT-VOCAB.md) and [shared helper/layout](bench/SHARED-HELPER.md) experiments use independent controls and retain the normal engine.
   [Helper depth and worker tuning](bench/HELPER-TUNING.md) adds optional writing and cached-follow-up profiles.
3. Treat larger contexts and higher-precision full models as separate capacity experiments. Porting Strata's expert scheduler to Metal is a larger engineering project.
4. Investigate two-device execution later. The AMD desktop's memory does not automatically merge with Mac unified memory; networking and GPU support must be tested separately.

The attached port plan predates native MTP support in the runtime pinned here. Avoid rebuilding those kernels or a custom draft loop until current upstream behavior has been tested. References: [Strata Mac fork](https://github.com/jinzy0623/Strata-macOS), [llama.cpp v0.6.0](https://github.com/ggml-org/llama.cpp/releases/tag/v0.6.0), [full model](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF), [draft files](https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF/tree/main/MTP).
