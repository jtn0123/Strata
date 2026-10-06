# Strata Mac experiment results

Measured on this 48 GiB M5 Pro. Raw JSON, CSV, native logs, exact prompt IDs and 250 ms memory samples are saved beside each run. Earlier results stay unchanged.

| Run | Prompt tokens | Output tok/s (median) | First token (median, s) | Input tok/s (median) | Peak RSS (GiB) | Peak swap (GiB) | Swap growth (GiB) | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| [small-baseline](results/20261006T105737Z-small-baseline/result.json) | 512 | 77.56 | 0.325 | 1576.7 | 3.01 | 0.00 | 0.00 | passed |
| [small-baseline](results/20261006T105737Z-small-baseline/result.json) | 2048 | 76.13 | 1.256 | 1631.4 | 3.01 | 0.00 | 0.00 | passed |
| [small-ubatch512](results/20261006T105818Z-small-ubatch512/result.json) | 512 | 77.41 | 0.248 | 2069.9 | 3.05 | 0.00 | 0.00 | passed |
| [small-ubatch512](results/20261006T105818Z-small-ubatch512/result.json) | 2048 | 75.76 | 0.943 | 2173.9 | 3.05 | 0.00 | 0.00 | passed |
| [small-baseline-confirm](results/20261006T105843Z-small-baseline-confirm/result.json) | 512 | 77.51 | 0.325 | 1579.3 | 3.01 | 0.00 | 0.00 | passed |
| [small-baseline-confirm](results/20261006T105843Z-small-baseline-confirm/result.json) | 2048 | 75.95 | 1.256 | 1631.6 | 3.01 | 0.00 | 0.00 | passed |
| [flash-baseline](results/20261006T111445Z-flash-baseline/result.json) | 512 | 38.74 | 1.230 | 416.3 | 34.39 | 0.02 | 0.01 | passed |
| [flash-baseline](results/20261006T111445Z-flash-baseline/result.json) | 2048 | 37.55 | 4.943 | 414.4 | 34.39 | 0.02 | 0.01 | passed |
| [flash-ubatch512](results/20261006T111541Z-flash-ubatch512/result.json) | 512 | 38.72 | 0.750 | 683.5 | 35.68 | 0.02 | 0.00 | passed |
| [flash-ubatch512](results/20261006T111541Z-flash-ubatch512/result.json) | 2048 | 37.44 | 3.111 | 658.4 | 35.68 | 0.02 | 0.00 | passed |
| [flash-mtp3-ubatch512](results/20261006T111640Z-flash-mtp3-ubatch512/result.json) | - | - | - | - | 37.35 | 0.14 | 0.12 | failed: RuntimeError: Streaming response has no first token or final timing record |
| [flash-mtp3-cpu-ubatch512](results/20261006T111806Z-flash-mtp3-cpu-ubatch512/result.json) | 512 | 45.05 | 1.016 | 504.3 | 38.31 | 1.99 | 1.85 | passed |
| [flash-mtp3-cpu-ubatch512](results/20261006T111806Z-flash-mtp3-cpu-ubatch512/result.json) | 2048 | 42.66 | 4.148 | 493.8 | 38.31 | 1.99 | 1.85 | passed |
| [flash-8k-ubatch512](results/20261006T111954Z-flash-8k-ubatch512/result.json) | 1024 | 38.27 | 1.504 | 680.9 | 35.94 | 1.93 | 0.00 | passed |
| [flash-8k-ubatch512](results/20261006T111954Z-flash-8k-ubatch512/result.json) | 4096 | 37.19 | 6.616 | 619.2 | 35.94 | 1.93 | 0.00 | passed |

## Optimization 1: conversation caching

Matched follow-up prompts through the Strata adapter, caching off versus on. Same model/settings, alternating pair order, excluded warm-up pairs. This measures follow-up waiting, not fresh-prompt throughput.

| Model / run | History budget | First token off (s) | First token on (s) | Less waiting | Less total response time | Output speed change | Checks | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| [small / 20261006T140905Z-small-conversation-cache](results/20261006T140905Z-small-conversation-cache/comparison.json) | 512 | 0.306 | 0.080 | 73.7% | 36.5% | -0.0% | 9/9 | passed |
| [small / 20261006T140905Z-small-conversation-cache](results/20261006T140905Z-small-conversation-cache/comparison.json) | 2048 | 1.005 | 0.083 | 91.8% | 70.4% | -0.0% | 9/9 | passed |
| [flash / 20261006T141016Z-flash-conversation-cache](results/20261006T141016Z-flash-conversation-cache/comparison.json) | 512 | 0.951 | 0.259 | 72.8% | 44.1% | +1.0% | 15/15 | passed |
| [flash / 20261006T141016Z-flash-conversation-cache](results/20261006T141016Z-flash-conversation-cache/comparison.json) | 2048 | 3.351 | 0.272 | 91.9% | 77.4% | -0.7% | 15/15 | passed |

Reduction = 100 x (1 - cached duration / uncached duration). Output speed change = 100 x (cached rate / uncached rate - 1). Prompt cache is one engine slot; an unrelated chat may replace it. Memory samples cover both modes in the same process; paired RSS values are not isolated allocation measurements.

## Interpretation

- Compare changes within the same model, prompt hash, sampling settings and context. Model names ending Q2_0 or Q4_K_M describe compressed weights, not fewer model layers or experts.
- Speed runs ignore EOS to generate a fixed output length. Separate normal chat checks test answer correctness and stop handling. Two sanity questions do not establish overall model quality.
- No concurrent model downloads during speed runs. OS file caches are uncontrolled; these are not guaranteed cold SSD tests. The first request may include additional shader compilation.
- RSS is a process measurement, not total GPU usage. Read the full-model native allocation log too. System disk reads include unrelated activity.
- Swap growth is relative to the start of each run. Peak swap includes pages left swapped by earlier experiments; the 8K run inherited swap from the CPU draft test.
- The default guard stops a run if swap grows by more than 2 GiB or available RAM stays below 384 MiB for four seconds. A stopped configuration is recorded as a failure, not a speed result.

## Integration checks

- [20261006T110621Z-small-integration](results/20261006T110621Z-small-integration.json): 8/9 checks passed.
- [20261006T110714Z-small-integration](results/20261006T110714Z-small-integration.json): 9/9 checks passed.
- [20261006T112221Z-flash-integration](results/20261006T112221Z-flash-integration.json): 9/9 checks passed.
- [20261006T141248Z-flash-integration](results/20261006T141248Z-flash-integration.json): 9/9 checks passed.
- [20261006T112501Z-flash-context-probe](results/20261006T112501Z-flash-context-probe.json): passed, varied records across 2831 input tokens.
- [20261006T141353Z-flash-cache-api](results/20261006T141353Z-flash-cache-api.json): 2/2 real Strata HTTP follow-ups correct with confirmed native cache reuse.

Initial SSD measurement: [raw data](results/ssd-initial.json). GGUF layouts: [full model](results/flash-gguf-inventory.json), [draft head](results/mtp-gguf-inventory.json).
