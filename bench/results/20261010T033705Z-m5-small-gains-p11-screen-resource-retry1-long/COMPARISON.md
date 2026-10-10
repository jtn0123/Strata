# M5 experiment: small-gains-p11-screen-resource-retry1-long

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
256 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| code / 859 | conv-direct | 45.747 | +0.00% | +0.00% | +0.00% | -0.59% |
| code / 859 | small-compact | 45.692 | -0.12% | -0.08% | -0.65% | -0.59% |
| prose / 1004 | conv-direct | 46.869 | +0.00% | +0.00% | +0.00% | -0.18% |
| prose / 1004 | small-compact | 46.820 | -0.10% | -0.33% | -1.06% | -0.18% |
| cached-ledger / 512 | conv-direct | 70.639 | +0.00% | +0.00% | +0.00% | -0.07% |
| cached-ledger / 512 | small-compact | 70.605 | -0.05% | -0.38% | -0.99% | -0.07% |
| cached-ledger / 2048 | conv-direct | 63.531 | +0.00% | +0.00% | +0.00% | +0.16% |
| cached-ledger / 2048 | small-compact | 63.291 | -0.38% | +0.88% | +1.68% | +0.16% |

Raw runs

- [conv-direct / 20261010T033721Z-m5-small-gains-p11-screen-resource-retry1-long-1-conv-direct](../20261010T033721Z-m5-small-gains-p11-screen-resource-retry1-long-1-conv-direct/result.json)
- [small-compact / 20261010T033908Z-m5-small-gains-p11-screen-resource-retry1-long-2-small-compact](../20261010T033908Z-m5-small-gains-p11-screen-resource-retry1-long-2-small-compact/result.json)
- [small-compact / 20261010T034048Z-m5-small-gains-p11-screen-resource-retry1-long-3-small-compact](../20261010T034048Z-m5-small-gains-p11-screen-resource-retry1-long-3-small-compact/result.json)
- [conv-direct / 20261010T034228Z-m5-small-gains-p11-screen-resource-retry1-long-4-conv-direct](../20261010T034228Z-m5-small-gains-p11-screen-resource-retry1-long-4-conv-direct/result.json)
