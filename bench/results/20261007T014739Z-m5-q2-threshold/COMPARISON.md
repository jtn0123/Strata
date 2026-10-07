# M5 experiment: q2-threshold

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
128 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | stock | 40.140 | +0.00% | +0.00% | +0.00% | +0.26% |
| chinese / 56 | q2-row2 | 40.084 | -0.14% | -0.14% | -0.20% | +0.26% |
| code / 48 | stock | 56.405 | +0.00% | +0.00% | +0.00% | +0.03% |
| code / 48 | q2-row2 | 56.314 | -0.16% | -0.17% | -0.38% | +0.03% |
| prose / 53 | stock | 42.836 | +0.00% | +0.00% | +0.00% | +0.03% |
| prose / 53 | q2-row2 | 42.739 | -0.23% | -0.17% | +0.03% | +0.03% |
| synthetic / 512 | stock | 48.969 | +0.00% | +0.00% | +0.00% | +0.15% |
| synthetic / 512 | q2-row2 | 48.898 | -0.15% | -0.28% | -0.56% | +0.15% |
| synthetic / 2048 | stock | 49.996 | +0.00% | +0.00% | +0.00% | +0.05% |
| synthetic / 2048 | q2-row2 | 49.910 | -0.17% | -0.29% | -0.34% | +0.05% |
| cached-ledger / 512 | stock | 66.027 | +0.00% | +0.00% | +0.00% | -0.19% |
| cached-ledger / 512 | q2-row2 | 66.164 | +0.21% | +0.01% | -0.22% | -0.19% |
| cached-ledger / 2048 | stock | 65.947 | +0.00% | +0.00% | +0.00% | +0.31% |
| cached-ledger / 2048 | q2-row2 | 65.899 | -0.07% | -0.18% | -0.24% | +0.31% |

Raw runs

- [stock / 20261007T014753Z-m5-q2-threshold-1-stock](../20261007T014753Z-m5-q2-threshold-1-stock/result.json)
- [q2-row2 / 20261007T014921Z-m5-q2-threshold-2-q2-row2](../20261007T014921Z-m5-q2-threshold-2-q2-row2/result.json)
- [q2-row2 / 20261007T015050Z-m5-q2-threshold-3-q2-row2](../20261007T015050Z-m5-q2-threshold-3-q2-row2/result.json)
- [stock / 20261007T015218Z-m5-q2-threshold-4-stock](../20261007T015218Z-m5-q2-threshold-4-stock/result.json)
