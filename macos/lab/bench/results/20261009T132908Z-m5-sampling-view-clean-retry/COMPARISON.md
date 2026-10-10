# M5 experiment: sampling-view-clean-retry

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
256 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | conv-direct | 40.687 | +0.00% | +0.00% | +0.00% | -0.14% |
| chinese / 56 | sampling-view | 40.651 | -0.09% | -0.08% | +0.51% | -0.14% |
| code / 48 | conv-direct | 59.523 | +0.00% | +0.00% | +0.00% | -0.23% |
| code / 48 | sampling-view | 59.481 | -0.07% | -0.10% | -0.39% | -0.23% |
| prose / 53 | conv-direct | 39.983 | +0.00% | +0.00% | +0.00% | -0.09% |
| prose / 53 | sampling-view | 39.977 | -0.01% | +0.01% | +0.02% | -0.09% |
| synthetic / 512 | conv-direct | 48.471 | +0.00% | +0.00% | +0.00% | -0.33% |
| synthetic / 512 | sampling-view | 48.391 | -0.17% | -0.32% | -0.77% | -0.33% |
| synthetic / 2048 | conv-direct | 49.904 | +0.00% | +0.00% | +0.00% | -0.29% |
| synthetic / 2048 | sampling-view | 49.881 | -0.05% | -0.24% | -0.44% | -0.29% |
| cached-ledger / 512 | conv-direct | 69.783 | +0.00% | +0.00% | +0.00% | +0.62% |
| cached-ledger / 512 | sampling-view | 70.152 | +0.53% | +1.61% | -0.07% | +0.62% |
| cached-ledger / 2048 | conv-direct | 63.519 | +0.00% | +0.00% | +0.00% | +0.62% |
| cached-ledger / 2048 | sampling-view | 63.758 | +0.38% | +0.12% | +0.19% | +0.62% |

Raw runs

- [conv-direct / 20261009T132924Z-m5-sampling-view-clean-retry-1-conv-direct](../20261009T132924Z-m5-sampling-view-clean-retry-1-conv-direct/result.json)
- [sampling-view / 20261009T133220Z-m5-sampling-view-clean-retry-2-sampling-view](../20261009T133220Z-m5-sampling-view-clean-retry-2-sampling-view/result.json)
- [sampling-view / 20261009T133517Z-m5-sampling-view-clean-retry-3-sampling-view](../20261009T133517Z-m5-sampling-view-clean-retry-3-sampling-view/result.json)
- [conv-direct / 20261009T133814Z-m5-sampling-view-clean-retry-4-conv-direct](../20261009T133814Z-m5-sampling-view-clean-retry-4-conv-direct/result.json)
