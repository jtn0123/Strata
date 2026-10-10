# Small-model benchmark — 2026-10-08

Chrome was closed and Docker Desktop stopped gracefully. Neither was restarted. Other project work was left running.

Qwen3.5 4B Q4_K_M (2.74 GB file) ran on the M5 Pro / 48 GiB Mac. This comparison changes only the upstream fused-residual correctness patch, from `m5-lab` to `m5-correctness`; both use the current prepared stack, full Metal offload and Tensor API enabled. The original v1 and the much larger Flash model were not measured in this batch.

Four 4K-context launches ran control / candidate / candidate / control. Each used one warmup and three measured repeats per workload, 128 output tokens, identical input token hashes, fixed seed, temperature zero, batch/ubatch 512 and eight CPU threads. The table uses the median of six measured samples per arm. Cached follow-ups use natural EOS and three measured answers per launch.

| Workload | Baseline tokens/s | Fix tokens/s | Change | Baseline first token | Fix first token |
|---|---:|---:|---:|---:|---:|
| chinese | 77.34 | 77.24 | -0.13% | 81.1 ms | 81.1 ms |
| code | 77.27 | 77.17 | -0.12% | 79.9 ms | 79.7 ms |
| prose | 77.36 | 77.24 | -0.16% | 80.8 ms | 80.4 ms |
| synthetic 512 tokens | 77.00 | 76.73 | -0.35% | 248.6 ms | 248.6 ms |
| synthetic 2048 tokens | 75.61 | 75.71 | +0.13% | 946.8 ms | 946.9 ms |
| cached-ledger 512 tokens | 77.22 | 77.11 | -0.14% | 80.2 ms | 80.3 ms |
| cached-ledger 2048 tokens | 75.61 | 75.46 | -0.19% | 82.2 ms | 82.1 ms |

The patch produced no meaningful measured speed gain: all generation changes were below 0.4%. Closing apps provided memory headroom; there is no matched before/after benchmark here to attribute a speed gain to that cleanup. Control generation drift ranged from -0.06% to +1.22%, so small changes should not be treated as established improvements.

| Fresh synthetic prompt | Baseline input tokens/s | Fix input tokens/s | Change |
|---|---:|---:|---:|
| 512 tokens | 2064.8 | 2065.0 | +0.01% |
| 2048 tokens | 2165.0 | 2164.9 | -0.01% |

All 163 answer/cache/retrieval checks passed across five model launches. The separate GPU regression check passed exactly 16 selected cases against CPU reference math (four weight types and row sizes 2, 3, 5, 8). Row size 4 and all runtime shapes are not covered by that native inventory.

The additional 8K context run passed three exact 6144-token retrieval fixtures with labels near the beginning, middle and end. Its speed is not a matched 8K comparison and is excluded from the table.

No new swap occurred in any launch or the GPU test. Peak model process RSS was 3.23 GiB; minimum available host memory was 24.01 GiB. RSS is not total Metal memory. Available RAM after cleanup initially rose from about 18 to 27 GiB; the final live reading is 29.79 GiB with normal memory pressure.

Every launch used the current passing 90-test offline gate, verified engine artifacts, model file identity/hash receipt and unchanged harness hashes. Those identities were rechecked after the batch. Each launch had an immediate 6 GiB minimum admission gate, normal pressure, three quiet CPU samples, and a resource monitor that stopped only its owned model server if guards were exceeded.

CPU activity snapshots are retained. The largest burst was Metal shader compilation during the owned GPU math check, between model launches. During model launches, the busiest observed non-server process groups summed to at most 14.1% of host CPU capacity; only the top eight groups were captured. These snapshots do not prove there was no other GPU activity. Warm file-cache state was uncontrolled. These checks validate the smaller dense model; they do not validate large-model MTP, expert streaming, SSD paging, or Flash capacity.

Raw evidence: [comparison and provenance](comparison.json), [background resource samples](resources.jsonl), [GPU check log](residual-16.log), [runner](runner.py).

Per-launch results:

- [20261008T122556Z-small-m5-1-m5-lab](../20261008T122556Z-small-m5-1-m5-lab/result.json) — 32/32 checks.
- [20261008T122657Z-small-m5-2-m5-correctness](../20261008T122657Z-small-m5-2-m5-correctness/result.json) — 32/32 checks.
- [20261008T122753Z-small-m5-3-m5-correctness](../20261008T122753Z-small-m5-3-m5-correctness/result.json) — 32/32 checks.
- [20261008T122848Z-small-m5-4-m5-lab](../20261008T122848Z-small-m5-4-m5-lab/result.json) — 32/32 checks.
- [20261008T122944Z-small-m5-8k-capacity](../20261008T122944Z-small-m5-8k-capacity/result.json) — 35/35 checks including three retrieval fixtures.
