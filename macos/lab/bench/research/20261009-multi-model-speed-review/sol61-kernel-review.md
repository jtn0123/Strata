# Sol 6.1: Metal and M5 kernel research

Independent `gpt-6.1-sol`, xhigh, read-only review on October 9, 2026. No builds, model/GPU/SSD tests, edits or process changes by the reviewer. The coordinator saved this summary. All estimates are hypotheses relative to current control; zero is the planning baseline.

## Ranked paths

| Direction | Decode TPS low/base/high | Prompt throughput low/base/high |
| --- | --- | --- |
| Compact active expert/token-tile launches | 0/0/0% | -3/+5/+12% |
| Exact Q2 cooperative-input dequantization | 0/0/0% | -3/+2/+8% |
| Reuse expert-route maps across projections | 0/0/0% | -1/+1/+4% |
| Sparse grouped-query F16 K/V reuse | -3/0/+3% | Untargeted |

These are not measured, additive, or confidence intervals. At 40% prompt-time share, +5% prompt throughput reduces complete-response time by only about1.9%.

## Active prompt tiles

`vendor/llama-m5-copy/ggml/src/ggml-metal/ggml-metal-ops.cpp:3009` launches `ceil(T/32) * ceil(output_channels/64) * E`. The current `kernels/mul_mm.metal:536-547` obtains each expert's actual token count and returns for an empty tile. For T512, E512 and ten assignments/token, the full expert/token grid has8192 tiles. Useful tiles are at most `floor((5120+31*512)/32)=656`. This launch-grid bound does not imply92% runtime saving: empty groups return quickly and useful math remains.

Existing normal-route records at `bench/features/20261009T090753Z-m5-routes-batch/depth3-routes/native.log:729` and `:15258` identify T508/T512 Q2 routed prompt shapes, including gate/up [2560,640,512] and down [640,2560,512]. They establish topology/shapes, not cost or occupancy.

Construct GPU-owned active `(expert, token_tile)` metadata and use an indirect launch; preserve original expert/token order,64x32 arithmetic tiles, Q2 dequantization, scaling and stores. No CPU routing readback. New versus P03: remove empty prompt launches without regrouping decode arithmetic.

Precedent: [MLX #4567](https://github.com/ml-explore/mlx/pull/4567), merged Sep26; [MLX #4572](https://github.com/ml-explore/mlx/pull/4572), merged Sep28. Their formats/math are not a Q2_0 replacement. [Apple indirect compute dispatch](https://developer.apple.com/documentation/metal/mtlcomputecommandencoder).

First prove exact mappings/output coverage for T32/33/64/127/508/512 with uniform, clustered, skewed and empty-expert routes. Later measure complete mapping+gate/up+activation+down+consumer graphs, without callbacks. Stop on mismatch or below10% repeatable component gain above twice drift before model timing.

## Cooperative input Q2

Current `kernels/mul_mm.metal:79` and `:602` stage dequantized weights/gathered inputs through threadgroup memory. [Apple TensorOps guidance](https://developer.apple.com/videos/play/wwdc2026/330/) introduces cooperative inputs that can avoid this round trip.

Stored Q2_0 is half scale plus16 packed bytes for64 values, reconstructing `(q-1)*d`; see `ggml/src/ggml-common.h:187` and `ggml-metal/kernels/dequantize.h:99`. It is not native MX. macOS27.2 and MacOSX27.0 SDK metadata were inspected, but API/header/compiler and compatible precision/layout remain unproved. TensorAPI is already enabled.

Begin with static eligibility, then separately authorized compile/unpack/half-rounding and exact full-tile checks. Preserve existing half conversions, K-step order, accumulator descriptors and non-relaxed precision. Stop before timing if impossible. Require10% full-operation improvement before a prompt model trial. P09's BF16 few-row experiment was a different regime.

## One route map per layer/ubatch

`src/llama-graph.cpp:2241,2254,2355` uses the same selected-expert IDs for up/gate/down. Yet `ggml-metal-ops.cpp:2890,2929` allocates output-local metadata and rebuilds map0 for each prompt projection. `kernels/mul_mm.metal:363-414` depends on IDs/count/strides, not weights or activations.

Share immutable mapping with graph-owned lifetime and invalidation for each ID version/shape/stride. Preserve each projection's independent activation scaling. Prove three real compatible maps become one, exact output and scratch safety, then complete-block gain above3% and twice drift. Prompt-only; distinct from N02 embedding ordering and P03 grouped dot products.

## Sparse GQA reuse, deferred

The model has24 query heads,2 KV heads,D256, full attention every fourth layer. `fa_vec_common.metal:59` maps twelve query heads onto each KV head. [MLX pinned GQA source](https://github.com/ml-explore/mlx/blob/99f109b567b969ef06974f1e0450ce0e2eeb4de2/mlx/backend/metal/kernels/sdpa_vector.h#L386-L485) shares K/V loads but requires q1, no mask and no sinks.

Our `qwen4exp.cpp:1001` QSA branch and `ggml-metal-ops.cpp:3518` sparse hint force vector attention. It needs a new masked/sparse T1-4 design, unchanged per-head reduction/softmax and normal cost attribution. Require15% attention+consumer component gain before model timing. A ready Tensor FlashAttention replacement was not found.
