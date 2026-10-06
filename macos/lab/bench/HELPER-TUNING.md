# Helper depth and CPU worker tuning

October 6, 2026. Full Qwen3.8-Flash-Next GSQ-RCO Q2_0 on the 48 GiB M5 Pro. This compares the existing packed shared helper against fresh two-token/eight-worker controls. The percentages below are additional gains from that helper profile, not gains from the original prediction-off baseline or the older roughly 47 TPS result.

Later on October 6, the [few-row GPU math experiment](METAL-MMA.md) upgraded the optional writing launcher to the new `mtp-mma` engine and three predicted tokens, and the fast follow-up launcher to that engine with four tokens. The settings, recommendations and tables below describe this earlier unpatched-engine checkpoint. Its raw records remain unchanged; use `--engine mtp-shared` to reproduce it.

## Decision

Keep the ordinary launcher on conversation caching with prediction off. Keep the balanced shared helper at two predicted tokens and eight CPU workers. One token helps short writing; three helps this code test and cached replies; four gives the best longer cached-ledger result but hurts prose and Chinese writing. There is no single winning prediction depth across every workload.

- `Start Strata - Writing Test.command`: one predicted token, eight helper workers. Short writing gains are modest in English; the Chinese test improves 16.3%. Long synthetic writing is unchanged, and cached generation slows 7-8%.
- `Start Strata - Fast Follow-ups Test.command`: four predicted tokens, eight helper workers. Longer cached-ledger generation improves 17.2% and the complete reply finishes 9.2% sooner. Short cached replies vary substantially, and Chinese/prose generation slows 19%/14%.
- For the measured three-token code profile, run the original shared test launcher with `--draft 3`. Code generation improves 5.0% and the complete code reply finishes 4.2% sooner in this test.
- Six or twelve helper workers add less than 1% generation speed. Twelve improves long-input throughput 2.9%, first-token wait 2.8% and full reply time 1.6%; eight remains the default. The depth launchers have not been benchmarked with those alternate worker counts.

## Prediction depth

All values are medians from four measurements per setting/workload. Depth order is 2, 1, 3, 4, 4, 3, 1, 2. Each pass excludes one warmup and measures two repeats.

| Workload / input or history | Control: 2 TPS | 1 TPS | 3 TPS | 4 TPS |
| --- | ---: | ---: | ---: | ---: |
| chinese / 56 | 36.14 | 42.03 | 34.33 | 29.36 |
| code / 48 | 45.91 | 46.28 | 48.22 | 46.52 |
| prose / 53 | 39.89 | 40.99 | 36.58 | 34.36 |
| synthetic / 512 | 42.74 | 44.52 | 41.87 | 38.08 |
| synthetic / 2048 | 41.39 | 41.36 | 43.01 | 41.22 |
| cached-ledger / 512 | 51.45 | 47.89 | 55.34 | 54.38 |
| cached-ledger / 2048 | 48.14 | 44.32 | 54.36 | 56.41 |

Changes from the current two-token control:

| Workload / input or history | Depth | Output gain | Complete reply quicker |
| --- | ---: | ---: | ---: |
| chinese / 56 | 1 | +16.29% | +12.84% |
| chinese / 56 | 3 | -5.01% | -4.98% |
| chinese / 56 | 4 | -18.77% | -21.30% |
| code / 48 | 1 | +0.81% | +0.77% |
| code / 48 | 3 | +5.02% | +4.23% |
| code / 48 | 4 | +1.33% | +1.06% |
| prose / 53 | 1 | +2.74% | +2.34% |
| prose / 53 | 3 | -8.32% | -8.39% |
| prose / 53 | 4 | -13.88% | -14.84% |
| synthetic / 512 | 1 | +4.17% | +2.88% |
| synthetic / 512 | 3 | -2.01% | -1.83% |
| synthetic / 512 | 4 | -10.90% | -9.55% |
| synthetic / 2048 | 1 | -0.08% | -0.53% |
| synthetic / 2048 | 3 | +3.93% | +0.70% |
| synthetic / 2048 | 4 | -0.40% | -0.84% |
| cached-ledger / 512 | 1 | -6.93% | -4.43% |
| cached-ledger / 512 | 3 | +7.55% | +3.67% |
| cached-ledger / 512 | 4 | +5.69% | +2.47% |
| cached-ledger / 2048 | 1 | -7.92% | -3.81% |
| cached-ledger / 2048 | 3 | +12.93% | +7.88% |
| cached-ledger / 2048 | 4 | +17.19% | +9.18% |

The two depth control passes differ by less than 0.8% TPS on every workload. Larger depth changes allocate additional rollback state, but all eight passes complete with zero new swap and no memory-guard stops. Target weights remain fully on Metal; the helper experts remain on CPU.

[Full depth tables, first-token delay, input throughput, acceptance and all raw run links](results/20261006T211035Z-tuning-depth/COMPARISON.md). [Machine-readable depth comparison](results/20261006T211035Z-tuning-depth/comparison.json).

## Helper CPU workers

Target CPU workers stay at eight. Only the helper generation/input worker count changes. Prediction depth stays at two. Order is 8, 6, 12, 12, 6, 8, with the same excluded warmup and repeat method. These results are separate from the depth sweep.

| Workload / input or history | 8 TPS | 6 TPS | 12 TPS | 6 output gain | 12 output gain |
| --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | 36.09 | 36.27 | 36.14 | +0.50% | +0.14% |
| code / 48 | 45.64 | 46.09 | 45.82 | +0.98% | +0.38% |
| prose / 53 | 39.74 | 40.10 | 39.88 | +0.91% | +0.35% |
| synthetic / 512 | 42.88 | 43.06 | 42.95 | +0.42% | +0.16% |
| synthetic / 2048 | 41.33 | 41.64 | 41.39 | +0.73% | +0.12% |
| cached-ledger / 512 | 51.59 | 51.79 | 51.44 | +0.39% | -0.29% |
| cached-ledger / 2048 | 48.23 | 48.41 | 48.43 | +0.37% | +0.40% |

Every thread-sweep pass reports zero new swap. The largest measured TPS increase is 0.98%; these differences are small relative to ordinary run variation. [Full worker tables and raw records](results/20261006T212441Z-tuning-threads/COMPARISON.md). [Machine-readable worker comparison](results/20261006T212441Z-tuning-threads/comparison.json).

## Validation and limits

Both sweeps use the same mtp-shared source/binary receipt and byte-verified packed Q3 helper, 4K context, batch/ubatch 512, F16 cache, temperature 0.6 and target threads eight. No main weights, expert counts, vocabulary subsets, Metal kernels, or GPU memory limits change. Native logs confirm target-table borrowing. Fresh timing replies emit 128 tokens with EOS ignored; answer checks and cached replies stop normally. Prompt hashes and fixed output counts must match before percentages are calculated.

All 240 depth and 180 thread answer checks pass. They cover arithmetic, JSON, Python, labels, Chinese and cached lookup. They are focused sanity checks, not a broad quality evaluation. Changing verification batch shape can change token paths; general exact-token equivalence is not claimed. OS file cache and machine temperature are not controlled. Prior suites are not pooled here.

The app feature sweep initially reproduced a quick-restart bug: the launcher preflight checked a recently closed TCP port without the address-reuse setting used by the actual server. It reported address in use even after the server exited. The preflight now uses SO_REUSEADDR on POSIX. A real socket test fails before the fix and passes after it; a genuinely active listener is still rejected. The original failed app-start record is retained, and the failure did not occur in either speed sweep.

- [Failing-before port test](features/20261006-runtime-port-before.log), [all 26 passing-after offline checks](features/20261006-runtime-port-after.log).
- [Initial app-start failure](results/20261006T213454Z-tuning-app-3-8.json) and [original feature log](helper-tuning-app-initial.log).
- [One-token app proof](results/20261006T213637Z-tuning-app-1-8.json), [three-token app proof](results/20261006T213646Z-tuning-app-3-8.json), [four-token app proof](results/20261006T213653Z-tuning-app-4-8.json): all 27 real API checks pass after the fix, including Unicode, native/adapter parity, OpenAI/Anthropic responses, streaming/EOS, explicit unsupported requests, cancellation and disconnect recovery. Their timings are excluded from speed comparisons. All model servers stop afterward.

Colima was stopped for both benchmark sweeps. The last thread resource sample is 21:34:29 UTC; a Colima VirtualMachine process appears at 21:34:50 UTC, outside this run. Later app checks pass while the VM is active, but the one-token and three-token checks record approximately 1.74 and 0.49 GiB of new system swap. Those functional memory samples must not be described as clean benchmark memory results. The exact source of each swapped page is not isolated. New VM activity was left untouched; this work did not start or restart Colima. [Observed resource change and app memory records](features/20261006-helper-tuning-resource-change.json).

## Reproduce

Provision the pinned shared engine/helper first. The first two commands print plans without loading models. Add --run to execute a benchmark. The app feature command loads models and stops them after testing. Stop the existing model before switching profiles.

```sh
.venv/bin/python scripts/benchmark_tuning.py --axis depth
.venv/bin/python scripts/benchmark_tuning.py --axis threads
.venv/bin/python scripts/benchmark_tuning.py --axis depth --run
.venv/bin/python scripts/benchmark_tuning.py --axis threads --run
.venv/bin/python scripts/verify_helper_tuning.py
```

`--draft-threads N` changes helper workers only. The two new launchers use the measured eight-worker setting and retain active-conversation caching. Kernel and vocabulary experiments remain separate. Cross-session caching and two-device execution remain deferred.
