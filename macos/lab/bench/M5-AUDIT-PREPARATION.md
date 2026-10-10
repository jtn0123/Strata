# M5 diagnostic preparation — October 7, 2026

The existing local setup is prepared for the next full-model diagnostic. OpenTaskManager's VM and local builds remain running, as requested. No further GPU/model run started after that instruction. Changes are local and uncommitted; the fork's `macos/lab` mirror has not been updated.

This batch improves the reliability of our measurements. It adds no inference optimization and establishes no new TPS gain. The earlier workload-specific rates remain the latest full-model speed evidence.

## Audit fixes

| ID | Result |
| --- | --- |
| A1 | App and benchmark commands share an exclusive model-running lock. A contention test confirms the blocked app never launches. |
| D1 | Memory monitoring starts from a prelaunch baseline, covers child teardown and rejects missing or failed telemetry. Tests cover startup swap, ignored termination, no live samples and persistent telemetry failure. |
| G2 | Every diagnostic launch rechecks available RAM, pressure and other servers. Full-model launches also require a quiet CPU window. Low-RAM, busy-host and later-launch refusal tests pass. |
| G1 | Untimed computational GPU buffers are rejected. Raw, timed and harmless untimed metadata counts are retained. |
| B2 | Native callback failures immediately exit the owned diagnostic child with code 86. Five CPU-only fatal-stop cases pass. |
| B1 | Target shards and the packed helper have observed SHA256/stat receipts and checked GGUF routing geometry. Captures include model provenance; full-model acceptance requires target and helper layer coverage. |
| B3 | Early failures and cleanup failures leave a failed capture. Original errors and cleanup errors are recorded separately, including child exit state. |
| F2, partial | Diagnostic receipts now verify linked dylib hashes, including Homebrew OpenSSL 3.6.4, plus compiler/SDK provenance. A portable dependency policy and fresh-directory recreation remain pending. |

The [original grade report](../.Codex/grade-report.md) retains its findings and marks the seven completed items. Its B− grade has not been recalculated. F1 provisioning receipts, G3 numerical-metric validation, H1 a complete recreation recipe and I1 a maintained offline gate remain open; F2 is partial.

## Verification

| Check | Observed result |
| --- | --- |
| Offline regressions | **72 tests pass**, no model/backend execution. [Log](features/20261007-m5-audit-offline.log) |
| Native CPU checks | Valid callback/strided routing checks, six invalid inputs, and **five fatal-stop cases** pass without backend initialization. [Log](features/20261007-m5-native-self-test.log) |
| Diagnostic build provenance | Source, executable, static archives and linked dylibs verify. Compiler: Apple clang 21.0.0; SDK: 27.0. [Receipt](features/20261007-m5-diagnostic-build.json) |
| Existing engines | All seven engine receipts verify; their source/binary identities remain unchanged. [Preparation receipt](features/20261007-m5-audit-preparation.json) |
| Full model files | Both Flash Q2_0 shards and the packed Q3 helper pass observed size/SHA256 checks: **67,675,439,456 bytes** scanned in 40.46 seconds. This was a bounded file-integrity scan, not a model load or SSD benchmark. [Receipt](features/20261007-m5-model-verification.json) |

The file scan used 16 MiB reads with macOS `F_NOCACHE`. Subsequent verification reuses hashes only while file identity, size, mtime and ctime match; it rereads GGUF headers and rechecks identities. File-cache state remains uncontrolled. Final monitoring/cleanup exception-path changes were tested offline after the accepted small-model smoke; they have not had another GPU/model run.

### Bounded small-model smoke

The accepted [control/split batch](features/20261007T190924Z-m5-split-batch/batch.json) used **Qwen3.5-4B-Q4_K_M**, context 2048, Tensor API enabled, greedy output, no speculative helper. Each launch made one warmup and two measured requests: input lengths 128/128/256, output lengths 4/16/16.

| Evidence | Unchanged control | Split diagnostic |
| --- | ---: | ---: |
| New swap | **0 bytes** | **0 bytes** |
| Minimum available RAM | 13.20 GiB | 13.31 GiB |
| Peak process RSS | 2.89 GiB | 2.91 GiB |
| Raw / timed GPU buffers | 82 / 82 | 43,451 / 43,451 |
| Untimed completed buffers | 0 | 0 |
| Monitor healthy / owned child stopped | Yes / Yes | Yes / Yes |

All **three paired text/token responses match**, including warmup. All 34,782 generation buffers across those three split requests are attributed to callback intervals. Splitting increases submissions and synchronization; these timings stay outside speed history. This dense 4B model establishes server/callback/attribution plumbing, not Flash expert reuse or accelerator utilization.

The [first smoke](features/20261007T190432Z-m5-split-batch/batch.json) was rejected by attribution validation despite matching outputs and zero new swap. Its graph counts included empty recurrent-state `CPY` placeholders. The pinned Metal implementation skips these empty tensors. The diagnostic now records zero-element geometry, and the parser permits only the exact extra operation counts proven by those markers; nonempty or unproven extras still fail. The second smoke passes with 3,702 proved empty-copy markers. Both runs' raw logs are retained.

## RAM cleanup and current hold

The same-user macOS MenuBarAgent was gracefully restarted after its executable, owner and system KeepAlive configuration were checked. Its observed RSS fell from **1.86 GiB to 0.03 GiB**. The first `launchctl` attempt lacked permission; ordinary same-user SIGTERM succeeded and macOS restarted the service. [Cleanup receipt](features/20261007-m5-safe-cleanup.json).

No VM, Java/Gradle worker, T3 session or other agent was stopped. Colima and Grafana were already stopped and remain stopped. Process RSS is not an exact measure of physically reclaimed memory.

Available RAM fluctuated with unrelated work: about 11–18 GiB in the final checks. The saved preparation snapshot has **18.00 GiB available**, below the full-model diagnostic's **34 GiB** gate. The gate refused without loading a model or stopping other work. Existing swap is distinct from new swap during a test.

## Next authorized test

Once the user releases testing and RAM/CPU checks pass, start with one full-model expert-route control/capture pair at depth three:

```sh
.venv/bin/python scripts/profile_m5_routes.py --mode routes --depths 3 --run
```

Require observed target/helper identity, all 48 target layers plus helper layer 48, matched output, healthy monitoring and zero new swap. Then run the bounded full-model split pair:

```sh
.venv/bin/python scripts/profile_m5_routes.py --mode split --depths 3 --run
```

Only after those diagnostics pass should depth four or a specific kernel/prefetch candidate be selected. Any speed candidate needs fresh matched controls and a separate TPS/latency comparison. The [six later experiment cards](M5-FUTURE-TEMPLATES.md) remain staged; no background trigger resumes them.

For this checkout, repeat the maintained load-free regressions with `.venv/bin/python scripts/validate_offline.py`. The explicit inventory excludes real sockets; native builds/self-tests and model/GPU commands are separate actions. See [the complete preparation recipe](M5-PREPARATION-RECIPE.md).
