# M5 draft-cap experiments

The existing-cap repair removes discarded helper work but has no qualified256-token speed gain. Fixed cap two fails the longer exact-output gate and is parked; no adaptive controller is implemented. Ordinary launchers and the practical three-guess control remain unchanged.

Future benchmarks and native diagnostic prompts use English prose and code only, per the user's October9 correction. Already completed evidence is preserved. Synthetic writing and cached ledgers remain English.

## D01: honor existing output-budget caps

Separate `m5-draftcap` engine over the practical copy/conv-direct control; global maximum three and all19 native allocation records unchanged. Helper greedy, minimum zero, confidence zero, packed sharedQ3/mixed placement/eight workers, Tensor API on, F16,4K, batch/ubatch512. IndependentABBA,256 fresh output tokens, temperature0.6, seed1234, warmup plus three measured repeats. No diagnostic traces during timing.

| English workload | Control TPS | Early-stop TPS | TPS change | Whole reply quicker | TPS control drift |
| --- | ---: | ---: | ---: | ---: | ---: |
| code | 59.482 | 59.464 | -0.030% | -0.027% | -0.129% |
| prose | 39.931 | 40.007 | +0.191% | +0.157% | +0.227% |

The code reply takes4.568→4.569s; prose6.678→6.667s. Both TPS deltas fall below1% and their respective control drift. None qualifies adoption. Separate synthetic/cache results remain in the [complete ABBA](../20261009T193647Z-m5-draftcap-tail/REPORT.md); cached512 +0.978% TPS is below its2.514% drift.

Bounded diagnostic control/off/tail replies match633 token IDs across22 requests. Completed-request cycles240 remain unchanged; successful helper decode calls720→702,18 discarded steps→0. Per-cycle acceptance and actual target dispatch rows match exactly. Seed repetition, cached/fresh continuation, normalEOS, short output limits, real streaming cancellation/reuse and oversized admission/recovery pass. This is2.5% less helper-step work in that diagnostic set, not2.5% faster model generation.

The timed bracket preserves84 exact fresh/cache output records and passes128 answer/cache checks. All four launches have healthy monitoring, clean exit and zero new swap. Astra independently recomputed the final summary and reviewed the saved native allocation/source/model evidence.

## D02: two guesses with maximum-three allocation

Forced two early-stop diagnostics initially match22 requests/633 token IDs against both a truncation-only two control and the repaired ordinary-three control. Same-width helper calls792→524 remove268 discarded steps. Relative to ordinary three, completed-request cycles240→264, helper calls702→524, target verification rows942→788. Less helper work requires more verification cycles; no TPS prediction follows from these counts.

The extended256-token synthetic512 writing fixture diverges in all three measured repetitions at zero-based index227, the228th emitted token: control16545 versus candidate25045. Prompts, seed1234, CPU sampling, weights/helper, engine receipts and all settings outside the cap axis match. Divergence was present in the running snapshot before interruption. This disproves exact output preservation on this fixture; it does not establish that the changed prose is lower quality or identify the exact numerical cause.

Stopped only the owned timing runner withSIGINT after saving evidence. The owned model exited cleanly, Metal allocations were released, memory monitoring remained healthy, zero new swap and no cleanup error occurred. The suite contains one complete control and a stopped candidate, not completedABBA. Do not present its partial observations as a qualified gain.

| Partial English observation | Three-guess TPS | Two-guess TPS | Status |
| --- | ---: | ---: | --- |
| code | 58.944 | 51.226 | Incomplete bracket; not qualified |
| prose | 39.594 | 38.930 | Incomplete bracket; not qualified |

Park fixed two and adaptive depth under the exact-output requirement. A materially different row-width/sampling/state implementation must first reproduce and repair the228th-token fixture, then qualify longer English/code, seeded continuation and mixed-cap behavior before any new speed trial. Do not simply repeat these same settings or weaken the output gate.

## Evidence and setup checks

- [Raw report and pins](REPORT.json), [independent Astra review](ASTRA-REVIEW.md).
- [Stock/off corrected analysis](../../features/20261009T193100376954Z-m5-draftcap-qualification/corrected-analysis.json), [off/tail native-step parity](../../features/20261009T193412937896Z-m5-draftcap-qualification/tail-parity.json), [two same-width parity](../../features/20261009T193516053626Z-m5-draftcap-qualification/batch.json).
- [Exact-output stop](two-early-output-stop.json), [candidate snapshot before interruption](two-candidate-at-stop.json), [final stopped candidate](../20261009T195332Z-m5-draftcap-two-2-draftcap2/result.json), [interrupted suite](../20261009T195018Z-m5-draftcap-two/comparison.json).
- [Isolated patch manifest](../../../config/m5_draftcap_experiment.json), [588 GPU math checks](../../features/20261009T192821Z-m5-math-m5-draftcap-on-conv-direct/checks.json), [decision ledger](../../EXPERIMENT-LEDGER.md).

The original diagnostic cap/parser and command-order rejection is preserved separately from its corrected analysis (X14). The tail suite's original relative report-path rejection is [preserved](../20261009T193647Z-m5-draftcap-tail/comparison-postcheck-original.json); frozen reanalysis recomputes all comparisons and validates outputs, settings, allocation, traces, math, source/model identity and memory without rerunning performance (X15). No original raw run is overwritten.

After the language-scope change,121 load-free checks pass; no additional model/GPU run was needed. All20 preexisting engines are unchanged;21 current receipts validate. The old offline/source snapshot from the actual runs is retained in [evidence](evidence/offline-at-model-runs.json). No hidden-state bit identity, checkpoint restore or near-context shift claim. No controller, launcher adoption, commit or push.

Next independent idea: an exact-format cooperative-input prompt kernel, after normal-shape/precision proof, focused on English prose and code. The adaptive path waits for a materially repaired exactness mechanism.
