# M5 experiment: draftcap-tail

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
256 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | conv-direct | 40.660 | +0.00% | +0.00% | +0.00% | +0.13% |
| chinese / 56 | draftcap-tail | 40.665 | +0.01% | -0.02% | -0.59% | +0.13% |
| code / 48 | conv-direct | 59.482 | +0.00% | +0.00% | +0.00% | -0.13% |
| code / 48 | draftcap-tail | 59.464 | -0.03% | -0.03% | -0.21% | -0.13% |
| prose / 53 | conv-direct | 39.931 | +0.00% | +0.00% | +0.00% | +0.23% |
| prose / 53 | draftcap-tail | 40.007 | +0.19% | +0.16% | -1.00% | +0.23% |
| synthetic / 512 | conv-direct | 48.474 | +0.00% | +0.00% | +0.00% | +0.01% |
| synthetic / 512 | draftcap-tail | 48.459 | -0.03% | -0.16% | -1.75% | +0.01% |
| synthetic / 2048 | conv-direct | 49.892 | +0.00% | +0.00% | +0.00% | -0.12% |
| synthetic / 2048 | draftcap-tail | 49.970 | +0.16% | -0.36% | -1.02% | -0.12% |
| cached-ledger / 512 | conv-direct | 69.432 | +0.00% | +0.00% | +0.00% | +2.51% |
| cached-ledger / 512 | draftcap-tail | 70.110 | +0.98% | +0.80% | +0.49% | +2.51% |
| cached-ledger / 2048 | conv-direct | 64.191 | +0.00% | +0.00% | +0.00% | -0.39% |
| cached-ledger / 2048 | draftcap-tail | 63.929 | -0.41% | -0.47% | +0.12% | -0.39% |

Raw runs

- [conv-direct / 20261009T193703Z-m5-draftcap-tail-1-conv-direct](../20261009T193703Z-m5-draftcap-tail-1-conv-direct/result.json)
- [draftcap-tail / 20261009T194000Z-m5-draftcap-tail-2-draftcap-tail](../20261009T194000Z-m5-draftcap-tail-2-draftcap-tail/result.json)
- [draftcap-tail / 20261009T194257Z-m5-draftcap-tail-3-draftcap-tail](../20261009T194257Z-m5-draftcap-tail-3-draftcap-tail/result.json)
- [conv-direct / 20261009T194552Z-m5-draftcap-tail-4-conv-direct](../20261009T194552Z-m5-draftcap-tail-4-conv-direct/result.json)
