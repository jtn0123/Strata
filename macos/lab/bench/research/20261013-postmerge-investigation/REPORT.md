# Post-merge M5 investigation and preparation

Researched October 13, 2026, after PR 4 merged as
`8c66e2030fe7e09b91fa4e0369c05cceabc1267e`. The user selected research and
preparation only. No model, GPU, storage benchmark or native build was run.
The checkout is back on `mac-m5-lab`; the fully merged local PR branch was retired.
The merged tree matches the tested PR head. Existing launchers and native sources
are unchanged.

## Correct the queue before testing

The earlier recommendation to try prompt-local drafting overlooked the completed
E02 entries further down the experiment ledger. It is not an untested next step.

| Existing path | Evidence | Current decision |
| --- | --- | --- |
| Varied-file code editing, E01 | Independent held-out Python/JavaScript/JSON comparisons qualified about 18.6–20.3% first-exposure generation improvement and 13.7–15.2% quicker complete replies over balanced. | Already validated; use the existing editing profile as the control for new editing work. |
| `ngram-simple`, E02 | 784 calls, zero drafts under a 12-token match and three-token proposal limit. The native implementation requires the possible copied continuation to be at least as long as the match. | Parked. The current upstream implementation still has that condition. Do not widen the qualified allocation just to activate it. |
| `ngram-map-k`, E02-M | Active and correct in a complete bracket, including 624 accepted proposed tokens in one candidate launch. First-exposure generation changes: Python +0.3818%, JavaScript −0.2072%, JSON −0.0681%; no language qualified. | Parked. A new matcher mechanism, identified workload gap or measured helper cost is required before revisiting. |
| Larger prompt chunks, E05/E06 | Optional Long Documents mode is already implemented and functionally validated. Qualified repeat long replies were roughly 8–9% faster in later monitored brackets. | Already available. Do not count another batch-size sweep as a new kernel investigation. |
| Warm short-text prefetch, P06 | Lookup envelope below 0.1% of complete reply time. | Parked for that workload. Long first exposure is a separately justified investigation. |

These decisions retain small gains as eligible. E02-M failed direction and
repeatability gates; it was not rejected merely for being below 1%. Raw failures,
inactive statistics, closing controls and original sources remain in their
existing local receipts. See [the ledger](../../EXPERIMENT-LEDGER.md).

## Fresh source check

The parent moved from the tested `ed4773eb7c8f1f1531ba2bc70e0e1987de2661af`
to `296b59d2f73c8f04a805df29c2fa97655adace78` (11 commits ahead at retrieval).
The relevant [Metal correction](https://github.com/Niko1221/Strata/commit/5ce999455b302722abec1900b85d3c9c604e83e8)
adds declared GDN launch limits, checks every dispatch against the pipeline's
threadgroup limit and fixes cooperative-tensor construction for older SDK headers.
It addresses correctness/compatibility; it supplies no measured speed gain for
our current llama.cpp engine. Carry it into an isolated parent investigation
before drawing conclusions from the parent kernels. Do not overwrite the old
comparison engine or its frozen sources.

Current llama.cpp was checked at
`091b6a7fc561b78da90a0ed2d524ec995458c657`. The bounded simple matcher remains
inactive under the existing long-key/short-proposal settings. The inspected MTP
diff mainly separates vision embeddings and hidden-state handling, plus clearing
the draft context's MoE-cache setting. It does not establish a new text-only speed
upgrade for this profile. Avoid a wholesale dependency update as a performance
experiment.

[Upstream prefetch PR 30405](https://github.com/ggml-org/llama.cpp/pull/30405)
is merged. Its macOS advisory-read change can be separated from its loader mapping
change. Our main weights and lazy lookup table already use different shards;
neither its RAM savings nor its M2 Ultra measurements transfer automatically.
The [MLX fork](https://github.com/yibie/strata-mlx/commit/2f11ab3e752adc84525d82c75d598b5898f96060)
has no newer main commit than the already reviewed 64 GB M5 Pro documentation
update at retrieval. Keep it as a separate capacity/quality project.

## Ordered investigation cards

The companion `plan.json` is a local, ignored specification, not an executable
runner. Every execution step remains held until the user authorizes testing.

| Order | Card | Benefit sought | Evidence required before timing a candidate |
| --- | --- | --- | --- |
| 1 | R0: merged real-model acceptance and baseline | A trustworthy current reference | English API replies, complete file edits, streaming/final counters, cancellation/reuse and restart all pass; record actual settings and owned-child cleanup. |
| 2 | R1: CPU/helper and submission-wait attribution | Locate avoidable pauses during generation | Diagnostic build reports actual helper-worker QoS and bounded helper-evaluation/GPU-wait envelopes. Untraced control measures observer overhead. |
| 3 | R2: helper QoS candidate, conditional | Small generation/response-time gain | R1 finds relevant workers below user-initiated QoS and enough attributed delay. Apply Apple's public QoS to helper workers only; successful application must be observed. |
| 4 | R3: parent-inspired long-prompt kernels | Faster reading and first response | Stage-level comparison isolates dense versus routed-expert prompt work; check actual shapes, activation precision, workspace and thread limits before porting one operation. |
| 5 | R4: bounded Apple lookup prefetch | Reduce first-exposure waiting | Actual lazy-row bounds, successful advice, page residency and demand-path page-in evidence; loader changes stay separate. |
| 6 | R5: focused failure contracts | Protect experiments and close coverage gaps | Reproduce specific missing validation/cleanup paths; extend strict checks to a driver when it is actively modified. |

### R0: baseline specification

Preserve the full Qwen3.8-Flash-Next GSQ-RCO Q2_0 target, packed shared Q3 helper,
mixed placement, eight helper CPU workers, MTP width three, confidence zero,
Tensor API on, P07 reduction, 4K/F16 and the profile's actual batch limits.
Balanced/editing use 512/512; Long Documents uses 1536/1536. Verify those limits
in target and helper logs, not only in requested arguments.

Start with one functional launch. Benchmark fresh short English prose, complete
Python/JavaScript/JSON editing and two long English retrieval/prose inputs.
Keep first encounter, same-input replay and a new question separate. Use complete
normal-EOS answers and a sufficient safety cap; capped or malformed replies retain
their raw evidence but cannot qualify performance. Functional-check timings are
not baseline speed results. Do not broaden into Chinese benchmarks.

Report native prompt/generation TPS, client first visible text, complete reply
time, actual output length, helper proposals/acceptance, queue delay where
observable, RAM floor, new swap and shutdown outcome. The UI's observational
history is useful but cannot substitute for matched workload measurements.

### R1/R2: helper scheduling and waits

Source inspection shows the Apple normal-priority branch in `ggml-cpu.c` retaining
inherited scheduling. It does not prove that real helper threads have low QoS.
Measure inside the actual helper workers; the launcher's own QoS is insufficient.
Distinguish requested QoS from effective boosts; an unspecified class does not
demonstrate low priority.
[Apple's guide](https://developer.apple.com/library/archive/documentation/Performance/Conceptual/EnergyGuide-iOS/PrioritizeWorkWithQoS.html)
and [public pthread declarations](https://github.com/apple-oss-distributions/libpthread/blob/main/include/pthread/qos.h)
provide the observation/application APIs. Avoid FIFO/realtime and unsupported
Apple CPU-affinity tuning.

The speculative dispatcher calls every implementation's `process()`. For a
non-shared helper context, MTP catch-up evaluates the accepted target batch and
maintains helper state even if a lookup wins the draft selection. That is a real
source path, but its cost is unmeasured. This may explain why another successful
lookup did not improve E02-M; that explanation remains an inference. Do not skip
catch-up work without proving positions, recurrent state, hidden-state handoff,
fallback, cancellation and a following request stay correct.

Trace helper catch-up, draft generation, CPU lookup/dequantization and GPU
completion waits separately. Avoid graph evaluation callbacks that break normal
fusion. Record unsummed/overlapping envelopes and observer cost; diagnostic
timings cannot become a speed claim. If workers already have suitable QoS, park
R2. If no meaningful helper/submission delay exists, do not build a scheduling
candidate merely because the API is available.

### R3: prompt-kernel feasibility

The [same-model parent comparison](../20261013-parent-metal-trial/REPORT.md)
observed 507.14 to 797.31 input tokens/s, 4.600 to 2.967 seconds to first text and
5.064 to 3.912 seconds for the complete short retrieval answer. Generation was
slower on the parent. These are backend/workload observations with different
batching, rounding, residency and transports, not a 57% isolated kernel gain.

Concrete source targets are `metal/src/engine/prompt_chain.inc`,
`metal/kernels/dense_mm.metal` and `metal/kernels/moe_mm.metal`. The parent's prompt
path converts dense matrices/activations to F16 and groups token rows by expert
for Metal matrix operations. It also has a parallel recurrent prompt path. The
changes span arithmetic, packing, dispatch and state handling; they are not a
single transferable switch. Our Tensor API and earlier grouped/tiled experiments
are already documented, so a proposal must name a different mechanism or shape.

First compare operation costs and total prompt time on actual 512/1536-token
chunks. If routed-expert matrix work dominates, qualify one parent-inspired
operation with identical Q2 weights, route IDs/order, explicit activation
precision and bounded scratch allocation. Preserve the current decode path.
Require numerical reference checks and whole-prompt/model-output validation.
Do not silently bundle F16 rounding, Q8 hyper-connection reads or larger workspace
into a claimed architectural gain. No extra full expert copy or anonymous
allocation is justified merely to inspect a kernel.

### R4: prefetch feasibility

The existing Qwen path calls `llama_prefetch_rows` for bounded lazy lookup rows,
but the pinned `llama_prefetch` platform guard excludes Apple. A macOS-only
advisory-read backport therefore has an identifiable integration point.
E03 observed a 145.288 ms lookup envelope on the first long document, about 2.94%
of its reply, and 1.527 ms on replay. The envelope includes CPU work and possible
overlap; it is not attributed physical SSD wait or a promised 3% gain.

Prepare bounded advice on actual eligible page ranges with file-lifetime and
overflow checks. Keep source IDs, advice return values, residency and page-in
counts. Do not preload the 28.8 GB shard, relabel fresh-process runs as cold SSD,
purge caches inside a bracket, or mix the loader fix into the prefetch candidate.
Stop this branch if hints do not cause useful overlap or warm-case overhead
outweighs first-exposure savings. Expected payoff is scoped first-response time;
generation TPS may be unchanged.

### R5: useful quality gaps

The existing source-bound report leaves real paths unexercised in
`trial_workloads.py` and the backend constructor. Candidate contracts include
backend URL/type validation, missing stop tokens and rejected timing/count
evidence across real-workload/cache transitions. Select actual behavior, not
tests that merely repeat implementation.

The parked Q2 campaign's per-run engine-identity check and the tuning helper's
declared workload-length check remain D01/D02. Fix these before reusing those
tools. Actively modified experimental drivers should join the maintained lint,
typing and protocol checks. Keep current floors/exclusions unchanged until
meaningful coverage supports an increase.

## Acceptance and boundaries

Each future candidate gets a new output directory, frozen source/model/binary
identities, fresh A/B/B/A controls and independent confirmation. Preserve exact
output/correctness, final timing packets, rejected receipts, continuous normal
pressure and zero new swap. Admission remains 34 GiB, ongoing floor 1 GiB and one
owned model at a time. No resource cleanup occurs inside a bracket.

Small gains remain eligible: both candidate launches must beat their controls
beyond twice control drift, with faster complete replies and no material
generation/first-text regression in the intended scope. Measure the combined
profile against its fresh control; do not add historical percentages.

At research preflight the host reported 48 GiB total, 35.6 GiB available and about
0.17 GiB existing swap. That clears the admission threshold at that moment, not
for a future run. Refresh it immediately before execution. No apps or VMs were
closed. Public links and synthetic specifications can be tracked; raw process
snapshots, private configs, downloaded source metadata and measurements remain
ignored.
