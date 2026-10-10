# M5 experiment: qsa-all-pools

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
256 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| code / 48 | conv-direct | 59.388 | +0.00% | +0.00% | +0.00% | -0.61% |
| code / 48 | qsa-all-pools | 59.402 | +0.02% | +0.03% | -0.96% | -0.61% |
| prose / 53 | conv-direct | 39.872 | +0.00% | +0.00% | +0.00% | -0.07% |
| prose / 53 | qsa-all-pools | 39.758 | -0.28% | -0.38% | -1.18% | -0.07% |
| synthetic / 512 | conv-direct | 48.416 | +0.00% | +0.00% | +0.00% | -0.19% |
| synthetic / 512 | qsa-all-pools | 48.406 | -0.02% | -0.16% | -1.05% | -0.19% |
| synthetic / 2048 | conv-direct | 49.857 | +0.00% | +0.00% | +0.00% | +0.07% |
| synthetic / 2048 | qsa-all-pools | 49.770 | -0.17% | +0.07% | +0.52% | +0.07% |
| cached-ledger / 512 | conv-direct | 70.063 | +0.00% | +0.00% | +0.00% | +0.13% |
| cached-ledger / 512 | qsa-all-pools | 70.319 | +0.37% | +0.03% | -0.36% | +0.13% |
| cached-ledger / 2048 | conv-direct | 63.723 | +0.00% | +0.00% | +0.00% | +0.65% |
| cached-ledger / 2048 | qsa-all-pools | 63.973 | +0.39% | -1.53% | -4.17% | +0.65% |

Raw runs

- [conv-direct / 20261009T215022Z-m5-qsa-all-pools-1-conv-direct](../20261009T215022Z-m5-qsa-all-pools-1-conv-direct/result.json)
- [qsa-all-pools / 20261009T215247Z-m5-qsa-all-pools-2-qsa-all-pools](../20261009T215247Z-m5-qsa-all-pools-2-qsa-all-pools/result.json)
- [qsa-all-pools / 20261009T215516Z-m5-qsa-all-pools-3-qsa-all-pools](../20261009T215516Z-m5-qsa-all-pools-3-qsa-all-pools/result.json)
- [conv-direct / 20261009T215742Z-m5-qsa-all-pools-4-conv-direct](../20261009T215742Z-m5-qsa-all-pools-4-conv-direct/result.json)
