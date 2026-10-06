# Optimization 3: Q2 GPU math

**Benchmarked October 6, 2026: keep the original engine as the default.** On this 48 GiB M5 Pro, the final confirmation showed small, mixed writing gains, slower prompt processing and little improvement to total response time. Earlier passes were affected by other work on the Mac. The Q2 candidate remains optional.

This changes how the GPU calculates the existing compressed Q2 weights. It keeps the full Flash-Next model, all experts and lazy SSD lookup. It is a speed experiment, not a change to model size or precision. The original engine and everyday launcher remain the baseline.

## Measured result

Final adjacent confirmation after Java build activity subsided; each entry is the median of three 512-token replies after an excluded warmup. Browser/UI and media-analysis work remained, so this was not a fully idle Mac.

| Input tokens | Original output TPS | Candidate output TPS | Writing change | Original input TPS | Candidate input TPS | Input change |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 512 | 37.91 | 38.01 | +0.27% | 679.25 | 637.88 | -6.09% |
| 2048 | 35.55 | 36.86 | +3.68% | 647.00 | 599.80 | -7.29% |

| Input tokens | Original first token | Candidate first token | Original full reply | Candidate full reply | Reply time reduction |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 512 | 0.754 s | 0.803 s | 14.235 s | 14.245 s | -0.07% |
| 2048 | 3.166 s | 3.415 s | 17.548 s | 17.309 s | +1.36% |

The short reply was essentially unchanged. The long reply finished about 0.24 seconds sooner but started about 0.25 seconds later. These small, inconsistent gains do not justify changing the everyday engine. [Exact confirmation, formulas and raw runs](results/20261006-q2-confirmation-analysis/COMPARISON.md).

The initial baseline/candidate/candidate/baseline comparison recorded **-8.83% / -7.30%** writing changes for 512/2048-token inputs. Java builds and browser tests were active during parts of that sequence, and the same candidate's short-prompt median varied from 29.20 to 34.60 to 38.01 TPS across the three passes. Those earlier differences do not establish that the patch itself caused a slowdown. [Original four-pass record](results/20261006T172232Z-q2-comparison/COMPARISON.md), [background observations](diagnostics/20261006-q2-background.jsonl).

All six successful passes completed **108/108 focused answer checks**: 54 on the candidate and 54 on the original engine. They covered arithmetic, structured output, record recall, simple code and normal stopping at greedy and sampled settings. The candidate changes floating-point accumulation; its sampled token sequences differed from the original's, so this is not a bit-for-bit parity claim.

The first attempted load stopped before timing because system swap grew **2.14 GiB** while the Docker VM was active. After Justin authorized stopping Colima, six passes completed without a memory-guard trip. Final-pair swap growth was 0.0006 GiB on the candidate and zero on the original; sampled minimum available RAM was 3.06 GiB and 2.76 GiB respectively. Earlier swap remained allocated. Colima and all lab model servers were left stopped; Justin requested no VM restart. [Stopped attempt](results/20261006T171840Z-q2-1-baseline/result.json).

## Prepared and checked

- Original engine: `vendor/llama.cpp/build/bin/llama-server`.
- Separate candidate: `vendor/llama-q2-masked/build/bin/llama-server`.
- Both use native source `d81235049384534c167caea52b85a694f6103d14`; the candidate adds only [the pinned Meld Q2 patch](../config/q2_experiment.json).
- Both are Release builds with embedded Metal, CPU and Accelerate support. Candidate tests are enabled and builds use two workers by default. No new system packages, login services, model downloads or GPU memory overrides were installed.
- Native GPU correctness: **122/122 Q2 matrix and expert-operation tests plus 2/2 Q4 control tests passed**, compared with CPU reference math. Peak sampled process RSS was **165.6 MiB**; no observed system swap growth. [Raw correctness record](features/20261006T171145Z-q2-metal/checks.json). These are synthetic operations, not full-model answers or inference benchmarks.
- Six offline workflow tests passed. They cover the default hold, percentage calculations and rejection of unequal settings, prompts, output counts, failed runs, memory-guard trips, unintended source edits and replaced native libraries.
- Build receipts hash the server and native libraries. The comparison runner refuses an altered source/build or a candidate without a matching passed correctness record.

## Check RAM without running anything

Double-click `Check RAM - Next Experiment.command`, or run:

```sh
.venv/bin/python scripts/benchmark_q2.py
```

This lists current available/wired memory, existing swap and the largest process names, then prints the test plan and exits. It does not start inference, quit apps, or measure model speed. Process RSS is approximate and excludes some Metal/compressed memory; inspect Activity Monitor too. Previous swap does not disappear immediately when an app closes. No Strata model server is currently left running.

## Benchmark command

From the lab directory, the prepared command is:

```sh
.venv/bin/python scripts/benchmark_q2.py --run
```

Run on AC power with other heavy work paused. It executes **baseline / candidate / candidate / baseline**, one model process at a time. The matched settings are the full Flash-Next Q2_0 model, 4K context, batch and ubatch 512, F16 cache, eight CPU threads, temperature 0.6, seed 1234, prediction off and no prompt reuse. Input sizes are 512 and 2048 tokens. Each has one excluded warmup and three measured 512-token outputs per run. Sustained outputs help check whether a micro-kernel gain carries through real inference. Normal-EOS answer checks run separately at both greedy and sampled settings.

Results preserve exact commands, source/patch/binary hashes, identical prompt hashes, model identity, raw text, input/output TPS, first-token time, total reply time, memory/swap samples, load time and native logs. The existing guard stops the model if new swap exceeds 2 GiB or available memory stays below 384 MiB for four seconds. A failed or guarded run cannot be used to claim a speed improvement.

The generated `COMPARISON.md` and `comparison.json` compare against this fresh baseline. Output improvement is `100 * (candidate TPS / baseline TPS - 1)`; waiting reduction is `100 * (1 - candidate seconds / baseline seconds)`. Negative percentages mean a regression. This is not a guaranteed cold-SSD test; macOS file caches and unrelated activity remain uncontrolled.

The full-model native answer checks and sustained measurements above are complete. Candidate-specific validation through the real Strata adapter remains separate; the everyday launcher still uses its previously verified original engine. The existing caching optimization remains enabled for normal app use; this kernel comparison deliberately measures fresh prompts. Benchmarking the prediction helper or larger contexts is a later, separate step.

## Reproduce preparation only

After provisioning the baseline lab and verified model files as described in the README:

```sh
.venv/bin/python scripts/prepare_q2.py --jobs 2
.venv/bin/python scripts/verify_q2.py
.venv/bin/python -m unittest discover -s tests -v
```

These commands build, test small synthetic tensors and check the workflow; they do not load a model or run speed tests. The candidate can later be selected explicitly with `scripts/run.py flash --engine q2-masked`; that command **does load the model** and has not been run during preparation. It does not change the normal launcher's default.
