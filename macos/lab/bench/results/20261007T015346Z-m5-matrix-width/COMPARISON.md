# M5 experiment: matrix-width

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
128 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | stock | 40.157 | +0.00% | +0.00% | +0.00% | +0.37% |
| chinese / 56 | nt1 | 39.761 | -0.98% | -0.91% | -0.14% | +0.37% |
| chinese / 56 | nt2 | 40.379 | +0.55% | +0.51% | -0.08% | +0.37% |
| code / 48 | stock | 56.458 | +0.00% | +0.00% | +0.00% | -0.05% |
| code / 48 | nt1 | 55.844 | -1.09% | -0.99% | -0.13% | -0.05% |
| code / 48 | nt2 | 56.677 | +0.39% | +0.30% | -0.35% | -0.05% |
| prose / 53 | stock | 42.883 | +0.00% | +0.00% | +0.00% | -0.04% |
| prose / 53 | nt1 | 42.445 | -1.02% | -0.93% | +0.01% | -0.04% |
| prose / 53 | nt2 | 43.085 | +0.47% | +0.46% | +0.26% | -0.04% |
| synthetic / 512 | stock | 49.007 | +0.00% | +0.00% | +0.00% | +0.04% |
| synthetic / 512 | nt1 | 48.550 | -0.93% | -1.15% | -1.67% | +0.04% |
| synthetic / 512 | nt2 | 49.293 | +0.58% | +0.36% | -0.39% | +0.04% |
| synthetic / 2048 | stock | 49.998 | +0.00% | +0.00% | +0.00% | -0.00% |
| synthetic / 2048 | nt1 | 49.558 | -0.88% | -0.97% | -1.00% | -0.00% |
| synthetic / 2048 | nt2 | 50.293 | +0.59% | +0.17% | -0.12% | -0.00% |
| cached-ledger / 512 | stock | 66.176 | +0.00% | +0.00% | +0.00% | +0.02% |
| cached-ledger / 512 | nt1 | 65.500 | -1.02% | -0.57% | -0.23% | +0.02% |
| cached-ledger / 512 | nt2 | 66.487 | +0.47% | +0.45% | +0.14% | +0.02% |
| cached-ledger / 2048 | stock | 65.963 | +0.00% | +0.00% | +0.00% | +0.17% |
| cached-ledger / 2048 | nt1 | 65.345 | -0.94% | -0.44% | -0.09% | +0.17% |
| cached-ledger / 2048 | nt2 | 66.371 | +0.62% | +0.51% | +0.46% | +0.17% |

Raw runs

- [stock / 20261007T015407Z-m5-matrix-width-1-stock](../20261007T015407Z-m5-matrix-width-1-stock/result.json)
- [nt1 / 20261007T015535Z-m5-matrix-width-2-nt1](../20261007T015535Z-m5-matrix-width-2-nt1/result.json)
- [nt2 / 20261007T015704Z-m5-matrix-width-3-nt2](../20261007T015704Z-m5-matrix-width-3-nt2/result.json)
- [nt2 / 20261007T015832Z-m5-matrix-width-4-nt2](../20261007T015832Z-m5-matrix-width-4-nt2/result.json)
- [nt1 / 20261007T020000Z-m5-matrix-width-5-nt1](../20261007T020000Z-m5-matrix-width-5-nt1/result.json)
- [stock / 20261007T020128Z-m5-matrix-width-6-stock](../20261007T020128Z-m5-matrix-width-6-stock/result.json)
