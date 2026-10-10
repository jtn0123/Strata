# M5 experiment: stack-v2-p07-short-answer-safety

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
32 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| code / 48 | conv-direct | 64.135 | +0.00% | +0.00% | +0.00% | +0.59% |
| code / 48 | small-reduce | 64.561 | +0.66% | +0.41% | +0.31% | +0.59% |
| prose / 53 | conv-direct | 52.462 | +0.00% | +0.00% | +0.00% | -0.03% |
| prose / 53 | small-reduce | 52.864 | +0.77% | +0.69% | +0.44% | -0.03% |
| cached-ledger / 512 | conv-direct | 71.574 | +0.00% | +0.00% | +0.00% | +2.33% |
| cached-ledger / 512 | small-reduce | 72.520 | +1.32% | +0.62% | -0.18% | +2.33% |
| cached-ledger / 2048 | conv-direct | 66.181 | +0.00% | +0.00% | +0.00% | -2.23% |
| cached-ledger / 2048 | small-reduce | 67.430 | +1.89% | +1.32% | -0.53% | -2.23% |

Raw runs

- [conv-direct / 20261010T072533Z-m5-stack-v2-p07-short-answer-safety-1-conv-direct](../20261010T072533Z-m5-stack-v2-p07-short-answer-safety-1-conv-direct/result.json)
- [small-reduce / 20261010T072624Z-m5-stack-v2-p07-short-answer-safety-2-small-reduce](../20261010T072624Z-m5-stack-v2-p07-short-answer-safety-2-small-reduce/result.json)
- [small-reduce / 20261010T072711Z-m5-stack-v2-p07-short-answer-safety-3-small-reduce](../20261010T072711Z-m5-stack-v2-p07-short-answer-safety-3-small-reduce/result.json)
- [conv-direct / 20261010T072759Z-m5-stack-v2-p07-short-answer-safety-4-conv-direct](../20261010T072759Z-m5-stack-v2-p07-short-answer-safety-4-conv-direct/result.json)
