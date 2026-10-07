# M5 experiment: confidence-followup

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
128 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | 0.0 | 35.792 | +0.00% | +0.00% | +0.00% | +0.26% |
| chinese / 56 | 0.2 | 36.019 | +0.63% | +0.54% | -0.35% | +0.26% |
| chinese / 56 | 0.4 | 37.301 | +4.22% | +3.72% | -0.23% | +0.26% |
| code / 48 | 0.0 | 56.575 | +0.00% | +0.00% | +0.00% | +0.11% |
| code / 48 | 0.2 | 56.603 | +0.05% | -0.00% | -1.63% | +0.11% |
| code / 48 | 0.4 | 54.989 | -2.80% | -2.57% | +0.08% | +0.11% |
| prose / 53 | 0.0 | 41.836 | +0.00% | +0.00% | +0.00% | +0.00% |
| prose / 53 | 0.2 | 42.398 | +1.34% | +1.21% | -0.10% | +0.00% |
| prose / 53 | 0.4 | 41.804 | -0.08% | -0.22% | -0.13% | +0.00% |
| synthetic / 512 | 0.0 | 46.218 | +0.00% | +0.00% | +0.00% | +0.53% |
| synthetic / 512 | 0.2 | 46.198 | -0.04% | -0.16% | -0.60% | +0.53% |
| synthetic / 512 | 0.4 | 44.355 | -4.03% | -3.23% | -0.20% | +0.53% |
| synthetic / 2048 | 0.0 | 49.631 | +0.00% | +0.00% | +0.00% | -0.01% |
| synthetic / 2048 | 0.2 | 49.666 | +0.07% | -0.22% | -0.42% | -0.01% |
| synthetic / 2048 | 0.4 | 46.274 | -6.76% | -3.07% | -0.27% | -0.01% |
| cached-ledger / 512 | 0.0 | 68.974 | +0.00% | +0.00% | +0.00% | +0.43% |
| cached-ledger / 512 | 0.2 | 68.938 | -0.05% | +0.02% | -0.03% | +0.43% |
| cached-ledger / 512 | 0.4 | 68.876 | -0.14% | -0.10% | -0.29% | +0.43% |
| cached-ledger / 2048 | 0.0 | 69.418 | +0.00% | +0.00% | +0.00% | +0.25% |
| cached-ledger / 2048 | 0.2 | 69.418 | +0.00% | -0.15% | -0.30% | +0.25% |
| cached-ledger / 2048 | 0.4 | 63.546 | -8.46% | -5.46% | -0.10% | +0.25% |

Raw runs

- [0.0 / 20261007T035423Z-m5-confidence-followup-1-0.0](../20261007T035423Z-m5-confidence-followup-1-0.0/result.json)
- [0.2 / 20261007T035554Z-m5-confidence-followup-2-0.2](../20261007T035554Z-m5-confidence-followup-2-0.2/result.json)
- [0.4 / 20261007T035724Z-m5-confidence-followup-3-0.4](../20261007T035724Z-m5-confidence-followup-3-0.4/result.json)
- [0.4 / 20261007T035855Z-m5-confidence-followup-4-0.4](../20261007T035855Z-m5-confidence-followup-4-0.4/result.json)
- [0.2 / 20261007T040026Z-m5-confidence-followup-5-0.2](../20261007T040026Z-m5-confidence-followup-5-0.2/result.json)
- [0.0 / 20261007T040156Z-m5-confidence-followup-6-0.0](../20261007T040156Z-m5-confidence-followup-6-0.0/result.json)
