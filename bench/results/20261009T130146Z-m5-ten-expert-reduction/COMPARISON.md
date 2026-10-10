# M5 experiment: ten-expert-reduction

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
256 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | conv-direct | 40.636 | +0.00% | +0.00% | +0.00% | +0.09% |
| chinese / 56 | reduce10 | 41.007 | +0.91% | +0.89% | +0.50% | +0.09% |
| code / 48 | conv-direct | 59.415 | +0.00% | +0.00% | +0.00% | -0.03% |
| code / 48 | reduce10 | 59.948 | +0.90% | +0.94% | +0.94% | -0.03% |
| prose / 53 | conv-direct | 39.845 | +0.00% | +0.00% | +0.00% | +0.04% |
| prose / 53 | reduce10 | 40.262 | +1.05% | +1.02% | +1.08% | +0.04% |
| synthetic / 512 | conv-direct | 48.462 | +0.00% | +0.00% | +0.00% | -0.26% |
| synthetic / 512 | reduce10 | 48.880 | +0.86% | +0.87% | +2.43% | -0.26% |
| synthetic / 2048 | conv-direct | 49.813 | +0.00% | +0.00% | +0.00% | -0.12% |
| synthetic / 2048 | reduce10 | 50.246 | +0.87% | +0.90% | +2.07% | -0.12% |
| cached-ledger / 512 | conv-direct | 70.050 | +0.00% | +0.00% | +0.00% | +2.55% |
| cached-ledger / 512 | reduce10 | 70.630 | +0.83% | +1.01% | +0.85% | +2.55% |
| cached-ledger / 2048 | conv-direct | 63.697 | +0.00% | +0.00% | +0.00% | +0.72% |
| cached-ledger / 2048 | reduce10 | 63.846 | +0.23% | +0.77% | +0.50% | +0.72% |

Raw runs

- [conv-direct / 20261009T130203Z-m5-ten-expert-reduction-1-conv-direct](../20261009T130203Z-m5-ten-expert-reduction-1-conv-direct/result.json)
- [reduce10 / 20261009T131007Z-m5-ten-expert-reduction-2-reduce10](../20261009T131007Z-m5-ten-expert-reduction-2-reduce10/result.json)
- [reduce10 / 20261009T131300Z-m5-ten-expert-reduction-3-reduce10](../20261009T131300Z-m5-ten-expert-reduction-3-reduce10/result.json)
- [conv-direct / 20261009T131551Z-m5-ten-expert-reduction-4-conv-direct](../20261009T131551Z-m5-ten-expert-reduction-4-conv-direct/result.json)
