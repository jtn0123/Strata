# Shared helper comparison

Status: passed

Shared-mixed retains batch 512, uses a byte-verified experts-first helper layout, keeps its experts on CPU and moves its small dense/attention operations to GPU. Automatic CPU-op offload is disabled so those experts stay on CPU during prefill. Its Metal mapped-weight span is about 45.6 MiB, versus 1,183 MiB for the same placement with the interleaved file. Target weights remain on Metal.

Full Flash-Next Q2_0 on the 48 GiB M5 Pro, 4K context, F16 cache, 8 threads, temperature 0.6. Plain has prediction off. Full uses the selected self-contained Q3 helper, CPU body/GPU output and two draft tokens. Shared-cpu removes only the helper's embeddings/output and borrows the target tables while retaining CPU body placement. Draft KV stays separate. Target weights/graph are unchanged; the borrowed Q5_K output changes draft precision from the helper's Q3_K. Plain/full/shared-cpu use batch/ubatch 512. No vocabulary subset or GPU-limit override is used.

Order: plain, full, shared-cpu, shared-mixed, shared-mixed, shared-cpu, full, plain. One excluded warmup and 2 measured repeats per workload per pass; 128 output tokens for fresh fixed-length timings. Normal-EOS checks and cached ledger replies retain their natural output lengths. Cache means the immediately preceding turn, without cross-session caching. Results from other suites use different output lengths and cannot be pooled here.

| Workload / input | plain TPS | full TPS | shared-cpu TPS | shared-mixed TPS | Sharing vs full | Placement vs plain |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| chinese / 56 | 37.22 | 32.55 | 34.18 | 34.34 | +5.01% | -7.74% |
| code / 48 | 37.66 | 42.70 | 42.34 | 42.98 | -0.85% | +14.15% |
| prose / 53 | 36.95 | 35.13 | 35.21 | 36.38 | +0.23% | -1.54% |
| synthetic / 512 | 37.54 | 36.93 | 37.85 | 41.22 | +2.50% | +9.80% |
| synthetic / 2048 | 36.02 | 36.21 | 37.59 | 38.99 | +3.83% | +8.24% |
| cached-ledger / 512 | 37.34 | 50.44 | 48.83 | 51.02 | -3.19% | +36.65% |
| cached-ledger / 2048 | 36.42 | 44.17 | 45.20 | 46.72 | +2.33% | +28.27% |

First token, seconds

| Workload / input | plain | full | shared-cpu | shared-mixed |
| --- | ---: | ---: | ---: | ---: |
| chinese / 56 | 0.282 | 0.370 | 0.362 | 0.319 |
| code / 48 | 0.269 | 0.357 | 0.350 | 0.310 |
| prose / 53 | 0.280 | 0.385 | 0.446 | 0.317 |
| synthetic / 512 | 0.763 | 1.132 | 1.115 | 0.979 |
| synthetic / 2048 | 3.178 | 4.544 | 4.501 | 4.140 |
| cached-ledger / 512 | 0.261 | 0.337 | 0.341 | 0.290 |
| cached-ledger / 2048 | 0.278 | 0.374 | 0.396 | 0.306 |

Complete reply, seconds

| Workload / input | plain | full | shared-cpu | shared-mixed |
| --- | ---: | ---: | ---: | ---: |
| chinese / 56 | 3.697 | 4.296 | 4.079 | 4.016 |
| code / 48 | 3.641 | 3.331 | 3.355 | 3.259 |
| prose / 53 | 3.719 | 4.001 | 4.065 | 3.849 |
| synthetic / 512 | 4.149 | 4.563 | 4.462 | 4.072 |
| synthetic / 2048 | 6.743 | 8.036 | 7.883 | 7.409 |
| cached-ledger / 512 | 0.906 | 0.820 | 0.829 | 0.762 |
| cached-ledger / 2048 | 0.912 | 0.898 | 0.904 | 0.799 |

Input tokens/second

| Workload / input | plain | full | shared-cpu | shared-mixed |
| --- | ---: | ---: | ---: | ---: |
| chinese / 56 | 198.746 | 151.608 | 155.021 | 175.818 |
| code / 48 | 178.794 | 134.666 | 137.332 | 154.944 |
| prose / 53 | 189.428 | 138.536 | 118.966 | 167.712 |
| synthetic / 512 | 672.055 | 452.759 | 459.856 | 523.668 |
| synthetic / 2048 | 644.724 | 450.760 | 455.380 | 494.774 |
| cached-ledger / 512 | 160.959 | 124.683 | 123.519 | 144.979 |
| cached-ledger / 2048 | 151.570 | 112.896 | 106.197 | 137.445 |

Draft acceptance, percent

| Workload / input | plain | full | shared-cpu | shared-mixed |
| --- | ---: | ---: | ---: | ---: |
| chinese / 56 | n/a | 49.606 | 53.279 | 51.200 |
| code / 48 | n/a | 78.571 | 78.571 | 78.571 |
| prose / 53 | n/a | 56.780 | 59.483 | 61.404 |
| synthetic / 512 | n/a | 60.526 | 66.667 | 71.154 |
| synthetic / 2048 | n/a | 63.393 | 69.811 | 69.811 |
| cached-ledger / 512 | n/a | 100.000 | 100.000 | 100.000 |
| cached-ledger / 2048 | n/a | 100.000 | 100.000 | 100.000 |

Raw records include exact source/binary/helper pins, answers, token IDs, native logs and memory samples.

- [plain / 20261006T185833Z-shared-1-plain](../20261006T185833Z-shared-1-plain/result.json): passed; new swap 0.000 GiB
- [full / 20261006T190011Z-shared-2-full](../20261006T190011Z-shared-2-full/result.json): passed; new swap 0.000 GiB
- [shared-cpu / 20261006T190204Z-shared-3-shared-cpu](../20261006T190204Z-shared-3-shared-cpu/result.json): passed; new swap 0.000 GiB
- [shared-mixed / 20261006T190357Z-shared-4-shared-mixed](../20261006T190357Z-shared-4-shared-mixed/result.json): passed; new swap 0.000 GiB
- [shared-mixed / 20261006T190540Z-shared-5-shared-mixed](../20261006T190540Z-shared-5-shared-mixed/result.json): passed; new swap 0.000 GiB
- [shared-cpu / 20261006T190724Z-shared-6-shared-cpu](../20261006T190724Z-shared-6-shared-cpu/result.json): passed; new swap 0.000 GiB
- [full / 20261006T190914Z-shared-7-full](../20261006T190914Z-shared-7-full/result.json): passed; new swap 0.000 GiB
- [plain / 20261006T191108Z-shared-8-plain](../20261006T191108Z-shared-8-plain/result.json): passed; new swap 0.000 GiB
