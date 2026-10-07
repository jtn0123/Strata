# M5 experiment: tensor-followup

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
128 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | on | 35.674 | +0.00% | +0.00% | +0.00% | +0.57% |
| chinese / 56 | off | 30.806 | -13.65% | -17.50% | -36.57% | +0.57% |
| code / 48 | on | 56.537 | +0.00% | +0.00% | +0.00% | +0.53% |
| code / 48 | off | 52.131 | -7.79% | -11.41% | -34.83% | +0.53% |
| prose / 53 | on | 41.836 | +0.00% | +0.00% | +0.00% | +0.19% |
| prose / 53 | off | 40.546 | -3.08% | -5.98% | -35.63% | +0.19% |
| synthetic / 512 | on | 45.794 | +0.00% | +0.00% | +0.00% | +1.91% |
| synthetic / 512 | off | 50.353 | +9.96% | -12.42% | -77.49% | +1.91% |
| synthetic / 2048 | on | 49.539 | +0.00% | +0.00% | +0.00% | +1.31% |
| synthetic / 2048 | off | 43.825 | -11.54% | -47.54% | -71.06% | +1.31% |
| cached-ledger / 512 | on | 67.388 | +0.00% | +0.00% | +0.00% | +3.50% |
| cached-ledger / 512 | off | 68.529 | +1.69% | -13.12% | -31.86% | +3.50% |
| cached-ledger / 2048 | on | 67.783 | +0.00% | +0.00% | +0.00% | +3.23% |
| cached-ledger / 2048 | off | 69.373 | +2.35% | -12.23% | -29.37% | +3.23% |

Raw runs

- [on / 20261007T004723Z-m5-tensor-followup-1-on](../20261007T004723Z-m5-tensor-followup-1-on/result.json)
- [off / 20261007T004855Z-m5-tensor-followup-2-off](../20261007T004855Z-m5-tensor-followup-2-off/result.json)
- [off / 20261007T005054Z-m5-tensor-followup-3-off](../20261007T005054Z-m5-tensor-followup-3-off/result.json)
- [on / 20261007T005250Z-m5-tensor-followup-4-on](../20261007T005250Z-m5-tensor-followup-4-on/result.json)
