# QSA shortcut qualification: R01 correction

Read-only Sol6.1 source audit, October9. No QSA change or model test was made.

The original research predicate `indexer_kpool_by_order=false` cannot activate on this target: `qwen4exp.cpp:82` sets it true. The false argument at line659 is the gather flag. A benchmark of that predicate would measure an inactive optimization.

The restricted geometric proof works with the actual cache-order mode. For unique contiguous text positions and padded pool count at most512, all complete visible pools plus the0-3-cell tail exactly cover the ordinary causal prefix. Positional holes, duplicate positions and sharing invalidate this proof. Ordinary M-RoPE text can be expanded to `[p,p,p,0]`; rejecting every `is_pos_2d()` batch would incorrectly exclude text.

Numeric behavior is still a blocker. Finite source tensors do not guarantee finite scores because Metal stages query/key values in F16. Overflow followed by addition of an invisible-pool negative-infinity mask can produce NaN. CPU and Metal clamp behavior differ for exceptional values; production fast math complicates the proof. A previous-step finite flag is insufficient. A current-step bound or device predicate with original-path fallback is required.

Before enabling the shortcut:

- Build a synthetic actual-score/mask fixture covering ordinary finite scores, zeros/ties, signed zeros, large values, NaN and both infinities in visible/future/padded pools.
- Check pool/tail boundaries, permuted physical cells, nonzero starting positions and lengths around2048. At that limit the padded pool budget increases from512 to576 and must fall back.
- Compare exact F16 mask bits and all raw/pooled cache digests. Keep the existing `n_sel` value and attention dispatch parameters.
- Include same-shape contiguous/hole/duplicate/sharing changes with graph reuse enabled and disabled. Store branch eligibility in the graph input and validate it in `can_reuse`.

The smallest eventual branch is after the existing pooled-cache scatter. Keep projections, pooling, normalization, RoPE and cache writes; remove only selection work once both geometric and numeric equivalence are proved. This candidate has no measured speed gain yet.

Source anchors: `vendor/llama-m5-copy/src/models/qwen4exp.cpp:82,663,728,796,851`, `src/llama-memory-hybrid-idx.cpp:516,965,1005`, `src/llama-kv-cache.cpp:1659`, `src/llama-batch.cpp:128`, `ggml/src/ggml-metal/kernels/fa_aux.metal:374,424,466`.
