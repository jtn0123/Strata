# Full-model GPU, context and SSD results — October 9, 2026

The prepared full-model queue is measured. The GPU correctness candidate passed without a useful speed gain. The full Qwen3.8-Flash-Next GSQ-RCO Q2_0 also passed a complete 4K/8K/8K/4K comparison: double the configured context, with fresh generation speed essentially unchanged, six exact-6144-token recall fixtures passing, and zero new swap. Normal launchers retain their existing engine and 4K default.

The first context trial remains failed because the model returned correct facts inside Markdown fences. Fixture v2 explicitly asks for raw JSON and forbids fences; the strict JSON grader is unchanged. The retry uses its own four fresh launches and is not pooled with that stopped trial.

## GPU correctness candidate

Control/fix/fix/control; three measured repeats plus one excluded warmup per workload per launch. Depth3 MTP, eight helper workers, F16, 4K, Tensor API on, batch/ubatch512 and 128 fresh output tokens are fixed. Both engines pass 572 general CPU-reference GPU cases; the fixed engine also passes 16 residual reproducer cases. All 128 model answer/cache checks pass.

| Workload | Control TPS | Fixed TPS | Change |
|---|---:|---:|---:|
| Chinese | 40.04 | 40.00 | -0.08% |
| Code | 56.36 | 56.45 | +0.16% |
| Prose | 42.74 | 42.74 | +0.00% |
| Synthetic / 512 | 49.01 | 48.91 | -0.22% |
| Synthetic / 2048 | 50.01 | 49.93 | -0.16% |

Fresh changes are -0.22% to +0.16%, with control generation drift below 0.50%. There is no useful TPS gain. Passing the backport does not establish that this Qwen graph exposes the original faulty fusion. [Matched candidate evidence](../20261009T085850Z-m5-metal-residual-correctness/comparison.json).

## 8K capacity and speed

Same native mtp-mma engine and short speed prompts at both contexts. Three 6144-token recall fixtures are capacity checks only, with facts near the beginning, middle and end. Each 8K launch passes 35 checks; each 4K launch passes 32. All 134 checks pass.

| Workload | 4K TPS | 8K TPS | Change | Reply-time reduction |
|---|---:|---:|---:|---:|
| Chinese | 40.13 | 40.13 | -0.00% | -0.11% |
| Code | 56.45 | 56.46 | +0.02% | -0.08% |
| Prose | 42.83 | 42.76 | -0.18% | -0.25% |
| Synthetic / 512 | 49.06 | 49.03 | -0.07% | -0.20% |
| Synthetic / 2048 | 49.96 | 50.07 | +0.20% | -0.35% |

Fresh generation differences are -0.18% to +0.20%, with fresh control drift below 0.36%. Whole-reply differences are below 0.36%. The short cached2048 reply has 5.84% control drift, so its apparent -2.24% generation difference is not a reliable context penalty. Cached replies are short structured answers and are not general writing TPS.

| Launch | Context | Checks | Minimum available RAM | New swap | Logged private buffers |
|---|---:|---:|---:|---:|---:|
| 1 | 4096 | 32/32 | 2.32 GiB | 0 | 1046.24 MiB |
| 2 | 8192 | 35/35 | 2.32 GiB | 0 | 1210.75 MiB |
| 3 | 8192 | 35/35 | 2.32 GiB | 0 | 1210.75 MiB |
| 4 | 4096 | 32/32 | 2.54 GiB | 0 | 1046.24 MiB |

Both 8K passes retained at least 2.32 GiB available. Process RSS is not total unique Metal memory. The private-buffer report was corrected after replaying real logs: attention and indexer KV caches had shared backend/kind labels and were overwritten. The 4K report now retains 96+24+8+2=130 MiB of KV, recovering an omitted 104 MiB; repeated compute reservations still count once. A failing regression was reproduced before the fix. All 91 maintained offline tests pass. Logged allocations remain component estimates, not physical peak RAM. [Full context comparison](../20261009T092650Z-context-8k/comparison.json).

## Expert weights and broader GPU costs

All 48 target expert layers and the helper layer are captured. Both depth3/4 captures match greedy control text and token IDs, including warmups; the routing and split suites provide 12 paired responses. Each token still needs its own calculation; repeated selections could share weight reads.

| Draft depth | Prompt | Verification rows | Unique experts, median | Repeated selection share |
|---|---:|---:|---:|---:|
| 3 | 512 | 4 | 27 | 30.90% |
| 3 | 2048 | 4 | 27 | 31.40% |
| 4 | 512 | 5 | 32 | 34.71% |
| 4 | 2048 | 5 | 32 | 35.22% |

Dominant target batches repeat about 31% of assignments at depth3 and 35% at depth4. This is within a layer/verification batch, with no cross-session cache or reusable output claim. [Routing evidence](../../features/20261009T090753Z-m5-routes-batch/batch.json).

| Depth / prompt | Expert matrix | Other matrix | Other operations | Attention/state | Vocabulary |
|---|---:|---:|---:|---:|---:|
| 3 / 512 | 21.9% | 31.4% | 38.7% | 3.9% | 4.1% |
| 3 / 2048 | 21.6% | 30.5% | 38.0% | 5.6% | 4.3% |
| 4 / 512 | 24.4% | 28.6% | 39.4% | 3.6% | 3.9% |
| 4 / 2048 | 23.5% | 28.4% | 39.1% | 5.4% | 3.5% |

These are split-diagnostic GPU intervals. Callbacks synchronize operations and prevent fusion; their overhead inflates small operations. They rank investigation targets and cannot establish normal kernel percentages, accelerator occupancy or a whole-model speedup. Helper vocabulary math accounts for about 56-61% of its split GPU interval. Large recurrent-state CPY nodes and BF16 matrices [320,10240] / [10240,320] are concrete additional targets alongside Q2_0 expert matrices. [Validated split evidence](../../features/20261009T091011Z-m5-split-batch/batch.json).

## Bounded lookup-file reads

128 offsets, three read-only passes; 6.09 MiB total. Digests and file identity match. Cache state is uncontrolled. No writes, preloads or full-table locking were performed.

| Pass | Median read | P95 read |
|---|---:|---:|
| sampled-first-pass | 123.729 microseconds | 155.958 microseconds |
| same-offset-repeat | 1.833 microseconds | 8.291 microseconds |
| ordered-repeat | 1.708 microseconds | 4.750 microseconds |

This measures sampled pread latency, not native mmap fault time, sequential SSD bandwidth, RAM-equivalent performance or an inference TPS gain. Prefetch still requires native wait/miss evidence. [Read probe](../../features/20261009T092253Z-lookup-io/probe.json).

## Current state and next useful work

Sixteen accepted full-model launches provide 262 answer/cache/recall checks, 168 measured speed samples and 12 paired diagnostic outputs. The original two-launch context trial is retained separately; its first 4K launch passed and its 8K launch failed raw-JSON formatting at seed7, before later seeds were attempted. All eight native engines and exact model files remain unchanged. The benchmark harness is unchanged within each batch; only the documented fixture/reporting changes separate the batches.

The model servers are stopped. A read-only reset of idle owned model pages restored 39.85 GiB available. T3 and WiFiman remain running; no VM, Docker or Chrome was restarted. Available memory varies with subsequent activity.

Next, validate the shared-matrix and large-state-copy shapes in bounded isolated tests, then compare one candidate in the normal fused runtime. A grouped expert-weight-read prototype can use the measured repeat distribution. Prefetch and larger-model paging still need actual native lookup waits and broader hot-set/capacity evidence. Quantized KV is unnecessary for this validated 8K/F16 fit and remains a separate later correctness task. No new kernel, pager, prefetcher or speed preset was adopted by these measurements.

[Combined summary](summary.json), [Original batch](batch.json), [Context retry](../20261009T092635Z-m5-context-v2/batch.json).
