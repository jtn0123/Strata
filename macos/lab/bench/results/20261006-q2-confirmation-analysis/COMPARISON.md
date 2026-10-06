# Q2 Metal confirmation

Adjacent candidate/baseline confirmation after Java build load subsided; same full model and settings, three measured 512-token replies per input length, one excluded warmup. Browser/UI and media-analysis work remained; not a fully idle or guaranteed cold-SSD test. Earlier four-pass results remain intact. Small gains are not established as repeatable.

Keep the original engine default; Q2 candidate remains optional. Writing speed gain is small/mixed and prompt processing regressed.

| Input tokens | Baseline output TPS | Candidate output TPS | Output change | Baseline input TPS | Candidate input TPS | Input change |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 512 | 37.91 | 38.01 | +0.27% | 679.25 | 637.88 | -6.09% |
| 2048 | 35.55 | 36.86 | +3.68% | 647.00 | 599.80 | -7.29% |

| Input tokens | Baseline first token (s) | Candidate first token (s) | Baseline reply (s) | Candidate reply (s) | Reply time reduction |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 512 | 0.754 | 0.803 | 14.235 | 14.245 | -0.07% |
| 2048 | 3.166 | 3.415 | 17.548 | 17.309 | +1.36% |

36/36 answer checks passed in this pair. Across all six successful passes, 108/108 answer checks passed. Numerical accumulation changed, so sampled token sequences can differ; this is not a bit-for-bit output claim.

- [baseline raw run](../20261006T173609Z-q2-quiet-baseline/result.json): 0.0000 GiB new swap, 2.76 GiB minimum available RAM. RSS is not total Metal memory.
- [candidate raw run](../20261006T173319Z-q2-quiet-confirmation/result.json): 0.0006 GiB new swap, 3.06 GiB minimum available RAM. RSS is not total Metal memory.

[Initial four-pass comparison](../20261006T172232Z-q2-comparison/COMPARISON.md) reported -8.83% and -7.30% output-rate changes, but background Java/browser activity distorted the comparison. Those values cannot establish that the patch caused the slowdown. [Recorded background snapshots](../../diagnostics/20261006-q2-background.jsonl).

An earlier load attempt stopped before timing after swap grew 2.14 GiB with the Docker VM active. The VM was then stopped with approval, and all six later passes completed without a memory-guard trip. [Stopped-load record](../20261006T171840Z-q2-1-baseline/result.json). Colima remains stopped as requested.
