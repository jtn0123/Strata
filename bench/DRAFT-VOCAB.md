# Smaller prediction vocabulary

Keep this optional. The corrected GPU path improves generation by about 4% over the full-vocabulary helper on synthetic writing, but cached ledger generation slows 9-10%, and the 128-token fresh writing replies do not finish sooner than the ordinary no-prediction profile. It adds memory. Do not combine it with the shared-helper candidate without another comparison.

These measurements use the full Flash-Next Q2_0 model on this 48 GiB M5 Pro: 4K context, batch/ubatch 512, F16 cache, eight threads, temperature 0.6 and two helper draft tokens. Six passes run plain/full/subset/subset/full/plain. Each pass excludes one warmup and retains two measurements per workload; each reported median therefore uses four measurements. Fresh timing replies are fixed at 128 tokens with EOS ignored; separate answers and cached ledger replies stop normally. Code, prose and Chinese input lengths below are the actual short prompts; synthetic writing uses 512/2048 input tokens.

| Workload | Plain TPS | Full helper TPS | Smaller list TPS | Change vs full helper |
| --- | ---: | ---: | ---: | ---: |
| Python code | 37.30 | 44.03 | 43.53 | -1.13% |
| English prose | 38.14 | 37.09 | 38.47 | +3.72% |
| Chinese writing | 37.98 | 34.76 | 35.50 | +2.12% |
| Synthetic writing, 512 input | 37.63 | 37.63 | 39.11 | +3.94% |
| Synthetic writing, 2048 input | 35.94 | 37.04 | 38.69 | +4.44% |
| Cached ledger, 512 history | 37.22 | 50.04 | 45.43 | -9.22% |
| Cached ledger, 2048 history | 36.01 | 46.05 | 41.39 | -10.12% |

For a 2048-token fresh input, input throughput falls from 655 tokens/s plain to 460 with the full helper and 443 with the subset. First token takes 3.13 / 4.45 / 4.64 seconds; the complete 128-token reply takes 6.66 / 7.91 / 7.93 seconds. The generation gain does not compensate for helper startup on this workload. Code replies do benefit from prediction: 3.68 / 3.22 / 3.27 seconds, with the full helper slightly better than the subset.

The smaller list limits only the helper to 106,299 of 248,320 token IDs. The main model still uses its full vocabulary. Cached draft acceptance falls from 100% with the full helper to 83.3% / 77.8% with the subset, matching its slower cached generation. A smaller output table is not a universal prediction improvement.

## Implementation and evidence

- The isolated port and multilingual token list are pinned in [the manifest](../config/draft_vocab_experiment.json), including the original Meld commit/license. The ordinary native engine is unchanged.
- The compact Q3 output table adds approximately 111.5 MiB; the full table remains for unsupported sampling/LoRA/scaled-head fallback. This saves output calculations, not model-file space.
- Our first port placed the compact output calculation on CPU when the helper body was on CPU. [Before](features/20261006T182323Z-vocab-routing-before/trace.json) and [after](features/20261006T182422Z-vocab-routing-after/trace.json) scheduler traces document the fix: mark the copied buffer as weights so the output matrix multiplication stays on Metal. The initial interrupted suite is retained and excluded from this decision.
- [Feature checks](features/20261006T183439Z-draft-vocab/checks.json) force the target to produce token ID 32768, outside the helper subset. Both the plain and subset profiles produce it. The full target vocabulary remains reachable. Nonidentity row mapping, invalid files and inherited environment overrides are also tested offline.
- The corrected six-pass comparison passes all 180 focused answer checks, including English/Chinese arithmetic and JSON, Python behavior, changed labels and cached ledger recall. These are focused checks rather than a broad quality evaluation; general identical output or sampling-distribution equivalence is not established.
- One subset pass records 53.3 MiB of additional system swap; the other five record none. Existing total swap remains separate. No pass triggers the memory guard. Background applications and OS file cache are uncontrolled; outliers remain in the records and medians.

[Full TPS, input throughput, first-token time, complete-reply time and acceptance tables](results/20261006T183950Z-vocab-comparison/COMPARISON.md), [machine-readable comparison](results/20261006T183950Z-vocab-comparison/comparison.json) and the linked individual raw records preserve exact commands, source/binary/model hashes, answers, tokens and memory samples.

## Reproduce

```sh
.venv/bin/python scripts/prepare_vocab.py --jobs 2
.venv/bin/python scripts/verify_vocab.py
.venv/bin/python scripts/benchmark_vocab.py --predict 128
# Explicitly load the model and run the comparison:
.venv/bin/python scripts/benchmark_vocab.py --predict 128 --run
```

Cross-session caching is not added. Cached trials reuse only the immediately preceding conversation turn.
