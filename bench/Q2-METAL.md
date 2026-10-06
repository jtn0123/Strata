# Optimization 3: Q2 GPU math

**Ready for an approved experiment; benchmarks and model loading are on hold.** Prepared October 6, 2026 on the 48 GiB M5 Pro. No new TPS or percentage speed gain is available yet.

This changes how the GPU calculates the existing compressed Q2 weights. It keeps the full Flash-Next model, all experts and lazy SSD lookup. It is a speed experiment, not a change to model size or precision. The original engine and everyday launcher remain the baseline.

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

## After explicit approval

From the lab directory, the prepared command is:

```sh
.venv/bin/python scripts/benchmark_q2.py --run
```

Run on AC power with other heavy work paused. It executes **baseline / candidate / candidate / baseline**, one model process at a time. The matched settings are the full Flash-Next Q2_0 model, 4K context, batch and ubatch 512, F16 cache, eight CPU threads, temperature 0.6, seed 1234, prediction off and no prompt reuse. Input sizes are 512 and 2048 tokens. Each has one excluded warmup and three measured 512-token outputs per run. Sustained outputs help check whether a micro-kernel gain carries through real inference. Normal-EOS answer checks run separately at both greedy and sampled settings.

Results preserve exact commands, source/patch/binary hashes, identical prompt hashes, model identity, raw text, input/output TPS, first-token time, total reply time, memory/swap samples, load time and native logs. The existing guard stops the model if new swap exceeds 2 GiB or available memory stays below 384 MiB for four seconds. A failed or guarded run cannot be used to claim a speed improvement.

The generated `COMPARISON.md` and `comparison.json` compare against this fresh baseline. Output improvement is `100 * (candidate TPS / baseline TPS - 1)`; waiting reduction is `100 * (1 - candidate seconds / baseline seconds)`. Negative percentages mean a regression. This is not a guaranteed cold-SSD test; macOS file caches and unrelated activity remain uncontrolled.

Full-model numerical behavior, answer quality, sustained speed and real-adapter performance of the candidate still need verification. A passing synthetic GPU test does not settle those questions. The existing caching optimization remains enabled for normal app use; this first kernel comparison deliberately measures fresh prompts. Benchmarking the prediction helper or larger contexts is a later, separate step.

## Reproduce preparation only

After provisioning the baseline lab and verified model files as described in the README:

```sh
.venv/bin/python scripts/prepare_q2.py --jobs 2
.venv/bin/python scripts/verify_q2.py
.venv/bin/python -m unittest discover -s tests -v
```

These commands build, test small synthetic tensors and check the workflow; they do not load a model or run speed tests. The candidate can later be selected explicitly with `scripts/run.py flash --engine q2-masked`; that command **does load the model** and has not been run during preparation. It does not change the normal launcher's default.
