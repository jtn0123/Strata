# M5 experiment: small-gains-p07-confirmation-short

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
256 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| code / 48 | conv-direct | 59.711 | +0.00% | +0.00% | +0.00% | +0.03% |
| code / 48 | small-reduce | 60.095 | +0.64% | +0.60% | +0.28% | +0.03% |
| prose / 53 | conv-direct | 40.058 | +0.00% | +0.00% | +0.00% | +0.05% |
| prose / 53 | small-reduce | 40.389 | +0.83% | +0.77% | -0.05% | +0.05% |
| cached-ledger / 512 | conv-direct | 70.412 | +0.00% | +0.00% | +0.00% | +3.13% |
| cached-ledger / 512 | small-reduce | 71.231 | +1.16% | +0.30% | -1.07% | +3.13% |
| cached-ledger / 2048 | conv-direct | 66.828 | +0.00% | +0.00% | +0.00% | -0.79% |
| cached-ledger / 2048 | small-reduce | 67.149 | +0.48% | +0.75% | +0.86% | -0.79% |

Raw runs

- [conv-direct / 20261010T035559Z-m5-small-gains-p07-confirmation-short-1-conv-direct](../20261010T035559Z-m5-small-gains-p07-confirmation-short-1-conv-direct/result.json)
- [small-reduce / 20261010T035725Z-m5-small-gains-p07-confirmation-short-2-small-reduce](../20261010T035725Z-m5-small-gains-p07-confirmation-short-2-small-reduce/result.json)
- [small-reduce / 20261010T035849Z-m5-small-gains-p07-confirmation-short-3-small-reduce](../20261010T035849Z-m5-small-gains-p07-confirmation-short-3-small-reduce/result.json)
- [conv-direct / 20261010T040013Z-m5-small-gains-p07-confirmation-short-4-conv-direct](../20261010T040013Z-m5-small-gains-p07-confirmation-short-4-conv-direct/result.json)
