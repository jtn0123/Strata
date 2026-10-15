# Strata Mac experiment decision ledger

Updated October 9, 2026. Read this file **before proposing or rerunning an optimization**. It collects unsuccessful, inconclusive and limited-benefit experiments in one place; the linked immutable reports retain commands, prompts, raw responses, counters, source/build/model hashes, memory samples and native logs. [Machine-readable index](experiment-ledger.json).

Do not repeat an entry just because a new session starts. A retry must cite its ID, identify what materially changed, satisfy its revisit condition, and use a new result directory. Append the new decision and link the old one; preserve rejected attempts and original evidence. A new mechanism or workload can justify a new experiment, but it must explain why the earlier result does not answer the new question. Estimates in research notes are hypotheses, not gains.

## Measurement rules and current setup

- Hardware: M5 Pro, 48 GiB unified memory, 20 GPU cores. Recent native experiments use revision `d81235049384534c167caea52b85a694f6103d14` plus separately hashed patches. Each evidence bundle is authoritative for its own pins.
- Current practical benchmark control: `m5-copy` / `conv-direct`, Qwen3.8-Flash-Next GSQ-RCO Q2_0, packed shared Q3 MTP helper, mixed placement, eight helper CPU workers, depth three, confidence zero, Tensor API on, 4K context, F16 KV, batch/ubatch 512. Ordinary app launchers keep their established settings; the benchmark control is not a new default for every launcher.
- The latest model comparisons use 256 output tokens, temperature 0.6, an excluded warmup, three measured repeats per workload per launch and independent ABBA controls. Earlier suites often use 128 tokens, other engines or other depths. Do not pool them or add their percentage gains. Cached ledger answers are short structured responses, not general writing TPS.
- Current small-gain validation: no fixed minimum percentage. A metric must improve above twice its own control drift, with both candidate launch medians beating both controls, on both English code and prose. Qualified individual candidates get one fresh confirmation bracket before combination. TPS, first-token latency and whole reply remain separate; material regressions, output failures and new swap block qualification. The [preregistered plan](../config/m5_small_gains_plan.json) is authoritative. Earlier 1%/10% gates remain historical decisions; component microseconds cannot be converted into model TPS gains.
- A failed feature, below-gate result, noisy result, narrow opt-in and invalid run are different decisions. A correctness fix or capacity improvement can be useful without adding TPS. Older runs accepted under looser memory rules do not automatically satisfy today's zero-new-swap requirement.
- Research/profiling must first establish that the affected operation exists in the normal fused runtime. Profiling callbacks can interrupt fusion and distort apparent costs. RSS is not total unique Metal memory; uncontrolled file cache is not a guaranteed cold SSD measurement.

## October 9 small-gain validation — native passed, model timing held

User explicitly authorized tracking and validating modest additions after reviewing the previous gates. P11, P07 and W02 are reopened under a **new plan declared before new model timings**. Their previous decisions and raw results remain intact. P12 is excluded because its unchanged scheduling loses on the required cases. See the [candidate tracker](small-gain-candidates.json), [plan](../config/m5_small_gains_plan.json) and [evidence bundle](results/20261009-small-gains/).

- **P11:** Compact empty-job scheduling; test complete long English code/prose prompts for actual first-token/reply benefit.
- **P07:** Exact ten-expert reduction; test ordinary English code/prose TPS and reply time.
- **W02:** Exact helper top10; test ordinary English code/prose TPS and reply time.
- Isolated `m5-small-stack` retains independent feature switches. Each candidate runs alone against original `m5-copy`/`conv-direct`. Freeze only a confirmed subset before a fresh combined test; percentages are never added as a performance claim. No automatic app default change.
- Cached512/2048 remain separate diagnostics. Loss above max(5%, twice own drift) requires follow-up before default promotion. Native buffers, process RSS, available memory, exact outputs, source/build/model hashes and zero-new-swap receipts remain mandatory.
- **X23:** New native checker incorrectly expected stdout-only `guard-stride` in top10 JSONL. Original-control native execution passed with zero new swap; no candidate/model ran. Entire first source/runtime/raw bundle preserved. Mirror original JSONL inventory while still validating all 30 stdout fixtures; fresh complete native qualification required. [Diagnosis](results/20261009-small-gains/native-initial-excluded/exclusion.json).
- **Native qualification completed:** All 27 original/individual/combined flag checks pass, zero new swap; 156 offline checks pass and all 26 original engines remain unchanged. No model TPS inference follows from those correctness checks. [Current report](results/20261009-small-gains/REPORT.md).
- **X24:** First original-control cold model load grew system swap by 3.0625 MiB and stopped before readiness or any answer. No candidate or speed result. The resource-only retry's 90-second preflight remained around 31.8–32.0 GiB available, below the unchanged 34 GiB launch requirement; no retry model launched and the one retry allowance remains unused. All three candidates remain possible additions awaiting model validation. No unsafe cleanup or changed guard. [Diagnosis](results/20261009-small-gains/model-initial-excluded/exclusion.json), [held preflight](results/20261009-small-gains/resource-retry-held-plan.json).

## October 9 compact scheduling pass (historical)

P11/P12 are built and screened independently. Neither clears its fixed component gate, so no model trial or new model TPS gain. All 148 offline checks pass; 26 engine receipts verify and all 24 original engines are unchanged. Twelve accepted launches add zero swap. See the [report](results/20261009-compact-tiles/REPORT.md) and [independent reviews](results/20261009-compact-tiles/INDEPENDENT-REVIEWS.md). Earlier sections retain historical snapshots.

### P11 - Compact expert/token32 worklist

- **Status:** Correct component; modest measured gain below model-trial gate, parked.
- **Settings:** m5-compact / compact-tiles, isolated original-copy control; actual M5 Pro, Q2_0 gate/up/down, F32, T32..512. GPU worklist after unchanged map0, own amax, bounded 654/656 capacity, original matrix arithmetic; no P10 reuse.
- **Result:** T508 uniform: 13.010602 → 12.402137 ms (4.676686% shorter); T512: 13.028599 → 12.560125 ms (3.595735%). Drift 0.228479% / 0.110273%. Shared gains 9.925744% / 7.893319%; mixed 4.973479% / 4.166039%. T32 uniform loses 1.664%. Real component gain, below the preregistered >10% gate on both uniform cases; no model trial or TPS claim.
- **Validation:** 273 correctness records per engine (91 fixtures, A/B/A); 18 timing cases in fresh ABBA. Two complete dependent blocks, exact finite F32 output digests, all six MM activation/fallback counters pass, immutable inputs/weights, valid maximum-capacity/skew/permuted routes, zero new swap across six launches. Independent Astra raw audit. Corrupt-header/overlap edges are source-reviewed, not runtime-injected.
- **Revisit:** Materially different worklist/math/data reuse or independently justified new model-latency trial scope/gate declared before execution. Do not rerun unchanged V1 or lower its existing gate after seeing timings. P12 tested only grid order and did not qualify.
- **Evidence:** [Report](results/20261009-compact-tiles/REPORT.md), [raw](results/20261009-compact-tiles/component/comparison.json), [verification](results/20261009-compact-tiles/final-verification.json).

### P12 - Channel-first compact job order

- **Status:** Correct component; slower on required uniform cases, parked.
- **Settings:** m5-compact-cols / compact-cols, original-copy control, independent fresh ABBA. Only transpose compact grid axes, remap logical coordinates and match overflow indexing; otherwise identical V1 arithmetic, worklist, scratch and barriers.
- **Result:** T508 uniform: 13.000143 → 13.059383 ms (0.455684% longer); T512: 13.036513 → 13.326677 ms (2.225780% longer). Drift 0.204317% / 0.336039%. Shared gains 5.017433% / 2.816913%; mixed 2.213451% / 0.695061%. Smaller uniform/mixed cases generally slower. Fails >10% gate; no model trial, cache-occupancy attribution or TPS gain.
- **Validation:** 273 correctness records per engine (91 fixtures, A/B/A); 18 timing cases in fresh ABBA. Two complete dependent blocks, exact finite F32 output digests, all six MM activation/fallback counters pass, immutable inputs/weights, valid maximum-capacity/skew/permuted routes, zero new swap across six launches. Independent Astra raw audit. Corrupt-header/overlap edges are source-reviewed, not runtime-injected.
- **Revisit:** Different measured scheduling or data-reuse mechanism with exact original math, complete overhead and fresh preregistered controls. Physical Metal group order is not guaranteed; do not revisit unchanged axis transpose.
- **Evidence:** [Report](results/20261009-compact-tiles/REPORT.md), [raw](results/20261009-compact-tiles/columns/comparison.json), [verification](results/20261009-compact-tiles/final-verification.json).
- **Driver:** `scripts/benchmark_m5_compact.py --variant cols` (and `benchmark_m5_compact_models.py --variant cols`). The separate `benchmark_m5_compact_cols.py` that produced this result is [archived with it](results/20261009-compact-tiles/columns/source/scripts/benchmark_m5_compact_cols.py).

The [R05 checkpoint lifecycle card](research/20261009-astra-stateless-checkpoint-plan.md) holds a general cache_prompt=false omission until later cache-enabled slot reuse is safe. Skipping serialization can change prompt splits and restore behavior. Exact-format cooperative-input prompt compute remains independently unimplemented.

## October9 next speed pass

Current completed pass: three independently tested mechanisms, all below their acceptance gates.140 offline tests pass;24 engine receipts verify and all22 original engines are unchanged. Model jobs are stopped; app defaults remain unchanged. Earlier sections retain historical snapshots.

### S06 - UTF8-safe token-piece cache

- **Status:** Parked optional; no qualified service latency gain.
- **Settings:** Qwen3.5-4B Q4_K_M on unchanged m5-copy; real StrataService, native prompt cache off, token cache empty per request. Independent English code/prose ABBA,256 outputs, excluded warmup+three repeats. Optional stream_piece_cache defaultfalse; nominal1MiB/4096piece budget.
- **Result:** Code reply3.364070→3.365691s (-0.048%quicker), prose3.373194→3.367038s (+0.182%); below1%/twice-drift gate. Conversioncalls256→137/175, serializedIDs32896→137/175. No nativeTPS attribution or SSD read/write gain.
- **Validation:** 32 real responses exact; real UTF8prefix comparisons; loadfree invalid/splitUTF8, prefix/reset/eviction, thinking/EOS/cancel/reuse service traces. Zero new swap. Astra verified pinned HTTPendpoint uses raw piece concatenation/lstrip0, not llama_detokenize cleanup. Actual model4B confirmed by verified receipts.
- **Revisit:** A measured end-to-end bottleneck in text conversion, or changed native streaming interface. Require correct pinned/owned server lifetime and every-prefix/parser parity; do not repeat same model/task to chase tiny noise.
- **Evidence:** [Report](results/20261009-next-speed-pass/REPORT.md), [Raw small-model comparison](results/20261009-next-speed-pass/streaming/20261009T212918Z-small/comparison.json), [Timing sources](results/20261009-next-speed-pass/streaming/source/pins.json).

### Q02 - QSA all-pool ranking removal

- **Status:** Correct bounded trial; no qualified model gain, parked.
- **Settings:** Unlike Q01, preserve actual scores/cache/mask scatter/n_sel/attention; remove only full-pool top-k and paired gathers. Isolated M5Pro/F16/QSA top2048/ratio4 path, n_pool≤512 and exact floatdump bound; actual backendMTL guard. FullQwen3.8 Q2_0/sharedQ3/mixed/8workers/depth3/256output original-copy ABBA/warmup+3.
- **Result:** Component64pools/T1 -4.898%time,128/T1 -10.145%,512/T512 -22.958%. Modelcode59.387734→59.401608TPS(+0.023%),reply+0.028%; prose39.871876→39.758446(-0.284%),reply-0.379%. Neither passes1% TPS/reply above own drift; no qualified cache/TTFT gain.
- **Validation:** 102componentfixtures perengine: actualscoring, stockpermutation/pairing, sparsepadding, NaN/Inf/extremes, restrictedmask/groups,CPUscatterreference andcompleteMetalplacement.104modelanswer/cache checks and96fresh/cache/warmupoutputs exact; acceptedfourmodel/sixcomponent launches zero new swap. Marker proves inputpreparation only; no cache-state bit or shaderfrequency claim.22original engines unchanged.
- **Revisit:** A different costly attention mechanism with exact numeric/cache proof, or a measured workload with much greater exposure. Q01 broader score/mask bypass remains unimplemented; ranking-only result does not qualify it. Preserve excluded fixture/coldload/inactiveguard failures and new full bracket.
- **Evidence:** [Detailed report](results/20261009-next-speed-pass/REPORT.md), [Model raw](results/20261009T215006Z-m5-qsa-all-pools/comparison.json), [Component raw](results/20261009-next-speed-pass/qsa/comparison.json), [Manifest](../config/m5_qsa_experiment.json).

### P10 - Adjacent GPU expert route-map reuse

- **Status:** Exact component passes, below speed gate; no model trial, parked.
- **Settings:** Isolatedm5-route-map over originalcopy, sameactivation/IDs,Q2[2560,640,512],T32..512,nextSWIGLUconsumesadjacentpairwithinencoder. BorrowpreviousTPE/IDS only, retainownamax, allocationoverlapguard+postbarriertracking. Syntheticvalidtop10routes; normaloptimizer/allocator, two dependentblocks terminalonly, freshABBA/500mswarmup/7x100ms.
- **Result:** T508uniform two blocks12.978406→12.877820ms(+0.775%quicker),T51213.011294→12.904925(+0.818%); below3%/twice-drift gate. T127uniform1.164%slower. Componenttimes are not modelTPS or a promptTTFT claim.
- **Validation:** 66fixtures×3 A/B/A phases perengine=396records; exact completeprojection/activation/down/residual digests, strictfulleligibleencoding counts and zero fallbackcounts. T31/513,40/2048IDstrides, ID/input mutations,mixedprecision,terminalonlychecks; fullMetal/onesplit/input/weights preserved. Six accepted launches zero new swap; newbackend572+16mathcasespass. Forcedoverlap/partitionedge source-only guards explicitly not tested. Sol6.1/Astra reviewed.
- **Revisit:** A different routing/math scheduling mechanism; R03compactexpert/tileworklist is distinct and queued. Do not rebenchmark unchanged mapreuse for a sub1% result or inherit it into R03 baseline. Any futuremodeltest needs normal-path proof and matching prompt/TTFT/reply metrics.
- **Evidence:** [Report](results/20261009-next-speed-pass/REPORT.md), [Component raw](results/20261009-next-speed-pass/route-map/comparison.json), [Before-GPU plan](results/20261009-next-speed-pass/route-map/plan.json), [Manifest](../config/m5_route_map_experiment.json).

### Excluded attempts in this pass

- **X19:** Initial original-control injected QSA score fixture made masked future pools live; stopped before scatter, then absent RAII produced exit-time Metal cleanup assertion. Fixed fixture masking and cleanup, archived original source. No candidate/model/TPS acceptance. [Failure](results/20261009-next-speed-pass/qsa/20261009T213413402049Z-check-control/result.json), [diagnosis](results/20261009-next-speed-pass/qsa/20261009T213413402049Z-check-control/exclusion.json).
- **X20:** Cold original-model control allocated589824bytes new swap before responses. Excluded; fresh warmed-cache retry retained zero guard. [Load](results/20261009T214505Z-m5-qsa-all-pools-1-conv-direct/result.json), [diagnosis](results/20261009T214505Z-m5-qsa-all-pools-1-conv-direct/exclusion.json).
- **X21:** Candidate backend guard used Metal instead of actualMTL; no eligible input marker. Interrupted, excluded entire bracket, archived source/build, fixed only registry name and ran fresh fullABBA. [Rejected bracket](results/20261009T214536Z-m5-qsa-all-pools/comparison.json), [diagnosis](results/20261009T214536Z-m5-qsa-all-pools/exclusion.json).

Next queued is R03compactexpert/tokenworklist, independently over originalcopy/P10disabled. T512dispatch8192pairs/outputtile, syntheticuniformneeds512, anyvalidtop10route≤656(T508≤654). Launch counts do not establish runtime savings or real route distributions. Astra recommends >10% complete two-block saving above twice drift, including construction/barriers, before a model prompt/TTFT trial. See [next screen](results/20261009-next-speed-pass/REPORT.md#next-queued-compact-experttoken-tile-launches).

## October9 exact-selection pass

### W01 - Ideal helper consumer-removal ceiling

- **Status:** Descriptive component screen; not a deployable selector or model gain.
- **Settings:** Unchanged m5-copy/conv-direct packed Q5_K head, K2560/M248320; compare full head/top10/gather against head-only,16 correctness cases each and fresh ABBA sustained timing.
- **Result:** Mixed1.897290 ->1.690753ms (10.886% less time), alternating1.900853 ->1.689099ms (11.140%). Removes all selection/gather cost with zero replacement; not a model TPS upper bound. All six launches zero new swap.
- **Validation:** Complete head/input/weight digest parity. The numeric10% reference was recorded after timing began; preserved explicitly as descriptive, not preregistered.
- **Revisit:** Use actual replacement cost and exact downstream behavior. W02 is the implemented follow-up; do not rerun this ideal floor as a claimed speed feature.
- **Evidence:** [Report](results/20261009-winner-screen/REPORT.md), [raw](results/20261009-winner-screen/comparison.json), [gate provenance](results/20261009-winner-screen/screen-plan.json).

### W02 - Exact parallel helper top10

- **Status:** Small measured benefit, optional trial; below default-adoption gate.
- **Settings:** New isolated m5-top10 on practical m5-copy/conv-direct patch. Parallel local/global distinct maxima with multiplicities; full ten ordered IDs/logits preserved. Any selected tie, nonfinite or subnormal uses unchanged bitonic+merge. Explicit M5Pro/contiguous248320F32/row1/k10/node-name guard. Same full model/helper/sampler/depth3/8workers/F16/4K/batch512. Component gate predeclared before GPU launch; original-engine model ABBA256+warmup+three repeats, English only.
- **Result:** Actual complete head/selection/gather1.903671 ->1.749372ms mixed (-8.105%),1.903449 ->1.750035ms alternating (-8.060%). Model code59.379496 ->60.027846TPS (+1.092%, reply0.959% quicker), prose39.937798 ->40.313896 (+0.942%, reply0.829%). Replies save43.893ms/55.364ms. Above corresponding drift, but neither passes both1% thresholds.2K synthetic generation+0.840%, whole reply0.198% slower. Cache/TTFT/prompt improvement not established.
- **Validation:** 16 head cases/4,966,398 score values and30 adversarial selector cases per check; all ten IDs/gather bits, CPU distribution/RNG and suppression behavior exact, fast/fallback/fast graph reuse. Original m5-copy component parity exact. Model104 checks and96 fresh/cache/warmup output comparisons exact; acceptance rates unchanged. Four accepted model launches zero new swap.21 original engines unchanged. Astra/Sol6.1 reviews; marker proves eligible entry only, not fast-branch frequency.
- **Revisit:** A materially faster exact selection mechanism or a documented workload with larger exposure. Raw-winner shortcut cannot ignore suppression/probability consumers. Preserve ties/exceptions and source/model/normal-path provenance; unchanged rerun is not justified just to cross the1% gate.
- **Evidence:** [Detailed report](results/20261009-top10/REPORT.md), [model report](results/20261009T205909Z-m5-parallel-top10/REPORT.md), [model raw](results/20261009T205909Z-m5-parallel-top10/comparison.json), [component raw](results/20261009-top10/comparison.json), [plan](results/20261009-top10/plan.json), [final verification](results/20261009-top10/model-final-verification.json), [reviews](results/20261009-top10/INDEPENDENT-REVIEWS.md), [manifest](../config/m5_top10_experiment.json).

### Q01 - QSA all-visible shortcut source qualification

- **Status:** Original predicate unreachable; corrected geometric proof, numeric qualification pending. No shortcut implemented or performance measured.
- **Settings:** Read-only actual Qwen4exp/cache-order/M-RoPE text/graph-reuse audit. Pool budget<=512; unique contiguous single-sequence cells required.
- **Result:** Original by_order=false predicate cannot activate: target sets true; nearby false argument means gather=false. Actual by_order=true can satisfy pool/tail causal-prefix proof. Finite source inputs alone do not prevent F16 score overflow/NaN; a current-step bound or predicate with original fallback remains necessary.
- **Validation:** Source-level visibility proof and counterexamples for holes/duplicate positions/sharing. No GPU fixture or model gain. Ordinary expanded text can be `[p,p,p,0]`; rejecting every is_pos_2d batch is also too broad. Preserve all cache writes, n_sel, attention dispatch and eligibility-aware graph reuse.
- **Revisit:** Synthetic exact mask/cache/reuse fixture with exceptional scores and continuation across512->576 padded pools. Do not benchmark an inactive guard or enable an unproved numerical shortcut.
- **Evidence:** [Qualification and fixture specification](research/20261009-qsa-qualification.md).

## Latest draft-cap experiments

### D01 — MTP inner loop honors existing server output-budget caps

- **Status:** Bounded correctness passes; no qualified256-token speed gain, not adopted.
- **Settings:** Isolated `m5-draftcap` over `m5-copy` / conv-direct; existing per-cycle caps only, configured max3 allocation unchanged. Packed sharedQ3/mixed/eight workers, greedy helper, minimum0, confidence0, Tensor API on, F16/4K/batch512. IndependentABBA,256 outputs, temperature0.6, seed1234, warmup+three repeats; diagnostics off.
- **Result:** Code59.482→59.464TPS (-0.030%), prose39.931→40.007 (+0.191%); whole replies -0.027%/+0.157% quicker, below1% and control drift. Code4.568→4.569s, prose6.678→6.667s. Cached512 +0.978% below2.514% drift. Diagnostic successful helper steps720→702,18 discarded steps→0 over240 completed-request cycles; work savings are not a TPS percentage.
- **Validation:** 588 GPU math/residual cases;633 diagnostic tokens exact across22 requests, identical acceptance and actual target row sequences; real cache reuse, seeded repetition, EOS, output limits, cancellation/recovery.84 exact fresh/cache timed outputs and128 checks across four clean launches;19 identical native allocation records each. All zero new swap. Astra independently audited. No hidden-state bit identity, checkpoint restoration or near-context shifting proof.
- **Revisit:** A known short output-budget workload or materially different omitted-work mechanism has a repeatable complete-response benefit above drift. Do not rerun the same256-token baseline expecting a general speed gain; unpredictable EOS is not solved by this repair.
- **Evidence:** [Report](results/20261009-draftcap/REPORT.md), [full ABBA](results/20261009T193647Z-m5-draftcap-tail/comparison.json), [native-step parity](features/20261009T193412937896Z-m5-draftcap-qualification/tail-parity.json), [manifest](../config/m5_draftcap_experiment.json), [Astra review](results/20261009-draftcap/ASTRA-REVIEW.md).

### D02 — True per-cycle cap two with configured maximum-three allocation

- **Status:** Parked for repeatable extended-output divergence; speed bracket stopped, adaptive controller deferred.
- **Settings:** Same D01 engine/allocation and early-stop repair, only cap2 override versus ordinary effective3 (`draftcap-tail`). Same precision/weights/placement/sampling, max3, minimum0, greedy helper and confidence0. Short diagnostics preceded256-token ABBA attempt.
- **Result:** Initial22 requests/633 token IDs match; same-width truncation-only versus real cap2 helper steps792→524,268 discarded→0. Compared with ordinary3, cycles240→264, helper702→524, target verification rows942→788. Extended synthetic512 writing diverges in all three repetitions at zero-based index227, the228th emitted token,16545 versus25045. Incomplete English observations code58.944→51.226TPS, prose39.594→38.930; not a qualified comparison or gain.
- **Validation:** Prompt hash, seed1234, CPU sampling,256 output count, native/build/model/helper receipts and all non-axis settings match. Mismatch exists in saved running snapshot before owned-runnerSIGINT. Fourteen candidate cases completed; owned model exits cleanly, healthy monitor, no cleanup error and zero new swap. No completedABBA; do not call this a quality regression or assert its numerical root cause. Astra confirms parking; short parity does not cover longer output.
- **Revisit:** A materially changed implementation first reproduces and repairs the228th-token fixture under exact-output rules, then qualifies longer English prose/code, seeded continuation and changing caps before timing. No unchanged rerun, output-gate relaxation or controller implementation based on this failed policy.
- **Evidence:** [Report](results/20261009-draftcap/REPORT.md), [repeatable mismatch](results/20261009-draftcap/two-early-output-stop.json), [pre-interruption snapshot](results/20261009-draftcap/two-candidate-at-stop.json), [final stopped candidate](results/20261009T195332Z-m5-draftcap-two-2-draftcap2/result.json), [interrupted suite](results/20261009T195018Z-m5-draftcap-two/comparison.json), [initial cap2 parity](features/20261009T193516053626Z-m5-draftcap-qualification/batch.json).

## Previous backend sampling and embedding screen

### N01 — Target backend sampling with static speculative graph

- **Status:** Parked for a demonstrated min-p semantics difference; no model TPS trial.
- **Settings:** Direct actual Metal min-p stage linked to verified `m5-copy` / `conv-direct`; eight seven-logit cases, p=0.5 and production p=0.05, sorted-flag true/false, separated controls and logf(p)/neighboring boundary values. No model loaded. Upstream #30223 graph fix is merged but not backported because it does not alter sampler arithmetic.
- **Result:** Four separated controls match eligibility; all four boundary cases CPU retain IDs[0,1,2,3] and Metal retains[0,1,2]. CPU >=threshold versus Metal strict STEP. No full-chain, RNG/rollback, generated-token or model-quality result, and no TPS gain measured. Both sorted-flag fixtures use already ordered values.
- **Validation:** Surviving logits and input bytes unchanged, maximum retained, eight native cases complete, zero new swap, minimum available RAM33.16GiB. Astra audited actual raw/source hashes and endorsed bounded parking. Diagnostic `passed` means the screen completed, not that full backend sampling qualified.
- **Revisit:** An isolated implementation first matches min-p eligibility/ties and complete-chain selections plus RNG/rollback under exact-semantic rules, or explicit authorization of separate quality-changing work. Do not rerun the same graph fix expecting it to repair arithmetic; do not conflate this with P08 CPU retrieval.
- **Evidence:** [Report](results/20261009-sampling-embedding/REPORT.md), [native cases/hashes](features/20261009T183544060739Z-m5-backend-sampling-eligibility/checks.json), [frozen probe](features/20261009T183544060739Z-m5-backend-sampling-eligibility/m5_sampling_probe.cpp), [Astra review](results/20261009-sampling-embedding/ASTRA-REVIEW.md).

### N02 — Upstream common/Qwen4exp embedding gather ordering

- **Status:** Parked: no removed normal handoff; more planned inputs, no TPS trial.
- **Settings:** `m5-embedding` isolated #30160 common/Qwen4exp hunks over `m5-copy`, no Gemma/helper graph change; current conv-direct/depth3/sharedQ3/mixed/eight helper workers/4K/F16/batch512. Normal scheduler debug2/verbosity5 diagnostic only, no evaluation callback. Six32-token greedy requests per engine: code/prose/Chinese, synthetic512, cached-followup and identical fresh follow-up.
- **Result:** Every matched target plan remains CPU→Metal, active CPU GET_ROWS2; Metal planned input tensors27→30. Extra inputs belong to inactive mixed-input branch; helper remains CPU→Metal→CPU→Metal, input counts0/14/2/2. No actual transfer-byte or measured slowdown/TPS claim. Topology screen fails to qualify a speed trial.
- **Validation:** Candidate572 math+16 residual cases; paired192 token IDs/text and draft counts exact; two cached/fresh parity checks,508 reused tokens. Forty request/role/displayed-size comparisons,23 target/139 helper plan dumps per engine. Dumps are rebuild/reallocation plans, not execution counts; printed sizes/names truncated, byte-safe request ranges exclude startup reserves. Both accepted launches zero new swap, min RAM2.149GiB. Hidden-state/logit equality not measured. Astra independently audited raw plans.
- **Revisit:** A different mechanism removes the observed unnecessary input copies, or a different padding/LoRA/embedding/input-placement workload demonstrates redundant normal crossings. The same upstream merge and unchanged pure-token baseline are insufficient. Preserve inactive graph branches correctly.
- **Evidence:** [Report](results/20261009-sampling-embedding/REPORT.md), [topology and frozen analyzer](features/20261009T184602948859Z-m5-embedding-topology/topology.json), [parity](features/20261009T184602948859Z-m5-embedding-topology/parity.json), [manifest](../config/m5_embedding_experiment.json), [Astra review](results/20261009-sampling-embedding/ASTRA-REVIEW.md).

## Previous sequential pass

### S01 — Parallel gate/up activation, four outputs per SIMD group

- **Status:** Parked below gate; component test only.
- **Settings:** `m5-gate-lanes`, `gate-up4`; preserve original Q2 dot products and uniform reductions, distribute the unchanged SwiGLU epilogue across lanes. A/B/C/C/B/A compares practical unfused control, new parallel version and old serial four-output ablation. Full real R4/R5 and distinct-expert blocks, normal fusion, no timing callbacks.
- **Result:** Real R4 297.497 → 296.937 us, 0.188% less time versus 0.226% control drift; conservative bracket reduction 0.016%. Real R5 -0.019% time reduction; distinct routes 0.93–1.13% slower. Failed the predeclared >=3% R4 reduction, >2x drift and bracket-separation screen. No model trial or TPS gain.
- **Validation:** 58 cases, 11,162,880 F32 values bit-identical; six accepted native runs, zero new swap.
- **Revisit:** A materially different epilogue/dispatch mechanism with a normal-path cost argument and repeatable complete-block improvement. The new parallel **eight-output** mode was not benchmarked; this result must not be described as testing it. Old serial eight-output failure is P01.
- **Evidence:** [Combined report](results/20261009-sequential-pass/REPORT.md), [raw gate evidence](results/20261009-sequential-pass/gate-lanes.json), [pinned manifest](../config/m5_gate_lanes_experiment.json), [predeclared screen](../config/m5_sequential_plan.json).
- **Driver:** `scripts/benchmark_m5_gate.py --engine m5-gate-lanes`. The separate `benchmark_m5_gate_lanes.py` that produced this result is [archived](results/20261009-next-speed-pass/before/scripts/benchmark_m5_gate_lanes.py).

### S02 — Zero extra Metal encoding workers

- **Status:** Rejected measured regression; full model.
- **Settings:** `m5-encoders` / `GGML_M5_LAB_N_CB=0` versus 1, otherwise current control settings; separate 1/0/0/1 bracket. These are command-encoding workers, not helper CPU workers.
- **Result:** Code 59.442 → 56.135 TPS (-5.563%); prose 39.943 → 37.750 (-5.489%); Chinese 40.669 → 38.390 (-5.605%). Complete replies took about 5.62–5.75% longer. Synthetic 512/2048 TPS fell 5.516%/5.102%. Retain one extra worker.
- **Validation:** Both encoder suites together: 234 prerequisite dependent/state graphs, 168 exact fresh/cached output records and 256 answer/cache checks; eight accepted model launches, zero new swap. Both constructors, effective startup counts, malformed override fallback and stats override covered.
- **Revisit:** Different backend scheduling implementation, CPU/GPU balance, hardware, or demonstrated encoding contention on a different workload. Repeating this exact count sweep on the same pinned model is low value.
- **Evidence:** [Model report](results/20261009T171405Z-m5-encoders0/REPORT.md), [raw comparison](results/20261009T171405Z-m5-encoders0/comparison.json), [prerequisites and log checks](results/20261009-sequential-pass/encoders0.json), [manifest](../config/m5_encoders_experiment.json).

### S03 — Two extra Metal encoding workers

- **Status:** Parked, no useful model gain; bounded compatibility limitation.
- **Settings:** `GGML_M5_LAB_N_CB=2` versus 1, independent 1/2/2/1 bracket. Helper CPU workers remain eight. Fusion matcher remains partition-local; changing command partitions can change fusion opportunities.
- **Result:** Code 59.467 → 59.325 TPS (-0.239%); prose 39.949 → 39.882 (-0.167%); Chinese 40.607 → 40.583 (-0.061%). Whole-reply changes -0.215%, -0.121%, -0.058%. Synthetic 2048 +0.085% TPS but whole reply -0.324%; no adoption gate met.
- **Validation:** Same combined coverage as S02. Count two is restricted to the pinned **callback-free** server path. Existing commit logic can leave the main buffer uncommitted with a non-null abort callback. No general callback fix was made. Pinned calloc initializes null; every later assignment is instrumented, and any non-null setter event invalidates a run. Accepted target/helper logs confirm count two and stats disabled.
- **Revisit:** First fix and validate the non-null callback commit path if general compatibility is required. Performance retry also needs a changed scheduling mechanism or evidence of an encoding bottleneck; callback repair alone is not a promised speed gain.
- **Evidence:** [Model report](results/20261009T172814Z-m5-encoders2/REPORT.md), [raw comparison](results/20261009T172814Z-m5-encoders2/comparison.json), [startup/callback evidence](results/20261009-sequential-pass/encoders2.json), [manifest](../config/m5_encoders_experiment.json).

### S04 — Q5_K single-token vocabulary head, two output rows

- **Status:** Rejected component regression; no model trial.
- **Settings:** `m5-head` / `head2`; exact Q5_K K=2560, M=248320, canonical strides, F32 single-token input/output, nsg=2; original unpacking/arithmetic/reduction. Eligible target and helper heads, full vocabulary; no expanded cache or reduced precision. Dependent head → top10 → gather graph, terminal sync, untimed pipeline prime, >=500ms warmup, seven >=100ms blocks per input pattern, ABBA.
- **Result:** Mixed input 1.904677 → 1.957748 ms (+2.786% time); alternating 1.908241 → 1.945478 ms (+1.951%). Control drift 0.10–0.26% across the head suites. Failed >=10% complete-operation speedup screen.
- **Validation:** Each head mode passes 16 cases / 4,966,398 output scores bit-identical to control, all-score CPU references, cancellation/one-hot/zero/scaled/tie cases and exact unsupported-path fallbacks. Both modes together compare 9,932,796 values. Probe RSS <3 GiB; all 11 accepted head launches zero new swap.
- **Revisit:** Different kernel geometry/data reuse or a changed head workload that explains this regression. Before a model trial, prove actual T1 strides and dispatch in a normal model capture; that capture was not warranted by the failed component screen and remains untested.
- **Evidence:** [Head report](results/20261009-sequential-pass/REPORT.md), [raw correctness/timing](results/20261009-sequential-pass/head.json), [manifest](../config/m5_head_experiment.json), [screen](../config/m5_sequential_plan.json).

### S05 — Q5_K single-token vocabulary head, four output rows

- **Status:** Rejected component regression; no model trial.
- **Settings:** Same exact guards and protocol as S04, `head4`, separate ABBA controls; global nr1/nsg2 defaults and all unsupported paths preserved.
- **Result:** Mixed 1.910208 → 1.931174 ms (+1.098% time); alternating 1.910681 → 1.934325 ms (+1.237%). Failed >=10% complete-operation improvement screen.
- **Validation:** Same complete correctness/fallback coverage and zero-swap requirement as S04. This is a full-head-plus-consumer measurement, not isolated kernel TPS.
- **Revisit:** A new mechanism and normal model dispatch proof as S04; a repeat of nr4 alone is not justified.
- **Evidence:** [Raw head bracket](results/20261009-sequential-pass/head.json), [report](results/20261009-sequential-pass/REPORT.md), [manifest](../config/m5_head_experiment.json).

## Earlier October 9 native experiments

### P01 — Serial fused gate/up, eight outputs

- **Status:** Rejected component regression.
- **Settings:** `m5-gate` / `gate-up8`; real captured R4/R5 routes, complete sequential expert block, stock fused-runtime control. Original serial activation epilogue.
- **Result:** R4 0.2954 → 0.3484 ms (+17.95% time); R5 0.3572 → 0.4138 (+15.84%). Distinct +18.60%/+17.94%; shared +8.50%/+9.45%. Control drift 0.41%/0.71% for real routes. Failed >=10% operator improvement; no TPS trial.
- **Validation:** 58 cases / 11,162,880 exact F32 values. Accepted final suite zero new swap; early fixture/storage failure excluded below.
- **Revisit:** Change the serial epilogue or underlying work distribution, not the same tile count. S01 is the recorded parallel-epilogue follow-up; its four-output mode also failed to qualify.
- **Evidence:** [Report](results/20261009-next-few/REPORT.md), [raw suite](results/20261009-next-few/REPORT.json), [frozen source hashes](results/20261009-next-few/source/SHA256.json), [manifest](../config/m5_gate_experiment.json).

### P02 — Serial fused gate/up, four outputs

- **Status:** Parked below gate; component only.
- **Settings:** Same suite as P01, `gate-up4`.
- **Result:** R4 0.2949 → 0.2962 ms (+0.42% time, 0.76% drift); R5 0.3575 → 0.3578 (+0.07%, 0.05% drift). Distinct +1.42%/+1.37%; shared 0.99%/0.82% less time. No >=10% real-route win or TPS trial.
- **Validation:** Same exact 58-case coverage as P01; accepted runs zero new swap.
- **Revisit:** New mechanism with full real-route evidence. S01 already tests parallel activation at this tile count; do not propose it as an untested idea.
- **Evidence:** [Report and raw links](results/20261009-next-few/REPORT.md), [raw suite](results/20261009-next-few/REPORT.json), [manifest](../config/m5_gate_experiment.json).

### P03 — Repeated-expert pair grouping, exact V4

- **Status:** Rejected component regression.
- **Settings:** `m5-group` / `expert-group`; eight sequential gate/up/SwiGLU/down/reduction/residual blocks, two full 512-expert weight sets, eight captured routes stratified by reuse, real R4/R5 and distinct/shared controls. Sixty measured graphs, four warmups, no callback tracing during performance.
- **Result:** Real R4 301.839 → 384.266 us (+27.31% time, 0.71% drift); R5 362.391 → 449.932 (+24.16%, -0.08% drift); distinct +8.65–8.78%, shared +22.98–26.25%. Failed >=10% real R4 improvement and regression limits. No model TPS run.
- **Validation:** 42 cases, 336 CPU projection references, 9,446,400 exact output values; 750 dispatch markers, unchanged data/padding. Six accepted runs zero new swap; peak RSS 4.48 GiB, minimum RAM 32.03 GiB. Register pressure is a hypothesis, not a measured cause.
- **Revisit:** A substantially different grouping kernel or measured register/occupancy explanation, with exact arithmetic and dependent sequential graphs. Repeated selections alone do not prove a profitable optimization.
- **Evidence:** [Final report](results/20261009T153117Z-m5-expert-pair-group/REPORT.md), [raw comparison](results/20261009T153117Z-m5-expert-pair-group/comparison.json), [plan](../config/m5_group_plan.json), [manifest](../config/m5_group_experiment.json).

### P04 — Grouping V2/V3 streamed kernels

- **Status:** Rejected correctness; performance ineligible.
- **Settings:** Development variants of P03 with streamed grouped computation.
- **Result:** Passed CPU tolerance but failed exact stock-bit comparison. Their timings cannot justify adoption. V4 restored known exact assignment ordering and passed correctness, then regressed (P03).
- **Validation:** V1 was accurate but used independent graphs permitting cross-block concurrency; its throughput timings were excluded from sequential latency claims. V2/V3 are preserved in the final report's development history.
- **Revisit:** Restore exact accumulation/output behavior before performance testing, or explicitly authorize and evaluate a separate quality-changing experiment. Do not relax the existing speed-only accuracy gate silently.
- **Evidence:** [Development history and evidence](results/20261009T153117Z-m5-expert-pair-group/REPORT.md), [raw comparison](results/20261009T153117Z-m5-expert-pair-group/comparison.json).

### P05 — GDN recurrent-state row groups one/two versus four

- **Status:** Inconclusive / no qualified component gain, parked.
- **Settings:** `m5-gdn`, `gdn-row1` / `gdn-row2` versus row4; native fused K4 path, actual target T1–4 capture, 786432-float slot stride. Final timing uses >=500ms sustained warmup, 512 synchronized samples, four states and unchanged-row4 negative controls. Includes fixture SUM/attention/copy/sync cost, not an isolated kernel.
- **Result:** Fused T4 controls 0.3989–0.4161 ms; row1 0.4052–0.4081, row2 0.4024–0.4039. T5 controls 0.4020–0.4132; row1 0.4049–0.4051, row2 0.4054–0.4212. No gain above final 4.33% control spread. Initial short bracket had 11.43% drift and was excluded as conclusive evidence. No TPS gain established.
- **Validation:** 32 cases per setting, 960 full output/cache/padding digests and 1,504,438,002 F32 values per setting exact. Retained-prefix rollback and continuation tested; T5/K4 prefix1 explicitly unavailable, not claimed. Accepted final suite zero new swap.
- **Revisit:** First demonstrate reproducible lower-noise timing or a different fused implementation with a substantial effect. Do not relabel noise as a win or claim all GDN optimization has been disproven.
- **Evidence:** [Detailed report](results/20261009-next-few/REPORT.md), [raw suite](results/20261009-next-few/REPORT.json), [frozen hashes](results/20261009-next-few/source/SHA256.json), [manifest](../config/m5_gdn_experiment.json).

### P06 — SSD lookup prefetch for warm short text

- **Status:** Screened low expected benefit; prefetch not implemented.
- **Settings:** `m5-lookup` native lookup tracing, 162 attributed operations on the 28.8 GB shard, 90-byte rows / 16 KiB pages; four normal requests, trace/control outputs matched for 392 tokens. Warm short code/prose/Chinese tasks.
- **Result:** Lookup CPU gather/dequant/scheduling envelope: prose 2.508 ms / 3.3295 s (0.0753%); code 1.885 ms / 2.4972 s (0.0755%); Chinese 2.433 ms / 3.3073 s (0.0736%); warmup 0.2677%. This is an upper-bound envelope, **not measured SSD wait**; overlap may overcount and OS cache is uncontrolled.
- **Validation:** Paired text/token equality; accepted suite zero new swap. Separate bounded pread probe had first-pass median 123.729 us and repeats 1.708–1.833 us, but does not establish native mmap waits, SSD sequential bandwidth or TPS potential.
- **Revisit:** Cold-cache, sustained long-context or memory-pressure workload with actual normal-path attributed lookup wait >=2% of reply time, before implementing a bounded prefetcher. Fast sequential SSD bandwidth alone does not satisfy this condition. Larger-model paging remains separately untested.
- **Evidence:** [Native lookup screen](results/20261009-next-few/REPORT.md), [raw attribution](results/20261009-next-few/REPORT.json), [bounded read context](results/20261009T085842Z-m5-next-batch/REPORT.md), [manifest](../config/m5_lookup_experiment.json).

### P07 — Ten-expert weighted reduction

- **Status:** Small measured benefit, opt-in; below default-adoption gate.
- **Settings:** `m5-reduce` / `reduce10`, exact ten-expert reduction beyond conv-direct; separate full-model ABBA, 256 output tokens, three measured repeats, depth3 current helper. Not stacked with other experimental paths.
- **Result:** Code 59.415 → 59.948 TPS (+0.90%, reply +0.94% quicker); prose 39.845 → 40.262 (+1.05%, +1.02%); Chinese 40.636 → 41.007 (+0.91%, +0.89%). Synthetic +0.86–0.87%. Only one real workload reaches both 1% thresholds; keep opt-in, not a default upgrade.
- **Validation:** Non-NaN operator bits and tested model outputs exact. Together with P08: 256 answer/cache checks, 168 output comparisons, eight accepted full-model launches zero new swap; minimum RAM 2.452 GiB, peak RSS 38.280 GiB.
- **Revisit:** A materially faster reduction implementation or a different documented workload. Existing benefit is real but small; do not call it a complete failure, a new untested idea or add it arithmetically to other suites.
- **Evidence:** [Model comparison](results/20261009T130146Z-m5-ten-expert-reduction/REPORT.md), [raw](results/20261009T130146Z-m5-ten-expert-reduction/comparison.json), [combined decision](results/20261009-next-three/REPORT.md), [manifest](../config/m5_reduce_experiment.json).

### P08 — Sampling-output view / CPU retrieval consolidation

- **Status:** Parked, no sustained model gain.
- **Settings:** `m5-sampling` / `sampling-view`; consolidate already-ready output retrieval, retaining CPU/common sampling semantics, full-model ABBA beyond conv-direct.
- **Result:** Ready retrieval 0.097706 → 0.030565 us per row, saving only 0.067141 us. Code 59.523 → 59.481 TPS (-0.07%), prose 39.983 → 39.977 (-0.01%), Chinese -0.09%, all within bracket drift; synthetic -0.05–0.17%. No useful whole-reply gain.
- **Validation:** Five small-model backend/CPU modes, multiple rows/negative indexing; actual greedy/stochastic and both grammar paths produce identical 18 selections. Full model exact outputs and zero new swap as P07. Initial 0.5 MiB new-swap control excluded completely.
- **Revisit:** Demonstrate a larger actual retrieval/synchronization bottleneck or new GPU-side sampling mechanism. Future **target backend sampling plus static speculative graph** is distinct and remains untested; do not confuse it with this CPU retrieval change.
- **Evidence:** [Model report](results/20261009T132908Z-m5-sampling-view-clean-retry/REPORT.md), [raw](results/20261009T132908Z-m5-sampling-view-clean-retry/comparison.json), [read-cost checks](features/20261009T132329116485Z-m5-sampling-read_cost-conv-direct/comparison.json), [manifest](../config/m5_sampling_experiment.json).

### P09 — Few-row BF16 TensorOps projections / split-K / specialization

- **Status:** Parked; no qualified component win. Relaxed precision rejected separately.
- **Settings:** `m5-hc`; exact stored BF16 weights, F32 activations/output, R4/R5, K/M=10240/320 and 320/10240, preserve residual fusion; five long-K splits, short-K direction and exact-K MMA specialization. Twenty distinct projection copies, 125 MiB working set, normal fusion, no profiling callbacks; scratch <=15 KiB, no weight cache, relaxed_precision=false.
- **Result:** Specialization down R4 35.580 → 35.417 us (0.46% less time versus 3.21% drift), R5 0.90% slower; up R4 36.174 → 35.613 (1.55% less time versus 2.36% drift), R5 0.78% slower. Long-K split8 down 36.001 → 40.075 us (11.32% more time), R5 14.90% more. Short-K up about 9% more time but 7–8% control drift makes exact slowdown uncertain. No >=10% operator win, so no model TPS trial.
- **Validation:** 864 CPU-reference shape/layout cases across 12 processes, unaffected fallback bits exact; eight broader GPU math/residual configurations. Relaxed precision API probe increased rounding error and was rejected before accepted performance tests.
- **Revisit:** Different data/compute reuse or demonstrated dispatch/occupancy explanation. Quantized **prompt** cooperative-input kernels are a different format and regime; BF16 few-row failure does not rule them out, but they require their own format/precision proof.
- **Evidence:** [Detailed report](results/20261009-next-three/REPORT.md), [confirmation brackets](results/20261009T135603Z-m5-hc-operator-confirmation/comparison.json), [complete experiment receipts](results/20261009-next-three/results.json), [manifest](../config/m5_hc_experiment.json).

### C01 — Scalar row-copy replacement

- **Status:** Parked, no useful fresh-model gain.
- **Settings:** `m5-copy` / `copy-scalar` versus stock; 128 fresh tokens, depth3, Tensor API on, eight helper workers, independent bracket within stock/scalar/vector4/direct/direct/vector4/scalar/stock.
- **Result:** Code 56.501 → 56.496 TPS (-0.01%); prose 42.877 → 42.861 (-0.04%); Chinese +0.17%; synthetic -0.24%/+0.08%. First-token delay generally worsened; no consistent fresh reply benefit.
- **Validation:** Eight copy model launches, 256 checks, exact fresh/cached tokens, zero new swap, minimum RAM 2.14 GiB; supplementary copy probe 224 bit-exact cases including tails/padding/fallbacks. Archive distinguishes the 47-case probe used at timing from newer 56-case checks.
- **Revisit:** Show the normal runtime actually executes enough eligible copies or change the copy mechanism materially. Isolated state-copy throughput is insufficient because normal GDN fusion removes the apparent large CPY (C03).
- **Evidence:** [Copy report](results/20261009T112641Z-m5-copy-resume/REPORT.md), [raw comparison](results/20261009T112641Z-m5-copy-resume/comparison.json), [manifest](../config/m5_copy_experiment.json).

### C02 — Four-wide vector row-copy replacement

- **Status:** No fresh-writing gain; narrow cached signal needs broader proof.
- **Settings:** Same suite as C01, `copy-v4`.
- **Result:** Code/prose both -0.24% TPS, Chinese +0.07%; synthetic -0.42%/-0.11%. Cached2048 +2.53% TPS, but only +0.56% whole-reply benefit on a short ledger fixture; cached512 -0.25%. Keep off as general speed feature.
- **Validation:** Same exact output and zero-swap proof as C01. Cached512 control drift 2.98%; small cached changes there are inconclusive. Copy-only scalar/vector1/4/8 screening does not establish full-model gains; the matched model table tests scalar and vector4.
- **Revisit:** Multiple realistic cached workloads with repeatable whole-reply benefit, normal dispatch proof and current adoption gate. Do not market this one short fixture as general chat acceleration.
- **Evidence:** [Copy report](results/20261009T112641Z-m5-copy-resume/REPORT.md), [raw](results/20261009T112641Z-m5-copy-resume/comparison.json).

### C03 — Large GDN state CPY inferred from split tracing

- **Status:** Invalid normal-path bottleneck attribution; optimization target parked.
- **Settings:** Per-operation split callbacks versus lighter ordinary-dispatch inventory.
- **Result:** Detailed split tracing interrupted cache fusion and exposed a costly-looking CPY. Lighter normal dispatch captured 123 shapes and no public large unfused GDN state CPY; native fusion already removes it. No valid model gain can be projected from that copy-only cost.
- **Validation:** Split traces still serve bounded diagnostic purposes, but their operation percentages are not ordinary inference shares. Direct convolution-state CONT removal is a distinct positive result K01.
- **Revisit:** A normal, uninstrumented or non-disruptively instrumented workload exhibiting the actual copy. Do not optimize this profiler artifact again without that proof.
- **Evidence:** [Correction and scope](results/20261009T112641Z-m5-copy-resume/REPORT.md), [normal inventory](results/20261009T112641Z-m5-copy-resume/shape-inventory/inventory.json), [earlier split context](results/20261009T085842Z-m5-next-batch/REPORT.md).

## Earlier settings sweeps

### T01 — Blindly raise draft depth to five

- **Status:** Rejected across measured fresh-writing and cached-follow-up tasks.
- **Settings:** `mtp-mma`; depth3 writing versus5, depth4 follow-ups versus5, temperature0.6, 128 fresh tokens, confidence0, ABCCBA-style bounded sweeps with fresh controls.
- **Result:** Writing code 56.43 → 53.54 TPS (-5.12%), prose -14.34%, Chinese -17.19%, synthetic -8.90–15.87%. Cached512 68.98 → 67.03 (-2.82%), complete reply 1.36% slower; cached2048 69.40 → 62.16 (-10.43%), reply 6.87% slower.
- **Validation:** Tensor/depth batch: 20 passes, 600 checks and 4004 prerequisite checks, zero new swap; fresh depth control drift <=0.163%, cached <=0.515%. Shape/acceptance changes can change token paths; no general exact-output claim.
- **Revisit:** Changed helper/model acceptance or cost-aware adaptation with evidence. Future adaptation stays within maximum3 and is **not** another blind depth5 sweep.
- **Evidence:** [Tables and methodology](M5-RESULTS.md), [writing raw](results/20261007T005423Z-m5-depth-writing/comparison.json), [follow-up raw](results/20261007T010359Z-m5-depth-followup/comparison.json).

### T02 — Raise draft depth to six for fresh writing

- **Status:** Rejected fresh-writing regression.
- **Settings:** Same writing suite as T01, depth6 versus3.
- **Result:** Code 56.43 → 50.38 TPS (-10.72%); prose 42.84 → 34.47 (-19.53%); Chinese 40.16 → 29.91 (-25.52%); synthetic512 -23.88%, synthetic2048 -13.25%. Higher depth adds work and lowers acceptance fraction.
- **Validation:** Same clean depth-suite evidence as T01. These end-to-end slowdowns do not isolate GPU, CPU or rollback-copy contributions.
- **Revisit:** New helper with substantially improved accepted-prefix/cycle cost. Existing short cached benefit T03 does not justify using six for general writing.
- **Evidence:** [Report](M5-RESULTS.md), [raw writing sweep](results/20261007T005423Z-m5-depth-writing/comparison.json).

### T03 — Depth six for short structured cached replies

- **Status:** Kept as narrow optional trial; long replies do not qualify.
- **Settings:** Depth6 versus4, cached ledger naturally stops after 25/24 tokens at history512/2048; separate short-structured launcher.
- **Result:** Cached512 68.98 → 75.50 TPS (+9.44%); complete reply 0.6252 → 0.5947 s (4.88% quicker, about30ms). Cached2048 69.40 → 69.73 (+0.48%); whole reply +0.04%, effectively tied. Fresh writing regresses (T02).
- **Validation:** Matched cached generation drift <0.17%; nine real API groups pass; zero new swap in speed suite. Structured short-answer rate is not general chat TPS.
- **Revisit:** A different realistic short-answer task if it can justify a specialized profile. Do not repeat this ledger fixture or advertise75.5 as ordinary writing speed.
- **Evidence:** [Scope and app proof](M5-RESULTS.md), [cached raw](results/20261007T010359Z-m5-depth-followup/comparison.json).

### T04 — Confidence threshold 0.2

- **Status:** No broad meaningful gain; retained confidence0.
- **Settings:** `mtp-mma`, separate depth3 writing and depth4 follow-up sweeps, threshold0.2 versus0, temperature0.6, 128 fresh tokens.
- **Result:** Writing code 56.36 → 56.34 TPS (-0.03%), prose +0.83%, Chinese +0.48%, synthetic -0.16%/-0.05%; follow-up cached essentially flat. No clear general upgrade.
- **Validation:** Follow-up0.2 reproduces all10 paired fresh outputs. Clean helper/confidence batch: 18 full passes, 540 checks, zero new swap; cached-control variation can exceed small gains. Initial Java-contention/swap attempt excluded below.
- **Revisit:** New model/helper acceptance distribution or adaptive policy with measured cycle cost, rather than the same fixed threshold sweep.
- **Evidence:** [Full helper/confidence report](M5-HELPER-RESULTS.md), [writing raw](results/20261007T034515Z-m5-confidence-writing/comparison.json), [follow-up raw](results/20261007T035416Z-m5-confidence-followup/comparison.json).

### T05 — Confidence threshold 0.4

- **Status:** Narrow prose opt-in; rejected as general upgrade.
- **Settings:** Separate writing depth3/follow-up depth4, threshold0.4 versus0; ordinary launchers unchanged.
- **Result:** Writing prose 42.83 → 43.61 TPS (+1.83%), reply1.58% quicker; code -0.57%, Chinese -1.33%, synthetic51249.02 →45.84 (-6.50%), synthetic2048 -3.72%. Follow-up Chinese +4.22% but code -2.8%, synthetic -4.03%/-6.76%; cached2048 69.42 →63.55 (-8.46%), reply5.46% slower. Apparent small cached writing gains are below4.37–5.73% control drift.
- **Validation:** Focused answers pass, but two of10 writing and three of10 follow-up paired fresh outputs change. Higher acceptance percentage mainly reflects fewer proposed tokens, not more accepted work. Clean batch zero new swap; separate prose trial passes nine API groups.
- **Revisit:** A measured workload-specific selector or materially changed helper. Do not silently combine this quality/path-changing setting with exact-output speed trials or existing opt-ins.
- **Evidence:** [Report and limitations](M5-HELPER-RESULTS.md), [writing raw](results/20261007T034515Z-m5-confidence-writing/comparison.json), [follow-up raw](results/20261007T035416Z-m5-confidence-followup/comparison.json).

### T06 — Six helper CPU workers instead of eight

- **Status:** Mixed tradeoff, not a balanced default improvement.
- **Settings:** Helper generation/prompt workers only, target workers8, depth3, `mtp-mma`; do not confuse with encoder-worker S02/S03.
- **Result:** Generation code +0.77%, prose +1.16%, Chinese +1.09%, synthetic2048 +1.05%; long prompt input 539.26 →521.92 tok/s (-3.21%), TTFT3.7986 →3.9247s, whole long reply1.56% slower.
- **Validation:** All10 paired fresh outputs exact, answer checks and zero new swap in clean helper suite. Earlier mtp-shared/depth2 sweep L07 also finds sub1% generation changes.
- **Revisit:** Different host CPU contention or helper placement, with input/TTFT/whole reply included. Decode TPS alone is insufficient.
- **Evidence:** [Report](M5-HELPER-RESULTS.md), [raw worker sweep](results/20261007T040326Z-m5-helper-workers/comparison.json).

### T07 — Twelve helper CPU workers instead of eight

- **Status:** Small balanced optional benefit, not a large default upgrade.
- **Settings:** Same isolated worker suite as T06, helper12 versus8, no combination with other trial launchers.
- **Result:** Code56.33 →56.85 TPS (+0.94%); prose +0.76%, Chinese +0.56%, synthetic2048 +0.82%. Long prompt +3.24%, TTFT3.14% quicker; full reply6.3427 →6.2025s (2.21% quicker). Separate trial exists; balanced control stays8.
- **Validation:** All10 paired fresh outputs reproduced; clean suite zero new swap; separate twelve-worker trial passes nine API groups.
- **Revisit:** New placement/model or contention pattern. Already measured small gain, not an untested route to a major TPS jump; combination needs its own fresh comparison.
- **Evidence:** [Report](M5-HELPER-RESULTS.md), [worker raw](results/20261007T040326Z-m5-helper-workers/comparison.json).

### T08 — BF16/Q2 few-row Tensor API dispatch thresholds

- **Status:** Parked, no meaningful gain.
- **Settings:** Isolated `m5-lab`, stock BF16 threshold4 versus3; Q2 threshold3 versus2, depth3; separate ABBA suites. Dense MMA knobs do not control separate routed `MUL_MAT_ID` experts.
- **Result:** BF16 code56.37 →56.40 TPS (+0.05%), synthetic +0.20–0.24%, fresh drift up to0.145%; Q2 code56.41 →56.31 (-0.16%), synthetic -0.15–0.17%, drift up to0.258%. Neither useful.
- **Validation:** Matrix batch:24 passes,720 checks,6864 CPU-reference prerequisite checks, zero new swap, minimumRAM3.083GiB. Dense Q2 storage is only73,175,040 bytes outside experts; storage share does not prove runtime cost share.
- **Revisit:** New dense kernel implementation or actual dispatch/cost evidence on changed shapes. Do not claim these already-tested thresholds optimize routed expert kernels.
- **Evidence:** [Matrix report](M5-GPU-TUNING.md), [BF16 raw](results/20261007T014132Z-m5-bf16-threshold/comparison.json), [Q2 raw](results/20261007T014739Z-m5-q2-threshold/comparison.json).

### T09 — Dense matrix tile limit one

- **Status:** Rejected small regression.
- **Settings:** `m5-lab`, tile limit1 versus stock limit4, depth3, separate bracketed matrix-width sweep.
- **Result:** Code56.46 →55.84 TPS (-1.09%); synthetic512 -0.93%,2048 -0.88%. No useful improvement.
- **Validation:** Same clean matrix batch as T08; candidates measured inside isolated engine after build-parity check, not against unrelated old launcher figures.
- **Revisit:** Different kernel/shapes or hardware with a reason one tile should win. Existing limit2 benefit is T10.
- **Evidence:** [Matrix report](M5-GPU-TUNING.md), [width raw](results/20261007T015346Z-m5-matrix-width/comparison.json).

### T10 — Dense matrix tile limit two

- **Status:** Marginal optional benefit; below broad adoption gate.
- **Settings:** Same suite as T09, limit2 versus4; separate two-tile trial launcher.
- **Result:** Code56.46 →56.68 TPS (+0.39%); prose +0.47%, Chinese +0.55%, synthetic +0.58–0.59%; fresh complete replies only0.17–0.51% quicker. Long prompt throughput -0.12%. Limited four samples per setting; not universal sub-percent proof.
- **Validation:** Exact10 measured paired fresh outputs, nine API groups, zero new swap; Chinese control drift0.37%, code/prose about0.05%. Build parity generation within0.17%, but prompt parity not established.
- **Revisit:** Changed kernel/shape or explicit combined-profile comparison. Existing knob is already tested; cannot claim a new large boost from it.
- **Evidence:** [Report and variation](M5-GPU-TUNING.md), [raw width sweep](results/20261007T015346Z-m5-matrix-width/comparison.json).

### T11 — Dense MMA GPU SIMD groups four/eight

- **Status:** Rejected measured small regressions.
- **Settings:** `m5-lab` dense matrix group overrides4/8 versus stock; not CPU workers or encoding workers.
- **Result:** Request4 code56.45 →55.61 TPS (-1.49%), synthetic -1.39%/-1.17%; request8 code56.45 →56.25 (-0.35%), synthetic -0.99%/-0.20%; fresh control drift <=0.187%.
- **Validation:** Same24-pass clean matrix batch as T08. No hardware accelerator occupancy counter was measured.
- **Revisit:** A different matrix kernel or measured occupancy/register explanation; do not repeat a blind group-count sweep.
- **Evidence:** [Report](M5-GPU-TUNING.md), [raw groups sweep](results/20261007T020256Z-m5-matrix-workers/comparison.json).

## Original helper / runtime approaches

### L01 — Masked Q2 Metal kernel from Meld

- **Status:** Optional, mixed small result; not a general engine upgrade.
- **Settings:** `q2-masked` versus original pinned engine, prediction off, temperature0.6, 512 output tokens, 4K/F16, batch512; final adjacent quiet confirmation, not a complete new ABBA.
- **Result:** Synthetic51237.91 →38.01 TPS (+0.27%);204835.55 →36.86 (+3.68%). Input throughput -6.09%/-7.29%; short reply0.07% slower, long1.36% quicker but TTFT about0.25s later. Earlier -8.83%/-7.30% figures are confounded by build/browser activity.
- **Validation:** 122 Q2 +2 Q4 CPU-reference GPU tests,108 focused checks across six successful passes. Accumulation changes sampled outputs; no bit-exact claim. Final candidate new swap0.0006GiB, so these historical runs do not satisfy current zero-new-swap adoption. First2.14GiB-swap load excluded.
- **Revisit:** New kernel design or a full quiet current-protocol comparison justified by actual normal costs. Do not reuse confounded percentages or assume all imported Q2 patches are improvements.
- **Evidence:** [Report](Q2-METAL.md), [final analysis](results/20261006-q2-confirmation-analysis/COMPARISON.md), [original raw](results/20261006T172232Z-q2-comparison/comparison.json), [manifest](../config/q2_experiment.json).

### L02 — Aggressively quantized Q2_0 helper

- **Status:** Rejected poor draft acceptance and Metal OOM.
- **Settings:** 1.110GB self-contained Q2_0 helper, full GPU, depth2; original runtime. This is helper quantization, not the successful main-model Q2_0 format.
- **Result:** <2% draft acceptance, partial writing about12–16 TPS (recorded medians13.86/14.42), then Metal out-of-memory/streaming failure. Partial failed-run figures are not accepted speed results.
- **Validation:** Failed native result/log preserved; do not infer safety or quality from loading successfully. Selected Q3 split/shared helper is a different approach.
- **Revisit:** Demonstrably better helper calibration/quantization and a viable memory layout, then accuracy and acceptance before timing. A smaller file alone is not sufficient.
- **Evidence:** [Helper report](PREDICTION.md), [failed raw result](results/20261006T145347Z-prediction-q2_0-gpu2/result.json).

### L03 — Put complete helper on GPU

- **Status:** Rejected at current48GiB working budget; small-batch trial slow.
- **Settings:** Original Q4/Q2_K GPU helpers and later shared helper full-GPU placement; no raised system GPU memory limit.
- **Result:** OriginalQ4 and1.491GBQ2_K fail generation within Metal working budget. Shared full-GPU batch512 also fails; batch128 passes focused checks but generates only about4–10TPS in a feature trial. Those feature timings are not matched benchmarks.
- **Validation:** Native OOM/streaming records retained. Loading is insufficient proof of viable generation. Packed mixed placement is the validated alternative.
- **Revisit:** A substantially smaller, accurate helper with different mapping/working-set requirements or changed hardware budget. Do not repeat full GPU placement unchanged or raise system limits as an unmeasured shortcut.
- **Evidence:** [Original helper attempts](PREDICTION.md), [originalQ4 failure](results/20261006T111640Z-flash-mtp3-ubatch512/result.json), [Q2_K failure](results/20261006T144952Z-prediction-q2-gpu2/result.json), [shared512 failure](results/20261006T182852Z-feature-shared-gpu/result.json), [shared128 trial](results/20261006T183135Z-feature-shared-gpu/result.json), [layout explanation](SHARED-HELPER.md).

### L04 — Original Q4 helper all CPU / smaller split alternatives

- **Status:** OriginalQ4 CPU profile rejected for clean-memory baseline; Q2_K split and Q3 CPU-only inferior alternatives.
- **Settings:** Self-containedQ4 helper CPU, depth3; later smallerQ2_K split and Q3 CPU-only versus selectedQ3 GPU-output split. Historical original engines/settings, not current packed helper.
- **Result:** Q4 CPU about43–45TPS but +1.85GiB swap and longer startup. Q2_K split no new swap but only1–6% writing gain with slower prompt startup. Q3 CPU-only no new swap but slower than selected split. No claim of a fresh current ABBA for these early screens.
- **Validation:** Individual raw results and helper preparation identities retained. Later Q3/shared packed profiles replace these specific memory/layout approaches.
- **Revisit:** A changed CPU helper/kernel/placement with evidence it avoids swap and improves full replies. Do not restore old heavy CPU helper just because generation TPS looked higher.
- **Evidence:** [Helper decisions](PREDICTION.md), [Q4 CPU raw](results/20261006T111806Z-flash-mtp3-cpu-ubatch512/result.json), [Q2_K split](results/20261006T145142Z-prediction-q2-output2/result.json), [historical scoreboard](RESULTS.md).

### L05 — 106K prediction vocabulary

- **Status:** Narrow mixed benefit; not adopted as general prediction upgrade.
- **Settings:** `draft-vocab`, helper106299/248320 tokens, full main vocabulary unchanged, depth2, temperature0.6,128 output tokens; full/subset controls in six-pass comparison. Adds111.5MiB compact head and retains full fallback table.
- **Result:** Synthetic writing +3.94–4.44% versus full helper; code -1.13%; cached generation -9.22%/-10.12% as acceptance drops. Fresh2048 whole reply7.93s versus7.91full/6.66plain, no latency improvement. Reducing helper vocabulary is not free capacity savings.
- **Validation:** 180 focused answers pass, full target out-of-subset token reachable; general output/distribution equivalence not established. One subset run adds53.3MiB swap, others zero; historical report retains it, so suite does not satisfy current clean-memory gate. Initial CPU-routed compact-head attempt was corrected and excluded.
- **Revisit:** Better vocabulary coverage/selection proven on realistic multilingual/code/cached tasks, memory accounting and complete-reply improvement; any shared-helper combination needs a new independent comparison.
- **Evidence:** [Report](DRAFT-VOCAB.md), [raw comparison](results/20261006T183950Z-vocab-comparison/comparison.json), [manifest](../config/draft_vocab_experiment.json).

### L06 — Shared helper with interleaved CPU/GPU tensors

- **Status:** Rejected layout; fixed by packed layout.
- **Settings:** Shared helper small dense tensors on GPU, experts on CPU, but GPU tensors interleaved with CPU weights in GGUF.
- **Result:** Loader maps from first to last GPU tensor, spanning1183.14MiB although intended GPU weights only45.64MiB; initial mixed generation fails. Repacking CPU experts first/GPU tensors last reduces mapped span to45.64MiB with identical tensor bytes. Do not restore interleaved layout.
- **Validation:** Packed mixed feature28 checks, zero new swap; 32 retained tensors/metadata byte-verified, full later240-check suite zero new swap. Shared table removal saves521MiB, not96% of whole-model RAM. BorrowedQ5_K output changes proposals relative to originalQ3 output, so no generic bit-equivalence claim.
- **Revisit:** Only if loader mapping changes are proven to support interleaved placement safely. Normal development should retain the packed helper.
- **Evidence:** [Layout report](SHARED-HELPER.md), [failed interleaved raw](results/20261006T183622Z-feature-shared-mixed/result.json), [packed pass](results/20261006T183903Z-feature-shared-mixed/result.json), [shared manifest](../config/mtp_shared_experiment.json).

### L07 — Original unpatched shared-helper depth/worker sweep

- **Status:** Historical workload tradeoffs; superseded by few-row MMA engine, not a universal setting win.
- **Settings:** `mtp-shared` before `mtp-mma`, depths1/3/4 versus2; helperCPU6/12 versus8 in separate depth2 sweep. Temperature0.6,128 output tokens.
- **Result:** Depth1 Chinese +16.29% and prose +2.74%, but cached -6.93–7.92%; depth3 code +5.02% but prose -8.32%; depth4 cached2048 +17.19% and reply9.18% quicker but Chinese -18.77%, prose -13.88%. Worker generation gains all <1%; twelve workers long reply1.6% quicker. No one setting wins every task.
- **Validation:** Depth240/worker180 focused checks, clean speed suites zero new swap; general exact-token equivalence not claimed. Later functional checks with a restarted VM added swap and must not be called clean speed evidence.
- **Revisit:** Changes in the current patched engine/acceptance or adaptive selection, with fresh matched controls. Never transfer these old-engine percentages directly to current control. T01–T07 cover later settings.
- **Evidence:** [Historical report](HELPER-TUNING.md), [depth raw](results/20261006T211035Z-tuning-depth/comparison.json), [workers raw](results/20261006T212441Z-tuning-threads/comparison.json), [subsequent engine](METAL-MMA.md).

## Useful results that must not be rediscovered or mislabeled failures

### K01 — Direct convolution-state copy without intermediate CONT

- **Status:** Kept as practical benchmark control / separate optional launcher.
- **Settings:** `m5-copy` / `conv-direct`, remove intermediateCONT before existing strided convolution-state copy; different operation from the absent large GDN CPY in C03.
- **Result:** Code56.501 →57.258TPS (+1.34%), prose42.877 →43.448 (+1.33%), Chinese +1.62%, synthetic204850.016 →50.737 (+1.44%). Fresh replies0.75–1.59% quicker. Small TTFT changes do not establish a strong latency win.
- **Validation:** Eight model launches,256 checks, exact fresh/cached outputs, zero new swap. Existing ordinary launchers unchanged; later experiments compare against this improvement.
- **Revisit:** Already implemented and measured; only new mechanism or explicit stacked-profile comparison needs testing. Do not count its gain again when reporting later comparisons.
- **Evidence:** [Report](results/20261009T112641Z-m5-copy-resume/REPORT.md), [raw](results/20261009T112641Z-m5-copy-resume/comparison.json).

### K02 — Metal Tensor API enabled

- **Status:** Retain existing enabled path; measured confirmation, not a newly added accelerator.
- **Settings:** On/off brackets at writingdepth3 and follow-updepth4, current `mtp-mma`; no separate Neural Engine runtime.
- **Result:** Writing2048 input312.08 →535.07tok/s (+71.46%), TTFT41.67% shorter, complete reply30.83% quicker; code generation +7.23%, Chinese +12.16%, prose flat. End-to-end differences include changed floating-point paths/acceptance, not pure kernel utilization.
- **Validation:** Clean20-pass tensor/depth batch; focused checks pass. Hardware AI occupancy and separate Neural Engine use unmeasured.
- **Revisit:** Future exact-format cooperative-input kernels are new work; simply enabling already-on Tensor API is not another optimization.
- **Evidence:** [On/off report](M5-RESULTS.md), [writing raw](results/20261007T004003Z-m5-tensor-writing/comparison.json), [follow-up raw](results/20261007T004710Z-m5-tensor-followup/comparison.json).

### K03 — 8K F16 context

- **Status:** Validated capacity option; not a decode-speed improvement.
- **Settings:** Full Flash, same `mtp-mma`, independent4K/8K/8K/4K,128 output tokens; separate exact6144-token recall fixtures at8K. 4K defaults preserved.
- **Result:** Fresh generation -0.18% to+0.20% versus4K, whole reply changes <0.36%; code56.45 →56.46TPS. Six long recall checks pass. Private logged buffers1046.24 →1210.75MiB, not physical RAM peak.
- **Validation:** 134 answer/cache/capacity checks; both8K launches zero new swap, >=2.32GiB available. First fixture returned correct facts in Markdown fences and failed strict rawJSON; explicit fixturev2 passed unchanged grader, independent full retry. Initial failure not pooled.
- **Revisit:** Larger context or stronger long-context quality/capacity study; quantizedKV requires independent correctness evidence and is unnecessary for this measured8K fit. Do not rerun8K merely hoping for higherTPS.
- **Evidence:** [Report](results/20261009T085842Z-m5-next-batch/REPORT.md), [accepted raw comparison](results/20261009T092650Z-context-8k/comparison.json), [original format failure](results/20261009T091833Z-context-8k/comparison.json).

### K04 — Upstream fused-residual correctness fix

- **Status:** Validated correctness patch; no meaningful measured TPS gain.
- **Settings:** `m5-correctness` versus `m5-lab` on4B Qwen3.5Q4_K_M and versus current engine on full Flash; independentABBA,128 output tokens,4K.
- **Result:** Small model fresh generation -0.35% to+0.13%; full model -0.22% to+0.16%, within drift. Keep purpose labeled correctness, not accelerator gain. Full model passing does not prove its actual graph exposed the original faulty fusion.
- **Validation:** Small163 answer/cache/capacity checks,16 selected residual cases; full128 answer/cache checks,572 general GPU cases per engine plus16 residual reproducer cases. Zero new swap in accepted launches.
- **Revisit:** Reproduce a relevant faulty graph or validate upstream rebase behavior; no speed rerun needed merely to rediscover the already-flat result.
- **Evidence:** [Small model report](results/20261008T122556Z-small-m5-screening/REPORT.md), [full model report](results/20261009T085842Z-m5-next-batch/REPORT.md), [full raw](results/20261009T085850Z-m5-metal-residual-correctness/comparison.json), [manifest](../config/m5_correctness_experiment.json).

## Invalid or excluded attempts: preserve, do not score as feature regressions

These are examples with explicit dispositions, not a claim that every compile error or raw failed process in the archive is individually summarized here. The existing [per-run scoreboard](RESULTS.md) and each linked suite remain the full run history.

| ID | Attempt / problem | Disposition and retry condition | Evidence |
| --- | --- | --- | --- |
| X01 | Original full-model load with Docker active;2.14GiB new swap | No speed samples accepted. After authorized VM stop, later trials completed. Retry only with normal admission/quiet host; do not weaken guard. | [Raw stopped load](results/20261006T171840Z-q2-1-baseline/result.json), [Q2 report](Q2-METAL.md) |
| X02 | Shared comparison interrupted by external Java builds/swap | Incomplete suite excluded; quiet independent eight-pass retry is SHARED-HELPER result. No feature regression claim from interrupted control. | [Interrupted comparison](results/20261006T185032Z-shared-comparison/comparison.json), [context](results/20261006T185032Z-shared-comparison/interruption-context.json) |
| X03 | Confidence/helper initial batch overlapped VoltTracker builds; follow-up +138.18MiB swap then forced cleanup/Metal assertion | Entire initial batch excluded, quiet batch retried unchanged; cleanup assertion is not accepted inference evidence. | [Interruption receipt](features/20261006-m5-helper-resource-interruption.json), [initial writing](results/20261007T032352Z-m5-confidence-writing/comparison.json), [initial follow-up](results/20261007T033300Z-m5-confidence-followup/comparison.json) |
| X04 | Earlier operation-profile baseline second launch +60.3MiB swap during build overlap | Baseline refresh incomplete; no optimization percentage against its first clean launch. Two clean later launches completed baseline. | [Operation report](M5-OPERATION-PROFILE.md), [later full baseline](results/20261009T042329Z-heavy-guarded-trial/REPORT.md) |
| X05 | Full heavy trial admitted at31.85GiB, below usual34GiB; +2.625MiB swap during load | No speed samples; target-only fallback deferred before launch. Read-only owned-model cache reset restored headroom; two normal-admission clean retries passed. | [Stopped trial](results/20261009T041819Z-heavy-guarded-trial/trial.json), [complete baseline](results/20261009T042329Z-heavy-guarded-trial/REPORT.md) |
| X06 | Initial8K rawJSON formatting check failed despite correct facts in fences | Fixturev2 explicitly asks for rawJSON, unchanged strict grader; fresh complete4K/8K bracket, no pooling. Capacity not judged from partial failure alone. | [Original context attempt](results/20261009T091833Z-context-8k/comparison.json), [retry](results/20261009T092650Z-context-8k/comparison.json) |
| X07 | Sampling-view initial control +0.5MiB swap | Excluded completely; full clean independentABBA accepted. Retry only after headroom settles. | [Initial suite](results/20261009T132423Z-m5-sampling-view/comparison.json), [clean suite](results/20261009T132908Z-m5-sampling-view-clean-retry/comparison.json) |
| X08 | Encoder0 initial control passed answers but +983040bytes/0.94MiB global swap | Excluded by suite's zero-new-swap rule; fresh unchanged suite accepted after headroom settled. Passed run status alone does not qualify adoption. | [Excluded run](results/20261009T171015Z-m5-encoders0-1-conv-direct/result.json), [stopped suite](results/20261009T170959Z-m5-encoders0/comparison.json) |
| X09 | Clean encoder0 suite initially rejected in postprocessing: app logger prefixes and absent unused callback-setter events | Preserve original rejection. Corrected parser accepts exact logger prefix/raw markers and proves null via pinned initialization/instrumented setters; analyzes same raw/source/settings without performance rerun. Any non-null callback still rejected. | [Original postcheck](results/20261009T171405Z-m5-encoders0/comparison-postcheck-original.json), [corrected comparison](results/20261009T171405Z-m5-encoders0/comparison.json) |
| X10 | Early gate probeSIGBUS: MetalVIEW overCPUINPUT storage | Corrected explicit Metal leaf placement/storage validation before accepted correctness/performance. Not a model failure or usable speed result. | [Final gate history](results/20261009-next-few/REPORT.md), [raw suite](results/20261009-next-few/REPORT.json) |
| X11 | GroupingV1 independent graphs allowed inter-block concurrency; GDN short bracket11.43% drift | V1 throughput not sequential latency; replace with dependent fixture. Noisy GDN timing excluded as conclusive; final sustained-warmup bracket still no qualified gain. | [Grouping history](results/20261009T153117Z-m5-expert-pair-group/REPORT.md), [GDN history](results/20261009-next-few/REPORT.md) |
| X12 | Copy probe same-second artifact collision; early compile/logging/trace-cap/CPU-admission failures | Original artifacts retained/excluded. Hardened microsecond IDs and frozen probe-at-model-runs receipt distinguish accepted speed data from supplementary checks. Admission deferral starts no model. | [Copy report](results/20261009T112641Z-m5-copy-resume/REPORT.md), [copy summary](results/20261009T112641Z-m5-copy-resume/summary.json) |
| X13 | Embedding diagnostic first pair: clean control, candidate admission deferred while RAM settled | Candidate loaded no model; incomplete pair excluded as comparative evidence. Preserve both receipts. Independent complete pair after ten-second pause passes; no guard or admission limit weakened. Raw log postprocessing handles byte offsets and known interleaved HTTP notices without rerunning accepted inference or using logged timings as speed evidence. | [Original control](features/20261009T184458121799Z-m5-embedding-topology/m5-copy/capture.json), [deferred candidate](features/20261009T184458121799Z-m5-embedding-topology/m5-embedding/capture.json), [complete pair](features/20261009T184602948859Z-m5-embedding-topology/parity.json) |
| X14 | Draft-cap diagnostic postprocessor conflated raw remaining/context budget with effective max3, then command normalization did not allow the explicit minimum0/greedy pair's position | Preserve original off rejection and frozen runner/raw log. Separate corrected analysis verifies source/build/model/runner identity, offline/resource checks, raw/effective distinction, actual target rows and real cancellation. Canonicalize only the two explicit scope pairs. No model rerun; not a native-feature or speed regression. | [Original rejected off](features/20261009T193100376954Z-m5-draftcap-qualification/off/capture.json), [corrected analysis](features/20261009T193100376954Z-m5-draftcap-qualification/off/reanalysis.json), [frozen reanalysis](features/20261009T193100376954Z-m5-draftcap-qualification/reanalysis-runner.py) |
| X15 | Completed tail ABBA failed final report-path formatting after output checks: relative path passed to absolute-root relative_to | Preserve original rejected comparison. Resolve input paths for future runs; frozen reanalysis recomputes unchanged raw summary and verifies engine/model/settings/math/outputs/allocation/traces/zero-swap evidence. No performance rerun or new source pin. | [Original rejection](results/20261009T193647Z-m5-draftcap-tail/comparison-postcheck-original.json), [accepted reanalysis](results/20261009T193647Z-m5-draftcap-tail/comparison.json), [frozen analyzer](results/20261009T193647Z-m5-draftcap-tail/reanalysis-runner.py) |

## Remaining ideas are not rejected results

The [ranked Astra queue](research/20261009-astra-future-queue.md) retains estimates and source links. The following have **not** been implemented or benchmarked in the latest pass:

1. Adaptive/mixed-cap controller and held-out policy calibration remain unimplemented or unqualified. Existing-cap early stop is tested in D01; actual fixed cap2 is parked in D02. Do not describe those completed experiments as untested, or resume an adaptive controller before fixing the demonstrated extended-output failure.
2. Quantized prompt cooperative-input kernels, after exact-format/precision proof; different from P09's BF16 few-row projection.

Parallel gate-up8, real-model T1 head dispatch proof, cold/pressured native lookup waits, larger-model SSD paging, cross-device execution and separate Neural Engine runtime remain untested or deferred. Unified memory on this Mac does not pool RAM with another computer. Do not mark those ideas disproven by unrelated tests.

Latest complete state: [draft-cap report](results/20261009-draftcap/REPORT.md), [raw decisions](results/20261009-draftcap/REPORT.json), [verification](results/20261009-draftcap/evidence/final-verification.json). No qualified new TPS gain;121 load-free checks,21 engine receipts and all20 preexisting engines unchanged. Tail ABBA is the latest completed matched speed suite; fixed2 stopped at its exact-output gate. Future workload selection and adoption use English prose/code only; completed historical data remains preserved. No benchmark is started by this ledger or its index.


### October9 top10 excluded attempts

- **X16:** First native build rejected mutable count pointers passed as const to set_bytes. Counts corrected; first build log preserved. No GPU/model result. [Log](results/20261009-top10/build-attempt-1.log).
- **X17:** First disabled-control fixture aborted on two-row gather shape; fixture corrected to3D source and row-aware reference. No candidate/performance launch, zero new swap. [Raw failure](results/20261009-top10/20261009T205247140211Z-check-control/result.json).
- **X18:** First cold original-model control load stopped on524288bytes new swap before any response. No model TPS accepted. Fresh warmed-cache ABBA retains zero-new-swap guard and a new prelaunch baseline; all four launches passed. [Failed comparison](results/20261009T205724Z-m5-parallel-top10/comparison.json), [load record](results/20261009T205740Z-m5-parallel-top10-1-conv-direct/result.json), [diagnosis/retry](results/20261009-top10/attempts.json).

The valid first top10 component bracket was superseded by a once-per-process dispatch marker, then rebuilt and requalified; it remains preserved as `comparison-before-dispatch-marker.json`. Final report adjudication changes no timings and preserves its original report/JSON. These are provenance updates, not failed performance attempts.

### X22 — Compact-tile original-control fixture used unsupported quantized CONT

- **Disposition:** Excluded before candidate execution or timing. Original control aborted at the T33 unsupported-shape fixture after 168 correctness records; native return -6, zero new swap.
- **Cause:** Fixture inserted `ggml_cont` around a Q2_0 weight slice. Pinned Metal supports Q2_0 copying to F32/F16, not Q2_0-to-Q2_0 CONT. This is a fixture error, not a compact-worklist result.
- **Correction/retry:** Retain quantized strided weight views supported by the original MM_ID row/expert strides. Record noncontiguous weights accurately; this exercises the combined shape/stride fallback. Keep F32 input CONT, candidate sources, precision, outputs and acceptance gate unchanged. Preserve this entire rejected source/runtime bundle and use a fresh complete bracket.
- **Evidence:** [Diagnosis and raw attempt](results/20261009-compact-tiles/component-initial-excluded/exclusion.json), [failed original control](results/20261009-compact-tiles/component-initial-excluded/20261009T234759515854Z-check-control/result.json).

### Latest small-gain validation and remote memory recovery

This is the current update to P11/P07/W02. Historical entries and old adoption thresholds above remain evidence of their original decisions; the new prospectively declared plan has no fixed minimum gain. [Complete report](results/20261009-small-gains/REPORT.md), [candidate tracker](small-gain-candidates.json), [final verification](results/20261009-small-gains/final-model-verification.json).

- **Resource recovery:** Administrator-only global purge was not authenticated and its owned prompt was cancelled when the user clarified they are remote. Targeted read-only `MS_INVALIDATE` on verified model files recovered 3.97 GiB of measured availability, sustaining >=35.97 GiB for 60 seconds with normal pressure and zero new swap. No app/service closure or model modification. This remote-compatible method should be considered before repeating demands for app shutdown/reboot. [Raw receipt](results/20261009-small-gains/memory-investigation/model-cache-trial-20261010T033512403513Z/result.json).
- **P07 — independently confirmed possible addition:** Short English code/prose TPS +0.5259%/+0.5878% in screening, +0.6107%/+0.7921% in independent confirmation. Reply benefits also qualify, with 27.08ms/50.79ms saved on confirmation. Native/output/resource gates pass. Defaults unchanged; do not assume a larger-prompt scope or add older percentages.
- **W02 — speed benefit with a small latency tradeoff:** Short code/prose TPS +0.7151%/+0.6453%, replies +0.5308%/+0.5189% quicker. Code first-token +3.525ms/+1.2651% trips the frozen material-regression guard; prose's +4.023ms is within its larger drift allowance. Keep a possible addition, not a claim of no benefit. No confirmation or combination under this plan. Revisit only after a prospectively declared absolute-latency tradeoff, then fresh validation; do not silently loosen the current guard or retroaccept this screen.
- **P11 — full-model V1 screen now complete:** Long English code/prose TPS -0.3087%/-0.1566%, no qualified prompt/reply scope. Its real component gains remain preserved but did not translate here. Revisit a changed implementation or declared workload exposure, not unchanged repetitions.
- **X24 resolution:** The one allowed complete resource-only retry passed: all 16 launches zero new swap, 416 answer/cache checks passed and 256 exact fresh/warmup/cache signature records validated. Original X24 and held preflight remain excluded; no partial pooling or guard changes. Only P07 confirmed, so no combination launched. Post-benchmark 38.49 GiB available, no model server, Colima stopped. [Resources](results/20261009-small-gains/memory-investigation/post-benchmark-resources.json).

## Sequential fixed-latency validation and P07 rollout (2026-10-10)

- Authorization: "Do them sequentially." New absolute W02 startup rule declared before fresh GPU/model runs; original plan/results remain unchanged. Frozen plan: `bench/results/20261010-small-gains-stack/plan.json`.
- **W02:** fresh ABBA code 59.7203→60.0688 TPS (+0.5835%), prose 40.0623→40.3473 TPS (+0.7114%). Average startup delays 4.254/6.207 ms; worst code/prose launch-pair delays 6.243 / 12.660 ms. Prose exceeds fixed 10 ms ceiling. Valid throughput tradeoff, held for general use; no confirmation/stacking. Revisit only after a material first-token-path change with a new frozen protocol.
- **P07:** prior independent short 256-output confirmation retained (+0.6107/+0.7921% TPS). New long safety: code 45.8500→46.1872 (+0.7356%), prose 46.8321→47.1436 (+0.6651%); generation qualifies both, one bracket only. New short 32-output safety: code 63.9946→64.5608 (+0.8848%, below its variation gate), prose 52.4660→52.8550 (+0.7415%). Neither safety cohort has material latency/reply/generation regression; no cached follow-up flags.
- **Resources/verification:** one non-admin read-only model-cache cleanup, +2.7955 GiB available; unchanged 34 GiB admission and zero-swap guards. 12 benchmark launches, 312 answer/cache checks, 192 output signatures, all exact and zero new swap. No native/source/math/model/precision changes; 5 load-free protocol checks passed.
- **Promotion:** normal no-argument `Start Strata.command` now selects `m5-small-stack/small-reduce` and the measured helper settings. Actual Strata API 16 English checks plus SSE streaming passed, native command matches selected configuration, zero new swap, both ports close. Original bytes retained in `Start Strata - Original Baseline.command`. Generic CLI source/explicit arguments preserved; no server remains running; no commit/push.
- Evidence: [bench/results/20261010-small-gains-stack/REPORT.md](results/20261010-small-gains-stack/REPORT.md); raw comparisons, launch receipts, guard histories, frozen source archive, promotion and app proof linked there.

## Maintained app profiles - October13,2026

Balanced P07 remains the normal launcher; editing lookup has a maintained dedicated option with bounded proposals and MTP fallback. Both enforce full-model admission34GiB, continuous normal pressure, zero new swap and1GiB ongoing floor. Current branch:171offline checks, five campaign-protocol checks and18 actual API/lifecycle groups pass, with five exact cross-profile reply texts. No new combined percentage; W02/High Power remain disabled. [Sanitized results and scope](PERMANENT-PROFILES.md). Raw evidence, process snapshots and weights stay local.

## October13 editing expansion and prompt-local drafting

- **E01 — varied complete-file edits:** prepared for the user-authorized next pass. Compare maintained balanced versus code-edit on disjoint Python/JavaScript/JSON files, with separate first-exposure and warmed results. This extends the earlier one-file finding; it does not repeat its fixture or claim a general chat gain.
- **E02 — prompt-local drafting:** prepared separately over the maintained code-edit control. Add ngram-simple ahead of ngram-mod and MTP; explicit match16/size3 bounds keep native maximum allocation width three. No helper-depth, model, precision, power or launcher changes.
- **Protocol:** fresh A/B/B/A, three warmed repeats, normal EOS and complete verbatim edits, prompt/text/token identity and actual native activation. Eligible first-exposure language scopes receive an independent bracket on held-out files. No fixed minimum percentage; both candidate launches must beat both controls beyond twice control drift. Faster complete reply and no material TPS loss are required, with at most100ms additional first-token latency. Cancellation/disconnect recovery, continuous normal pressure and zero new swap remain mandatory.
- **Preparation validation:**11 new load-free harness checks and196 total offline checks pass. Tests reject partial/capped files, missing languages/repetitions, output-token divergence, incomplete brackets, swap, control drift and average gains hiding a losing candidate. Full-model entry remains34GiB and the ongoing floor1GiB. Raw evidence is ignored locally; no automatic default promotion.
- **Evidence locations:** `bench/results/20261013-editing-breadth-v1` and `bench/results/20261013-prompt-local-v1`. Any failed attempt stays in place. A retry requires a documented source/workload/resource change and a new directory; partial results cannot become a speed claim.

- **E01-X1 — checker rejection, not a native failure:** v1 stopped after its first candidate launch because the harness looked for per-draft DEBUG output at the normal TRACE verbosity. Its native statistics prove727 generated/723 accepted lookup drafts and2178 proposed/2150 accepted lookup tokens. Both completed launches returned all three complete files verbatim, with identical tested text/token signatures, normal pressure and zero new swap. The partial bracket remains excluded from performance claims. Original source bytes are preserved and verified against the frozen hashes. The corrected checker reads actual bounded native counters; a new regression test rejects absent activation, impossible acceptance and proposals beyond width three. Retry directory `bench/results/20261013-editing-breadth-v2`; workload, model, math, command and performance gates remain unchanged.

- **E01-X2 — confirmation prelaunch hold:** the corrected v2 screen completed all four valid launches. The first confirmation admission happened before macOS released the preceding model's memory; no native child or response was produced. Preserve that held arm and the v2 campaign's failed status. A separate, single resource-only continuation in `bench/results/20261013-editing-breadth-confirm-v3` waited for the unchanged34GiB threshold, verified the identical frozen source/model closure, and ran a complete independent held-out bracket. No partial data was pooled and the valid screen was not repeated. Future maintained runs now use the existing bounded90second headroom-settle helper before every admission, including phase transitions.
- **E01 — independently confirmed:** screen first-exposure gains Python19.228%, JavaScript20.038%, JSON17.122%; held-out confirmation Python73.105→87.414TPS (+19.573%), JavaScript72.966→87.789 (+20.314%), JSON73.108→86.697 (+18.587%). Held-out complete replies4.0717→3.4543s,4.4237→3.7646s and3.8763→3.3461s, respectively;13.676–15.163% quicker. Both generation and full-reply scopes qualify in all three languages in both brackets. Held-out warmed editing gains22.744%,22.866%,22.848%, kept separate from first exposure.
- **E01 scope and resources:**96 complete-file replies,32 prose-control replies and eight disconnect/reuse checks across eight accepted launches; tested text/token signatures exact. New swap0, continuous normal pressure, minimum available3.054GiB, peak process RSS37.650GiB. Candidate extra average RSS26.6MiB in screen/58.6MiB in confirmation; RSS is not unique Metal memory. This validates the existing optional editing profile on six files. It does not change its native arguments, establish broader task accuracy, create a new general-chat gain, or add percentages to the original one-file result. Warmed prose replay is diagnostic only.
- **E02 prospective choice:** before its first model run, use the native standard12-token prompt-local match with explicitly bounded three-token proposals, ahead of unchanged match16 ngram-mod and MTP3 fallback. The earlier match16 preparation was not executed. This is a separate feature screen over the kept editing profile, not a blind helper-depth retry. Complete held-out confirmation is required for any new first-exposure gain. Current checker validation197 load-free tests passes; default balanced/editing inference arguments remain unchanged.

- **E02 — inactive under the three-token cap, parked:** `bench/results/20261013-prompt-local-v1` stops after its first candidate, with no scored percentage. All16 normal-EOS replies in each completed arm and both disconnect/reuse checks passed at normal pressure/new swap0, but ngram-simple recorded784 calls and zero generated or accepted drafts. The pinned `common/ngram-map.cpp` returns empty whenever `copy_max < size_ngram`; with size_ngram12 and size_mgram3, it can never pass that condition. Do not raise the draft allocation or rerun the same flags. The original source and inactive native statistics remain preserved. Maintained tooling now rejects this known combination before any model load.
- **E02-M — qualified alternative, prepared:** the existing ngram-map-k implementation accepts a12-token key and up to three proposed tokens without that coupling. A CPU-only probe linked to the exact current engine's ngram-map object passes18 synthetic matching/nonmatching cases across keys4/12/16 and proposal widths1/2/3. It also reproduces the simple matcher's empty result in every short-proposal case. No model, GPU/backend initialization, native source patch or engine rebuild. Trial adds map-k(match12,size3,min-hits1) ahead of unchanged ngram-mod/MTP fallback. Current proof/source/object/binary hashes are checked before and after each arm; active map drafts are required while an unused fallback is allowed. New result directory `bench/results/20261013-prompt-map-v1`; fresh controls and held-out confirmation, not reuse of the inactive trial's timings.

- **E02-M — active and correct, no qualified gain:** complete fresh A/B/B/A passed all48 whole-file edits,16 prose replies, four disconnect/reuse checks, exact prompt/text/token signatures, normal pressure and zero new swap. The new matcher actually generated208/accepted208 drafts (624/624tokens) in its first candidate launch, alongside active fallback. First-exposure Python generation+0.3818%/reply+0.3071%; JavaScript−0.2072%/reply−0.0963%; JSON−0.0681%/reply−0.1975%. No language passes the frozen direction/drift/full-reply gates, so no confirmation was launched and the feature remains disabled. This does not reject validated sub1% gains; this screen failed its repeatability gate. Revisit only a changed matcher/identified workload gap or measured helper cost. Preserve `bench/results/20261013-prompt-map-v1`, its CPU proof and original source; do not repeat the same flags.
- **E03 — conditional SSD prefetch next:** source inspection confirms the Qwen path already supplies bounded lookup-row ranges through `llama_prefetch_rows`, while the pinned `llama_prefetch` platform guard excludes Apple. A prefetch-only backport can be isolated from loader mapping changes. P06's warm lookup envelope remains below0.1% of reply time, so no unchanged warm-only prefetch speed retry is warranted. The next gate is a native cold/long-prompt lookup-cost capture with attributed eligible pages, file/cache provenance and the unchanged resource policy. A >=2% lookup envelope permits investigation but is not proof of SSD wait; unknown cache state must remain labelled unknown. No prefetch or mapping change is enabled by this pass.
- **Reproduction:** `scripts/prepare_ngram_probe.py --build` prepares/verifies the CPU-only matcher receipt; `scripts/benchmark_editing.py --experiment editing|prompt-map --output bench/results/<new-directory> --run` runs the complete-file comparison. Without the execution flag, preparation does not load a model. Model weights, personal/raw outputs, native objects/binaries and source snapshots remain ignored locally.

### Real performance-monitor validation and EOS counter handoff

- **Observed and repaired:** a real maintained app request exposed a missing native completion record. The pinned shell closes the backend generator at its stop token; the native timing packet can arrive immediately afterward. Before the fix, the Monitor correctly labelled its rate as server-derived and left prompt speed/acceptance/reuse unknown. The backend now captures the final packet and permits an EOS-only drain bounded to0.5s, checking cancellation every50ms. User cancellation/non-stop closure skips that drain; missing final data remains unknown. Cancel-before-start also clears prior-request counters. No native binary, math, model, inference argument or sampling change.
- **Regression evidence:** the real close-at-EOS and stale cancel-before-start behaviors fail before/pass after. Eight maintained load-free transport checks also cover cancellation, partial output, missing/queued final records and the drain deadline. Total207 offline tests, five campaign-protocol checks and seven browser-state/timing tests pass;18 actual native CPU matcher cases passed separately.
- **Real app proof:** two complete-file API replies match the expected edit at normal EOS. Native generation85.376/90.263TPS, prompt throughput327.082/79.683TPS, draft acceptance100%, reused0/303tokens. These are observed functional checks, not matched performance gains; the second request reuses almost all of its prompt, so its tiny prompt-throughput sample is not comparable to the first full read. All nine actual API/integration groups pass after the fix, including native/adapter greedy token parity, SSE, context/tool rejection and cancellation/disconnect recovery.
- **Real browser proof:** the synthetic file edit matches verbatim; browser first text889.4ms/full request4311.7ms, native generation81.707TPS, prompt395.514TPS and draft acceptance96.3%. This browser request includes187 characters of reasoning and a different rendered prompt; it is not comparable to the thinking-off controlled editing fixtures. Monitor fields say live model/native timing; the numeric export contains no prompt/reply, home path or guard-file path. The acceptance label now names all draft tokens, including lookup proposals, rather than implying an MTP-only figure.
- **Shutdown/privacy:** the owned app/native processes stopped, ports8095/8096 closed, continuous pressure remained normal and new swap stayed0. Runtime evidence is local in `bench/results/20261013-real-monitor-feature-v2`; screenshots and raw outputs are not committed. Native engine and model bytes remain unchanged, and the unhelpful extra matchers remain disabled.

### E03 — long English lookup attribution, prefetch still disabled

- **Status:** Two complete diagnostic/parity launches passed. No prefetch candidate or TPS improvement measured. This changes the scope from P06's warm short prompts; it does not revive that unchanged trial.
- **Settings:** `scripts/capture_lookup_long.py`; two synthetic2337/2346-token English documents, first encounter and exact replay, no warmup/prompt reuse, greedy, normal EOS within256tokens. `m5-lookup`/conv-direct over the earlier m5-copy engine, existing Q2 target/sharedQ3/MTP3/mixed/eight workers/4K/F16/batch512. P07 absent; native fusion preserved. Native tracing is excluded from performance comparisons. Trace runs first; subsequent control establishes output parity only.
- **Evidence:** First document gather envelope145.288ms/4941.669ms reply =2.940%, including144.335ms before observed first text (3.029% of4765.339ms). Exact replay1.527ms/4661.893ms =0.0328%. Other document first21.096ms/4740.340ms =0.4450%, replay1.654ms/4684.368ms =0.0353%. Exact lazy shard1/offset192/90-byte row/16KiB page attribution, loader prefetch eligibility and nine invocations/request verified. The Apple platform guard still excludes actual advice. Cache state unknown; envelopes include CPU gather/dequantization, scheduling, overlap and trace perturbation, not measured SSD wait.
- **Validation:** Eight full normal-EOS outputs; all four trace/control text/token/prompt signatures identical. Continuous normal pressure, zero new swap, healthy monitor and both owned children stopped. Minimum available RAM2.98/3.38GiB. No cache purge, preload/wiring, cleanup during runs, source/model/precision/default change.212 maintained offline tests pass. Raw/frozen source stays local at `bench/features/20261013-lookup-long-v1`.
- **Decision/revisit:** One first encounter crosses the diagnostic2% gate, permitting bounded prefetch-only investigation with actual eligible page residency/advice evidence. Approximately145ms is the conservative opportunity scale on this request, not a promised savings or general decode gain. Qualify first-text/full-reply changes independently against control drift. Preserve warm-only parking; do not claim these unknown-cache launches are controlled cold runs. [Sanitized result and next gates](research/20261013-parent-mac-refresh/REPORT.md).

### Parent Mac support refresh

- **Fresh source:** `Niko1221/Strata` main is now `ed4773eb7c8f1f1531ba2bc70e0e1987de2661af`; it includes native `metal/`, Mac installation and `docs/MAC.md`. Earlier out-of-scope/no-parent-port statements are historical. Its M5 Max128GB/M4 mini32GB measurements are not our M5 Pro48GiB results.
- **Load-free proof:** Thirteen pinned upstream source files saved locally; relevant setup, allocator and draft-round code inspected. Unchanged CPU-only arena-budget tests compiled and passed47checks. No parent setup, new model/pack, GPU initialization or candidate inference. Its installer selects streaming/no-MTP at48GiB; actual runtime budget and helper/pack compatibility remain unqualified. Q8 HC defaults require separation from BF16 architecture comparisons. Existing helper backend sampling is already on, so that flag is not a new candidate.
- **Queue:** Native prefetch attribution/candidate, isolated parent compatibility/memory plan, measured helper round-trip/chaining opportunity, separate MLX budget, then contiguous expert storage for larger streamed models. New engine adapter/benchmark still needs implementation; no automatic switch, transferred foreign percentages or repeat of parked exact-sampling failures. [Evidence and scope](research/20261013-parent-mac-refresh/REPORT.md).

### E04 — parent native Metal engine on this48GiB M5 Pro

- **Status:** Isolated source build and real same-model trial completed. Keep the current engine for normal generation/editing. Parent long-prompt processing is worth separate work; no automatic app/default change.
- **Preparation:** Parent `ed4773eb7c8f1f1531ba2bc70e0e1987de2661af`, its pinned CPU ggml `3cf03257f219afbe7334045ff7c6a06ac68c627d`, verified Apple metal-cpp headers and separate pinned Python environment. Exact existing Q2 shards reused. Native index/dense/tokenizer pack introduces zero tensor conversions. Private contiguous expert copy verifies all48×512expert blobs against the GGUF. No new model checkpoint; source/weights/raw results/private config remain outside Git.
- **Completed bracket:** Fresh current/parent/parent/current, two requests on six English workloads per launch,48 normal-EOS outputs. Current balanced P07/sharedQ3/MTP3/mixed/eight workers; parent reduced20decimal-GB expert cache, no MTP, default rounded Q8 HC. Identical rendered/tokenized input,4K,greedy, no prompt caching. Different native timing definitions/transports and uncontrolled OS caches are documented. All four launches: healthy monitor, normal pressure, zero new swap, owned children stopped.
- **Generation:** Prose38.83→26.17TPS (−32.60%); short code67.30→22.89 (−65.98%); balanced file edits73.31–73.71→25.66–26.12 (−64.37–65.18%). All24file outputs are verbatim and token-identical across backends. Native parent file replies take about2.5–2.6times as long. Same-day dedicated current editing supplement independently completes six exact file edits: first86.30–88.34TPS, replay89.31–90.93TPS, active bounded lookup/MTP counters, normal pressure/new swap0. The supplement is not an additional confirmed percentage or part of the balanced bracket.
- **Long input:** Token-identical short retrieval response; first text4.600→2.967s (35.50% sooner), whole reply5.064→3.912s (22.74% sooner), native prompt processing507.14→797.31tokens/s (+57.22%). Parent answer generation itself is31.48 versus64.77TPS. Both answer `team Grove` with correct numeric facts; the original exact owner-string checker expects `Grove` and rejects both. Both code responses add prohibited Markdown fences, so their strict syntax checks fail. Format/rubric results are retained; no broad code/quality equivalence is claimed.
- **Memory:** Current peak process RSS37.49/37.51GiB, parent24.17/24.57GiB; minimum available RAM3.58/3.72 versus10.44/10.52GiB. RSS is not unique VRAM. Total swap about0.20GiB existed at entry; the accepted bracket adds0. Parent setup lazily initializes its real window/arena on the first request, so READY is not complete startup-to-answer timing.
- **Excluded attempts:** First two smoke admissions held with no child; automatic26.58GB arena stopped at pressure2 before an answer. Comparison v1 has two full launches then an empty held third arm; excluded as a bracket. Repeated1.38GiB pack SHA scans promoted clean cache; identity-bound cached verification now rescans changed files, with regression coverage, and a new whole bracket replaces it. BF16-HC20GB completed one response then stopped on11.0625MiB new swap; entire attempt excluded from speed. First editing supplement admission held, no child, replaced by a fresh complete supplement. Full original source and every failed receipt remain local.
- **Interactive trial:** Separate localhost8097 parent web/OpenAI app and owned-child guard.20GB app returns an exact file edit, then the pressure guard stops it during idle without new swap; not an accepted stable app profile. Interactive cache reduced to12GB independently from the20GB comparison. Private launcher refuses a second engine, requires34GiB/normal pressure, stops on new swap/pressure warning, and blocks automatic restart within a failed session. It may release only its own verified clean expert-copy cache before admission; current model files and other apps are untouched. API/idle/shutdown evidence is recorded in the report.
- **Validation/decision:**222 maintained load-free checks pass. Shader/executable/model/pack identities and original runner source frozen and retained. Do not transfer M5 Max128GB108–120TPS to this Mac. Preserve the parent for capacity/long-prompt work; inspect its matrix prompt path separately against the kept resident/drafting path. [Measured table, exclusions and launcher scope](research/20261013-parent-metal-trial/REPORT.md).

- **E04 final interactive proof:**12GB cache returns three exact normal-EOS API edits across two sessions, remains loaded/healthy across idle checks149.1s apart, and closes with a healthy guard receipt/new swap0/normal pressure. Final minimum available RAM19.72GiB, peak process RSS17.25GiB. A held-wait-lock test reproduces the earlier blocking signal handler and passes with nonblocking forwarding plus a bounded force-stop timer; two transport-free regression checks added. Owned processes stopped and8097 closed. The first missing-receipt shutdown attempt is preserved; no benchmark rerun was used to hide it.

### E05 — prompt chunk sweep after the native-parent comparison

- **Status:** Three complete balanced trials and one editing validation; correct and resource-safe. Larger chunks are scoped long-input candidates, not a promoted general default.256 rejected for speed. Full mixed editing confirmation preserved.
- **Material change:** E04 showed faster parent long-prompt input processing. Sweep the maintained resident/P07/sharedQ3/MTP3 engine rather than switching backends: control batch/ubatch512/512; candidates512/256,1024/1024,1536/1536. Both native target/helper sizes verified.4K/F16,greedy,768 safety cap/normal EOS,no prompt cache; no math, model, memory-guard or power-mode change.
- **Method/results:** Each independent A/B/B/A has three responses per task, first exposure separate from two replays.1024 balanced long repeat prompt throughput+6.72–6.77%, whole reply5.75–6.05% faster.1536 balanced+10.42–11.63% prompt throughput, whole reply8.53–10.03% faster (about0.42–0.47seconds saved). No validated general generation-TPS gain.256 long replies17.23–18.28% slower for only about0.14GiB RSS savings; reject.1536 average RSS cost about0.62GiB and some short/first-exposure rows fail the declared regression gate.
- **Editing validation:** Separate1536 comparison with three other full Python/JavaScript/JSON files plus English short/long inputs. Long repeat replies4.67–6.07% faster, but second candidate/closing controls slow and short-task speed confirmation is mixed. Per-launch ngram counts identical652/649drafts and1950/1929tokens, and per-request draft counts identical across slow/fast replies. Resource failure and missing lookup activation ruled out; GPU/thermal/power cause unproven. No selection of favorable arms or default promotion.
- **Validation:**216complete normal-EOS answers/16launches; all prompt/text/output-ID parity and factual/verbatim checks pass, all children stopped, normal pressure, zero new swap (about0.21GiB already present), minimum available2.83GiB/max process RSS38.78GiB.229 load-free tests pass. Original sources and every raw response preserved; postflight verifies native chunk sizes in both contexts and intact original snapshot hashes.
- **Revisit:** Instrument continuous contention plus clock/thermal state before a new full editing confirmation or long-document app promotion. Must set both logical and physical batch sizes in the app; current512 guards remain. Do not repeat256 unchanged or count prompt gains as added decode TPS. [Measured tables, drift, costs and next evidence](research/20261013-prompt-chunks/REPORT.md).

### E06 — optional long-document profile and monitored runtime investigation

- **Status:** User requested adoption after E05; added separate optional Long Documents launcher with batch/ubatch1536, preserved normal chat/editing512 settings and editing qualification guard. Same model/4K/F16/P07/sharedQ3/MTP3. Actual app API and integration validate this mode; no claim that API feature timings are benchmarks.
- **Implementation:** Real logical batch parameter, early no-silent-clamp checks, actual target/helper log verification, UI Monitor/export batch metadata, strict unchanged runtime RAM guards. Existing balanced/code-edit defaults stay512.
- **Validation:** Real optional launcher passes English facts, complete edit, SSE, long-document facts, integration and cleanup/new swap0.239load-free tests and JS syntax pass. Separate clock pass and fault/output-gap pass each complete72normal-EOS answers/four launches; all144exact text/token/prompt identities match and all guards/samplers healthy/children stopped. Original runner/tool/engine/model identities and sources frozen and retained per campaign; no pooling changed-source runs.
- **Performance:** Long repeat replies+8.33/9.04% faster in clock pass,+7.91/8.93% in fault pass. Positive scopes clear own drift gates. No confirmed general generation gain. Clock pass single JSON80.14TPS outlier remains included: aggregate JSON replay−2.68%generation and2.52%longer reply, blocking that scope. Median clock1618MHz/thermal nominal/low other CPU/new swap0 in that event; no demonstrated global clock collapse. Earlier sustained slowdown not reproduced; cause remains open.
- **Memory/read evidence:** Some larger-chunk process page-ins occur without new swap, e.g. first Python209/132 counter increments in candidate windows. These are approximate overlapping whole-request observations, not measured SSD bytes or proof of a lookup bottleneck. The fault pass keeps file generation roughly86.6–90TPS and does not reproduce the80TPS JSON outlier. SSE captures are client observations with grouped bursts, not GPU timings.
- **Failed probe:** First idle sampler treats GPU clock0 as an error, stops cleanly/no model. Independent capture confirms power-gated clock0/active0. Reader corrected to preserve unavailable frequency and continue; meaningful idle→active regression and fresh smoke pass. Failed receipt remains local.
- **Fresh research/next:** Parent unchangeded4773. MLX new2f11ab3documentation records real64GB M5 Pro results, not a matched48GiB backend upgrade. Next investigate actual helper QoS before changing it, native waits, bounded Apple prefetch, separate MLX quality/memory and low-priority parked-conversation caching. No realtime scheduling, guard lowering or default promotion. [Proof, exclusions and measured tables](research/20261013-long-documents-mode/REPORT.md); [five ordered investigations](research/20261013-long-documents-mode/NEXT.md).

### E07 — bug and polish pass after merging PR 3

- **Scope/decision:** Four agents and coordinator cross-review corrected 22 confirmed runtime, benchmark and UI findings. No model/GPU run, native build, default-setting change or TPS gain claimed. [Findings, evidence and boundaries](research/20261013-bug-polish/REPORT.md).
- **Failure paths:** Both maintained supervisors are stoppable with ownership checks; ordinary/legacy launcher cancellation reaps owned children even during publication. Native/consumer failures use structured API errors without failed-request speed claims. Final swap checks, actual token/caching counts, health/exit receipts, engine/model identity and concurrent provenance publication are enforced.
- **UI:** Safe Undo, explicit truncated-stream failure with retained text, transient attachment reattachment/export, numeric/share-setting validation, quick-link startup ownership, theme contrast and narrow-screen local table scrolling. Browser proof uses mock/synthetic fixtures only.
- **Validation:** 281 offline Python tests, 27 JavaScript tests, 12 benchmark-termination tests, one app-termination test containing six signal/stage cases, two port checks and five campaign-protocol tests pass locally. Fresh committed-export and exact-head hosted CI remain separately reported on the follow-up PR. Models/private/raw evidence/screenshots stay ignored.
- **Deferred:** D01 parked Q2 per-run engine identity and D02 malformed tuning workload lengths must be hardened before reusing those tools. Preserve previous rejected experiments and their revisit conditions; this maintenance pass does not reopen them.

### E08 — post-merge investigation, execution held

- **Status:** Research and preparation only at the user's request. No model/GPU/storage benchmark, native build or new speed result. Merged PR 4 is the source reference; ordinary inference settings are unchanged.
- **Queue correction:** E01 breadth is already qualified, E02 simple drafts are inactive under width three, E02-M map drafts are active/correct without a repeatable gain, and E06 already supplies the optional long-document profile. Do not repeat those flags or count them as untested ideas.
- **New source evidence:** Parent moved eleven commits beyond the tested `ed4773e`; `5ce9994` adds Metal launch-limit checks and a prompt-shader SDK correction. These are correctness prerequisites for the separate parent track, not an established TPS gain in the maintained engine. Current llama.cpp still blocks the same short simple-draft configuration; the inspected MTP changes do not establish a text-only upgrade.
- **Prepared order:** R0 merged functional validation/current baseline; R1 actual helper QoS and CPU/GPU-wait attribution; conditional R2 helper-only Apple QoS; R3 isolated parent-inspired prompt operation; R4 bounded Apple lazy-row prefetch; R5 targeted failure contracts and D01/D02 hardening before tool reuse. All execution remains held. Each candidate needs a materially distinct mechanism, frozen identities, fresh matched controls, independent confirmation, complete correctness, normal pressure and zero new swap.
- **Evidence:** [Source findings, feasibility, stage gates and revisit conditions](research/20261013-postmerge-investigation/REPORT.md). The companion JSON cards and raw metadata remain ignored locally. Small repeatable gains are eligible; no estimated or historical percentages are added together.

### E09 — post-merge real-model baseline and persistent MTP helper pools

- **R0 passed:** User authorized execution. All three actual app profiles pass API/integration/restart checks. Code Editing native baseline completes18 normal-EOS answers plus three whole-file API edits; first Python/JavaScript/JSON generation87.35/88.02/86.94 TPS. First prose and replay remain separate; these are not a new Balanced-chat speed claim.
- **R1 implemented:** Separate pinned `m5-waits` engine, trace/persistent-helper-pool flags both off by default, unchanged kept engine/profile settings. Diagnostics retain existing GPU waits/fusion; observed wall envelopes are excluded from speed claims.506 matrix plus16 fused-residual reference checks, 48 full-answer qualification outputs and 144untraced bracket outputs pass exact parity; adapter cancellation/reuse and all 12 accepted launch resource/exit gates pass, zero new swap.
- **Mechanism:** Control creates/frees 2,002 helper pools in12 diagnostic requests; persistence removes every disposable helper graph. First file lifecycle envelopes9.47–9.62 ms/about 0.25–0.29% of replies; first prose39.48 ms/0.72%. These are traced envelopes, not physical SSD time or promised gains. Bounded actual helper worker samples show requested class 21 Default and 33 User Interactive;21 is not Utility. Effective boosts are unmeasured and later samples are exhausted.
- **Speed decision:** First prose screen 39.554→39.667 TPS/+0.286%, full reply0.261% quicker. Independent confirmation averages +0.355% TPS/+0.319% quicker but fails twice-control-drift and every-launch direction gates. Editing is flat and some confirmation prompt scopes regress. Keep as a possible small signal/experimental artifact; no default adoption or cumulative TPS increase. A gain below 1% is eligible when validated; this one is unconfirmed. Do not rerun unchanged pool toggles for a broad win.
- **Failed/excluded receipts:** Two 34 GiB prelaunch holds/no model; symlink-path cache helpers refuse unverified files; two bundled native UI gzip builds fail through alias paths before a physical-path/UI-off rebuild; qualification v1 rejects a harness EOS-display assertion after 12 native answers. Corrected, separately frozen v2 requires full stop-token parity and the actual shell's visible-text behavior. Every failed receipt remains retained, outside accepted comparisons; no guard lowering or cleanup inside brackets.
- **Quality/next:** 356 offline tests,21 lint/type/format targets,14 strict,87.37% line/75.28% branch focused coverage; original 20 per-file floors preserved and new parser 100%/100%. R2 remains conditional after Default-worker observations; R3 needs actual prompt-operation attribution; R4 bounded Apple prefetch and R5 parked-tool contracts remain distinct work. No PR/push or hosted CI claim in this local experiment.
- **Evidence:** [Baseline, both brackets, limitations, rejected attempts and revisit conditions](research/20261014-baseline-and-helper-pool/REPORT.md). Raw responses, runners, memory/build receipts and traces remain ignored under the local feature campaign.

### E10 — N00 prompt-chunk operation inventory and GPU time (attribution only)

- **What ran:** user-authorized model run on the kept `m5-small-stack` engine and unchanged settings.
  - Inventory launches at 512 and 1,536 logged every encoded Metal dispatch with tensor shapes and fusion; their timings are discarded.
  - Timing launches in the order 512/1,536/1,536/512 recorded only command-buffer GPU timestamps, three fresh one-token requests per prompt.
  - All six launches passed the 34 GiB admission, normal-pressure, zero-new-swap and cleanup guards. One earlier attempt was held at 33.7–33.9 GiB until background apps were quit; the threshold was not lowered.
- **Findings:**
  - Every target chunk encodes the same 3,322 dispatches regardless of size.
  - Target GPU time fits about 171 ms per chunk + 1.02 ms per token + 0.21 ms per token per 1,000 earlier tokens, within ±3.3% over 13 chunk measurements of 284–1,532 tokens.
  - 1,536 chunks use 12.3–12.6% less target GPU time on long prompts.
  - The GPU sits idle for 427–463 ms per long prompt (9.5–11.5%) while the MTP helper's experts run on the CPU.
  - The server's 4-token checkpoint chunk costs 39.6–50.8 ms of GPU time per request.
  - The pinned launch-wide fusion counter double-counts MoE-reduce fusions.
- **Decision:** attribution only; no default, kernel or speed claim changes.
- **Revisit:** rerun only after an engine, model, chunk rule or helper-placement change. Next candidates are:
  - overlapping the helper's CPU experts, or moving them to the GPU for prompt batches;
  - a segment-timed diagnostic build to locate the per-chunk cost before N01;
  - a reuse check before touching the 4-token checkpoint.
- **Evidence:** [report](research/20261014-n00-prompt-ops/REPORT.md). Native logs, per-request rows and inventories stay ignored under the local feature folder.

### E11 — N00b segment-timed prompt chunks (attribution only)

- **What ran:** user-authorized model run on `m5-segments`, an isolated diagnostic clone of the kept `m5-small-stack` engine plus a segment timer. The timer is off unless `GGML_M5_LAB_SEGMENTS` is set. Settings and prompts were unchanged from E10.
  - With the timer on, each graph is encoded into one Metal command buffer per part:
    - each layer's mixer, router, routed experts and combine;
    - the output head, when the chunk samples a token.
  - Four launches alternated the timer on and off, at 512 and at 1,536.
  - All four passed the 34 GiB admission, normal-pressure, zero-new-swap and cleanup guards.
  - Two earlier attempts were held by the zero-swap guard until background helpers were quit; the guard was not changed.
  - Two attempts exposed tool faults and were fixed before the accepted run (see the report).
- **Findings:**
  - The fixed per-chunk GPU cost, 164.0 ms with the timer on (170.7 ms off), splits into:
    - routed experts: 89.4 ms;
    - router: 42.4 ms;
    - recurrent mixers: 27.9 ms;
    - attention mixers: 7.5 ms;
    - combine: about 0.
  - Per token, the recurrent mixers cost most (0.470 ms).
  - The timer's segment sums are within −1.2% to +0.4% of the timer-off chunk time for chunks of 284 tokens and more.
  - All 48 outputs (token and top-8 probabilities) matched.
- **Decision:** attribution only; no default, kernel or speed claim changes. The diagnostic engine is not a candidate.
- **Revisit:** rerun only after an engine, model or chunk-rule change. Next candidates are:
  - helper-expert overlap during prompt reading;
  - a finer split of the router segment;
  - a weight-reading check on the experts' fixed term before N01.
- **Evidence:** [report](research/20261014-n00b-segments/REPORT.md). Native logs, per-request rows, memory samples and held attempts stay ignored under the local feature folders.

### E12 — N15 helper overlap during prompt reading (diagnostic engine)

- **What ran:** user-authorized model run on `m5-overlap`, an isolated diagnostic clone of the kept `m5-small-stack` engine with two switches, both off unless set:
  - `GGML_M5_LAB_CONTEXT_QUEUE` gives each Metal context its own command queue;
  - `GGML_M5_LAB_HELPER_OVERLAP` holds the MTP helper's decode of a prompt chunk that samples no token until the target's next chunk is queued. Any other helper call or helper-state step runs the waiting chunk first.

  Settings and prompts were unchanged from E10.
  - Eight launches: at 512, overlap/serial/serial/overlap; at 1,536, serial/overlap/overlap/serial.
  - Each launch made three fresh one-token reads per prompt (top-8 probabilities), then three replies of up to 128 tokens.
  - All eight passed the 34 GiB admission, normal-pressure, zero-new-swap and cleanup guards.
  - A first smoke test found a fault, fixed before the accepted run: the server's per-pass status task ran the waiting helper chunk early, so nothing overlapped.
- **Findings:**
  - At the default 512-token chunks:
    - long prompts were read 10.6–10.8% faster (4,057–4,076 instead of 4,535–4,567 ms), short prompts 4.5–6.7% faster;
    - GPU idle per long prompt fell from 517–536 to 110–119 ms;
    - whole long-prompt replies finished 9.5–10.4% sooner.
  - Outputs (token, top-8 probabilities, reply text, length and draft counts) matched in all 96 reads and 96 replies.
  - Memory was unchanged: peak RSS 37.43–38.10 GiB against 37.77–38.15 GiB, and zero swap growth.
  - Decode steps cost the same in both modes. The first draft after a long prompt took 2.5–3.5 ms longer. At 512 this lowers the reported tok/s of the 11- and 31-token replies after long prompts by 0.9–1.4%.
  - At 1,536 the gain was 0.0–4.6% for long prompts. Higher disk reads in all four 1,536 launches made reply speed there undecided.
- **Decision:** a measured prompt-reading gain in a diagnostic engine; no default changes. Concurrent slots, cancellation mid-prompt and checkpoint restores with a waiting helper chunk were not exercised.
- **Revisit:** qualify a candidate at 512 with the standard app suite (256-token replies, editing and Long Documents profiles), plus cancel and checkpoint-restore checks after or with N06. Chunk order at 1,536 is a separate experiment.
- **Evidence:** [report](research/20261014-n15-helper-overlap/REPORT.md). Native logs, per-request rows, memory samples and smoke tests stay ignored under the local feature folders.

### E13 — N02 Apple advisory reads for lazy lookup rows (diagnostic engine)

- **What ran:** user-authorized model run on `m5-advise`, an isolated diagnostic clone of the kept `m5-small-stack` engine. It adds one switch, off unless set, in `src/llama-mmap.cpp`:
  - `GGML_M5_LAB_ADVISE=madvise` passes the pages of a chunk's lazy lookup-table rows to `madvise(MADV_WILLNEED)` before the gather, as llama.cpp PR 30405 does on Apple;
  - `GGML_M5_LAB_ADVISE=rdadvise` passes the same spans to `fcntl(F_RDADVISE)`;
  - a trace prints the pages asked for, those not in memory beforehand (`mincore`) and the advice time.

  Settings were unchanged from E12 at 512.
  - Six launches: no advice, madvise, F_RDADVISE, F_RDADVISE, madvise, no advice.
  - Each launch read five unseen 2,088-token documentation excerpts twice (first exposure, then replay, 32-token replies), then the four standard prompts twice with up to 128 tokens.
  - All six passed the 34 GiB admission, normal-pressure, zero-new-swap and cleanup guards.
  - A check run before them confirmed that both calls return with every advised page in memory.
  - A first full run was stopped by the zero-new-swap guard (512 KiB, 2.64 GiB available) in its third launch. It is held; the rerun used only excerpts that run had not been given.
- **Findings:**
  - First-exposure penalty (first read minus replay, median of 10 documents per mode): 333 ms with no advice, 189 ms with madvise (−43%), 168 ms with F_RDADVISE (−50%). The whole first read was 2.7% and 3.0% faster.
  - Per 1,000 pages not in memory: 17.5–18.1 ms without advice, 10.5–11.1 ms with madvise, 8.5–9.1 ms with F_RDADVISE, per launch.
  - Warm replays were 0.9% (madvise) and 1.3% (F_RDADVISE) slower: advice on resident pages costs 5.5–14.4 ms per 2,088-token request.
  - Reply speed was within −0.1% to +1.0%, and reply text was identical in every request.
  - Memory: peak RSS 38.84–39.14 GiB in every mode, at least 2.84 GiB available, zero swap growth.
  - Both calls are synchronous on this Mac: they read about 3.7–6.0 µs per missing page before returning.
- **Decision:** a measured first-exposure gain with a small warm cost, in a diagnostic engine; no default changes.
- **Revisit:** skip advice for pages already advised since load, or advise one chunk ahead from a helper thread; measure first exposure and warm cost again.
- **Evidence:** [report](research/20261014-n02-advise/REPORT.md). Native logs, per-request rows, memory samples, the check run and the stopped run stay ignored under the local feature folders.

### E14 — N06 MTP draft state across context checkpoint restores (diagnostic engine)

- **What ran:** user-authorized model run on `m5-mtpstate`, an isolated diagnostic clone of the kept `m5-small-stack` engine. It changes one file, `common/speculative.cpp`:
  - with each context checkpoint, the MTP draft saves its pending row and last verification rows in llama.cpp PR 30141's layout;
  - `GGML_M5_LAB_MTP_STATE=restore` applies them on a checkpoint restore, as the PR does; unset keeps the pinned behaviour, which ignores them;
  - `GGML_M5_LAB_MTP_STATE_TRACE=1` prints each save and restore, with how far the row in use is from the saved one.

  Settings were unchanged from E13.
  - Four launches: stale, restore, restore, stale.
  - Each launch held one chat conversation per standard prompt with the prompt cache on: a first reply, a regenerate, a follow-up and an edited follow-up, greedy, up to 128 tokens.
  - All four passed the 34 GiB admission, normal-pressure, zero-new-swap and cleanup guards.
- **Findings:**
  - Restores: 16 per mode, 8 on regenerates and 8 on edits; plain follow-ups reused the whole cache. All 32 read a valid saved state; the 16 in restore mode applied it.
  - The row in use at every restore was stale: a median relative difference of 1.12 from the saved row (0.93–1.46).
  - Drafts, accepted counts (1,082 of 1,604, 67.5%) and reply text were identical in both modes, request for request. Both launches of each mode matched, and every regenerate drafted exactly as its first reply.
  - Regenerate and edit prompt times were the same in both modes (49.4–55.4 and 257.7–272.2 ms, apart from one 406.6 ms edit in the first launch).
  - The saved verification rows make a checkpoint up to 19.9 MiB larger (112.6 to 132.5 MiB after a long prompt).
  - Memory: peak RSS 38.04–38.31 GiB, at least 3.11 GiB available, zero swap growth, at most 5 checkpoints held.
- **Decision:** the stale row is real but changed no measured draft or output; the fix is not adopted and no default changes.
- **Revisit:** with a llama.cpp upgrade that includes PR 30141, add its checkpoint memory to that upgrade's memory check. N07 may proceed once it measures the bytes it would remove. Sampled replies, several slots, cancellation and position-0 restores were not tried.
- **Evidence:** [report](research/20261014-n06-mtpstate/REPORT.md). Native logs, per-request rows and memory samples stay ignored under the local feature folder.

### E15 — N15 qualification as an app setting (not qualified)

- **What ran:** user-authorized model run of the helper overlap as an app setting, `overlap-reduce` on the `m5-overlap` engine: the kept `small-reduce` switches plus `GGML_M5_LAB_CONTEXT_QUEUE=1` and `GGML_M5_LAB_HELPER_OVERLAP=1`. It was compared against the kept engine and switches.
  - Three A/B/B/A brackets under the E05 prompt-chunk protocol: the default app (balanced drafting, 512), the Code Editing app (code-edit drafting, 512) and the Long Documents app (balanced, 1,536).
  - After its timed requests, every launch held chat conversations with regenerate, follow-up and edited follow-up (up to 256 tokens). It then cancelled a long streamed prompt 0.5 s after sending, resumed it with the prompt cache on, and repeated a fresh short request.
  - The rule was fixed in `qualify_ops.py` before the run. All 12 launches passed the 34 GiB admission, normal-pressure, zero-new-swap and cleanup guards.
- **Findings:**
  - Long prompts at 512: first text 9.5–12.6% sooner, whole reply 8.6–11.5% sooner. At 1,536: 4.6–7.1% and 4.4–6.6%. Short prompts: first text 3.4–12.2% sooner.
  - Every timed and chat reply and its draft counts were identical in all four launches of each app; every quality check passed.
  - Every cancel stopped mid-prompt (1,024 of 2,332 tokens at 512, 796 at 1,536). Every resume reused those tokens and wrote the fresh answer. There were 8–12 checkpoint restores per launch, every regenerate matched its first reply, and every fresh repeat matched.
  - Memory: peak RSS 37.86–38.72 GiB, at least 2.46 GiB available, zero swap growth.
  - Two rows regressed in reply tok/s, each through one slow reply in an overlap launch:
    - default long-prose replay, −4.95% against an allowed −2.06%;
    - Long Documents python-client first exposure, −2.58% against −1%.

    Slow replies (over 4% above the kept median) were as common without the overlap: 8 of 84 kept and 7 of 84 overlap replies.
  - Replies after long prompts at 512 took a median 2.3–3.3 ms longer (N15's first-draft cost), 1.5–1.9% of an 11-token reply.
  - The first scoring failed every launch, kept ones included, on a faulty cancel check that counted the server's early HTTP headers as a reply. The check now uses the stop point. The decision was recomputed from the saved launches and did not change.
- **Decision:** not qualified; the app is unchanged and N15 remains a diagnostic engine.
- **Revisit:** find and remove the first-draft cost after a long prompt, then qualify again. Before that run, fix a rule with enough replies per row that one slow reply cannot decide a row.
- **Evidence:** [report](research/20261014-n15-qualify/REPORT.md). Native logs, per-request rows, conversation text and memory samples stay ignored under the local feature folder.

### E16 — N01: llama.cpp #30373 on the expert matrices, without the model (not ported)

- **What ran:** `test-backend-ops` timing of the expert matrix operation (`MUL_MAT_ID`) alone on Metal, at the model's Q2_0 gate/up [2560, 640, 512] and down [640, 2560, 512] shapes with 10 experts per token. No model was loaded.
  - Four setups, each a scratch copy of the pinned source: pristine, pristine plus #30373, the kept patch with `small-reduce`, and the kept patch with `small-reduce` plus P11's compact tiles.
  - Random routes at 32, 512 and 1,536 tokens, and a sweep at 512 tokens that puts the same work on 10 to 512 experts.
  - Two rounds of pristine, #30373, kept, compact, compact, kept, #30373, pristine. Every setup matched the CPU backend on all 10 cases.
- **Findings:**
  - #30373 against pristine, summed over 48 layers: +2.6% at 32 tokens, +1.4% at 512 (294.9 → 298.9 ms), −1.7% at 1,536 (562.2 → 552.8 ms). Down got faster (−4.5% at 512, −9.7% at 1,536) and gate/up slower (+4.7%, +3.1%).
  - The kept engine's compact tiles took 283.8 ms at 512, 4.0% less than kept without them and 5.1% less than #30373. They gave no full-model gain in the P11 screen.
  - Moving the same work from 10 to 512 experts adds 137.1 ms per 512-token chunk on the pristine source (134.6 → 271.7 ms): 1.90–2.04 µs per expert per matrix, about the same in all four setups.
- **Decision:** not ported. At the default chunk size it is slower on our shapes, and it needs a three-file merge with the kept patch.
- **Revisit:** if upstream changes its gate/up path, or if the model ever needs its duplicate-id fix.
- **Evidence:** [report](research/20261014-n01-sizing/REPORT.md). Raw runs and logs stay ignored under the local feature folder.
