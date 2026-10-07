# M5 experiment: helper-workers

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
128 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | 8 | 40.060 | +0.00% | +0.00% | +0.00% | -0.08% |
| chinese / 56 | 6 | 40.497 | +1.09% | +0.95% | -0.58% | -0.08% |
| chinese / 56 | 12 | 40.283 | +0.56% | +0.59% | +0.81% | -0.08% |
| code / 48 | 8 | 56.327 | +0.00% | +0.00% | +0.00% | +0.01% |
| code / 48 | 6 | 56.761 | +0.77% | +0.60% | -0.83% | +0.01% |
| code / 48 | 12 | 56.855 | +0.94% | +0.88% | +0.30% | +0.01% |
| prose / 53 | 8 | 42.797 | +0.00% | +0.00% | +0.00% | -0.02% |
| prose / 53 | 6 | 43.293 | +1.16% | +0.97% | -0.78% | -0.02% |
| prose / 53 | 12 | 43.124 | +0.76% | +0.74% | +0.54% | -0.02% |
| synthetic / 512 | 8 | 48.909 | +0.00% | +0.00% | +0.00% | +0.04% |
| synthetic / 512 | 6 | 49.493 | +1.19% | +0.03% | -3.11% | +0.04% |
| synthetic / 512 | 12 | 49.307 | +0.81% | +1.63% | +3.75% | +0.04% |
| synthetic / 2048 | 8 | 49.928 | +0.00% | +0.00% | +0.00% | -0.04% |
| synthetic / 2048 | 6 | 50.454 | +1.05% | -1.56% | -3.32% | -0.04% |
| synthetic / 2048 | 12 | 50.336 | +0.82% | +2.21% | +3.14% | -0.04% |
| cached-ledger / 512 | 8 | 66.065 | +0.00% | +0.00% | +0.00% | -0.16% |
| cached-ledger / 512 | 6 | 66.762 | +1.06% | +0.34% | -0.51% | -0.16% |
| cached-ledger / 512 | 12 | 66.419 | +0.54% | +0.47% | +0.44% | -0.16% |
| cached-ledger / 2048 | 8 | 65.755 | +0.00% | +0.00% | +0.00% | -0.04% |
| cached-ledger / 2048 | 6 | 66.390 | +0.97% | +0.28% | -0.51% | -0.04% |
| cached-ledger / 2048 | 12 | 66.258 | +0.76% | +0.63% | +0.47% | -0.04% |

Raw runs

- [8 / 20261007T040333Z-m5-helper-workers-1-8](../20261007T040333Z-m5-helper-workers-1-8/result.json)
- [6 / 20261007T040501Z-m5-helper-workers-2-6](../20261007T040501Z-m5-helper-workers-2-6/result.json)
- [12 / 20261007T040630Z-m5-helper-workers-3-12](../20261007T040630Z-m5-helper-workers-3-12/result.json)
- [12 / 20261007T040757Z-m5-helper-workers-4-12](../20261007T040757Z-m5-helper-workers-4-12/result.json)
- [6 / 20261007T040924Z-m5-helper-workers-5-6](../20261007T040924Z-m5-helper-workers-5-6/result.json)
- [8 / 20261007T041053Z-m5-helper-workers-6-8](../20261007T041053Z-m5-helper-workers-6-8/result.json)
