# M5 experiment: depth-followup

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
128 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | 4 | 35.829 | +0.00% | +0.00% | +0.00% | -0.09% |
| chinese / 56 | 5 | 33.285 | -7.10% | -7.08% | -0.27% | -0.09% |
| chinese / 56 | 6 | 29.936 | -16.45% | -18.27% | -0.93% | -0.09% |
| code / 48 | 4 | 56.699 | +0.00% | +0.00% | +0.00% | +0.06% |
| code / 48 | 5 | 53.555 | -5.54% | -5.26% | -0.51% | +0.06% |
| code / 48 | 6 | 50.445 | -11.03% | -11.09% | -0.87% | +0.06% |
| prose / 53 | 4 | 41.947 | +0.00% | +0.00% | +0.00% | +0.09% |
| prose / 53 | 5 | 36.689 | -12.53% | -13.12% | -0.64% | +0.09% |
| prose / 53 | 6 | 34.455 | -17.86% | -19.91% | -0.98% | +0.09% |
| synthetic / 512 | 4 | 46.230 | +0.00% | +0.00% | +0.00% | -0.16% |
| synthetic / 512 | 5 | 41.268 | -10.73% | -9.27% | -0.71% | -0.16% |
| synthetic / 512 | 6 | 37.298 | -19.32% | -18.34% | -0.89% | -0.16% |
| synthetic / 2048 | 4 | 49.739 | +0.00% | +0.00% | +0.00% | -0.04% |
| synthetic / 2048 | 5 | 45.542 | -8.44% | -4.09% | -0.65% | -0.04% |
| synthetic / 2048 | 6 | 43.396 | -12.75% | -6.36% | -0.78% | -0.04% |
| cached-ledger / 512 | 4 | 68.982 | +0.00% | +0.00% | +0.00% | +0.01% |
| cached-ledger / 512 | 5 | 67.035 | -2.82% | -1.36% | -0.20% | +0.01% |
| cached-ledger / 512 | 6 | 75.497 | +9.44% | +4.88% | -0.68% | +0.01% |
| cached-ledger / 2048 | 4 | 69.398 | +0.00% | +0.00% | +0.00% | -0.17% |
| cached-ledger / 2048 | 5 | 62.159 | -10.43% | -6.87% | -1.62% | -0.17% |
| cached-ledger / 2048 | 6 | 69.730 | +0.48% | +0.04% | -0.55% | -0.17% |

Raw runs

- [4 / 20261007T010406Z-m5-depth-followup-1-4](../20261007T010406Z-m5-depth-followup-1-4/result.json)
- [5 / 20261007T010536Z-m5-depth-followup-2-5](../20261007T010536Z-m5-depth-followup-2-5/result.json)
- [6 / 20261007T010710Z-m5-depth-followup-3-6](../20261007T010710Z-m5-depth-followup-3-6/result.json)
- [6 / 20261007T010848Z-m5-depth-followup-4-6](../20261007T010848Z-m5-depth-followup-4-6/result.json)
- [5 / 20261007T011026Z-m5-depth-followup-5-5](../20261007T011026Z-m5-depth-followup-5-5/result.json)
- [4 / 20261007T011201Z-m5-depth-followup-6-4](../20261007T011201Z-m5-depth-followup-6-4/result.json)
