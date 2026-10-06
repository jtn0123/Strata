# Strata Mac Lab

Local, measured experiments for an Apple M5 Pro with 48 GiB unified memory. This workspace keeps Strata's existing Mac interface and uses a revision-pinned native llama.cpp Metal server behind it. All inference stays on the Mac.

## Run

From this folder:

```sh
.venv/bin/python scripts/run.py flash
```

Open **http://127.0.0.1:8095**. OpenAI-compatible clients use **http://127.0.0.1:8095/v1**; the native engine is on **http://127.0.0.1:8096/v1**. Ctrl-C stops both processes. Double-click `Start Strata.command` to launch the full model, or `Stop Strata.command` to release its memory. The normal profile uses 4K context, processing batch 512 and no MTP. To use the small development model:

```sh
.venv/bin/python scripts/run.py small
```

No login service or system-wide Python packages are installed. Native and Strata source checkouts are under `vendor/`; model files and virtual environment stay outside git.

## Recreate the environment

Prerequisites: native ARM64 macOS, Apple's Command Line Tools, Python 3 and `uv`. The build embeds Metal source for runtime compilation, so the standalone Metal compiler is not required for this initial path. This does not establish that every optional Metal 4 tensor optimization is enabled.

```sh
python3 scripts/provision.py
.venv/bin/python scripts/download_models.py small
.venv/bin/python scripts/download_models.py flash
.venv/bin/python scripts/download_models.py mtp
```

Sources, dependencies and model revisions are pinned in `config/` and `requirements.txt`. Downloads resume and verify exact byte count and SHA256 before a model becomes available. About 72 GB of model storage plus build files and 20 GiB spare disk space are needed for all three downloads.

## Test and track

```sh
.venv/bin/python scripts/benchmark.py small --label small-baseline
.venv/bin/python scripts/benchmark.py small --label small-ubatch512 --ubatch 512
.venv/bin/python scripts/benchmark.py flash --label flash-baseline
.venv/bin/python scripts/benchmark.py flash --label flash-mtp-cpu --ubatch 512 --spec draft-mtp --draft 3 --draft-placement cpu
.venv/bin/python scripts/report.py
```

Run one configuration at a time on AC power, with no downloads during speed measurements. Each run starts and stops its own engine on an unused local port. Results include exact commands, model hashes/revisions, hardware/power snapshots, load time, first-token delay, input/output token speeds, raw responses, memory/swap samples, native logs and CSV. A failed attempt also leaves a result record. Existing records are never replaced. [Scoreboard](bench/RESULTS.md).

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

The full files do not include an MTP block. The optional 2.79 GB self-contained Q4_K_M draft head is downloaded separately. The pinned upstream runtime has a qwen4exp MTP graph; its loader still requires the draft's own embeddings/output projection. Therefore this lab uses the self-contained head, not the smaller shared variant.

The GPU draft exceeded the default GPU memory budget on this Mac. A CPU draft passed the timing and two answer checks and produced 43-45 output tokens/s, versus 37-39 without it. It also added 1.85 GiB of swap and increased first-response time. It stays off in the normal profile. Greedy output diverged after token 92 in the 512-token workload, while the 2048-token workload matched exactly; do not assume bit-for-bit parity across this batch-based optimization. Raw results preserve both outputs. No system GPU memory limit was changed.

## Next steps

1. Preserve the small baseline, then load and benchmark full Q2_0 at short context with SSD lookup enabled.
2. Change one setting at a time: processing batch, MTP, then context size. Keep correctness checks and memory limits in every run.
3. Increase context only after a stable no-swap configuration. Treat higher-precision full models as separate capacity experiments.
4. Investigate two-device execution later after measuring the Mac. The AMD desktop's memory does not automatically merge with Mac unified memory; networking and GPU support must be tested separately.

The attached port plan predates native MTP support in the runtime pinned here. Avoid rebuilding those kernels or a custom draft loop until current upstream behavior has been tested. References: [Strata Mac fork](https://github.com/jinzy0623/Strata-macOS), [llama.cpp v0.6.0](https://github.com/ggml-org/llama.cpp/releases/tag/v0.6.0), [full model](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF), [draft files](https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF/tree/main/MTP).
