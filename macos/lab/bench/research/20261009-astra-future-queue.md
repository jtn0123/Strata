# Astra's next M5 experiments

Current completed follow-up: [P11/P12 compact scheduling](../results/20261009-compact-tiles/REPORT.md) is screened: V1 long-uniform time is 3.596–4.677% shorter, V2 takes 0.456–2.226% longer; both below the fixed >10% model gate. No model/TPS trial. Do not queue unchanged R03 again. The [R05 source card](20261009-astra-stateless-checkpoint-plan.md) holds general serialization omission pending cache lifetime and split preservation; Q2 cooperative-input remains unimplemented.

Latest research: [October9 multi-model speed review](20261009-multi-model-speed-review/REPORT.md) adds source-backed winner-only helper selection, all-visible QSA selection, shared prompt route maps and compact active prompt dispatch. Recommended bounded generation probes are helper selection and QSA equivalence; prompt-only work has separate response-latency metrics. These are research proposals, with no implementation or new benchmark gain. D01/D02/N01/N02 remain parked under their recorded revisit conditions. The cooperative-input idea below remains a later prompt candidate rather than the only next option.

The first six ideas below have now received bounded screening: [sequential report](../results/20261009-sequential-pass/REPORT.md), [sampling/embedding report](../results/20261009-sampling-embedding/REPORT.md), [draft-cap report](../results/20261009-draftcap/REPORT.md), and [decision ledger S01–S05/N01/N02/D01/D02](../EXPERIMENT-LEDGER.md). Existing-cap early stop is correct within tested scope but has no useful256-token gain; actual cap2 diverges at the228th emitted token of a longer English fixture. Fixed2/adaptive work is parked under the exact-output rule. Next independent idea is exact-format cooperative-input prompt work, focused on English prose/code. Read the ledger before proposing a repeat; estimates below are archived hypotheses, not measured gains.

Read-only Astra evaluation, refreshed October 9, 2026. The estimates below are hypotheses for allocating experiment effort, not measured improvements or additive gains. All three immediate experiments preserve model weights, numerical precision, context and maximum draft depth.

| Order | Idea | Why investigate | Effort | Hypothesized TPS change: low / base / high |
| --- | --- | --- | --- | ---: |
| 1 | Parallel SwiGLU activation epilogue | Current fused kernel serializes activation math in one GPU lane | Small | -1 / 0 / +1% |
| 2 | Additional Metal encoding threads: 0 or 2 versus current 1 | Existing backend mechanism; preparation overhead and helper CPU contention need a real model test | Small | -2 / 0 / +2% |
| 3 | Two/four Q5_K vocabulary output rows per SIMD group | Eligible target/helper single-token full vocabulary heads currently use one; reuse the original templated arithmetic | Small-medium | -2 / +0.5 / +2% |
| 4 | Target backend sampling with a static speculative graph | A relevant graph fix merged today; actual sampler eligibility must be proven | Medium | -2 / +0.5 / +2% |
| 5 | Embedding gather graph ordering | Active upstream work could reduce CPU/GPU scheduler crossings if they exist locally | Medium | -1 / 0 / +1%; prompt speed possibly +3% |
| 6 | Draft length based on accepted-prefix and actual cycle cost | Code/prose acceptance differs; keep maximum draft depth three | Medium-high | -3 / +1 / +4% on mixed workloads |
| 7 | Cooperative-input dequantization for prompt matrix operations | Requires an exact-format Metal TensorOps adaptation; GGUF Q2_0 is not automatically a native MX format | High | Decode base 0%; prompt -3 / +2 / +8% |

Zero improvement is plausible for every immediate candidate. Prior grouping, serial gate tiles, GDN rows and lookup prefetch are parked based on the [last pass](../results/20261009-next-few/REPORT.md).

## Sequential execution and acceptance

1. **Activation epilogue:** keep every Q2 dot product and uniform SIMD reduction unchanged. Each output lane retains its reduced gate/up scalars, then performs the same activation after all reductions. Require all 58 cases and exact bits. Compare the practical unfused control, the new lane version and the old serial gate-up4 as an explanatory ablation. Before results, Astra endorsed a >=3% real R4 complete-block reduction above twice control drift, both candidate launches faster than both controls, real R5 regression <=2%, and all-distinct regression <=5%. This qualifies at most one model trial; it does not establish a model gain.
2. **Encoding threads:** an initialization-only 0..2 override, preserving n_main, fusion, barriers, synchronization, placements and all helper CPU worker settings. n_cb counts extra encoding threads, corresponding to up to 1/2/3 command buffers including the main thread. Test both backend constructors and effective settings. Fusion-stat mode forces zero and must stay disabled for timings. Run independent 1/0/0/1 and 1/2/2/1 model brackets; stop after the bounded sweep if neither improves above drift.
3. **Q5_K head:** start with nr0=2, then nr0=4 at unchanged nsg=2. Guard exact K=2560, M=248320, Q5_K stored weights, F32 input/output and a single activation row. Preserve original unpacking, accumulation and reduction order. Test the full vocabulary, cancellation, diverse activations, top-k/ties and unsupported shapes/layouts. No vocabulary trimming or expanded-weight cache. Require >=10% repeatable whole-head-plus-consumer improvement before a model trial.

Model adoption remains >=1% fresh TPS and whole-reply improvement on two real workloads, above bracket drift, with exact output tokens/text, rollback/cache checks and zero new swap. Each candidate gets an independent fresh control. Cached responses remain separate. All builds and heavy execution are serialized; default launchers stay unchanged until qualification.

The [fresh independent Astra evaluation](20261009-astra-next-plan-review.md) supplied the staged gates, now executed in D01/D02: isolated actual early stopping, bounded native-step/target-width proof, exact outputs/continuation/cancellation, full tailABBA and an early-stopped fixed2 trial with unchanged maximum-three allocation. [Independent result audit](../results/20261009-draftcap/ASTRA-REVIEW.md) confirms no qualified gain and the longer exactness failure. The controller remains unimplemented; a materially changed implementation must repair the recorded fixture before any held-out calibration. The original16-observation/3% rule remains unsupported. [Updated card](20261009-astra-adaptive-depth-plan.md). Future benchmark/capture prompts and adoption use English prose and code only; completed historical evidence is preserved.

## Upstream refresh and later prerequisites

[llama.cpp #30223](https://github.com/ggml-org/llama.cpp/pull/30223) stabilizes backend sampling graph topology across speculative ubatches. GitHub API verified merged at 2026-10-09 14:20:26 UTC, merge a518119d30cade6260f7494120863428a3fe8ee5. N01's min-p accuracy screen now parks the complete backend experiment; the graph fix does not alter arithmetic and was not backported. It is not a measured upgrade here.

[llama.cpp #30160](https://github.com/ggml-org/llama.cpp/pull/30160) merged at 2026-10-09 17:43:06 UTC, merge8e2d31e0eb658d0382d3106a61369dff81f0c080, head49b76388035a748ca00cd73c32d67dc9a560d656 (API verified). N02's isolated backport passes bounded output/cache parity but does not remove any target handoff and adds planned Metal inputs27→30. Parked without TPS trial for this current pure-token baseline; see the report for limits and revisit conditions.

Astra checked [current Metal context](https://github.com/ggml-org/llama.cpp/blob/50e3e3e480c80b9ee0ea067e475602d540dc62c8/ggml/src/ggml-metal/ggml-metal-context.m) and [Q5_K constants](https://github.com/ggml-org/llama.cpp/blob/50e3e3e480c80b9ee0ea067e475602d540dc62c8/ggml/src/ggml-metal/ggml-metal-impl.h), confirming the mechanisms already exist upstream. These experiments remain based on our pinned, tested source; no wholesale upstream update is included.

The native Strata metal-mac head remains [13da72298e0505bdcc4069bd87e96bc11e7b7aa5](https://github.com/liangxiwei/Strata-for-mac/tree/13da72298e0505bdcc4069bd87e96bc11e7b7aa5). Astra found no fresh native-fork kernel replacement for this queue. [Apple TensorOps guidance](https://developer.apple.com/videos/play/wwdc2026/330/) motivates the later prompt experiment; actual format support and precision still need proof.


## October9 execution update

R02's raw-winner premise was corrected for model token suppression. W02 implements exact parallel top10: complete component8.1% quicker, full-model code+1.092%TPS/prose+0.942%, whole replies+0.959%/+0.829%; below default adoption, optional trial. R01's original guard is unreachable and numerical equivalence is unproved; the corrected synthetic qualification fixture is next, followed by exact-format cooperative-input prompt work. [Measured outcomes and retry rules](../EXPERIMENT-LEDGER.md), [QSA qualification](20261009-qsa-qualification.md).
