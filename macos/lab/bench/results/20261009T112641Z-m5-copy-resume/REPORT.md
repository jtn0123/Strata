# M5 incremental copy experiments

Qwen3.8-Flash-Next GSQ-RCO Q2_0, M5 Pro 48 GiB. Depth 3, eight helper workers, Tensor API on, 4K context, F16 cache, 128 fresh output tokens. Only the named native copy mode changes.

Each mode has two model launches and three measured repeats per workload. One warmup is excluded. Control and candidate order: stock, scalar, vector4, direct convolution, direct convolution, vector4, scalar, stock.

| Workload | Setting | TPS | Gain vs fresh stock | First-token reduction | Total-response reduction | Stock drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| chinese/56 | stock | 40.073 | +0.00% | +0.00% | +0.00% | +0.20% |
| chinese/56 | copy-scalar | 40.140 | +0.17% | -1.00% | +0.17% | +0.20% |
| chinese/56 | copy-v4 | 40.100 | +0.07% | -1.10% | +0.03% | +0.20% |
| chinese/56 | conv-direct | 40.721 | +1.62% | +0.65% | +1.59% | +0.20% |
| code/48 | stock | 56.501 | +0.00% | +0.00% | +0.00% | +0.04% |
| code/48 | copy-scalar | 56.496 | -0.01% | -0.74% | -0.17% | +0.04% |
| code/48 | copy-v4 | 56.365 | -0.24% | -0.96% | -0.32% | +0.04% |
| code/48 | conv-direct | 57.258 | +1.34% | +0.68% | +1.21% | +0.04% |
| prose/53 | stock | 42.877 | +0.00% | +0.00% | +0.00% | +0.01% |
| prose/53 | copy-scalar | 42.861 | -0.04% | -0.90% | -0.12% | +0.01% |
| prose/53 | copy-v4 | 42.775 | -0.24% | -0.99% | -0.31% | +0.01% |
| prose/53 | conv-direct | 43.448 | +1.33% | +0.64% | +1.28% | +0.01% |
| synthetic/512 | stock | 49.060 | +0.00% | +0.00% | +0.00% | -0.56% |
| synthetic/512 | copy-scalar | 48.943 | -0.24% | -0.39% | -0.17% | -0.56% |
| synthetic/512 | copy-v4 | 48.851 | -0.42% | -1.44% | -0.58% | -0.56% |
| synthetic/512 | conv-direct | 49.744 | +1.39% | +0.43% | +1.19% | -0.56% |
| synthetic/2048 | stock | 50.016 | +0.00% | +0.00% | +0.00% | -0.21% |
| synthetic/2048 | copy-scalar | 50.056 | +0.08% | -0.89% | -0.39% | -0.21% |
| synthetic/2048 | copy-v4 | 49.963 | -0.11% | -1.29% | -0.74% | -0.21% |
| synthetic/2048 | conv-direct | 50.737 | +1.44% | +0.13% | +0.75% | -0.21% |
| cached-ledger/512 | stock | 69.069 | +0.00% | +0.00% | +0.00% | +2.98% |
| cached-ledger/512 | copy-scalar | 69.033 | -0.05% | -0.53% | -0.26% | +2.98% |
| cached-ledger/512 | copy-v4 | 68.893 | -0.25% | -0.58% | -0.30% | +2.98% |
| cached-ledger/512 | conv-direct | 69.754 | +0.99% | +1.02% | +0.78% | +2.98% |
| cached-ledger/2048 | stock | 63.062 | +0.00% | +0.00% | +0.00% | +0.49% |
| cached-ledger/2048 | copy-scalar | 63.749 | +1.09% | -0.76% | +0.17% | +0.49% |
| cached-ledger/2048 | copy-v4 | 64.655 | +2.53% | -1.15% | +0.56% | +0.49% |
| cached-ledger/2048 | conv-direct | 63.193 | +0.21% | +0.39% | +0.64% | +0.49% |

Validation: 8 model launches; 120 measured fresh outputs; 256 answer/cache checks. Every fresh and cached output matches stock token for token. No new swap. Minimum available RAM: 2.14 GiB. Peak process RSS: 38.13 GiB; RSS is not total Metal memory.

The detailed split trace exposed a costly-looking state CPY by interrupting graph fusion. The lighter normal-path inventory confirms native GDN cache fusion already removes those state copies. Copy-only speedups therefore do not represent model TPS gains.

[Raw comparison](/Users/justin/Documents/Github/Strata-Mac-Lab/bench/results/20261009T112641Z-m5-copy-resume/comparison.json)
[Normal-path shape inventory](/Users/justin/Documents/Github/Strata-Mac-Lab/bench/results/20261009T112641Z-m5-copy-resume/shape-inventory/inventory.json)
[Complete summary](/Users/justin/Documents/Github/Strata-Mac-Lab/bench/results/20261009T112641Z-m5-copy-resume/summary.json)

Post-run hardening: 224/224 bit-exact copy cases pass, including explicitly admitted aligned vector tails, strided convolution tails with and without CONT, unaligned/different-shape/transposed fallbacks, special F32 bit patterns, untouched destination padding and unchanged source bytes. Eight copy-only perf passes complete with microsecond artifact IDs. The earlier same-second collision is retained and excluded. The native model engine is unchanged. The exact 47-case probe/source/harness/build receipt used during model runs is archived in `probe-at-model-runs/`; the newer 56-case probe is supplementary validation after model timing.

The copy-only state microbenchmark gain does not predict model TPS: the large state CPY is absent from normal dispatch. Vector4 does show +2.53% native TPS on the short cached-2048 ledger fixture, with only +0.56% wall-time improvement; both passes are above controls, but broader follow-up fixtures are needed before calling that a general chat improvement. Cached-512 TPS control drift is 2.98%, larger than the measured 0.99% candidate change; no cached TPS gain is established. First-token reductions of 0.13-0.68% are too small for a strong latency claim. Fresh total-response time falls 0.75-1.59%. Initial Metal compilation/logging repairs, a trace-cap retry, the CPU-admission deferral and artifact-name collision are excluded from performance comparisons.

[Optional direct-copy launcher](../../../Start%20Strata%20-%20Direct%20Copy%20Trial.command) is syntax-checked and leaves ordinary launchers unchanged. It has not been left running. All eight existing engines are unchanged, T3/WiFiman remain open, and Chrome/Docker/VM remain stopped.

Current maintained offline gate: 94/94 tests pass after the probe artifact-ID hardening and completion bookkeeping. The optional launcher parser selects the measured 4K/F16/depth3/eight-helper-worker/Tensor-API-on configuration without starting an app or model. Final resource snapshot: about 37.97 GiB available; model servers are stopped.
