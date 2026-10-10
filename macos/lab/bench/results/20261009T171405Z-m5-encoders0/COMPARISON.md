# M5 experiment: encoders0

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
256 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | conv-direct | 40.669 | +0.00% | +0.00% | +0.00% | +0.04% |
| chinese / 56 | encoders0 | 38.390 | -5.60% | -5.75% | -1.71% | +0.04% |
| code / 48 | conv-direct | 59.442 | +0.00% | +0.00% | +0.00% | +0.13% |
| code / 48 | encoders0 | 56.135 | -5.56% | -5.71% | -1.79% | +0.13% |
| prose / 53 | conv-direct | 39.943 | +0.00% | +0.00% | +0.00% | -0.04% |
| prose / 53 | encoders0 | 37.750 | -5.49% | -5.62% | -1.80% | -0.04% |
| synthetic / 512 | conv-direct | 48.439 | +0.00% | +0.00% | +0.00% | -0.16% |
| synthetic / 512 | encoders0 | 45.767 | -5.52% | -5.08% | -0.84% | -0.16% |
| synthetic / 2048 | conv-direct | 49.812 | +0.00% | +0.00% | +0.00% | -0.14% |
| synthetic / 2048 | encoders0 | 47.270 | -5.10% | -3.28% | -0.40% | -0.14% |
| cached-ledger / 512 | conv-direct | 69.755 | +0.00% | +0.00% | +0.00% | -0.45% |
| cached-ledger / 512 | encoders0 | 66.551 | -4.59% | -3.56% | -1.52% | -0.45% |
| cached-ledger / 2048 | conv-direct | 63.896 | +0.00% | +0.00% | +0.00% | +0.30% |
| cached-ledger / 2048 | encoders0 | 60.270 | -5.68% | -3.82% | -1.37% | +0.30% |

Raw runs

- [conv-direct / 20261009T171421Z-m5-encoders0-1-conv-direct](../20261009T171421Z-m5-encoders0-1-conv-direct/result.json)
- [encoders0 / 20261009T171718Z-m5-encoders0-2-encoders0](../20261009T171718Z-m5-encoders0-2-encoders0/result.json)
- [encoders0 / 20261009T172022Z-m5-encoders0-3-encoders0](../20261009T172022Z-m5-encoders0-3-encoders0/result.json)
- [conv-direct / 20261009T172325Z-m5-encoders0-4-conv-direct](../20261009T172325Z-m5-encoders0-4-conv-direct/result.json)
