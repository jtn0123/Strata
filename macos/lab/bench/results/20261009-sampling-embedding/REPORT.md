# Backend sampling and embedding ordering: screened and parked

October 9, 2026. Neither candidate qualifies for a TPS trial. No speed gain or slowdown was measured in this pass, and the practical control remains `m5-copy` / `conv-direct`. The latest earlier matched 256-token controls remain about 59.4 TPS for code, 39.9 for prose and 40.6 for Chinese; these are carried forward from the [previous speed suite](../20261009-sequential-pass/REPORT.md), not measurements from the diagnostics below.

| Candidate | Actual result | Decision |
| --- | --- | --- |
| Target backend sampling | Four separated controls match CPU eligibility. All four min-p boundary cases exclude one token that CPU retains, including production min-p 0.05. | Park under the existing exact-semantics speed-only rules. |
| Upstream embedding ordering | Target remains CPU → Metal; planned Metal input tensors increase 27 → 30. Helper plan remains unchanged. | Park for the current pure-token input and mixed helper placement. |

## Sampling: accuracy screen before any model load

[Upstream #30223](https://github.com/ggml-org/llama.cpp/pull/30223) merged October 9 at 14:20:26 UTC (`a518119d30cade6260f7494120863428a3fe8ee5`). It stabilizes backend sampling graph topology across speculative ubatches; it does not change sampling arithmetic. The API snapshot and file patches are frozen in [upstream evidence](evidence/pr-30223.json).

The [native probe](../../features/20261009T183544060739Z-m5-backend-sampling-eligibility/m5_sampling_probe.cpp) links the verified current `m5-copy` engine and executes a direct Metal min-p graph. Eight seven-logit cases cover min-p 0.5 and 0.05, CPU sorted-flag true/false, and separated controls versus `logf(p)` with neighboring representable values. Inputs are already ordered in both flag cases; this is not shuffled-input coverage.

All four separated cases match. In every boundary case CPU retains token IDs `[0,1,2,3]`, while Metal retains `[0,1,2]`. CPU uses `>=` at the threshold; Metal's strict STEP excludes equality. Surviving Metal logits remain unchanged and input bytes are preserved. [Raw case results and hashes](../../features/20261009T183544060739Z-m5-backend-sampling-eligibility/checks.json), [native log](../../features/20261009T183544060739Z-m5-backend-sampling-eligibility/native.log).

This is a min-p stage result, not a complete default-chain, generated-token, RNG rollback or model-quality result. The graph fix was not backported: it cannot repair this arithmetic difference. `status: passed` means the diagnostic completed successfully; its decision is to park the optimization. No model or TPS benchmark ran for sampling. Zero new swap, healthy monitor, minimum available RAM 33.16 GiB, peak probe RSS 80.1 MiB.

Revisit N01 only after an isolated backend implementation matches eligibility, tie behavior, complete-chain selections and RNG/rollback behavior under the existing rules, or after explicit authorization of a separate quality-changing experiment. Do not assume setting a flag proves the entire chain is offloaded.

## Embedding: normal scheduler plans and bounded model parity

[Upstream #30160](https://github.com/ggml-org/llama.cpp/pull/30160) merged October 9 at 17:43:06 UTC (`8e2d31e0eb658d0382d3106a61369dff81f0c080`). The [isolated manifest](../../../config/m5_embedding_experiment.json) pins the common embedding and Qwen4exp PLE ordering changes on top of `m5-copy`, retaining `ggml_build_forward_order` for inactive branches. Gemma changes are outside this experiment; Qwen's separate MTP helper graph is unchanged. [Frozen patch/manifest](source/SHA256.json), [build log](evidence/build.log).

The candidate passes [572 GPU math cases plus 16 fused-residual cases](../../features/20261009T184336Z-m5-math-m5-embedding-on-conv-direct/checks.json), without new swap. Untimed normal-server captures then compare control/candidate with Tensor API on, `conv-direct`, depth three, confidence zero, shared packed Q3 helper, mixed placement/eight helper CPU workers, F16 KV, 4K context and batch/ubatch 512. Only the engine differs. Explicit scheduler debug2 and verbosity5 apply to these diagnostic launches; there is no evaluation callback and no speed claim from logging-perturbed timings.

Six requests per engine cover code, prose, Chinese, an exact 512-token prompt, a cached follow-up and that same follow-up fresh. Each returns 32 greedy tokens. All **192 token IDs and output text match**, as do draft-attempt/accepted counts per request. Both cached/fresh comparisons match; the cached request reports 508 reused tokens. This is bounded output/cache continuation parity, not equality of all hidden state, logits or general quality. [Paired captures and parity](../../features/20261009T184602948859Z-m5-embedding-topology/parity.json).

The [analyzed topology](../../features/20261009T184602948859Z-m5-embedding-topology/topology.json) compares 40 request/role/displayed-size groups, including 17 target and 23 helper groups. Each engine emits 23 target and 139 helper plan dumps during actual request byte ranges. Startup reserve plans are excluded. These are rebuild/reallocation **plan dumps**, not graph execution counts.

| Matched plan | Control | Candidate |
| --- | --- | --- |
| Target backends | CPU → Metal | CPU → Metal |
| Active target CPU operations | 2 GET_ROWS | 2 GET_ROWS |
| Target Metal split inputs | 27 | 30 |
| Helper backends | CPU → Metal → CPU → Metal | unchanged |
| Helper input counts by split | 0 / 14 / 2 / 2 | unchanged |

The token and PLE gathers already share the same CPU stage in the control. The candidate instead moves inactive mixed-input `DUP` / `SET_ROWS` nodes onto Metal, adding planned inputs `inp_mixed_embd`, the inactive mixed-token gather result, and `inp_mixed_slots`. The scheduler's split input-copy loop does not skip inputs merely because destination compute is inactive. Printed size strings/names are truncated; we do not infer exact transfer bytes or assert a measured slowdown. It fails the precondition of removing a normal boundary/input transfer, so no ABBA TPS trial follows.

Both accepted launches have healthy monitoring and zero new swap. Lowest available RAM is 2.149 GiB; highest process RSS is 37.442 GiB. RSS is not total unique Metal memory. The earlier incomplete pair retained a clean control but deferred the candidate before model load while RAM settled; it is excluded as comparative evidence. A new complete pair adds an explicit ten-second pause. [Original incomplete control](../../features/20261009T184458121799Z-m5-embedding-topology/m5-copy/capture.json), [deferred candidate](../../features/20261009T184458121799Z-m5-embedding-topology/m5-embedding/capture.json), [accepted control](../../features/20261009T184602948859Z-m5-embedding-topology/m5-copy/capture.json), [accepted candidate](../../features/20261009T184602948859Z-m5-embedding-topology/m5-embedding/capture.json).

Revisit N02 only for an isolated mechanism that removes the observed unnecessary inputs or a different embedding/padding/LoRA/input-placement workload with demonstrated redundant crossings. An upstream merge alone does not justify rerunning this identical setup.

## Harness repair, independent review and next experiment

An inherited `GGML_SCHED_DEBUG` or `GGML_SCHED_DEBUG_REALLOC` could contaminate ordinary timing environments. The maintained environment filter now clears this prefix, and diagnostic runners explicitly restore recorded debug settings. The existing inherited-environment regression reproduced the issue before the fix and passed afterward. This does not show that historical timings inherited those variables. [Fail-before log](evidence/scheduler-env-before.log), [pass-after log](evidence/scheduler-env-after.log).

Astra independently audited the sampling source/raw case evidence and the embedding runner/raw plans; it endorsed both bounded parking decisions. [Review notes and limitations](ASTRA-REVIEW.md). The final verification checks the current offline gate (120 passing tests after maintained changes), all 20 engine receipts, and unchanged fingerprints for all 19 preexisting engines. No owned model server remains, no ordinary launcher default changes, no commit/push, and no background application is stopped or restarted by this pass. [Verification](evidence/final-verification.json).

Next is **cost-aware draft length capped at three**, followed by exact-format cooperative-input prompt kernels. Astra found that per-cycle `dp.n_max` currently truncates MTP results after the helper loop; reducing that value alone would still execute the helper steps. The [concrete next card](../../research/20261009-astra-adaptive-depth-plan.md) first measures complete cycles, then proves actual early stopping and forced-cap correctness before bounded2↔3 calibration/policy and ABBA. It is not another blind increase in prediction depth. No adaptive policy or prompt kernel is implemented or benchmarked here. [Updated queue](../../research/20261009-astra-future-queue.md), [decisions N01/N02 and retry history](../../EXPERIMENT-LEDGER.md).
