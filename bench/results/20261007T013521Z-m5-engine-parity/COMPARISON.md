# M5 experiment: engine-parity

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
128 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | mtp-mma | 40.069 | +0.00% | +0.00% | +0.00% | +0.20% |
| chinese / 56 | m5-lab | 40.031 | -0.10% | -0.20% | -1.16% | +0.20% |
| code / 48 | mtp-mma | 56.447 | +0.00% | +0.00% | +0.00% | -0.19% |
| code / 48 | m5-lab | 56.356 | -0.16% | -0.24% | -0.86% | -0.19% |
| prose / 53 | mtp-mma | 42.836 | +0.00% | +0.00% | +0.00% | -0.04% |
| prose / 53 | m5-lab | 42.827 | -0.02% | -0.12% | -1.01% | -0.04% |
| synthetic / 512 | mtp-mma | 49.014 | +0.00% | +0.00% | +0.00% | -0.32% |
| synthetic / 512 | m5-lab | 48.943 | -0.14% | -0.62% | -1.91% | -0.32% |
| synthetic / 2048 | mtp-mma | 49.967 | +0.00% | +0.00% | +0.00% | -0.04% |
| synthetic / 2048 | m5-lab | 49.883 | -0.17% | -1.14% | -1.71% | -0.04% |
| cached-ledger / 512 | mtp-mma | 66.067 | +0.00% | +0.00% | +0.00% | +0.68% |
| cached-ledger / 512 | m5-lab | 66.030 | -0.06% | -0.21% | -0.45% | +0.68% |
| cached-ledger / 2048 | mtp-mma | 65.805 | +0.00% | +0.00% | +0.00% | -0.06% |
| cached-ledger / 2048 | m5-lab | 65.737 | -0.10% | -0.19% | -0.31% | -0.06% |

Raw runs

- [mtp-mma / 20261007T013534Z-m5-engine-parity-1-mtp-mma](../20261007T013534Z-m5-engine-parity-1-mtp-mma/result.json)
- [m5-lab / 20261007T013703Z-m5-engine-parity-2-m5-lab](../20261007T013703Z-m5-engine-parity-2-m5-lab/result.json)
- [m5-lab / 20261007T013831Z-m5-engine-parity-3-m5-lab](../20261007T013831Z-m5-engine-parity-3-m5-lab/result.json)
- [mtp-mma / 20261007T014000Z-m5-engine-parity-4-mtp-mma](../20261007T014000Z-m5-engine-parity-4-mtp-mma/result.json)
