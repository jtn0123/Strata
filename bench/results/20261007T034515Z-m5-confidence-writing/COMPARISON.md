# M5 experiment: confidence-writing

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
128 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | 0.0 | 40.075 | +0.00% | +0.00% | +0.00% | +0.27% |
| chinese / 56 | 0.2 | 40.268 | +0.48% | +0.44% | -0.35% | +0.27% |
| chinese / 56 | 0.4 | 39.542 | -1.33% | -1.22% | +0.02% | +0.27% |
| code / 48 | 0.0 | 56.364 | +0.00% | +0.00% | +0.00% | +0.11% |
| code / 48 | 0.2 | 56.344 | -0.03% | -0.06% | -1.00% | +0.11% |
| code / 48 | 0.4 | 56.040 | -0.57% | -0.52% | -0.17% | +0.11% |
| prose / 53 | 0.0 | 42.826 | +0.00% | +0.00% | +0.00% | +0.23% |
| prose / 53 | 0.2 | 43.181 | +0.83% | +0.64% | -0.89% | +0.23% |
| prose / 53 | 0.4 | 43.608 | +1.83% | +1.58% | -0.31% | +0.23% |
| synthetic / 512 | 0.0 | 49.020 | +0.00% | +0.00% | +0.00% | -0.43% |
| synthetic / 512 | 0.2 | 48.940 | -0.16% | -0.74% | -2.46% | -0.43% |
| synthetic / 512 | 0.4 | 45.835 | -6.50% | -5.80% | -2.74% | -0.43% |
| synthetic / 2048 | 0.0 | 49.954 | +0.00% | +0.00% | +0.00% | +0.62% |
| synthetic / 2048 | 0.2 | 49.927 | -0.05% | -0.62% | -1.35% | +0.62% |
| synthetic / 2048 | 0.4 | 48.096 | -3.72% | -2.32% | -1.62% | +0.62% |
| cached-ledger / 512 | 0.0 | 65.007 | +0.00% | +0.00% | +0.00% | +4.37% |
| cached-ledger / 512 | 0.2 | 66.003 | +1.53% | +0.70% | -0.11% | +4.37% |
| cached-ledger / 512 | 0.4 | 66.119 | +1.71% | +0.65% | -0.11% | +4.37% |
| cached-ledger / 2048 | 0.0 | 64.086 | +0.00% | +0.00% | +0.00% | +5.73% |
| cached-ledger / 2048 | 0.2 | 65.744 | +2.59% | +1.34% | -0.19% | +5.73% |
| cached-ledger / 2048 | 0.4 | 65.798 | +2.67% | +1.46% | -0.01% | +5.73% |

Raw runs

- [0.0 / 20261007T034522Z-m5-confidence-writing-1-0.0](../20261007T034522Z-m5-confidence-writing-1-0.0/result.json)
- [0.2 / 20261007T034653Z-m5-confidence-writing-2-0.2](../20261007T034653Z-m5-confidence-writing-2-0.2/result.json)
- [0.4 / 20261007T034821Z-m5-confidence-writing-3-0.4](../20261007T034821Z-m5-confidence-writing-3-0.4/result.json)
- [0.4 / 20261007T034951Z-m5-confidence-writing-4-0.4](../20261007T034951Z-m5-confidence-writing-4-0.4/result.json)
- [0.2 / 20261007T035120Z-m5-confidence-writing-5-0.2](../20261007T035120Z-m5-confidence-writing-5-0.2/result.json)
- [0.0 / 20261007T035248Z-m5-confidence-writing-6-0.0](../20261007T035248Z-m5-confidence-writing-6-0.0/result.json)
