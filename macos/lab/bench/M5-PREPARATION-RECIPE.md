# Recreate the default launcher and the M5 diagnostic preparation

Use a fresh lab directory. Preserve existing dirty checkouts, receipts and model files. This recipe is documentation; it has not been executed in a fresh directory. Python is **3.12**. Prerequisites are native ARM64 macOS, Apple's Command Line Tools, `uv`, Git, `curl` and sufficient disk space. No login service is installed.

Everything these steps read is tracked in this repository: the scripts, `config/` (model registry, engine manifests and runtime pins), `patches/` and the Flash header inventory `bench/results/flash-gguf-inventory.json`. Engine checkouts, builds and receipts (`vendor/`), model files (`models/`) and the virtual environment stay ignored; the steps below make them.

## Default launcher chain

The blocks below, in order, are what `Start Strata.command` needs: its `balanced` profile runs Flash on the `m5-small-stack` engine with the packed shared Q3 helper. [README.md](../README.md#recreate-the-environment) lists the same commands. `tests/test_recreate_recipe.py` checks that both lists match and that each step's prerequisites, as the scripts and `config/` define them, come from an earlier step.

### Source and baseline provisioning — CPU build, no inference

From the fresh lab root:

<!-- default-profile-chain -->
```sh
uv run --python 3.12 --no-project python scripts/provision.py --jobs 1
```

`.venv/bin/python scripts/provision.py --check-only` afterwards repeats the preflight and verifies the baseline engine without changing anything.

Provisioning fetches the two exact revisions in `config/runtime.json`, creates Python 3.12, installs pinned requirements and builds baseline native tools. It now writes and verifies `vendor/llama.cpp/build/lab-receipt.json`. Existing sources must be clean at their pins and an existing venv must use Python 3.12 before any install/build mutation.

**External library policy:** the existing diagnostic uses the resolved OpenSSL **3.6.4** libraries recorded in `bench/runtime/m5-eval/build.json`, plus recorded Apple compiler/SDK versions. Keep that dependency set unchanged for comparisons; diagnostic execution checks dylib hashes. A new host needs an explicit dependency review and fresh build receipt; do not copy an old host's receipt or claim identical binaries. Full fresh-directory dependency reproduction remains pending under audit F2.

`provision.py --local-http-only` explicitly disables optional OpenSSL for a **fresh baseline build**. `prepare_shared.py`, `prepare_mma.py` and `prepare_m5.py` do not take that option; they build with the plain flags in `config/runtime.json`, so it is not the complete portable reproduction recipe yet. Do not rebuild the current measured engines with it.

### Model preparation — downloads and file transformations, no inference

These commands use disk/network bandwidth and read/write model payloads. They do not execute model/GPU inference. Do not run them during benchmarks or the current testing hold; the present Mac already has verified files.

<!-- default-profile-chain -->
```sh
.venv/bin/python scripts/download_models.py flash
.venv/bin/python scripts/download_models.py mtp_bf16
.venv/bin/python scripts/prepare_draft.py q3
.venv/bin/python scripts/prepare_shared.py --jobs 1
.venv/bin/python scripts/prepare_shared_layout.py
```

The BF16 source derives Q3; sharing removes duplicate embedding/output tensors; packing changes only tensor order. All retained tensors/metadata and registered output hashes must match. Unexpected/corrupt/partial files are preserved for review. `prepare_shared.py` also builds the `mtp-shared` engine on the CPU, before it derives the shared helper, so run `prepare_draft.py q3` first. `download_models.py` refuses derived models such as `mtp_q3`; the preparation scripts make them.

`bench/results/flash-gguf-inventory.json` is tracked, so `inspect_gguf.py flash` is not part of this chain. It reads headers only; rerunning it rewrites that tracked file, and the inventory alone is not file-integrity proof. The `small` model and the original standalone Q4 helper (`mtp`) are not required for this profile.

By registered byte count the model files in this chain total 78.5 GB, of which Flash is 66.4 GB. Budget at least **110 GiB free** for these model files, derivation intermediates and native builds; recheck actual free space before downloading. Capacity on disk is not a physical RAM budget.

### Engines for the launcher — CPU build, no inference

<!-- default-profile-chain -->
```sh
.venv/bin/python scripts/prepare_mma.py --jobs 1
.venv/bin/python scripts/prepare_m5.py --engine m5-small-stack --build --jobs 1
```

`prepare_mma.py` needs the baseline and shared-weight checkouts and builds the `mtp-mma` engine with its operation tester. `prepare_m5.py` requires verified `baseline` and `mtp-mma` build receipts, applies `patches/mtp-m5-small-stack.patch` to a fresh clone of the baseline checkout, builds `llama-server` and `test-backend-ops`, and writes a `bench/features/*-m5-preparation.json` record. Neither loads a model.

### Offline gate

<!-- default-profile-chain -->
```sh
.venv/bin/python scripts/validate_offline.py
```

Starting `Start Strata.command` after this is model/GPU work (see the hold below). The launcher checks the `m5-small-stack` source diff and build receipt, the full SHA256 of the Flash and packed-helper files (67.7 GB read on first use, then cached in `bench/runtime/model-verification.json`), free ports and at least 34 GiB of available memory. It does not re-check the baseline, `mtp-shared` or `mtp-mma` engines, but its model header check reads `vendor/llama.cpp/gguf-py`, so keep the baseline checkout.

Not yet checked in a fresh directory: whether quantization and GGUF writing reproduce the registered SHA256s on another Mac (a mismatch stops `prepare_draft.py`, `prepare_shared.py` or `prepare_shared_layout.py` and keeps the file for review), and whether the engine builds succeed without network access or without Homebrew OpenSSL (CMake only warns). The local engine checkouts were made by an older version of these scripts.

## Optional diagnostic engines — CPU compilation/self-test

```sh
.venv/bin/python scripts/prepare_m5.py --engine m5-lab --build --jobs 1
.venv/bin/python scripts/prepare_m5.py --engine m5-trace --build --jobs 1
.venv/bin/python scripts/profile_m5_routes.py --build
.venv/bin/python scripts/prepare_m5.py --engine m5-correctness --build --jobs 1
```

These need the launcher chain's baseline and MMA engines. The diagnostic requires baseline, MMA and trace receipts; unrelated optional engines are checked if already built but are not prerequisites for a clean setup. Every optional engine has a separate checkout, patch identity, build and receipt. The diagnostic links trace libraries, runs its CPU-only strided-routing self-test and five fatal-stop fixtures, and writes `bench/runtime/m5-eval/build.json`. It does not initialize a GPU backend. `m5-correctness` additionally stages the upstream fused-residual fix; its GPU reproducer remains unrun.

## Maintained offline gate and plan cards

```sh
.venv/bin/python scripts/validate_offline.py
.venv/bin/python scripts/prepare_m5_future.py --prepare
.venv/bin/python scripts/memory_budget.py
.venv/bin/python scripts/benchmark_context.py
.venv/bin/python scripts/profile_lookup_io.py
```

The gate uses the explicit `config/offline_tests.json` inventory, denies unmocked sockets/network/native subprocesses, and permits only the local Git fixture operations used by provenance tests. It excludes the real-socket integration suite and all native builds/self-tests/model/GPU work. A failed or stale source fingerprint blocks accepted card preparation. Receipt/log: `bench/features/offline-validation.json` and `.log`.

Cards go into a new `bench/plans/*-m5-future/` folder, with `not-run` result templates and no measurements. The context and lookup commands above display plans only. Accounting reads saved headers/logs. There is no automatic benchmark trigger or resume watcher.

## Model/GPU testing — held until the user's go-ahead

The staged queue is in [M5-FUTURE-TEMPLATES.md](M5-FUTURE-TEMPLATES.md) and `config/m5_future_plan.json`. Any command adding `--run` starts real work. Full model launches require a fresh quiet-host/normal-pressure check and at least **34 GiB available RAM**. Do not stop unrelated VMs or builds to meet it.

For speed claims, fresh controls bracket one candidate in control/candidate/candidate/control order; reject new swap, unhealthy monitoring, failed teardown, drifted sources/prompts or answer failures. Record TPS, first-token delay, complete reply time and control drift. Instrumented route/split timings and the 6144-token recall trial stay outside the normal TPS comparison. Quantized KV, native SSD prefetch and expert paging remain separate unimplemented candidates.
