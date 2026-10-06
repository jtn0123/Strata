# Shared prediction helper and Metal layout

This experiment removes two duplicated helper tables and borrows the main model's existing tables. The derived helper shrinks from 1,797,864,960 to 1,251,560,832 bytes: 546,304,128 bytes (521.0 MiB, 30.4%) less duplicated weight data. All 32 retained tensors and metadata are verified unchanged. The full main model and its 512 experts per layer stay intact. This is useful headroom, not enough by itself to move to a substantially larger full model.

The draft retains its own conversation state. Only weight tensors are borrowed; target ownership and lifetime stay with the main model. The borrowed output uses the target's Q5_K precision rather than the old helper's Q3_K, so proposal accuracy and acceptance can change. This comparison tests that complete sharing change rather than claiming a pure allocation-only speed improvement.

## Measured speed and response time

Keep the packed mixed profile optional. Compared with the old helper, it writes 7.7-11.6% faster on the synthetic writing workloads, processes those inputs 9.8-15.7% faster, and finishes cached ledger replies 7.0-11.0% sooner. Code generation changes only +0.7% versus the old helper; that small difference is not a persuasive additional code-speed gain. The main improvement there is the helper memory saving.

Against ordinary prediction-off operation, the mixed profile improves generation 8.2-9.8% on writing, 14.1% on code and 28.3-36.6% on cached ledger replies. Most of the code/cached generation improvement already existed with the old helper. Cached complete replies finish 12.4-15.9% sooner than plain. A fresh 2048-token input still makes the 128-token reply finish 9.9% later than plain; Chinese/prose are also slower overall. The ordinary launcher therefore keeps prediction off.

Full Flash-Next Q2_0 on this 48 GiB M5 Pro, 4K context, batch/ubatch 512, F16 cache, eight threads, temperature 0.6 and two draft tokens. Eight passes alternate plain/full/shared-cpu/shared-mixed then reverse that order. Each pass excludes one warmup and retains two measurements per workload, giving four measurements per reported median. Fresh replies emit exactly 128 tokens with EOS ignored for timing; answer checks and cached ledger replies stop normally. The mixed profile includes packed layout and disabled automatic CPU-op offload; its timing is not a separate estimate of each of those changes.

| Workload / input or history | Plain TPS | Old helper TPS | Shared CPU TPS | Packed mixed TPS | Mixed vs old helper | Mixed vs plain |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Chinese writing / 56 | 37.22 | 32.55 | 34.18 | 34.34 | +5.52% | -7.74% |
| Python code / 48 | 37.66 | 42.70 | 42.34 | 42.98 | +0.67% | +14.15% |
| English prose / 53 | 36.95 | 35.13 | 35.21 | 36.38 | +3.54% | -1.54% |
| Writing / 512 | 37.54 | 36.93 | 37.85 | 41.22 | +11.63% | +9.80% |
| Writing / 2048 | 36.02 | 36.21 | 37.59 | 38.99 | +7.68% | +8.24% |
| Cached ledger / 512 | 37.34 | 50.44 | 48.83 | 51.02 | +1.15% | +36.65% |
| Cached ledger / 2048 | 36.42 | 44.17 | 45.20 | 46.72 | +5.77% | +28.27% |

Complete reply, seconds:

| Workload / input or history | Plain | Old helper | Packed mixed | Quicker vs old helper | Quicker vs plain |
| --- | ---: | ---: | ---: | ---: | ---: |
| Chinese writing / 56 | 3.697 | 4.296 | 4.016 | +6.52% | -8.64% |
| Python code / 48 | 3.641 | 3.331 | 3.259 | +2.16% | +10.49% |
| English prose / 53 | 3.719 | 4.001 | 3.849 | +3.78% | -3.51% |
| Writing / 512 | 4.149 | 4.563 | 4.072 | +10.75% | +1.85% |
| Writing / 2048 | 6.743 | 8.036 | 7.409 | +7.80% | -9.88% |
| Cached ledger / 512 | 0.906 | 0.820 | 0.762 | +7.01% | +15.89% |
| Cached ledger / 2048 | 0.912 | 0.898 | 0.799 | +11.01% | +12.35% |

For the fresh 2048-token input, plain / old helper / packed mixed input throughput is 644.7 / 450.8 / 494.8 tokens/s, and first-token delay is 3.18 / 4.54 / 4.14 seconds. On the cached 2048-history ledger reply, first-token delay is 0.278 / 0.374 / 0.306 seconds. This is computation throughput, not SSD read/write bandwidth.

All 240 focused answer checks pass across the eight runs, with no additional swap and no memory-guard stops. These repeated arithmetic/JSON/Python/label/ledger checks are not a broad quality evaluation. The borrowed target tables can change proposals and output tokens; general bit-for-bit or sampling-distribution equivalence is not established. OS file cache, temperature and background applications remain uncontrolled; small differences should not be treated as guaranteed gains.

The restart followed a stable idle period. [Resource samples](shared-quiet-resources.jsonl) track Java, stress processes and selected macOS background work through the completed suite. [The full comparison](results/20261006T185833Z-shared-comparison/COMPARISON.md) includes all input, first-token, complete-reply and acceptance tables. [Raw comparison](results/20261006T185833Z-shared-comparison/comparison.json) and [incremental percentages](results/20261006T185833Z-shared-comparison/incremental-percentages.json) link back to exact individual records.

## Why file order mattered

Full-GPU helper placement exhausted Metal's working budget at batch 512. Batch 128 completed focused checks but generated only about 4-10 TPS in its feature trial, so it is rejected. Moving only small dense helper operations to GPU also failed initially: the GGUF interleaved CPU expert tables between those GPU tensors. The native loader maps from the first to the last tensor assigned to a backend, causing Metal to map 1,183.14 MiB despite only 45.64 MiB of intended GPU weights.

Repacking puts the three CPU expert tables first and the 29 small GPU tensors last. Every tensor byte, type, shape and metadata field matches. The mixed helper's Metal mapped-weight span becomes 45.64 MiB. Its expert calculations remain on CPU, and `--no-op-offload` prevents automatic offload of those CPU operations during prefill. The main model stays on Metal. No system GPU memory limit is changed.

This fixes an allocation problem and makes mixed placement runnable on this Mac; it is not a 96% reduction of the whole model's RAM usage. The packed helper has the same file size as the shared helper.

## Evidence

- [Sharing manifest and patch/source pins](../config/mtp_shared_experiment.json), [shared preparation and byte proofs](results/20261006T182700Z-prepare-mtp-shared/preparation.json), [packed preparation and byte proofs](results/20261006T183818Z-prepare-shared-layout/preparation.json).
- [Full-GPU batch-512 failure](results/20261006T182852Z-feature-shared-gpu/result.json) and [batch-128 functional but slow trial](results/20261006T183135Z-feature-shared-gpu/result.json). Native logs retain the Metal out-of-memory evidence; a loaded model is not proof a configuration can generate normally.
- [Interleaved mixed-layout failure](results/20261006T183622Z-feature-shared-mixed/result.json) and [packed mixed-layout feature pass](results/20261006T183903Z-feature-shared-mixed/result.json): 28 focused checks, no additional swap in the successful packed trial.
- [Feature bundle](features/20261006T183903Z-mtp-shared/checks.json) also proves that the stripped helper is rejected cleanly when loaded without a target. Offline tests transform real miniature GGUF files, preserve Unicode metadata and tensor bytes, and check that packing reduces the GPU mapping span.
- [All nine tokenizer metadata fields match](features/20261006T191320Z-shared-tokenizer.json), including ordered token strings/types/merges and special-token settings. The [16 offline checks](features/20261006T1913-offline-tests.log) pass, covering source/build pins, vocabulary validation/environment scoping and real GGUF removal/packing.
- Final provisioning review reproduced a fresh-clone bug: saved helper registry entries prevented generation when the local derived files were absent. [Five failing-before tests](features/20261006T1916-reprovision-before.log) and [all 21 passing-after tests](features/20261006T1918-reprovision-after.log) document the fix. Missing quantized/shared/packed helpers can be regenerated; their saved size/hash must match, and registry pins stay unchanged. Shared/packed recreation tests use real miniature GGUF files; the quantizer orchestration test uses a deterministic stub, not another full-model quantization or speed run.
- The packed mixed profile passes [all nine real Strata app/API checks](results/20261006T185730Z-flash-integration.json): native/adapter greedy token parity, Unicode, OpenAI/Anthropic answers, streaming/EOS, explicit unsupported-tool and context-overflow rejection, cancellation and disconnect recovery. [Exact launch settings, source/binary/model pins and memory proof](results/20261006T185722Z-shared-app-proof.json) record no additional swap and confirm both servers stopped. Functional timings are excluded from the speed comparison.

Feature trials above use 64 output tokens without excluded warmup and are not the matched speed comparison. Their partial timings are not adopted performance gains.

The [initial shared comparison](results/20261006T185032Z-shared-comparison/comparison.json) was interrupted during its full-helper control after external Java builds increased CPU contention and system swap. [The interruption snapshot](results/20261006T185032Z-shared-comparison/interruption-context.json) records the condition. That incomplete suite is excluded from the speed recommendation rather than interpreted as a candidate regression.

## Reproduce

```sh
.venv/bin/python scripts/prepare_shared.py --jobs 2
.venv/bin/python scripts/prepare_shared_layout.py
.venv/bin/python scripts/verify_shared.py --mixed-only
.venv/bin/python scripts/benchmark_shared.py --include-mixed
# Explicitly load the model and run the comparison:
.venv/bin/python scripts/benchmark_shared.py --include-mixed --run
```

Stop the current app before switching profiles. `Start Strata - Shared Prediction Test.command` launches the packed mixed profile with two draft tokens, 4K context and batch/ubatch 512. The ordinary launcher retains conversation caching with prediction off. Cross-session caching is deferred.
