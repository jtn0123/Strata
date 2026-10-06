# Draft vocabulary comparison

Status: failed

Full Flash-Next Q2_0 on the 48 GiB M5 Pro. All profiles use 4K context, batch/ubatch 512, F16 cache, 8 CPU threads and temperature 0.6. Plain disables prediction; full/subset use the same isolated binary, Q3_K_S helper, two draft tokens and CPU helper body/GPU output. Subset limits only the helper's word list from 248,320 to 106,299 tokens. The target still verifies with its complete vocabulary.

Order: plain, full, subset, subset, full, plain. One excluded warmup and 2 measured repeats per workload per pass. Fresh workloads emit exactly 256 tokens with EOS ignored for timing; answer checks and cached ledger replies stop normally. English code, prose and Chinese workloads are included. Cached measurements reuse the immediately preceding turn; no cross-session cache is added. Percentages below compare fresh measurements, not older runs. OS file cache and other apps are uncontrolled.

| Workload / input | Plain TPS | Full helper TPS | Subset TPS | Subset vs full | Subset vs plain |
| --- | ---: | ---: | ---: | ---: | ---: |

| Workload / input | Plain first token (s) | Full first token (s) | Subset first token (s) | Plain reply (s) | Full reply (s) | Subset reply (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |

| Workload / input | Plain input TPS | Full input TPS | Subset input TPS | Full acceptance | Subset acceptance |
| --- | ---: | ---: | ---: | ---: | ---: |

Raw runs retain exact weights/settings/source/binary hashes, token IDs, checks, logs and memory samples.

- [plain / 20261006T181358Z-vocab-1-plain](../20261006T181358Z-vocab-1-plain/result.json): passed; new swap 0.000 GiB
- [full / 20261006T181631Z-vocab-2-full](../20261006T181631Z-vocab-2-full/result.json): passed; new swap 0.000 GiB
- [subset / 20261006T181924Z-vocab-3-subset](../20261006T181924Z-vocab-3-subset/result.json): passed; new swap 0.000 GiB

KeyboardInterrupt: 
