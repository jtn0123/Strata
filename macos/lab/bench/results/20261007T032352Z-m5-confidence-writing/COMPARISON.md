# M5 experiment: confidence-writing

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
128 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | 0.0 | 40.067 | +0.00% | +0.00% | +0.00% | +0.41% |
| chinese / 56 | 0.2 | 40.149 | +0.20% | +0.07% | -0.59% | +0.41% |
| chinese / 56 | 0.4 | 39.111 | -2.39% | -2.44% | -2.45% | +0.41% |
| code / 48 | 0.0 | 56.347 | +0.00% | +0.00% | +0.00% | +0.13% |
| code / 48 | 0.2 | 56.323 | -0.04% | -0.08% | -0.41% | +0.13% |
| code / 48 | 0.4 | 55.737 | -1.08% | -1.22% | -2.11% | +0.13% |
| prose / 53 | 0.0 | 42.792 | +0.00% | +0.00% | +0.00% | +0.24% |
| prose / 53 | 0.2 | 43.108 | +0.74% | +0.57% | -0.70% | +0.24% |
| prose / 53 | 0.4 | 43.135 | +0.80% | +0.54% | -2.08% | +0.24% |
| synthetic / 512 | 0.0 | 48.972 | +0.00% | +0.00% | +0.00% | -0.19% |
| synthetic / 512 | 0.2 | 48.475 | -1.01% | -1.68% | -3.44% | -0.19% |
| synthetic / 512 | 0.4 | 45.815 | -6.45% | -5.38% | -1.06% | -0.19% |
| synthetic / 2048 | 0.0 | 50.001 | +0.00% | +0.00% | +0.00% | -0.05% |
| synthetic / 2048 | 0.2 | 49.887 | -0.23% | -0.91% | -1.35% | -0.05% |
| synthetic / 2048 | 0.4 | 47.975 | -4.05% | -2.45% | -1.18% | -0.05% |
| cached-ledger / 512 | 0.0 | 65.196 | +0.00% | +0.00% | +0.00% | +2.16% |
| cached-ledger / 512 | 0.2 | 65.446 | +0.38% | -0.13% | -0.70% | +2.16% |
| cached-ledger / 512 | 0.4 | 65.411 | +0.33% | -0.09% | -0.41% | +2.16% |
| cached-ledger / 2048 | 0.0 | 63.874 | +0.00% | +0.00% | +0.00% | +5.79% |
| cached-ledger / 2048 | 0.2 | 63.867 | -0.01% | -0.35% | -0.74% | +5.79% |
| cached-ledger / 2048 | 0.4 | 64.802 | +1.45% | +0.60% | -0.40% | +5.79% |

Raw runs

- [0.0 / 20261007T032359Z-m5-confidence-writing-1-0.0](../20261007T032359Z-m5-confidence-writing-1-0.0/result.json)
- [0.2 / 20261007T032532Z-m5-confidence-writing-2-0.2](../20261007T032532Z-m5-confidence-writing-2-0.2/result.json)
- [0.4 / 20261007T032701Z-m5-confidence-writing-3-0.4](../20261007T032701Z-m5-confidence-writing-3-0.4/result.json)
- [0.4 / 20261007T032831Z-m5-confidence-writing-4-0.4](../20261007T032831Z-m5-confidence-writing-4-0.4/result.json)
- [0.2 / 20261007T033002Z-m5-confidence-writing-5-0.2](../20261007T033002Z-m5-confidence-writing-5-0.2/result.json)
- [0.0 / 20261007T033132Z-m5-confidence-writing-6-0.0](../20261007T033132Z-m5-confidence-writing-6-0.0/result.json)
