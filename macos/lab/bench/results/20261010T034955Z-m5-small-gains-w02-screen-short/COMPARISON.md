# M5 experiment: small-gains-w02-screen-short

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
256 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| code / 48 | conv-direct | 59.689 | +0.00% | +0.00% | +0.00% | +0.04% |
| code / 48 | small-top10 | 60.126 | +0.73% | +0.58% | -1.15% | +0.04% |
| prose / 53 | conv-direct | 40.095 | +0.00% | +0.00% | +0.00% | -0.03% |
| prose / 53 | small-top10 | 40.361 | +0.66% | +0.51% | -1.38% | -0.03% |
| cached-ledger / 512 | conv-direct | 70.587 | +0.00% | +0.00% | +0.00% | +2.73% |
| cached-ledger / 512 | small-top10 | 72.162 | +2.23% | -0.16% | -1.34% | +2.73% |
| cached-ledger / 2048 | conv-direct | 66.870 | +0.00% | +0.00% | +0.00% | +0.03% |
| cached-ledger / 2048 | small-top10 | 67.422 | +0.83% | +0.59% | +0.28% | +0.03% |

Raw runs

- [conv-direct / 20261010T035011Z-m5-small-gains-w02-screen-short-1-conv-direct](../20261010T035011Z-m5-small-gains-w02-screen-short-1-conv-direct/result.json)
- [small-top10 / 20261010T035135Z-m5-small-gains-w02-screen-short-2-small-top10](../20261010T035135Z-m5-small-gains-w02-screen-short-2-small-top10/result.json)
- [small-top10 / 20261010T035258Z-m5-small-gains-w02-screen-short-3-small-top10](../20261010T035258Z-m5-small-gains-w02-screen-short-3-small-top10/result.json)
- [conv-direct / 20261010T035421Z-m5-small-gains-w02-screen-short-4-conv-direct](../20261010T035421Z-m5-small-gains-w02-screen-short-4-conv-direct/result.json)
