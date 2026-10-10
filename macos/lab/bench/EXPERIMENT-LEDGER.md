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

## October 10 next-test preparation — no runs

[Prepared sequence](results/20261010-next-tests/README.md) adds U10-03 input tokenization caching and U10-02 sixteen-row prompt dispatch as disabled candidates. U10-03 uses exact full rendered input within one tokenizer instance; it does not reopen S06 output-piece caching or persisted conversation state. U10-02 changes tile width while retaining the original 16-row arithmetic product; it does not rerun unchanged P11/P12 compact worklists. Both have new preregistered protocols, bounded resources, exact-output/activation gates, empty metrics and no automatic reruns. Their performance and real-model/GPU correctness remain untested.

U10-01 MLX has pinned source and isolated resolved dependencies, but no model-ready supervisor or physical 48 GiB/F32 measurement. R08 remains a design pending exposed helper planning cost. The original P07 keeper and all prior results are retained. Preparation is not a speed gain or default promotion.

## Executed next tests — October 10

[Complete results](results/20261010-next-tests-v2/REPORT.md). U10-03 passed 96 exact Service answers but lacks a shared first-content/reply benefit; parked and disabled. U10-02 passed 819 exact GPU fixtures but all 18 ABBA component cases are slower (5.61–41.13% extra time); rejected, no full-model trial. U10-01 passes device/import, F32 full-model base-state loading and a bounded 6 GB paged English reply (15 decoded tokens at 12.889 TPS, first token5.218s, peak13.575GiB arrays); feasible for follow-up, no matched/native parity or keeper claim. Every model/GPU launch has zero new swap. Current P07 defaults and its independent 60.084/40.375 TPS code/prose cohort remain unchanged.

The vocabulary helper’s preparation compile failure/preflight rejection and both memory-service signal attempts are retained in the report. Revisit cache/tile work only after material implementation or workload-exposure changes; next useful model work is a new warmed MLX cache-budget comparison plus state/output qualification.

## U10-01 warmed MLX cache comparison — October 10

[Complete report](results/20261010-mlx-cache-v1/REPORT.md), [immutable preregistration](results/20261010-mlx-cache-v1/frozen.json), [raw comparison](results/20261010-mlx-cache-v1/comparison.json), [post-run verification](results/20261010-mlx-cache-v1/post-run-verification.json).

- **Scope:** full pinned Flash-Next Q2_0, F32 activations, paged MLX, no helper/lookup/guess rows, English code/prose only. Fresh 6/12/12/6 decimal GB cache processes; two fixed excluded warmups then three measured repeats per workload, 128 output cap. Conversation resets before every answer; expert cache stays warm within each process. Timings exclude tokenization/detokenization/API work.
- **Result:** code 12.9696 → 14.5361 TPS (+12.0782%), prose 13.0559 → 15.7287 (+20.4717%). First token 1.5245 → 1.1918 s / 1.9812 → 1.5189 s; capped reply 11.3157 → 9.9363 s / 11.7125 → 9.5946 s. Both 12 GB launch medians beat both 6 GB controls. TPS gains exceed twice own control drift (1.4771% code / 0.1653% prose). All latency/generation safety gates pass; no fixed minimum gain required.
- **Resources/exactness:** 32 full token/finish/decoded-position/pending-token checks, 24 measured answers, all four launches healthy and zero new swap; minimum host available 13.3396 GiB, peak MLX arrays 19.3372 GiB for 12 GB. The existing 0.493 GiB swap remains unchanged. 184 offline tests, 165 archived source/config/test files and 5,028 dependency artifacts verify; saved summary recomputes exactly. Every answer ends at the length cap; complete-answer quality is not established. Position/pending checks are not full tensor-state equality or native parity.
- **Exposure:** logical decode expert reads fall 50.06% code / 60.84% prose; cache hit rates 80.03 → 90.03% / 82.29 → 93.07%. These are pager requests, not SSD hardware bandwidth. OS file cache was uncontrolled; no cache purge or service change occurred mid-bracket.
- **Decision/revisit:** qualifies for follow-up within MLX; no default promotion and no TPS/percentage addition to P07. One complete bracket is not an independent confirmation campaign. Do not rerun unchanged. Next native/MLX compatibility and a separately preregistered 16 GB feasibility/cache study are designs with no runner or new model launch: [requirements](results/20261010-mlx-cache-v1/NEXT-PLAN.json). Current P07 retains its independent 60.0842/40.3755 TPS code/prose cohort.

### Resource preparation retained with this campaign

Small-model cache reclamation removes 2.553 GiB of visible residency but gains only 0.462 GiB of host available RAM. Idle build-binary cache reclamation has no measured gain; idle object inspection finds just 5.797 MiB of residency and is not followed by a purge. Preserve [small-model receipt](results/20261009-small-gains/memory-investigation/small-model-cache-trial-20261010T133040486778Z/result.json), [idle-build receipt](results/20261009-small-gains/memory-investigation/idle-build-cache-trial-20261010T133248164957Z/result.json) and [inspection](results/20261010-next-tests-v2/memory-cleanup/ram-audit-20261010T133510405303Z/REPORT.md); do not repeat unchanged ineffective cleanup.

After explicit authorization, WiFiman's GUI and its verified WebKit children close; the dormant root daemon remains installed/running, and no service is disabled. Its WireGuard interface list was empty, and the network route remains `en0`. A task-started idle computer-use UI helper is also closed after exact process-identity verification; T3/Codex remain running. [Detailed closure/cleanup receipt](results/20261010-next-tests-v2/memory-cleanup/wifiman-close-20261010T134317139114Z/REPORT.md). The last cleanup snapshot meets 34 GiB but its whole 60-second interval does not; no native admission qualification is claimed from it. All cleanup was outside the model comparison.

## Native/MLX greedy-output preparation and RAM recovery — October 10

- **Implemented:** first correctness screen for four fresh English code/prose 128-token responses, using prior MLX exact inputs/output IDs, native `m5-small-stack`/`small-reduce`, F32 KV/512 context/32-token batches, temperature-only greedy sampling and no prediction helper. Ordinary F16 KV/4K/MTP settings remain unchanged. This screen alone cannot qualify full tensor state, numerical bounds, complete-answer quality, conversation continuation, sampled/API behavior or speed.
- **Qualification:** 188 offline tests pass for original v1, 190 after adding the guarded one-fresh-attempt selector; each has 168 immutable archived source/config/test files and exact runtime/model/reference pins. Both copied gate receipts/logs are retained. The v2 selector refuses a prior child, memory-monitor or answer attempt and pins the unchanged original exclusion.
- **Original admission rejection:** [v1 report](results/20261010-native-mlx-greedy-v1/REPORT.md), [original result](results/20261010-native-mlx-greedy-v1/result.json), [exclusion](results/20261010-native-mlx-greedy-v1/exclusion.json). Existing 34 GiB native preflight refused before any model process/request; post-refusal snapshot 33.976 GiB. No output correctness, model-fit or timing result exists.
- **One fresh resource-only attempt:** [v2 report](results/20261010-native-mlx-greedy-v2/REPORT.md), [original result](results/20261010-native-mlx-greedy-v2/result.json), [exclusion](results/20261010-native-mlx-greedy-v2/exclusion.json). After additional user-authorized idle text-analysis cleanup, preflight again refuses before any child/request; post-refusal snapshot 33.824 GiB. No guard changed, outputs pooled or further automatic attempt queued. Future actual-supervisor headroom must have more margin for background variation; do not repeat either immutable campaign unchanged.
- **RAM work:** [Complete report](results/20261010-mlx-cache-v1/memory-preparation/REPORT.md). Only 0.242 GiB model residency existed, so release gives a tiny gain. Cache/media stop step gains 0.241 GiB of host available RAM; text-analysis stop gains 0.083 GiB in a separate interval. Both global 60-second settles remain above 34 GiB, with normal pressure and zero new swap; those intervals do not guarantee later supervisor admission. T3/Codex remain running; no service disabled, forced kill or model/build data change. Do not add RSS or these deltas as uniquely recovered physical RAM.
- **No-op diagnostic parked:** native artifact cache inspection finds only 23.11 MiB unique residency; no further purge. Owned supervisor RSS is 37.66 MiB after all provenance checks, GC collects zero and allocator relief reports zero bytes returned. No memory hook added. Preserve [diagnostic](results/20261010-mlx-cache-v1/memory-preparation/setup-memory-diagnostic.json); it does not establish per-process causality for the larger host dips. Revisit only with materially changed observed allocations.

## R08-OBSERVE-v1 — Native diagnostic engine and baseline

- **Status:** implemented, isolated and disabled by default. Retains P07 arithmetic/settings and adds calibrated CPU setup stages/reuse reasons, request/role GPU-buffer labels, helper catch-up/draft/acceptance counters, prompt-checkpoint creation and every allocation reservation. No new waits, tensor callbacks, precision changes, optimization or ordinary-launcher change. The original R08 design entry remains historical; helper graph reuse itself is not implemented.
- **Small-model baseline:** Qwen3.5-4B Q4_K_M, helper off, F16 KV/4K/batch512, temperature0.6/seed1234, 128-token cap, fresh control/observer-off/observer-on/control, one warmup and three measured English answers per workload per launch. Code **77.8864 TPS**, first token **79.463 ms**, reply **1.71018 s**; prose **77.8183 TPS**, first token **80.211 ms**, reply **1.71243 s**. All 32 capped answers match inputs/output IDs/text/finish/helper counts; 24 are measured. This is a different model/topology from P07's historical 60.0842/40.3755 TPS full-model cohort.
- **Observer cost:** enabled monitoring costs **2.3511% code / 2.0986% prose TPS**. Disabled observer build differs -0.1520%/-0.0886%, within 0.3594%/0.2364% control drift. Use enabled monitoring only for diagnosis; keep it off when measuring candidate gains. Small-model generation graph planning is 1.086/1.058 ms per answer, about 0.065%/0.063% of its phase; do not extrapolate this to the full helper.
- **Validation:** 197 maintained offline tests, pinned observer source/build patch, four physical small-model launches, healthy monitors, normal pressure, zero new swap and minimum30.132GiB available. CPU/Mach calibration spread34.791microseconds, widest bracket1microsecond. No new synthetic GPU math suite or full-model helper/long/cached/state qualification. All outputs are length capped; complete-answer quality is not established.
- **Resource work:** freshly used small-model cache released once outside comparison, model identity unchanged; +2.538GiB available over60seconds, zero new swap. Visible residency2.553GiB→0 is not unique physical RAM. No unrelated process stopped. Load-free historical full-model audit preserves19 reservations and unknown physical overlap; no RAM admission or fit claim changed.
- **Full-model diagnostic:** frozen P07 short-English/256-output protocol; first preflight refused at **33.462GiB available <34GiB**, before model/GPU child or request. No helper timing or performance samples. Campaign is immutable and excluded; no automatic retry or partial resume. A future new ID requires stable actual-supervisor headroom with margin and the same resource gates.
- **Next:** measure exposed full-helper planning cost before implementing R08 reuse. If negligible, prioritize R09 exact-format prompt kernels after arithmetic/precision proof. Do not revisit already-flat small-model planning without changed workload exposure.
- **Evidence:** [Monitoring overview](M5-MONITORING.md), [small per-area baseline](results/20261010-observe-small-v1/MONITORING.md), [raw small campaign](results/20261010-observe-small-v1/result.json), [held full campaign](results/20261010-observe-flash-v1/REPORT.md), [allocation audit](results/20261010-observe-budget-v1/REPORT.md), [Astra queue](research/20261010-astra-next-priorities/ASTRA.md).
- **Load-free postcheck:** an initial equality assertion compared saved JSON string keys with in-memory integer Counter keys. The [rejection](results/20261010-observe-small-v1/postcheck-initial-rejection.json) and [exact diagnosis/correction](results/20261010-observe-small-v1/postcheck-correction.json) are retained. JSON-normalized recomputation matches all raw diagnostics exactly; no model rerun, raw mutation or timing change. [Final verification](results/20261010-observe-small-v1/post-run-verification.json) passes 29 native receipts, both frozen closures, all32 outputs and the unchanged ordinary launcher; no model server remains.
