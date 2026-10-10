# M5 experiment: copy-kernels

Status: passed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
128 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | stock | 40.073 | +0.00% | +0.00% | +0.00% | +0.20% |
| chinese / 56 | copy-scalar | 40.140 | +0.17% | +0.17% | -1.00% | +0.20% |
| chinese / 56 | copy-v4 | 40.100 | +0.07% | +0.03% | -1.10% | +0.20% |
| chinese / 56 | conv-direct | 40.721 | +1.62% | +1.59% | +0.65% | +0.20% |
| code / 48 | stock | 56.501 | +0.00% | +0.00% | +0.00% | +0.04% |
| code / 48 | copy-scalar | 56.496 | -0.01% | -0.17% | -0.74% | +0.04% |
| code / 48 | copy-v4 | 56.365 | -0.24% | -0.32% | -0.96% | +0.04% |
| code / 48 | conv-direct | 57.258 | +1.34% | +1.21% | +0.68% | +0.04% |
| prose / 53 | stock | 42.877 | +0.00% | +0.00% | +0.00% | +0.01% |
| prose / 53 | copy-scalar | 42.861 | -0.04% | -0.12% | -0.90% | +0.01% |
| prose / 53 | copy-v4 | 42.775 | -0.24% | -0.31% | -0.99% | +0.01% |
| prose / 53 | conv-direct | 43.448 | +1.33% | +1.28% | +0.64% | +0.01% |
| synthetic / 512 | stock | 49.060 | +0.00% | +0.00% | +0.00% | -0.56% |
| synthetic / 512 | copy-scalar | 48.943 | -0.24% | -0.17% | -0.39% | -0.56% |
| synthetic / 512 | copy-v4 | 48.851 | -0.42% | -0.58% | -1.44% | -0.56% |
| synthetic / 512 | conv-direct | 49.744 | +1.39% | +1.19% | +0.43% | -0.56% |
| synthetic / 2048 | stock | 50.016 | +0.00% | +0.00% | +0.00% | -0.21% |
| synthetic / 2048 | copy-scalar | 50.056 | +0.08% | -0.39% | -0.89% | -0.21% |
| synthetic / 2048 | copy-v4 | 49.963 | -0.11% | -0.74% | -1.29% | -0.21% |
| synthetic / 2048 | conv-direct | 50.737 | +1.44% | +0.75% | +0.13% | -0.21% |
| cached-ledger / 512 | stock | 69.069 | +0.00% | +0.00% | +0.00% | +2.98% |
| cached-ledger / 512 | copy-scalar | 69.033 | -0.05% | -0.26% | -0.53% | +2.98% |
| cached-ledger / 512 | copy-v4 | 68.893 | -0.25% | -0.30% | -0.58% | +2.98% |
| cached-ledger / 512 | conv-direct | 69.754 | +0.99% | +0.78% | +1.02% | +2.98% |
| cached-ledger / 2048 | stock | 63.062 | +0.00% | +0.00% | +0.00% | +0.49% |
| cached-ledger / 2048 | copy-scalar | 63.749 | +1.09% | +0.17% | -0.76% | +0.49% |
| cached-ledger / 2048 | copy-v4 | 64.655 | +2.53% | +0.56% | -1.15% | +0.49% |
| cached-ledger / 2048 | conv-direct | 63.193 | +0.21% | +0.64% | +0.39% | +0.49% |

Raw runs

- [stock / 20261009T111822Z-m5-copy-kernels-1-stock](../20261009T111822Z-m5-copy-kernels-1-stock/result.json)
- [copy-scalar / 20261009T112023Z-m5-copy-kernels-2-copy-scalar](../20261009T112023Z-m5-copy-kernels-2-copy-scalar/result.json)
- [copy-v4 / 20261009T112225Z-m5-copy-kernels-3-copy-v4](../20261009T112225Z-m5-copy-kernels-3-copy-v4/result.json)
- [conv-direct / 20261009T112653Z-m5-copy-kernels-resume-4-conv-direct](../20261009T112653Z-m5-copy-kernels-resume-4-conv-direct/result.json)
- [conv-direct / 20261009T112859Z-m5-copy-kernels-resume-5-conv-direct](../20261009T112859Z-m5-copy-kernels-resume-5-conv-direct/result.json)
- [copy-v4 / 20261009T113103Z-m5-copy-kernels-resume-6-copy-v4](../20261009T113103Z-m5-copy-kernels-resume-6-copy-v4/result.json)
- [copy-scalar / 20261009T113309Z-m5-copy-kernels-resume-7-copy-scalar](../20261009T113309Z-m5-copy-kernels-resume-7-copy-scalar/result.json)
- [stock / 20261009T113513Z-m5-copy-kernels-resume-8-stock](../20261009T113513Z-m5-copy-kernels-resume-8-stock/result.json)
