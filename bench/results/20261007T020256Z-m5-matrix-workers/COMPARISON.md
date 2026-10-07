# M5 experiment: matrix-workers

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
128 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | stock | 40.101 | +0.00% | +0.00% | +0.00% | -0.06% |
| chinese / 56 | nsg4 | 39.538 | -1.40% | -1.34% | -0.26% | -0.06% |
| chinese / 56 | nsg8 | 40.032 | -0.17% | -0.16% | +0.11% | -0.06% |
| code / 48 | stock | 56.447 | +0.00% | +0.00% | +0.00% | -0.01% |
| code / 48 | nsg4 | 55.606 | -1.49% | -1.36% | -0.28% | -0.01% |
| code / 48 | nsg8 | 56.252 | -0.35% | -0.26% | +0.21% | -0.01% |
| prose / 53 | stock | 42.819 | +0.00% | +0.00% | +0.00% | -0.10% |
| prose / 53 | nsg4 | 42.212 | -1.42% | -1.36% | -0.58% | -0.10% |
| prose / 53 | nsg8 | 42.739 | -0.19% | -0.23% | -0.09% | -0.10% |
| synthetic / 512 | stock | 48.963 | +0.00% | +0.00% | +0.00% | +0.19% |
| synthetic / 512 | nsg4 | 48.283 | -1.39% | -0.99% | +0.04% | +0.19% |
| synthetic / 512 | nsg8 | 48.476 | -0.99% | -0.79% | -0.20% | +0.19% |
| synthetic / 2048 | stock | 49.984 | +0.00% | +0.00% | +0.00% | -0.07% |
| synthetic / 2048 | nsg4 | 49.400 | -1.17% | -0.26% | +0.36% | -0.07% |
| synthetic / 2048 | nsg8 | 49.886 | -0.20% | -0.21% | -0.17% | -0.07% |
| cached-ledger / 512 | stock | 66.188 | +0.00% | +0.00% | +0.00% | -0.13% |
| cached-ledger / 512 | nsg4 | 65.197 | -1.50% | -0.90% | -0.11% | -0.13% |
| cached-ledger / 512 | nsg8 | 66.035 | -0.23% | -0.10% | +0.10% | -0.13% |
| cached-ledger / 2048 | stock | 65.832 | +0.00% | +0.00% | +0.00% | +0.24% |
| cached-ledger / 2048 | nsg4 | 65.084 | -1.14% | -0.88% | -0.58% | +0.24% |
| cached-ledger / 2048 | nsg8 | 65.783 | -0.07% | -0.34% | -0.72% | +0.24% |

Raw runs

- [stock / 20261007T020317Z-m5-matrix-workers-1-stock](../20261007T020317Z-m5-matrix-workers-1-stock/result.json)
- [nsg4 / 20261007T020445Z-m5-matrix-workers-2-nsg4](../20261007T020445Z-m5-matrix-workers-2-nsg4/result.json)
- [nsg8 / 20261007T020615Z-m5-matrix-workers-3-nsg8](../20261007T020615Z-m5-matrix-workers-3-nsg8/result.json)
- [nsg8 / 20261007T020744Z-m5-matrix-workers-4-nsg8](../20261007T020744Z-m5-matrix-workers-4-nsg8/result.json)
- [nsg4 / 20261007T020913Z-m5-matrix-workers-5-nsg4](../20261007T020913Z-m5-matrix-workers-5-nsg4/result.json)
- [stock / 20261007T021042Z-m5-matrix-workers-6-stock](../20261007T021042Z-m5-matrix-workers-6-stock/result.json)
