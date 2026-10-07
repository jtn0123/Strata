# M5 experiment: tensor-writing

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
128 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | on | 39.835 | +0.00% | +0.00% | +0.00% | -0.23% |
| chinese / 56 | off | 35.515 | -10.84% | -14.09% | -35.03% | -0.23% |
| code / 48 | on | 56.074 | +0.00% | +0.00% | +0.00% | +0.05% |
| code / 48 | off | 52.292 | -6.75% | -10.23% | -34.21% | +0.05% |
| prose / 53 | on | 42.503 | +0.00% | +0.00% | +0.00% | -0.13% |
| prose / 53 | off | 42.497 | -0.01% | -3.16% | -35.19% | -0.13% |
| synthetic / 512 | on | 48.014 | +0.00% | +0.00% | +0.00% | -0.19% |
| synthetic / 512 | off | 48.354 | +0.71% | -19.38% | -79.01% | -0.19% |
| synthetic / 2048 | on | 49.750 | +0.00% | +0.00% | +0.00% | +0.28% |
| synthetic / 2048 | off | 47.624 | -4.27% | -44.56% | -71.44% | +0.28% |
| cached-ledger / 512 | on | 64.926 | +0.00% | +0.00% | +0.00% | +3.54% |
| cached-ledger / 512 | off | 64.637 | -0.45% | -14.29% | -32.77% | +3.54% |
| cached-ledger / 2048 | on | 63.872 | +0.00% | +0.00% | +0.00% | +5.20% |
| cached-ledger / 2048 | off | 63.585 | -0.45% | -13.35% | -29.41% | +5.20% |

Raw runs

- [on / 20261007T004017Z-m5-tensor-writing-1-on](../20261007T004017Z-m5-tensor-writing-1-on/result.json)
- [off / 20261007T004147Z-m5-tensor-writing-2-off](../20261007T004147Z-m5-tensor-writing-2-off/result.json)
- [off / 20261007T004345Z-m5-tensor-writing-3-off](../20261007T004345Z-m5-tensor-writing-3-off/result.json)
- [on / 20261007T004540Z-m5-tensor-writing-4-on](../20261007T004540Z-m5-tensor-writing-4-on/result.json)
