# Shared helper comparison

Status: failed

Shared-mixed retains batch 512, uses a byte-verified experts-first helper layout, keeps its experts on CPU and moves its small dense/attention operations to GPU. Automatic CPU-op offload is disabled so those experts stay on CPU during prefill. Its Metal mapped-weight span is about 45.6 MiB, versus 1,183 MiB for the same placement with the interleaved file. Target weights remain on Metal.

Full Flash-Next Q2_0 on the 48 GiB M5 Pro, 4K context, F16 cache, 8 threads, temperature 0.6. Plain has prediction off. Full uses the selected self-contained Q3 helper, CPU body/GPU output and two draft tokens. Shared-cpu removes only the helper's embeddings/output and borrows the target tables while retaining CPU body placement. Draft KV stays separate. Target weights/graph are unchanged; the borrowed Q5_K output changes draft precision from the helper's Q3_K. Plain/full/shared-cpu use batch/ubatch 512. No vocabulary subset or GPU-limit override is used.

Order: plain, full, shared-cpu, shared-mixed, shared-mixed, shared-cpu, full, plain. One excluded warmup and 2 measured repeats per workload per pass; 128 output tokens for fresh fixed-length timings. Normal-EOS checks and cached ledger replies retain their natural output lengths. Cache means the immediately preceding turn, without cross-session caching. Results from other suites use different output lengths and cannot be pooled here.

| Workload / input | plain TPS | full TPS | shared-cpu TPS | shared-mixed TPS | Sharing vs full | Placement vs plain |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |

First token, seconds

| Workload / input | plain | full | shared-cpu | shared-mixed |
| --- | ---: | ---: | ---: | ---: |

Complete reply, seconds

| Workload / input | plain | full | shared-cpu | shared-mixed |
| --- | ---: | ---: | ---: | ---: |

Input tokens/second

| Workload / input | plain | full | shared-cpu | shared-mixed |
| --- | ---: | ---: | ---: | ---: |

Draft acceptance, percent

| Workload / input | plain | full | shared-cpu | shared-mixed |
| --- | ---: | ---: | ---: | ---: |

Raw records include exact source/binary/helper pins, answers, token IDs, native logs and memory samples.

- [plain / 20261006T185032Z-shared-1-plain](../20261006T185032Z-shared-1-plain/result.json): passed; new swap 0.000 GiB

KeyboardInterrupt: 
