# M5 experiment: encoders2

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
256 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | conv-direct | 40.607 | +0.00% | +0.00% | +0.00% | +0.03% |
| chinese / 56 | encoders2 | 40.583 | -0.06% | -0.06% | +0.83% | +0.03% |
| code / 48 | conv-direct | 59.467 | +0.00% | +0.00% | +0.00% | -0.06% |
| code / 48 | encoders2 | 59.325 | -0.24% | -0.21% | +0.46% | -0.06% |
| prose / 53 | conv-direct | 39.949 | +0.00% | +0.00% | +0.00% | +0.05% |
| prose / 53 | encoders2 | 39.882 | -0.17% | -0.12% | +0.62% | +0.05% |
| synthetic / 512 | conv-direct | 48.449 | +0.00% | +0.00% | +0.00% | +0.04% |
| synthetic / 512 | encoders2 | 48.342 | -0.22% | -0.37% | -1.40% | +0.04% |
| synthetic / 2048 | conv-direct | 49.818 | +0.00% | +0.00% | +0.00% | -0.28% |
| synthetic / 2048 | encoders2 | 49.860 | +0.08% | -0.32% | -0.69% | -0.28% |
| cached-ledger / 512 | conv-direct | 69.985 | +0.00% | +0.00% | +0.00% | +0.03% |
| cached-ledger / 512 | encoders2 | 70.119 | +0.19% | +0.33% | +0.34% | +0.03% |
| cached-ledger / 2048 | conv-direct | 64.145 | +0.00% | +0.00% | +0.00% | -0.26% |
| cached-ledger / 2048 | encoders2 | 63.317 | -1.29% | -0.61% | +0.05% | -0.26% |

Raw runs

- [conv-direct / 20261009T172830Z-m5-encoders2-1-conv-direct](../20261009T172830Z-m5-encoders2-1-conv-direct/result.json)
- [encoders2 / 20261009T173129Z-m5-encoders2-2-encoders2](../20261009T173129Z-m5-encoders2-2-encoders2/result.json)
- [encoders2 / 20261009T173426Z-m5-encoders2-3-encoders2](../20261009T173426Z-m5-encoders2-3-encoders2/result.json)
- [conv-direct / 20261009T173721Z-m5-encoders2-4-conv-direct](../20261009T173721Z-m5-encoders2-4-conv-direct/result.json)
