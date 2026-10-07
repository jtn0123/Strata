# M5 GPU matrix tuning results

Measured October 6, 2026 on the 48 GiB, 20-GPU-core M5 Pro. UTC artifact names fall on October 7. This follows the [Tensor API and prediction-depth batch](M5-RESULTS.md). Colima and Grafana stayed stopped.

## Decision

- Keep the existing ordinary, writing, fast-follow-up and short-structured launchers. Neither row-threshold change produces a useful gain; one-tile and GPU worker overrides regress.
- A two-tile limit produces a small, repeated generation improvement: +0.39% for code and about +0.59% for synthetic text. Expose it only as `Start Strata - M5 Two-Tile Trial.command`, using the isolated `m5-lab` engine at depth three. All nine real API check groups pass.
- This is a modest optional trial, not a significant new jump in model speed or model capacity. No settings are combined with depth six or other new tuning. Model bytes, helper, expert kernels, lazy SSD lookup and GPU memory limit are preserved.

## Six settings against fresh controls

Each row uses its own bracketed stock control. Differences across suites are not pooled or stacked with historical gains.

| Setting | Stock code TPS | Candidate code TPS | Code gain | Synthetic 512 gain | Synthetic 2048 gain |
| --- | ---: | ---: | ---: | ---: | ---: |
| BF16: start at 3 rows | 56.37 | 56.40 | +0.05% | +0.24% | +0.20% |
| Q2: start at 2 rows | 56.41 | 56.31 | -0.16% | -0.15% | -0.17% |
| Tile width: limit 1 | 56.46 | 55.84 | -1.09% | -0.93% | -0.88% |
| Tile width: limit 2 | 56.46 | 56.68 | +0.39% | +0.58% | +0.59% |
| GPU groups: request 4 | 56.45 | 55.61 | -1.49% | -1.39% | -1.17% |
| GPU groups: request 8 | 56.45 | 56.25 | -0.35% | -0.99% | -0.20% |

## Two-tile trial: output and response time

| Workload / input | Stock TPS | Trial TPS | Output gain | Stock complete reply | Trial complete reply | Reply quicker | Stock first token | Trial first token |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | 40.16 | 40.38 | +0.55% | 3.4582 s | 3.4405 s | +0.51% | 0.2952 s | 0.2954 s |
| code / 48 | 56.46 | 56.68 | +0.39% | 2.5319 s | 2.5244 s | +0.30% | 0.2823 s | 0.2833 s |
| prose / 53 | 42.88 | 43.08 | +0.47% | 3.2542 s | 3.2394 s | +0.46% | 0.2926 s | 0.2919 s |
| synthetic / 512 | 49.01 | 49.29 | +0.58% | 3.4949 s | 3.4823 s | +0.36% | 0.9032 s | 0.9067 s |
| synthetic / 2048 | 50.00 | 50.29 | +0.59% | 6.3168 s | 6.3063 s | +0.17% | 3.7765 s | 3.7809 s |
| cached-ledger / 512 | 66.18 | 66.49 | +0.47% | 0.6409 s | 0.6380 s | +0.45% | 0.2753 s | 0.2749 s |
| cached-ledger / 2048 | 65.96 | 66.37 | +0.62% | 0.6385 s | 0.6353 s | +0.51% | 0.2893 s | 0.2880 s |

The longer synthetic input processes 542.41 versus 541.78 input tokens/s (-0.12%). There is no measured input-processing gain. Complete fresh replies improve only 0.17-0.51%, depending on workload. Cached replies improve about 0.45-0.51%, a few milliseconds. Those are 25/24-token structured answers, not long chat generation.

## Isolated build parity

Before tuning, current `mtp-mma` and isolated `m5-lab` stock settings run in ABBA order. Fresh generation differs by at most 0.17%; every paired fresh token/text output matches the opening control. Input processing is about 0.85-1.88% slower in the isolated build; the long-input control itself drifts about 1.80%. Generation parity is supported, but this does not establish identical prompt latency. All tuning percentages above are measured inside the isolated build, not claimed directly against the current writing launcher.

## Method and checks

Each threshold comparison uses stock/candidate/candidate/stock. Tile and worker comparisons use stock/A/B/B/A/stock. Each setting has two model launches, an excluded warmup per workload and two measured repeats per launch; tables use medians of four samples. The packed mixed Q3 helper, depth three, F16 cache, 4K context, batch/ubatch 512, eight target/helper workers, temperature 0.6, seed 1234, confidence 0.0 and Tensor API on stay fixed. Profiling callbacks are disabled during speed trials. Fresh outputs are fixed at 128 tokens; cached replies stop naturally.

- 24 full-model speed passes; 720/720 answer checks; zero observed swap growth and no memory-guard stops.
- 6864/6864 CPU-reference GPU math checks across 12 prerequisite launches, including repeated stock prerequisites.
- Lowest available RAM in speed tests: 3.083 GiB. Peak process RSS: 38.372 GiB; RSS includes shared mappings and is not total Metal memory.
- Both two-tile launches reproduce all ten measured fresh outputs of the opening stock control. GPU math and focused answers pass; this is not a broad model-quality evaluation.
- Nine real app/API check groups pass for the two-tile trial: Unicode, greedy native/adapter parity, OpenAI streaming/non-streaming, Anthropic, explicit tool/overflow rejection, cancellation and disconnect recovery. Zero new swap; at least 3.403 GiB available. Functional-check timings are excluded from speed results.
- All 40 offline workflow checks and trial-launcher shell syntax pass. All six native engine/source receipts verify after testing. Comparison summaries were recomputed from immutable raw runs. [Batch receipt](features/20261006-m5-matrix-batch.json), [offline checks](features/20261006-m5-matrix-offline.log).

## Variation

| Comparison | Largest absolute fresh TPS control drift | Largest absolute cached TPS control drift |
| --- | ---: | ---: |
| engine-parity | 0.325% | 0.677% |
| bf16-threshold | 0.145% | 0.274% |
| q2-threshold | 0.258% | 0.305% |
| matrix-width | 0.368% | 0.168% |
| matrix-workers | 0.187% | 0.239% |

The two-tile control drifts only 0.05% for code/prose and 0.04% for synthetic text, while Chinese drifts 0.37%. Code candidates include one 56.31 TPS sample among roughly 56.6-56.8 TPS samples. Four samples per setting do not establish a universal sub-percent gain; keep it optional. Short cached repeats range roughly 61-72 TPS even when outputs are the same. Bracketing and matched prompts are necessary, and medians do not remove that variation.

## What this tuning can affect

The saved [weight inventory](results/flash-gguf-inventory.json) contains 202 Q2_0 tensors, including 144 routed-expert tensors. Routed experts account for 99.785% of Q2 storage (33,973,862,400 bytes); only 73,175,040 Q2 bytes are outside them. The row/tile/group controls apply to dense few-row MMA operations, not the separate `MUL_MAT_ID` routed-expert kernels. This limits the scope of these knobs. Storage shares are not execution-time shares and do not prove where decoding is bottlenecked.

The M5 Tensor API remains enabled. These tests do not measure hardware AI-accelerator occupancy, do not enable the separate Neural Engine, and do not implement compressed-weight cooperative-input shaders.

## Next work

The subsequent [helper/confidence batch](M5-HELPER-RESULTS.md) completes the three comparisons that remained after this stage. All twelve prepared experiments are now complete. For larger GPU changes, add request-phase and tensor-shape timing evidence to separate prompt processing from generation, then choose one compressed-weight/dequantization kernel worth changing. The aggregate GPU timings from the earlier batch cannot identify a decoding bottleneck.

## Raw evidence

- [engine-parity](results/20261007T013521Z-m5-engine-parity/comparison.json) and [comparison table](results/20261007T013521Z-m5-engine-parity/COMPARISON.md); the record links every full-model pass.
- [bf16-threshold](results/20261007T014132Z-m5-bf16-threshold/comparison.json) and [comparison table](results/20261007T014132Z-m5-bf16-threshold/COMPARISON.md); the record links every full-model pass.
- [q2-threshold](results/20261007T014739Z-m5-q2-threshold/comparison.json) and [comparison table](results/20261007T014739Z-m5-q2-threshold/COMPARISON.md); the record links every full-model pass.
- [matrix-width](results/20261007T015346Z-m5-matrix-width/comparison.json) and [comparison table](results/20261007T015346Z-m5-matrix-width/COMPARISON.md); the record links every full-model pass.
- [matrix-workers](results/20261007T020256Z-m5-matrix-workers/comparison.json) and [comparison table](results/20261007T020256Z-m5-matrix-workers/COMPARISON.md); the record links every full-model pass.
- [Two-tile app proof](results/20261007T021215Z-mma-app-3-8.json) and [integration checks](results/20261007T021220Z-flash-integration.json).
- [GPU math receipt](features/20261007T013521Z-m5-math-m5-lab-on-stock/checks.json).
- [GPU math receipt](features/20261007T013528Z-m5-math-mtp-mma-on-stock/checks.json).
- [GPU math receipt](features/20261007T014133Z-m5-math-m5-lab-on-bf16-row3/checks.json).
- [GPU math receipt](features/20261007T014140Z-m5-math-m5-lab-on-stock/checks.json).
- [GPU math receipt](features/20261007T014740Z-m5-math-m5-lab-on-q2-row2/checks.json).
- [GPU math receipt](features/20261007T014747Z-m5-math-m5-lab-on-stock/checks.json).
- [GPU math receipt](features/20261007T015346Z-m5-math-m5-lab-on-nt1/checks.json).
- [GPU math receipt](features/20261007T015353Z-m5-math-m5-lab-on-nt2/checks.json).
- [GPU math receipt](features/20261007T015400Z-m5-math-m5-lab-on-stock/checks.json).
- [GPU math receipt](features/20261007T020256Z-m5-math-m5-lab-on-nsg4/checks.json).
- [GPU math receipt](features/20261007T020304Z-m5-math-m5-lab-on-nsg8/checks.json).
- [GPU math receipt](features/20261007T020310Z-m5-math-m5-lab-on-stock/checks.json).
