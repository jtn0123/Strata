# M5 experiment: bf16-threshold

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
128 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | stock | 40.129 | +0.00% | +0.00% | +0.00% | -0.10% |
| chinese / 56 | bf16-row3 | 40.191 | +0.15% | +0.15% | +0.03% | -0.10% |
| code / 48 | stock | 56.372 | +0.00% | +0.00% | +0.00% | +0.02% |
| code / 48 | bf16-row3 | 56.401 | +0.05% | +0.05% | +0.04% | +0.02% |
| prose / 53 | stock | 42.838 | +0.00% | +0.00% | +0.00% | -0.14% |
| prose / 53 | bf16-row3 | 42.815 | -0.05% | -0.04% | -0.06% | -0.14% |
| synthetic / 512 | stock | 48.945 | +0.00% | +0.00% | +0.00% | -0.06% |
| synthetic / 512 | bf16-row3 | 49.062 | +0.24% | -0.12% | -1.09% | -0.06% |
| synthetic / 2048 | stock | 49.956 | +0.00% | +0.00% | +0.00% | -0.11% |
| synthetic / 2048 | bf16-row3 | 50.054 | +0.20% | +0.21% | +0.23% | -0.11% |
| cached-ledger / 512 | stock | 65.947 | +0.00% | +0.00% | +0.00% | +0.27% |
| cached-ledger / 512 | bf16-row3 | 66.143 | +0.30% | +0.71% | +0.70% | +0.27% |
| cached-ledger / 2048 | stock | 65.796 | +0.00% | +0.00% | +0.00% | +0.15% |
| cached-ledger / 2048 | bf16-row3 | 65.881 | +0.13% | +0.14% | +0.18% | +0.15% |

Raw runs

- [stock / 20261007T014147Z-m5-bf16-threshold-1-stock](../20261007T014147Z-m5-bf16-threshold-1-stock/result.json)
- [bf16-row3 / 20261007T014315Z-m5-bf16-threshold-2-bf16-row3](../20261007T014315Z-m5-bf16-threshold-2-bf16-row3/result.json)
- [bf16-row3 / 20261007T014443Z-m5-bf16-threshold-3-bf16-row3](../20261007T014443Z-m5-bf16-threshold-3-bf16-row3/result.json)
- [stock / 20261007T014611Z-m5-bf16-threshold-4-stock](../20261007T014611Z-m5-bf16-threshold-4-stock/result.json)
