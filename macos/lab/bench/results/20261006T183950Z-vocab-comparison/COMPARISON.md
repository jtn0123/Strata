# Draft vocabulary comparison

Status: passed

Full Flash-Next Q2_0 on the 48 GiB M5 Pro. All profiles use 4K context, batch/ubatch 512, F16 cache, 8 CPU threads and temperature 0.6. Plain disables prediction; full/subset use the same isolated binary, Q3_K_S helper, two draft tokens and CPU helper body/GPU output. Subset limits only the helper's word list from 248,320 to 106,299 tokens. The target still verifies with its complete vocabulary.

Order: plain, full, subset, subset, full, plain. One excluded warmup and 2 measured repeats per workload per pass. Fresh workloads emit exactly 128 tokens with EOS ignored for timing; answer checks and cached ledger replies stop normally. English code, prose and Chinese workloads are included. Cached measurements reuse the immediately preceding turn; no cross-session cache is added. Percentages below compare fresh measurements, not older runs. OS file cache and other apps are uncontrolled.

| Workload / input | Plain TPS | Full helper TPS | Subset TPS | Subset vs full | Subset vs plain |
| --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | 37.98 | 34.76 | 35.50 | +2.12% | -6.54% |
| code / 48 | 37.30 | 44.03 | 43.53 | -1.13% | +16.70% |
| prose / 53 | 38.14 | 37.09 | 38.47 | +3.72% | +0.87% |
| synthetic / 512 | 37.63 | 37.63 | 39.11 | +3.94% | +3.95% |
| synthetic / 2048 | 35.94 | 37.04 | 38.69 | +4.44% | +7.64% |
| cached-ledger / 512 | 37.22 | 50.04 | 45.43 | -9.22% | +22.06% |
| cached-ledger / 2048 | 36.01 | 46.05 | 41.39 | -10.12% | +14.95% |

| Workload / input | Plain first token (s) | Full first token (s) | Subset first token (s) | Plain reply (s) | Full reply (s) | Subset reply (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | 0.281 | 0.344 | 0.349 | 3.624 | 4.000 | 3.925 |
| code / 48 | 0.270 | 0.340 | 0.344 | 3.675 | 3.223 | 3.265 |
| prose / 53 | 0.275 | 0.348 | 0.363 | 3.605 | 3.771 | 3.671 |
| synthetic / 512 | 0.756 | 1.081 | 1.090 | 4.132 | 4.453 | 4.337 |
| synthetic / 2048 | 3.127 | 4.450 | 4.644 | 6.664 | 7.908 | 7.925 |
| cached-ledger / 512 | 0.261 | 0.330 | 0.336 | 0.908 | 0.809 | 0.867 |
| cached-ledger / 2048 | 0.280 | 0.348 | 0.348 | 0.918 | 0.849 | 0.904 |

| Workload / input | Plain input TPS | Full input TPS | Subset input TPS | Full acceptance | Subset acceptance |
| --- | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | 199.6 | 162.9 | 160.7 | 49.6% | 49.6% |
| code / 48 | 178.4 | 141.6 | 139.6 | 78.6% | 73.5% |
| prose / 53 | 192.9 | 152.5 | 146.2 | 56.8% | 58.6% |
| synthetic / 512 | 677.4 | 474.1 | 470.0 | 60.5% | 62.5% |
| synthetic / 2048 | 655.0 | 460.4 | 442.6 | 63.4% | 65.5% |
| cached-ledger / 512 | 161.2 | 127.4 | 125.1 | 100.0% | 83.3% |
| cached-ledger / 2048 | 150.3 | 120.9 | 121.0 | 100.0% | 77.8% |

Raw runs retain exact weights/settings/source/binary hashes, token IDs, checks, logs and memory samples.

- [plain / 20261006T183950Z-vocab-1-plain](../20261006T183950Z-vocab-1-plain/result.json): passed; new swap 0.000 GiB
- [full / 20261006T184129Z-vocab-2-full](../20261006T184129Z-vocab-2-full/result.json): passed; new swap 0.000 GiB
- [subset / 20261006T184322Z-vocab-3-subset](../20261006T184322Z-vocab-3-subset/result.json): passed; new swap 0.052 GiB
- [subset / 20261006T184513Z-vocab-4-subset](../20261006T184513Z-vocab-4-subset/result.json): passed; new swap 0.000 GiB
- [full / 20261006T184707Z-vocab-5-full](../20261006T184707Z-vocab-5-full/result.json): passed; new swap 0.000 GiB
- [plain / 20261006T184856Z-vocab-6-plain](../20261006T184856Z-vocab-6-plain/result.json): passed; new swap 0.000 GiB
