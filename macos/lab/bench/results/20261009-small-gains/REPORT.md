# Small-gain validation — October 9, 2026

**Three possible additions are tracked. Native correctness passed; full-model performance validation is held for memory. No new TPS gain or combination has been validated in this pass.**

The user authorized accepting useful, repeatable small gains instead of requiring an arbitrary 1% or 10% threshold. This is a new protocol, declared before new model timings. Earlier gates, decisions and evidence remain intact.

| Candidate | Earlier evidence | Current validation | Next test |
| --- | --- | --- | --- |
| P11 compact expert/token scheduling | Uniform T508/T512 two-block component time 4.677%/3.596% shorter. These are component gains, not model TPS. | Exact native outputs and activation/fallback checks pass alone and with other flags. | Fresh original-control ABBA on complete long English code/prose prompts; first-token and whole-reply latency. |
| P07 exact ten-expert reduction | Earlier code/prose generation gains about 0.90%/1.05%, reply gains about 0.94%/1.02%. | Native finite output bits, CPU references and expected ordered fusion counts pass alone and with other flags. | Fresh ordinary English code/prose ABBA, then one confirmation if qualified. |
| W02 exact helper top10 | Earlier code 59.3795→60.0278 TPS (+1.092%); prose 39.9378→40.3139 (+0.942%). Replies 0.959%/0.829% quicker. | All ten IDs, gather bits, consumers and adversarial fast/fallback fixtures match with every flag combination. | Fresh ordinary English code/prose ABBA, then one confirmation if qualified. |

Earlier numbers are context, not fresh confirmation. See the [live candidate tracker](../../small-gain-candidates.json), [preregistered plan](../../../config/m5_small_gains_plan.json), [experiment ledger](../../EXPERIMENT-LEDGER.md) and linked original evidence there. P12's unchanged column-first grid remains excluded because it was slower on the required component cases.

## What is prepared and verified

- New isolated `m5-small-stack`, containing exactly original-copy + P07 + W02 + P11 V1, with independent switches for each feature. No change to ordinary app defaults. Native source/patch/build receipts are pinned.
- All 27 model-free correctness launches pass: original controls plus all eight combined-engine flag settings, each checked with all three inherited probes. This covers 3,681 principal case records and an additional 270 adversarial top10 fixtures. All 27 launches add zero swap. Largest probe process RSS: 1.677 GiB.
- Disabled features retain original arithmetic and dispatch; inherited top10 scratch planning still exists when its flag is off. This is an output/dispatch control, not a claim of identical allocations. Reduction and compact scratch remain separate and allocator-accounted.
- 156 offline checks pass, including the metric decisions, exact activation requirements, original model control, zero-swap monitor settings, removal of synthetic filler timings from short cohorts, and cached-regression flags.
- All 27 unique run identities, six probe builds/current binaries, engine pins, 161 archived source files, raw outputs/logs and resource receipts are verified before model execution. All 26 original engine receipts remain unchanged.
- Independent Astra source/harness review found no remaining blocker. This is source review, not certification of future model speed. [Review receipt](independent-source-review.json).

## How small gains will qualify

Each real task has an excluded warmup and three measured 256-token responses in every fresh process launch. Use A/B/B/A, with the median within each launch, then average the two launch medians per arm. Retain every repetition and both between-launch drifts; do not claim statistical significance from two launches per arm.

A metric can qualify at any positive percentage if its benefit exceeds twice its own control drift and both candidate medians beat both control medians. The same metric scope must qualify on both English code and prose. TPS, first-token delay and complete reply time are separate; a prompt-latency scope also requires complete-reply benefit. Material TPS/first-token/reply regressions block the workload scope. Exact fresh/warmup/cache outputs, native activation, source/model/settings identity and resource guards are mandatory.

First screen all three candidates independently. A qualified screen receives exactly one fresh confirmation bracket. Only candidates qualifying in both brackets can enter a frozen combined test; percentages are never added as a claimed gain. Cached512/2048 timings are separate diagnostics; loss greater than max(5%, twice own drift) flags independent follow-up before default promotion. No automatic default adoption.

## Excluded attempts and present hold

**X23 — results-checker error, not a native feature failure.** The first original-control top10 probe completed with return code zero and no new swap, but the new checker incorrectly expected stdout-only `guard-stride` in JSONL. The inherited runner intentionally excludes that single JSONL record. All 30 stdout fixtures remain validated. Entire first source/runtime/raw bundle is preserved; the corrected full 27-launch native qualification passed. [Diagnosis](native-initial-excluded/exclusion.json).

**X24 — original-control cold model load, resource-only exclusion.** Before any response or model-ready event, macOS system swap grew by 3,211,264 bytes (3.0625 MiB). The unchanged zero-new-swap monitor terminated the original `m5-copy` child near lazy-table prefetch. No candidate ran and no speed data exist. Existing swap is separate from new growth; causality from background work has not been established. Preserve the initial source archive and raw attempt. [Diagnosis and paths](model-initial-excluded/exclusion.json).

The plan permits at most one complete resource-only retry after fresh headroom and quiet-host checks. The subsequent 90-second preflight stayed around 31.8–32.0 GiB available, below the unchanged 34 GiB launch requirement. The retry was **held before any model launched** and the single retry allowance remains unused. No large unrelated job or VM was identified for safe closure; no unrelated app/service was stopped. No cache purge, forced memory pressure, source/fixture change, relaxed guard or pooled partial result was used. [Held preflight](resource-retry-held-plan.json), [log](resource-retry-held.stdout.log), [frozen held driver](resource-retry-held-runner.py).

There is no model server or background benchmark waiter left running. The [retry driver](resource-retry.py) can resume after the same resource requirements pass, verifies the current complete closure, freezes its own execution receipt and uses the unchanged canonical bracket function. It will stop on any further resource/parity/activation failure. A held preflight is preserved rather than overwritten. No commit, push or PR was made in this pass.

## Evidence

- [Native source/build/raw verification](native-checks.json)
- [Original-engine verification before model load](before-model-verification.json)
- [Offline validation](offline-validation-reviewed.log)
- [Candidate status at this hold](tracking-held.json)
- [Canonical model runner](../../../scripts/benchmark_m5_small_gains.py)

The initial hold was resolved by the remote cleanup below. All three model screens and P07's independent confirmation are now complete. Current practical baseline remains original `m5-copy`/`conv-direct`; comparisons use their own fresh controls and do not replace historical TPS figures from other workloads.

## Remote resource recovery and retry

After user authorization, administrator-only global cache purge was cancelled because the user is remote. Targeted read-only invalidation of verified model-file cache increased available RAM **32.09 ->36.06 GiB (+3.97 GiB)** and held **>=35.97 GiB for 60 seconds, normal pressure, zero new swap**. Model file identities and benchmark settings/guards remained unchanged. [Raw cleanup receipt](memory-investigation/model-cache-trial-20261010T033512403513Z/result.json), [explanation](memory-investigation/REPORT.md#authorized-remote-cleanup-2026-10-09-evening), [campaign host preparation](host-preparation-20261010T033702104144Z.json).

The original one-resource-retry driver completed with its unchanged complete source closure and exited zero. **All 16 full-model launches passed with zero new swap.** The initial X24 failure and held preflight remain excluded; no partial results were pooled. [Driver log](resource-retry-remote-cache-20261010T033702104144Z.stdout.log), [final verification](final-model-verification.json).

## Completed model results

All tests use the same full Qwen3.8-Flash-Next Q2_0 model and packed shared Q3 helper, mixed placement, depth3, 8 helper CPU workers, F16 KV, 4K context, batch512, Tensor API on, temperature0.6 and seed1234. Each bracket is fresh A/B/B/A, with an excluded warmup and three measured repetitions per task per launch. Percentages use averages of the two launch medians per arm. They are protocol-qualified repeatability results, not a statistical-significance claim or additive gains.

| Candidate/phase | English task/input tokens | Baseline TPS | Candidate TPS | TPS change | Reply time reduction | Decision |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| P11 compact screen | Code/859 | 45.8333 | 45.6918 | -0.3087% | -0.2807% | No qualified gain |
| P11 compact screen | Prose/1004 | 46.8932 | 46.8197 | -0.1566% | -0.2979% | No qualified gain |
| P07 reduction screen | Code/48 | 59.6869 | 60.0008 | +0.5259% | +0.5198% | Qualifies generation/reply |
| P07 reduction screen | Prose/53 | 40.0938 | 40.3294 | +0.5878% | +0.5968% | Qualifies generation/reply |
| W02 top10 screen | Code/48 | 59.6769 | 60.1036 | +0.7151% | +0.5308% | Held: first-token guard |
| W02 top10 screen | Prose/53 | 40.0954 | 40.3542 | +0.6453% | +0.5189% | Qualifies this task only |
| P07 reduction confirmation | Code/48 | 59.7194 | 60.0842 | +0.6107% | +0.5953% | Independently confirmed |
| P07 reduction confirmation | Prose/53 | 40.0582 | 40.3755 | +0.7921% | +0.7631% | Independently confirmed |

**P07 is a confirmed possible addition for short English generation and complete reply time.** Both independent brackets qualify on both tasks, with no fixed minimum gain. Its confirmation saves 27.08ms/code reply and 50.79ms/prose reply at 256 generated tokens. Confirmation control TPS drift is only 0.0300% and 0.0458%, respectively. No larger-prompt P07 scope is established by this pass.

**W02 remains a possible tradeoff, not a failed speed idea.** Both tasks have positive TPS and overall reply improvements above their control variation. Code first-token latency increases 278.645 ->282.170ms (+3.525ms/+1.2651%); this exceeds the frozen `max(1%, twice own drift)` material-regression limit. Prose adds 4.023ms, which is within its larger control-latency drift allowance. The code guard blocks the common scope, so no W02 confirmation or combination ran. Any decision to tolerate a few milliseconds must be preregistered with an explicit latency tradeoff and freshly validated; this result is not retroactively relabeled accepted.

**P11's V1 component gain did not translate to these model workloads.** Retain its native/component proof and this complete model result. Revisit only a materially different implementation or prospectively declared workload exposure; an unchanged speed rerun is not needed to rediscover this flat result.

Only reduction was independently confirmed. The plan requires at least two independently confirmed candidates before combination testing, so no combination launched and no percentages were summed. App defaults and launchers remain unchanged.

Validation: **416 answer/cache checks passed; exact parity verified across 256 fresh, warmup and cached output records** within the four independent brackets. All feature-encoding receipts and memory comparisons passed; no cached-regression follow-up flags were raised. Complete canonical source closure and native prerequisites were reverified after execution. No model server remains. Post-benchmark available RAM was **38.49 GiB**, normal pressure, with swap still exactly **529,137,664 bytes**, unchanged from the cleanup baseline. Colima remains stopped. [Resource receipt](memory-investigation/post-benchmark-resources.json).

- [P11 full-model screen](../20261010T033705Z-m5-small-gains-p11-screen-resource-retry1-long/REPORT.md)
- [P07 screen](../20261010T034406Z-m5-small-gains-p07-screen-short/REPORT.md)
- [W02 screen](../20261010T034955Z-m5-small-gains-w02-screen-short/REPORT.md)
- [P07 independent confirmation](../20261010T035543Z-m5-small-gains-p07-confirmation-short/REPORT.md)
