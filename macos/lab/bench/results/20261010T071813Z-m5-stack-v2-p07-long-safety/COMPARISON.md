# M5 experiment: stack-v2-p07-long-safety

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
256 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| code / 859 | conv-direct | 45.850 | +0.00% | +0.00% | +0.00% | -0.02% |
| code / 859 | small-reduce | 46.187 | +0.74% | +0.60% | +0.33% | -0.02% |
| prose / 1004 | conv-direct | 46.832 | +0.00% | +0.00% | +0.00% | -0.21% |
| prose / 1004 | small-reduce | 47.190 | +0.76% | +0.66% | +0.91% | -0.21% |
| cached-ledger / 512 | conv-direct | 70.109 | +0.00% | +0.00% | +0.00% | -0.16% |
| cached-ledger / 512 | small-reduce | 70.664 | +0.79% | +1.07% | +0.05% | -0.16% |
| cached-ledger / 2048 | conv-direct | 63.595 | +0.00% | +0.00% | +0.00% | -0.77% |
| cached-ledger / 2048 | small-reduce | 63.565 | -0.05% | +0.41% | -0.45% | -0.77% |

Raw runs

- [conv-direct / 20261010T071832Z-m5-stack-v2-p07-long-safety-1-conv-direct](../20261010T071832Z-m5-stack-v2-p07-long-safety-1-conv-direct/result.json)
- [small-reduce / 20261010T072014Z-m5-stack-v2-p07-long-safety-2-small-reduce](../20261010T072014Z-m5-stack-v2-p07-long-safety-2-small-reduce/result.json)
- [small-reduce / 20261010T072155Z-m5-stack-v2-p07-long-safety-3-small-reduce](../20261010T072155Z-m5-stack-v2-p07-long-safety-3-small-reduce/result.json)
- [conv-direct / 20261010T072335Z-m5-stack-v2-p07-long-safety-4-conv-direct](../20261010T072335Z-m5-stack-v2-p07-long-safety-4-conv-direct/result.json)
