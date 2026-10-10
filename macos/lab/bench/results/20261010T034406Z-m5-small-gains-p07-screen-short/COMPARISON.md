# M5 experiment: small-gains-p07-screen-short

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
256 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| code / 48 | conv-direct | 59.687 | +0.00% | +0.00% | +0.00% | -0.01% |
| code / 48 | small-reduce | 60.053 | +0.61% | +0.60% | +0.38% | -0.01% |
| prose / 53 | conv-direct | 40.106 | +0.00% | +0.00% | +0.00% | +0.11% |
| prose / 53 | small-reduce | 40.329 | +0.56% | +0.60% | +0.42% | +0.11% |
| cached-ledger / 512 | conv-direct | 72.015 | +0.00% | +0.00% | +0.00% | +0.62% |
| cached-ledger / 512 | small-reduce | 71.590 | -0.59% | +0.10% | +0.30% | +0.62% |
| cached-ledger / 2048 | conv-direct | 64.938 | +0.00% | +0.00% | +0.00% | +6.01% |
| cached-ledger / 2048 | small-reduce | 65.468 | +0.82% | -0.67% | -0.13% | +6.01% |

Raw runs

- [conv-direct / 20261010T034423Z-m5-small-gains-p07-screen-short-1-conv-direct](../20261010T034423Z-m5-small-gains-p07-screen-short-1-conv-direct/result.json)
- [small-reduce / 20261010T034547Z-m5-small-gains-p07-screen-short-2-small-reduce](../20261010T034547Z-m5-small-gains-p07-screen-short-2-small-reduce/result.json)
- [small-reduce / 20261010T034710Z-m5-small-gains-p07-screen-short-3-small-reduce](../20261010T034710Z-m5-small-gains-p07-screen-short-3-small-reduce/result.json)
- [conv-direct / 20261010T034832Z-m5-small-gains-p07-screen-short-4-conv-direct](../20261010T034832Z-m5-small-gains-p07-screen-short-4-conv-direct/result.json)
