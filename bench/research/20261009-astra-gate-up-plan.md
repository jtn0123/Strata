# Conditional next experiment: Q2 gate/up plus SwiGLU

Prepared October 9, 2026. This is a reviewable experiment plan, not an implementation or a speed result. Only this Markdown file was written during preparation; no native changes, builds or GPU runs were performed.

**Plain-language next step:** test whether calculating the expert's gate and up projections together, then applying SwiGLU immediately, saves time while producing exactly the same answers.

Run this only if the current grouping ABBA fails its operator gate, or later as a separately matched experiment. Do not stack it on a losing grouping kernel. Preserve the grouping variants and negative results. This card does not predict a TPS improvement.

## Control and bounded candidate

Start a new isolated engine from `vendor/llama-m5-copy`, pinned llama.cpp `d81235049384534c167caea52b85a694f6103d14` plus `patches/mtp-m5-copy.patch`. Keep the accepted direct-convolution setting, Tensor API setting, precision and existing dispatch defaults unchanged. Introduce one disabled-by-default experiment flag. Keep expert down projection and final expert reduction separate.

The first candidate handles one routed assignment at a time. It reads the two existing Q2_0 weight buffers, computes gate/up with the original Q2 arithmetic, and writes the SwiGLU result. It does not group repeated experts, cache decoded weights, change quantization, pack/reorder the model, or require per-layer host readbacks.

## Source evidence and actual graph requirement

The Qwen model calls the expert builder with `LLM_FFN_SILU` in [qwen4exp.cpp](../../vendor/llama-m5-copy/src/models/qwen4exp.cpp), `build_layer_ffn`, line 1149. The separate expert projections are constructed in [llama-graph.cpp](../../vendor/llama-m5-copy/src/llama-graph.cpp), lines 2241 and 2254, and the ordinary activation is `ggml_swiglu_split(ctx0, cur, up)` at line 2297. The merged gate/up, scale, bias and clamp branches nearby must remain outside the initial candidate.

The [saved split capture](../features/20261009T091011Z-m5-split-batch/depth3-split/capture.json) contains target layer-zero events 14641/14642 for Q2_0 gate/up `[2560,640,512,1]`, followed by event 14647 for `ffn_moe_swiglu-0`, `GGML_OP_GLU`, output `[640,10,4,1]`. Events 14643–14646 include GET_ROWS, shared-expert GLU and unary work between the projections and expert GLU.

**That capture proves the observed operator identities and shapes, not normal optimized-graph adjacency or normal kernel cost.** Its evaluation callback splits execution and changes fusion. A normal, fusion-preserving graph inspection is still required before implementing the matcher: record original and optimized node indices, exact gate/up input pointers, ID tensor identity, GLU input order, intervening nodes and all consumers. Use a correctness-only structure/dispatch marker, not callback timings or fusion-stat performance measurements. Verify that the pattern survives normal scheduling and actually fires in target R4/R5 graphs; do not infer eligibility from the standalone probe alone.

## Matcher, lifetime and fallback contract

The proposed subgraph is two sibling `MUL_MAT_ID` operations feeding one split `GLU/SWIGLU`. It is not a linear dependency chain: the second projection does not consume the first. The generic chain validator in [ggml-metal-fusion.cpp](../../vendor/llama-m5-copy/ggml/src/ggml-metal/ggml-metal-fusion.cpp), around line 1110, therefore cannot be used unchanged.

- Require both weights to be contiguous Q2_0 `[2560,640,512,1]`; F32 contiguous activation `[2560,1,R,1]`; identical I32 ID tensor `[10,R,1,1]`; and `R` equal to four or five. Start with contiguous IDs. Require contiguous F32 `[640,10,R,1]` projections and final output.
- Match exact `GGML_GLU_OP_SWIGLU`, two explicit inputs, and their gate/up roles. Do not identify the gate by graph order or tensor name. Reject other GLUs, clamps, scales, biases, LoRA branches, merged gate/up layouts and extra dimensions.
- Reject any external consumer, retained diagnostic output or view of either elided projection. Explicitly validate the sibling subgraph with `ggml_can_fuse_subgraph_ext` or equivalent existing consumer checks; do not bypass consumer validation merely because the pattern needs a custom matcher.
- Integrate the pattern with allocation dependencies and optimizer grouping as well as encoding. `ggml_metal_fusion_add_pattern_alloc_deps` at line 807 keeps external inputs alive through the fused output; `ggml_metal_fusion_max` at line 1170 informs optimizer grouping. A dispatch-only adjacent-node check can miss a reordered pattern and cannot establish safe allocation lifetimes.
- Preserve full memory-range validation at encoding, using the existing checks around line 985. The fused destination must not overlap either weight buffer, activations, IDs or another live output. Keep optimizer-phase structural checks separate from allocated-address checks. Reject partial matches and patterns crossing encoder/scheduler boundaries.
- Every rejected case executes the existing implementation. Test these rejections, not just the positive kernel path.

## Arithmetic and register budget

Use the existing bit sums, lane/K partition and SIMD reduction from [mul_mv.metal](../../vendor/llama-m5-copy/ggml/src/ggml-metal/kernels/mul_mv.metal), `kernel_mul_mv_q2_0_f32_impl` at line 386. The reference SwiGLU is [unary.metal](../../vendor/llama-m5-copy/ggml/src/ggml-metal/kernels/unary.metal), line 261: `x0 / (1.0f + exp(-x0))`, then multiplication by `x1`. Match its F32 semantics and input order exactly.

The grouping investigation showed why source-level algebra is insufficient: streamed loop variants passed strict CPU error checks but changed output bits; restoring the original ordered pair body restored exact parity. Preserve operation order and test compiler output behavior through exact result comparisons. Do not introduce fast approximations or weaken the bit gate.

Two projection accumulators and two weight-address sets increase live state. A separate four-output-row-per-projection control limits this pressure; an eight-row variant might reuse more activation loads but also reduce occupancy or spill. Evaluate only these bounded alternatives if correctness passes. Do not add repeated-expert grouping to the same kernel. The smaller tile does not automatically reduce activation loads compared with the stock eight-row kernels.

## What could be saved, and what is not established

Replacing two projection dispatches plus GLU with one dispatch could remove two dispatches and an intermediate dependency barrier. Gate/up writes plus GLU reads total `4 * 640 * 10 * R * sizeof(float)`: **409,600 bytes at R4 and 512,000 bytes at R5 per layer**. These are logical tensor transfers that the fused kernel could avoid. Its final activation write remains.

Expert weight references remain unchanged. The compiler/allocator may still reserve intermediate storage unless elision removes it; do not claim an allocation reduction without measurement. Hardware caches may already satisfy much of this traffic. Lost gate/up concurrency, register pressure and interactions with shared-expert work can outweigh launch or traffic savings. None of the arithmetic above is measured DRAM traffic, saved wall time or a TPS forecast.

## Checks and decision gate

1. Prove the normal model graph is eligible and the intended fused dispatch fires, with ordinary fusion and graph optimization enabled. Confirm every rejection path, additional-consumer case, alias case and graph-reuse case. Disable diagnostics for timing.
2. Use the actual `ggml_swiglu_split` operation in the operator fixture. Retain recorded R4/R5 routes, distinct/shared/duplicate routes, exact stored Q2 weights, cancellation/wide inputs and adjacent-row fallbacks. Check baseline and candidate activated/down outputs bit-for-bit, with independent CPU dequantization references. A diagnostic variant that retains gate/up outputs is a separate test and must not accidentally disable the fusion under test.
3. Measure the complete sequential gate/up/SwiGLU/down graph with weighted ten-expert reduction and residual after each block. Include all dispatch, allocation/scratch and synchronization costs. Use the two independent full-512-expert weight sets and eight recorded routes already prepared for grouping; retain input/ID/weight preservation and memory/swap checks.
4. Run matched fresh ABBA launches with unchanged environment, no callback profiler and no diagnostic markers. Require a repeatable real-route operator improvement beyond bracket drift, exact correctness, and no material all-distinct regression. Stop if register pressure or lost concurrency erases the gain; do not chase more tile variants without new evidence.
5. Only a passed operator gate qualifies a separately matched full-model test at the existing MTP depth-three settings. That test must establish tokens/logits/state behavior, sustained writing TPS, complete-reply time, acceptance and memory on real prose/code workloads. Operator latency alone is not model TPS.

This preparation leaves implementation and performance claims pending. If grouping fails, the user-facing recommendation is: **keep the current engine; the next small test is calculating gate and up together, with exact-output checks before any model benchmark.**
