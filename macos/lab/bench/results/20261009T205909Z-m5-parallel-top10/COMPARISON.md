# M5 experiment: parallel-top10

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
256 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| code / 48 | conv-direct | 59.379 | +0.00% | +0.00% | +0.00% | +0.28% |
| code / 48 | top10 | 60.028 | +1.09% | +0.96% | -0.97% | +0.28% |
| prose / 53 | conv-direct | 39.938 | +0.00% | +0.00% | +0.00% | +0.15% |
| prose / 53 | top10 | 40.314 | +0.94% | +0.83% | -1.01% | +0.15% |
| synthetic / 512 | conv-direct | 48.432 | +0.00% | +0.00% | +0.00% | -0.31% |
| synthetic / 512 | top10 | 48.886 | +0.94% | +0.71% | -0.97% | -0.31% |
| synthetic / 2048 | conv-direct | 49.868 | +0.00% | +0.00% | +0.00% | +0.07% |
| synthetic / 2048 | top10 | 50.287 | +0.84% | -0.20% | -1.50% | +0.07% |
| cached-ledger / 512 | conv-direct | 70.840 | +0.00% | +0.00% | +0.00% | -0.20% |
| cached-ledger / 512 | top10 | 70.647 | -0.27% | -0.19% | +0.14% | -0.20% |
| cached-ledger / 2048 | conv-direct | 63.868 | +0.00% | +0.00% | +0.00% | +0.97% |
| cached-ledger / 2048 | top10 | 63.969 | +0.16% | +0.62% | +0.79% | +0.97% |

Raw runs

- [conv-direct / 20261009T205924Z-m5-parallel-top10-1-conv-direct](../20261009T205924Z-m5-parallel-top10-1-conv-direct/result.json)
- [top10 / 20261009T210152Z-m5-parallel-top10-2-top10](../20261009T210152Z-m5-parallel-top10-2-top10/result.json)
- [top10 / 20261009T210419Z-m5-parallel-top10-3-top10](../20261009T210419Z-m5-parallel-top10-3-top10/result.json)
- [conv-direct / 20261009T210646Z-m5-parallel-top10-4-conv-direct](../20261009T210646Z-m5-parallel-top10-4-conv-direct/result.json)
