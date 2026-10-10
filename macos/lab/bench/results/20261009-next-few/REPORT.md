# Next three M5 candidates

No additional TPS improvement qualified in this pass. The existing working setup and launchers remain unchanged. All three candidates were implemented in isolated native builds, with Astra checking the paths and benchmark methods.

## Expert gate/up fusion

Exact tested output bits matched the control for 11,162,880 values in each of the two variants. 58 cases included actual recorded routing IDs, fallbacks, retained outputs and eight-block chains. All graph computation ran on Metal through the normal scheduler/optimizer; no CPU graph fallback.

| Variant | Rows | Routing | Control block latency | Candidate block latency | Time change | Control drift |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| gate-up8 | 4 | real | 0.2954 ms | 0.3484 ms | +17.95% | 0.41% |
| gate-up8 | 4 | distinct | 0.3053 ms | 0.3621 ms | +18.60% | 0.05% |
| gate-up8 | 4 | shared | 0.2921 ms | 0.3170 ms | +8.50% | 0.03% |
| gate-up8 | 5 | real | 0.3572 ms | 0.4138 ms | +15.84% | 0.71% |
| gate-up8 | 5 | distinct | 0.3667 ms | 0.4325 ms | +17.94% | 0.08% |
| gate-up8 | 5 | shared | 0.3510 ms | 0.3841 ms | +9.45% | 0.39% |
| gate-up4 | 4 | real | 0.2949 ms | 0.2962 ms | +0.42% | 0.76% |
| gate-up4 | 4 | distinct | 0.3046 ms | 0.3090 ms | +1.42% | 0.58% |
| gate-up4 | 4 | shared | 0.2918 ms | 0.2889 ms | -0.99% | 0.12% |
| gate-up4 | 5 | real | 0.3575 ms | 0.3578 ms | +0.07% | 0.05% |
| gate-up4 | 5 | distinct | 0.3667 ms | 0.3717 ms | +1.37% | 0.21% |
| gate-up4 | 5 | shared | 0.3507 ms | 0.3478 ms | -0.82% | 0.02% |

Positive time change means slower. Each row averages the two control or candidate launch medians from its own ABBA bracket. Latency includes gate/up/SwiGLU/down/reduction/residual plus dispatch/synchronization, normalized per block in an eight-block graph. These are component measurements, not model TPS. Neither variant met the 10 percent operator gate. No model speed trial was started.

## Recurrent-state tuning

All 32 cases passed in each setting. 960 full output/cache/padding buffers, covering 1,504,438,002 F32 values per setting, had identical SHA256 manifests versus stock. CPU recurrence checks covered every written attention/state value. Retained rollback prefixes and their subsequent continuations matched; T=5/K=4 prefix 1 is explicitly unavailable and was not claimed tested.

Normal full-model capture confirmed fused K=4, target T=1–4, and cache slot stride 786432 floats. T=5 is adjacent coverage. Perf uses matching dimensions, strides and aligned offsets; correctness retains deliberately padded/misaligned fixtures.

| Variant | T | Fused control envelope | Candidate repeats | Above-drift benefit? |
| --- | ---: | ---: | ---: | --- |
| gdn-row1 | 4 | 0.3989–0.4161 ms | 0.4052–0.4081 ms | No |
| gdn-row2 | 4 | 0.3989–0.4161 ms | 0.4024–0.4039 ms | No |
| gdn-row1 | 5 | 0.4020–0.4132 ms | 0.4049–0.4051 ms | No |
| gdn-row2 | 5 | 0.4020–0.4132 ms | 0.4054–0.4212 ms | No |

The initial short bracket was inconclusive (11.43 percent fused T=4 control drift). The final bracket used at least 500 ms continuous warmup, 512 single-graph synchronized samples, and four distinct states per case. The unchanged rows=4 specialization served as an additional negative control. Fused T=4 control spread narrowed to 4.33 percent; candidate differences did not establish a repeatable gain. This does not prove the individual kernel has no possible improvement: the fixture includes a SUM consumer, attention copy and synchronization.

## Native lookup cost

| Text | Reply wall time | Complete lookup envelope | Upper bound of reply time |
| --- | ---: | ---: | ---: |
| prose | 3.3295s | 2.508 ms | 0.0753% |
| code | 2.4972s | 1.885 ms | 0.0755% |
| chinese | 3.3073s | 2.433 ms | 0.0736% |

The native trace attributed 162 lookup operations to the separate 28.8 GB shard, 90-byte rows and 16 KiB pages. Every request interval had complete non-crossing operation coverage. Traced and untraced outputs matched exactly across four requests (392 generated tokens). Warmup lookup envelope was 0.2677 percent of its shorter 8-token response.
The envelope includes CPU gather/dequantization and scheduling; it is not measured SSD wait. Target/helper overlap can overcount. The OS page cache was not controlled, and these are short text workloads. This screens decode/response lookup cost, not cold model-load speed or long-context/memory-pressure behavior. On these workloads even eliminating every lookup would remove less than 0.08 percent of measured reply time, so macOS prefetch is parked.

## Validation and next step

26final accepted runs had zero new swap. A separate initial diagnostic with 0.44 MiB swap growth was excluded and retried. The first gate probe placement crash was corrected before timings. All 13 previous engines were checked unchanged; the maintained offline gate passed 118 tests. Model servers were shut down after their owned runs. No commit, push or launcher-default change was made.

Astra identified one bounded next experiment: keep the exact Q2 dot products and reductions, then distribute the unchanged SwiGLU epilogue across SIMD lanes. The current fused kernel serializes 4/8 exp/divide/store operations in lane 0. Register pressure is a plausible additional cause of the eight-row regression; spills were not measured. This is a future hypothesis, not a confirmed TPS gain.

[Raw results and paths](REPORT.json)
[Frozen source bundle](source/SHA256.json)
