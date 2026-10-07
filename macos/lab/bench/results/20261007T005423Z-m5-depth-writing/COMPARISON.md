# M5 experiment: depth-writing

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
128 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | 3 | 40.163 | +0.00% | +0.00% | +0.00% | -0.02% |
| chinese / 56 | 5 | 33.258 | -17.19% | -18.98% | +0.23% | -0.02% |
| chinese / 56 | 6 | 29.915 | -25.52% | -31.40% | -0.65% | -0.02% |
| code / 48 | 3 | 56.426 | +0.00% | +0.00% | +0.00% | +0.08% |
| code / 48 | 5 | 53.537 | -5.12% | -4.80% | +0.21% | +0.08% |
| code / 48 | 6 | 50.379 | -10.72% | -10.70% | -0.48% | +0.08% |
| prose / 53 | 3 | 42.838 | +0.00% | +0.00% | +0.00% | +0.07% |
| prose / 53 | 5 | 36.696 | -14.34% | -15.22% | +0.00% | +0.07% |
| prose / 53 | 6 | 34.471 | -19.53% | -22.23% | -0.69% | +0.07% |
| synthetic / 512 | 3 | 49.012 | +0.00% | +0.00% | +0.00% | -0.05% |
| synthetic / 512 | 5 | 41.234 | -15.87% | -14.10% | -0.52% | -0.05% |
| synthetic / 512 | 6 | 37.306 | -23.88% | -23.53% | -0.64% | -0.05% |
| synthetic / 2048 | 3 | 50.029 | +0.00% | +0.00% | +0.00% | +0.06% |
| synthetic / 2048 | 5 | 45.574 | -8.90% | -3.48% | +0.71% | +0.06% |
| synthetic / 2048 | 6 | 43.397 | -13.25% | -5.98% | +0.30% | +0.06% |
| cached-ledger / 512 | 3 | 65.841 | +0.00% | +0.00% | +0.00% | +0.52% |
| cached-ledger / 512 | 5 | 66.447 | +0.92% | +0.89% | -0.22% | +0.52% |
| cached-ledger / 512 | 6 | 75.262 | +14.31% | +7.01% | -0.93% | +0.52% |
| cached-ledger / 2048 | 3 | 65.911 | +0.00% | +0.00% | +0.00% | +0.06% |
| cached-ledger / 2048 | 5 | 61.864 | -6.14% | -4.21% | -0.70% | +0.06% |
| cached-ledger / 2048 | 6 | 68.516 | +3.95% | +1.49% | -0.84% | +0.06% |

Raw runs

- [3 / 20261007T005430Z-m5-depth-writing-1-3](../20261007T005430Z-m5-depth-writing-1-3/result.json)
- [5 / 20261007T005559Z-m5-depth-writing-2-5](../20261007T005559Z-m5-depth-writing-2-5/result.json)
- [6 / 20261007T005734Z-m5-depth-writing-3-6](../20261007T005734Z-m5-depth-writing-3-6/result.json)
- [6 / 20261007T005913Z-m5-depth-writing-4-6](../20261007T005913Z-m5-depth-writing-4-6/result.json)
- [5 / 20261007T010052Z-m5-depth-writing-5-5](../20261007T010052Z-m5-depth-writing-5-5/result.json)
- [3 / 20261007T010226Z-m5-depth-writing-6-3](../20261007T010226Z-m5-depth-writing-6-3/result.json)
