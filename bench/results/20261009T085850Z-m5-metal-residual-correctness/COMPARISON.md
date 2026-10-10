# M5 experiment: metal-residual-correctness

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
128 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | m5-lab | 40.038 | +0.00% | +0.00% | +0.00% | +0.39% |
| chinese / 56 | m5-correctness | 40.004 | -0.08% | -0.25% | -0.55% | +0.39% |
| code / 48 | m5-lab | 56.360 | +0.00% | +0.00% | +0.00% | -0.49% |
| code / 48 | m5-correctness | 56.449 | +0.16% | +0.08% | -0.13% | -0.49% |
| prose / 53 | m5-lab | 42.742 | +0.00% | +0.00% | +0.00% | +0.38% |
| prose / 53 | m5-correctness | 42.743 | +0.00% | -0.06% | -0.45% | +0.38% |
| synthetic / 512 | m5-lab | 49.013 | +0.00% | +0.00% | +0.00% | +0.04% |
| synthetic / 512 | m5-correctness | 48.907 | -0.22% | -0.27% | -0.09% | +0.04% |
| synthetic / 2048 | m5-lab | 50.008 | +0.00% | +0.00% | +0.00% | +0.09% |
| synthetic / 2048 | m5-correctness | 49.926 | -0.16% | -0.64% | -0.99% | +0.09% |
| cached-ledger / 512 | m5-lab | 69.280 | +0.00% | +0.00% | +0.00% | -0.27% |
| cached-ledger / 512 | m5-correctness | 68.914 | -0.53% | +0.30% | -0.43% | -0.27% |
| cached-ledger / 2048 | m5-lab | 62.561 | +0.00% | +0.00% | +0.00% | -0.11% |
| cached-ledger / 2048 | m5-correctness | 62.416 | -0.23% | +0.17% | -0.06% | -0.11% |

Raw runs

- [m5-lab / 20261009T085904Z-m5-metal-residual-correctness-1-m5-lab](../20261009T085904Z-m5-metal-residual-correctness-1-m5-lab/result.json)
- [m5-correctness / 20261009T090114Z-m5-metal-residual-correctness-2-m5-correctness](../20261009T090114Z-m5-metal-residual-correctness-2-m5-correctness/result.json)
- [m5-correctness / 20261009T090323Z-m5-metal-residual-correctness-3-m5-correctness](../20261009T090323Z-m5-metal-residual-correctness-3-m5-correctness/result.json)
- [m5-lab / 20261009T090541Z-m5-metal-residual-correctness-4-m5-lab](../20261009T090541Z-m5-metal-residual-correctness-4-m5-lab/result.json)
