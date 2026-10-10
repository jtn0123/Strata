# Exact parallel helper top10 selection

Isolated `m5-top10` over the unchanged practical `m5-copy` patch. No model/sampler/precision/vocabulary/cache change. Full-model ABBA completed; small benefit below the default-adoption gate.

The raw-winner proposal was replaced: model suppress-token bias can change the winning candidate, so all ten ordered candidates must be preserved. Parallel local distinct maxima retain counts; global selection uses the new path only when each selected value is unique and all inputs are finite normal values or zeros. Selected ties, subnormals and nonfinite values execute the unchanged legacy sorting stages.

| Packed-head input | Control ms | Candidate ms | Time saved | Control drift |
| --- | ---: | ---: | ---: | ---: |
| mixed | 1.903671 | 1.749372 | 8.105% | 0.519% |
| alternating | 1.903448 | 1.750035 | 8.060% | 0.132% |

These are complete head+selection+gather component times, not model TPS. The predeclared2% component gate and twice-control-drift rule passed for both inputs. ABBA, fresh launches, pipeline prime,500ms sustained warmup,7x100ms blocks.

Validation:16 packed-head cases/4,966,398 complete score values per check;30 adversarial selector cases including selected/cutoff ties, below-cutoff duplicates, signed zeros, negative/extreme values, NaN/Inf/subnormals, shape guards and fast/fallback/fast graph reuse. All ten IDs, gathered bits, CPU distribution/RNG and suppressed-winner receipts match the control. Original m5-copy head/consumer evidence also matches all16 cases. Controls remained unchanged.

All six accepted current-source launches have zero new swap; peak RSS 1.407GiB, minimum available RAM 35.789GiB. RSS does not include every Metal allocation; native bounded allocation evidence is separate.

Scope: explicit opt-in only, M5 Pro, contiguous single F32 row of248320 values, top10 sampling-node identity.32-lane SIMD is qualified only on this device. A normal-path marker proves eligible-variant entry, not that every invocation avoided fallback. Existing app launchers remain unchanged.

[Raw comparison](comparison.json), [preregistered component plan](plan.json), [original-engine parity](original-engine-component-parity.json), [excluded/development attempts](attempts.json), [model plan](model-plan.json).

Earlier ideal consumer-removal screen: approximately11% complete-operation saving with zero replacement cost, no selector and no model. Its numeric reference was recorded after timing began; it was descriptive, not preregistered. [Ceiling evidence](../20261009-winner-screen/comparison.json).

Two initial development errors were recorded: mutable count pointers during build, and a two-row fixture gather shape. The first full-model control cold load stopped after0.5MiB new swap before responses; no TPS result was accepted. A fresh warmed-cache retry retains the zero-new-swap guard.

Independent Astra reviewed the full-top10 design and found the raw-winner suppression blocker. Sol6.1 reviewed native scratch bounds, selection proof, barriers, fallback logic and host receipts; no remaining static blocker. This is a bounded qualification, not a general GPU-backend certification.


## Full-model result

Fresh original-engine ABBA completed: English code59.379496 ->60.027846TPS (+1.092%), prose39.937798 ->40.313896 (+0.942%). Whole replies4.574689 ->4.530796s (43.893ms/0.959% quicker) and6.675852 ->6.620488s (55.364ms/0.829%). Both gains exceed their bracket drift but neither workload reaches both1% thresholds; default adoption is false. Candidate512 synthetic generation+0.938%;2048+0.840%, but2K complete reply0.198% slower. First-token and prompt speed have no measured improvement in this bracket; cache gains are not qualified.

All104 answer/cache checks pass.96 fresh/cache/warmup output comparisons match original control, acceptance rates unchanged, four accepted full-model launches have zero new swap allocation. Existing system swap is separate. The first cold control load remains excluded (+0.5MiB new swap, no responses); the fresh warm retry used the unchanged guard. [Canonical model report](../20261009T205909Z-m5-parallel-top10/REPORT.md), [raw comparison](../20261009T205909Z-m5-parallel-top10/comparison.json), [final verification](model-final-verification.json).

The authoritative final report removes inherited encoder-specific claims and uses one strict verdict; the initial report/JSON are preserved alongside it. Supplementary dependency copies were captured during the first control and are labeled accordingly. No timing rerun was used for report adjudication.

Optional local launcher: `Start Strata - Fast Selection Trial.command`. It uses this bounded experimental engine, not the app's established default. Native changes are local and uncommitted; nothing was pushed or published.
