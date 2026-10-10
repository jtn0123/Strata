# M5 experiment: copy-kernels

Status: failed

Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.
128 output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.

| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |

Raw runs

- [stock / 20261009T111822Z-m5-copy-kernels-1-stock](../20261009T111822Z-m5-copy-kernels-1-stock/result.json)
- [copy-scalar / 20261009T112023Z-m5-copy-kernels-2-copy-scalar](../20261009T112023Z-m5-copy-kernels-2-copy-scalar/result.json)
- [copy-v4 / 20261009T112225Z-m5-copy-kernels-3-copy-v4](../20261009T112225Z-m5-copy-kernels-3-copy-v4/result.json)

RuntimeError: Host still busy ([26.9, 17.3, 15.1] percent CPU); diagnostic deferred without stopping other work
