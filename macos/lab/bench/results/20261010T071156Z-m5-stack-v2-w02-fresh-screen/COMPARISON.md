# M5 experiment: stack-v2-w02-fresh-screen

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
256 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| code / 48 | conv-direct | 59.720 | +0.00% | +0.00% | +0.00% | +0.02% |
| code / 48 | small-top10 | 60.069 | +0.58% | +0.52% | -1.40% | +0.02% |
| prose / 53 | conv-direct | 40.060 | +0.00% | +0.00% | +0.00% | -0.04% |
| prose / 53 | small-top10 | 40.347 | +0.72% | +0.73% | -1.64% | -0.04% |
| cached-ledger / 512 | conv-direct | 70.402 | +0.00% | +0.00% | +0.00% | -0.03% |
| cached-ledger / 512 | small-top10 | 70.970 | +0.81% | +0.34% | -0.53% | -0.03% |
| cached-ledger / 2048 | conv-direct | 64.291 | +0.00% | +0.00% | +0.00% | -0.12% |
| cached-ledger / 2048 | small-top10 | 64.358 | +0.10% | +1.23% | +2.13% | -0.12% |

Raw runs

- [conv-direct / 20261010T071215Z-m5-stack-v2-w02-fresh-screen-1-conv-direct](../20261010T071215Z-m5-stack-v2-w02-fresh-screen-1-conv-direct/result.json)
- [small-top10 / 20261010T071351Z-m5-stack-v2-w02-fresh-screen-2-small-top10](../20261010T071351Z-m5-stack-v2-w02-fresh-screen-2-small-top10/result.json)
- [small-top10 / 20261010T071520Z-m5-stack-v2-w02-fresh-screen-3-small-top10](../20261010T071520Z-m5-stack-v2-w02-fresh-screen-3-small-top10/result.json)
- [conv-direct / 20261010T071648Z-m5-stack-v2-w02-fresh-screen-4-conv-direct](../20261010T071648Z-m5-stack-v2-w02-fresh-screen-4-conv-direct/result.json)
