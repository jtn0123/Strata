# Independent Astra draft-cap review

October 9, 2026. Existing `gpt-6-astra` reviewer independently inspected the isolated source, qualification runner and completed raw records. Read-only review; the coordinator alone built and ran GPU/model work. This is a source/correctness review, not a measured speed gain.

The scoped implementation has no identified blocking native defect for a single slot, greedy helper, confidence zero, minimum zero, and configured maximum three. The early stop preserves the existing target sampler, helper hidden-state handoff and catch-up. It does not change model weights, precision or placement. Global maximum three remains fixed, preserving recurrent-state allocation.

## Existing-cap repair

Independent off→tail comparison verifies 22 request identities and 633 token IDs/text exactly. Every actual target dispatch width and per-cycle acceptance record is identical. Completed-request cycles remain 240. Successful helper decodes fall 720→702; 18 discarded steps become zero. The captures include full/partial/zero acceptance, seeded/greedy requests, real cache reuse, EOS, short output limits, cancellation after five tokens, idle recovery and subsequent clean replies. Both have healthy monitoring, clean owned-child exit and zero new swap.

[Original control/off evidence](../../features/20261009T193100376954Z-m5-draftcap-qualification/corrected-analysis.json), [corrected off analysis](../../features/20261009T193100376954Z-m5-draftcap-qualification/off/reanalysis.json), [tail parity](../../features/20261009T193412937896Z-m5-draftcap-qualification/tail-parity.json).

## Fixed cap two with unchanged maximum-three allocation

Two-off→two preserves all 22 requests / 633 token IDs and text, acceptance records and target-width sequences:

| Completed-request work | Two-off | Two |
| --- | ---: | ---: |
| Draft cycles | 264 | 264 |
| Successful helper decodes | 792 | 524 |
| Three-row target verifications | 260 | 260 |
| Two-row target verifications | 4 | 4 |
| Discarded helper steps | 268 | 0 |

Tail→two also preserves those tested outputs. Draft cycles increase 240→264; helper decodes decrease 702→524 and target verification rows decrease 942→788. These counts do not predict TPS by themselves. Both cap-two captures have real cancellation, matching task IDs, cache reuse, healthy monitoring, zero new swap and current source/build/model proof. Frozen runner hashes match the recorded receipts.

Use `draftcap-tail` as the timed fixed-two control: it directly matches the qualification pair and changes only the cap-two override. Forced-three is unnecessary bookkeeping and was not separately captured.

[Cap-two same-width parity](../../features/20261009T193516053626Z-m5-draftcap-qualification/batch.json), [tail/two policy parity](../../features/20261009T193516053626Z-m5-draftcap-qualification/policy-parity.json).

## Corrected diagnostic postprocessing

The first off capture was rejected by its postprocessor because the server's raw remaining/context budget can exceed three; the configured maximum independently limits actual helper width. Preserve the original rejected receipt. A separate reanalysis checks original frozen runner identity, unchanged native engine/build and models, current offline gate and memory/cleanup before analyzing the same raw log with the corrected distinction. Models were not rerun for this correction.

The original stock/off option order differed only for explicit minimum-zero/greedy flags. Canonicalizing those two pairs preserves raw commands and rejects missing/duplicate/scope-changing flags. The corrected parser links each verification to its following actual target dispatch, records genuine cancellation, and correctly labels stock helper-step counting as unmeasured.

Before timed runs, the reviewer caught an overbroad `accepted ` log rejection: ordinary cumulative acceptance statistics use that word. The timing driver was corrected before execution to reject the exact diagnostic event syntax. Diagnostics and inherited LLAMA tracing are disabled during timing. The numerical adoption gate requires TPS and whole-reply improvement on at least two real workloads, above their respective control drift; its explanatory rule is scoped to this experiment.

## Limits

No full hidden-state bit comparison or checkpoint restoration event was observed. Oversized-prompt admission rejection and recovery do not prove near-context shifting. The unchanged maximum-three rollback path uses its existing recurrent-state capability. Qualification proves bounded output/continuation/cancellation behavior, not universal numerical equivalence. A controller remains deferred until timing and held-out evidence justify it.

## Completed tail speed audit

The reviewer independently recomputed the [tail ABBA](../20261009T193647Z-m5-draftcap-tail/comparison.json). Its 84 fresh/cache output records match exactly, 128 checks pass, four monitors are healthy with clean owned-child exit and zero new swap. Actual early-stop selections are false/true/true/false, all diagnostic events are absent, and all four runs have the same 19 allocation records. Both math prerequisite receipts pass with the same engine pin.

Code -0.030%, prose +0.191% and Chinese +0.012% TPS deltas all fall below their own control drift and the 1% threshold. Cached512 +0.978% also falls below its 2.514% drift. This supports removed wasted work, without a qualified speed gain.

The [original report rejection](../20261009T193647Z-m5-draftcap-tail/comparison-postcheck-original.json) was raised only when formatting a relative qualification-record path after the measured runs and output checks completed. A frozen reanalysis recomputes the summary and verifies source/model/current engine proof, settings, math, actual allocation, diagnostics, outputs and memory against unchanged raw records. The reviewer checked recorded raw-result and frozen-source hashes, unchanged order/run IDs/prerequisite references and exact recomputed summaries. No performance rerun was used or needed. The timing driver resolves input paths before subsequent runs.

## Extended fixed-two trial and final decision

The reviewer independently verified the [exact-output stop](two-early-output-stop.json): all three completed synthetic512 repetitions diverge at zero-based index227, the228th emitted token,16545 versus25045. Prompt hashes, seed1234, complete generation settings/CPU sampling,256 output count, engine/model/helper/runtime/source receipts and non-axis settings match. The same14 completed cases exist in the running snapshot taken beforeSIGINT and in the final stopped candidate; the divergence predates interruption.

Candidate monitoring is healthy, zero new swap, owned child exited, no cleanup error. Native log shows orderly cleanup and Metal deallocation; no model server remains. Only the first control is registered in the failed suite, so there is no completedABBA or qualifiedTPS comparison. Earlier633-token diagnostic parity remains valid for its tested requests and lengths. Park fixed two and adaptive depth under the exact-output requirement.

The user's latest scope is English prose and code. No further Chinese investigation or benchmark was performed; completed historical evidence remains intact.
