# Optimization 2: smaller prediction helper

Keep prediction optional. The normal profile retains caching and no MTP: the fixed-length writing gain disappears at temperature 0.6 and fresh-prompt startup becomes slower. Cached ledger replies finish 4-10% sooner, a limited workload benefit.

The main model, native runtime, context and processing batch stay the same. Selected helper: locally generated Q3_K_S pure, two draft tokens, output projection on GPU and its body on CPU. It is 1.798 GB, versus 2.786 GB for the original self-contained Q4 helper (35.5% smaller). Norms/router precision and shape-compatible fallback quantization are preserved. Derived SHA256 and preparation receipts are in config/models.json.

| Workload | Size | Baseline output tok/s | Prediction output tok/s | Writing change | First-token delay change | Total time change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| greedy | 512 | 38.97 | 43.15 | +10.7% | +43.0% | +0.1% |
| greedy | 2048 | 37.59 | 42.53 | +13.1% | +38.3% | +12.5% |
| sampled | 512 | 38.99 | 38.38 | -1.6% | +47.5% | +10.1% |
| sampled | 2048 | 37.48 | 37.30 | -0.5% | +41.3% | +20.0% |
| cached_sampled | 512 | 38.54 | 52.04 | +35.1% | +28.1% | -10.1% |
| cached_sampled | 2048 | 37.27 | 46.83 | +25.6% | +32.6% | -3.9% |

Positive writing change is faster. Positive delay/time change is slower. Percentages use candidate / matched baseline - 1. Synthetic writing runs produce 128 fixed tokens with EOS ignored; cached follow-ups use real ledger answers and normal EOS. Cache comparisons use only cache-on measured cases and exclude warm-ups. Exact prompt hashes, sampling, native logs and memory records are preserved.

No additional swap growth occurred in the selected helper runs. Existing system swap remained; this is not a claim of zero total swap. These are limited local benchmarks with uncontrolled OS file cache and background applications.

## Evidence

- greedy: [baseline](results/20261006T144910Z-prediction-baseline-a/result.json), [prediction](results/20261006T145640Z-prediction-q3-output2/result.json).
- sampled: [baseline](results/20261006T145946Z-prediction-baseline-b-t06/result.json), [prediction](results/20261006T150044Z-prediction-q3-output2-t06/result.json).
- cached_sampled: [baseline](results/20261006T150238Z-flash-prediction-cache-baseline-t06/comparison.json), [prediction](results/20261006T150413Z-flash-prediction-q3-output2-cache-t06/comparison.json).
- [Machine-readable percentage calculations](results/20261006T155425Z-prediction-summary.json).

## Other attempts

- A 1.491 GB Q2_K helper with all-GPU placement exceeded the Metal working set on its first request. Its split placement ran without new swap, but its writing gain was only about 1-6% and prompt startup was slower.
- A 1.110 GB Q2_0 helper ran initially with less than 2% draft acceptance, wrote at only 12-16 tokens/s, then failed with a Metal out-of-memory error. It is rejected. Partial failed-run speeds are not adopted benchmark results.
- The Q3 CPU-only helper also ran without new swap, but was slower than the selected split placement.

The selected helper also passed [nine real Strata API/adapter checks](results/20261006T155222Z-flash-integration.json), with its exact launch settings preserved in [the app proof](results/20261006T155345Z-prediction-app-proof.json). The ordinary launcher remains on caching without prediction; `Start Strata - Prediction Test.command` launches the optional measured profile after stopping the current app.

All attempts remain in the main scoreboard. The selected greedy and temperature-0.6 native runs each passed 18 focused answer checks. These check arithmetic, structured extraction, label changes and a small Python function; they are not a broad model-quality evaluation. Greedy output differs from the baseline after token 92 on the synthetic 512-token prompt, as in the original MTP experiment; 2048-token greedy output matches. Do not claim general bit-for-bit equivalence.
