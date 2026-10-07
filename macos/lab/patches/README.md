# Isolated native experiments

## Prepared M5 tuning and diagnostics

[m5-lab-controls.patch](m5-lab-controls.patch) adds disabled-by-default controls for BF16/Q2_0 row thresholds and bounded few-row tile/worker choices, plus optional GPU command-buffer timestamps. [mtp-m5-lab.patch](mtp-m5-lab.patch) combines these additions with the already measured shared-helper/MMA source. [The manifest](../config/m5_lab_experiment.json) pins every component, the full diff and the modified file list. Existing checkouts and launchers are preserved.

The candidate is compiled, with no GPU or model tests run at this preparation stage. It does not add a compressed-weight shader, change weights, change routed expert kernels or raise memory limits. [The test plan and validation limits](../bench/M5-NEXT.md) separate prepared comparisons from later measured/adopted improvements. This is private-fork laboratory work; no upstream PR is submitted.

`q2-masked-metal.patch` is an unchanged copy of Tim / Meld Labs' first patch from [meld-turbo](https://github.com/MeldlabsAI/meld-turbo/blob/ef2101f5f2517204e1d755522d0b84346c4c9f0a/patches/0001-metal-Q2_0-matvec-via-masked-pre-scaled-y-one-FMA-pe.patch), repository revision `ef2101f5f2517204e1d755522d0b84346c4c9f0a`, patch commit `c31f8234172cf1fe27f24370df8ab2cf0ec4ad47`. The original author and commit metadata remain in the patch; its MIT notice is in [MELD-LICENSE.txt](MELD-LICENSE.txt).

The patch replaces bit-by-bit conditional addition with pre-scaled inputs and masked multiplications for Q2_0 matrix-vector operations. It keeps the stored weights unchanged. Floating-point accumulation order changes, so output tokens can differ despite numerical checks passing.

Only this one Metal file is changed in the Q2 candidate. Other experiments below use separate checkouts and binaries. Source and patch hashes are pinned in [q2_experiment.json](../config/q2_experiment.json). [Our M5 Pro comparison](../bench/Q2-METAL.md) measured +0.3% / +3.7% writing speed, slower prompt processing and little complete-reply benefit. The normal engine remains unchanged.

## Draft vocabulary

[draft-vocab-upstream.patch](draft-vocab-upstream.patch) preserves Meld's original patch metadata. [draft-vocab-metal.patch](draft-vocab-metal.patch) ports it to our v0.6.0 pin, adds strict file validation, limits activation to MTP and retains the full head for CPU sampling, LoRA and scaled output. Our port also marks the copied buffer as weights: otherwise the scheduler places the output calculation on the CPU when the helper body is on CPU. Scheduler traces show the corrected output operation on Metal. The [manifest](../config/draft_vocab_experiment.json) pins both source and the multilingual 106,299-token list from the same Meld revision. Its MIT license is above.

The compact head is an additional allocation, about 111.5 MiB for our Q3 helper. The full helper head remains available for fallback. This experiment saves draft computation, not model-file space. The main model's graph and verification vocabulary remain unchanged.

## Shared helper weights

[mtp-shared-weights.patch](mtp-shared-weights.patch) is a focused backport inspired by [Daniel Han's qwen4exp/mtp branch](https://github.com/danielhanchen/llama.cpp/tree/6fcaa16f4b360649933a54d1f91ad40ed35c0e11). [The manifest](../config/mtp_shared_experiment.json) pins that reference and our independent port. The ggml authors' MIT notice is in [LLAMA-LICENSE.txt](LLAMA-LICENSE.txt).

Only an MTP-only helper may omit token embeddings/output. Its context validates the target architecture and shapes, then borrows the tensors without taking ownership. Draft KV remains separate: weight borrowing must not select the Gemma assistant's shared-KV speculation path. The target model must outlive the helper context, as it does in the server. No other graph changes from that branch are included.

The helper's file layout also matters on Metal. The loader maps the range between the first and last GPU tensor; interleaved CPU expert tables were inside that range and exhausted the GPU working budget. `scripts/prepare_shared_layout.py` groups the three CPU expert tables first and the 29 small GPU tensors last, checks every retained tensor byte and metadata field, and records the new file hash. With mixed placement, the helper's mapped GPU-weight span falls from 1,183 MiB to 45.6 MiB. This is a helper allocation change, not a reduction of the main model's memory. Mixed placement disables automatic CPU-op offload so the helper experts remain on CPU during prefill.

The derived helper removes exactly two tensors and verifies every retained tensor byte and metadata field. It borrows the target's Q5_K output rather than the original helper's Q3_K output, so proposal precision and acceptance can change. The target weights and graph remain unchanged. No experiment raises the system GPU memory limit.

## Few-row dense Metal math

[metal-mma-types-upstream.patch](metal-mma-types-upstream.patch) is an unchanged Git-format patch from [llama.cpp PR #30065](https://github.com/ggml-org/llama.cpp/pull/30065), commit `b0cb151326e6b436c265c641f23235864f7de090`. The original authorship and commit metadata are retained; the MIT license is in [LLAMA-LICENSE.txt](LLAMA-LICENSE.txt). This draft upstream change adds generic few-row MMA kernel instantiations and dispatch for BF16, Q2_0, Q3_K and other quantized types. It changes dense MUL_MAT operations, not the routed MUL_MAT_ID expert kernel.

[mtp-shared-mma.patch](mtp-shared-mma.patch) combines that unchanged patch with our existing shared-helper patch against the same v0.6.0 pin. The three shared-helper source files remain byte-identical to the control. [The manifest](../config/mtp_mma_experiment.json) pins both components and the full combined source diff. The candidate uses its own checkout, binary and build receipt; it accepts the existing packed shared helper without copying model weights.

The new row thresholds come from an M3 Ultra. Those upstream operation speedups are not M5 Pro inference results. Our experiment checks the actual model's pipeline selection and CPU-reference correctness before matched end-to-end measurements. Ordinary launchers are unchanged.
