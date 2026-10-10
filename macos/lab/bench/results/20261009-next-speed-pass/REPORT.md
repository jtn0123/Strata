# Next speed pass: three experiments

All three mechanisms were implemented and tested separately. None met its predeclared acceptance gate. Existing app launchers and the practical control remain unchanged.

## S06: token-piece cache

Actual small model: Qwen3.5-4B Q4_K_M. One original m5-copy engine, independent code/prose ABBA,256 output tokens, excluded warmup and three repetitions, empty token cache per request. This changes service text conversion rather than GPU inference.

| English task | Control reply | Cached reply | Reply quicker | Control drift | Native conversion calls |
| --- | ---: | ---: | ---: | ---: | ---: |
| code | 3.364070s | 3.365691s | -0.048% | -0.228% | 256 → 137 |
| prose | 3.373194s | 3.367038s | +0.182% | +0.525% | 256 → 175 |

32 real responses and UTF-8 prefix qualification match exactly; load-free parser tests include thinking, EOS, cancellation and reuse. Serialized token IDs drop32896→137(code)/175(prose). These reductions are HTTP text work, not model SSD speed or a native-TPS gain. Neither task passes1% reply improvement above twice drift. Optional flag stays false.

Pinned /detokenize concatenates raw common_token_to_piece output with lstrip0, then JSON handles invalid UTF-8. It bypasses llama_detokenize whitespace cleanup. U+FFFD fallback is conservative. Scope/provenance belongs to the verified owned server; future endpoint/model-lifetime changes require renewed validation.

[Small-model raw result](streaming/20261009T212918Z-small/comparison.json), [report](streaming/20261009T212918Z-small/REPORT.md), [archived timing sources](streaming/source/pins.json).

## Q02: remove ranking when all attention pools are selected

This differs from Q01: it retains actual indexer scores, liveness, mask scatter, cache writes, n_sel and attention dispatch. Only top-k ordering and two gathers are removed for fully selected pools on the pinned M5Pro/F16 path. Legacy path remains above512 pools.

102 component cases per engine pass exact mask/score/input comparisons, stock permutation and score/member pairing, sparse padding, exceptional scores, restricted masks and full Metal placement. Realizable component savings include4.898% at64pools/one token,10.145% at128/one token and22.958% at512/512. Small-pool512-token shapes are synthetic and did not qualify the model launch.

Original m5-copy/conv-direct versus isolated m5-qsa/qsa-all-pools, Qwen3.8-Flash-Next GSQ-RCO Q2_0, shared packed Q3 helper, mixed placement/eight workers, depth3/confidence0, TensorAPIon, F16/4K/batch512. Fresh ABBA,256 outputs, excluded warmup plus three repetitions.

| Workload/input | Control TPS | Candidate TPS | TPS change | Reply quicker | First token quicker | TPS drift | Reply drift |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| code/48 | 59.387734 | 59.401608 | +0.023% | +0.028% | -0.957% | -0.613% | -0.522% |
| prose/53 | 39.871876 | 39.758446 | -0.284% | -0.379% | -1.180% | -0.070% | -0.025% |
| synthetic/512 | 48.415807 | 48.406028 | -0.020% | -0.164% | -1.052% | -0.191% | -0.527% |
| synthetic/2048 | 49.856941 | 49.770406 | -0.174% | +0.067% | +0.522% | +0.072% | +0.116% |
| cached-ledger/512 | 70.062796 | 70.318937 | +0.366% | +0.031% | -0.361% | +0.134% | +0.290% |
| cached-ledger/2048 | 63.723144 | 63.973477 | +0.393% | -1.527% | -4.171% | +0.651% | +0.115% |

Strict model adoption is false: neither English task passes1% TPS and whole-reply gains above its own absolute control drift.104 answer/cache checks and96 output comparisons including warmups match; four accepted launches have zero new swap. First-token/cache gains are not qualified. Runtime input marker is present only in candidate launches; it proves eligible input preparation, not shader frequency or cache-state bit identity.2K continuations and the component576-pool fallback are tested separately.

[Canonical model report](../20261009T215006Z-m5-qsa-all-pools/REPORT.md), [model raw](../20261009T215006Z-m5-qsa-all-pools/comparison.json), [component raw](qsa/comparison.json), [model closure archived before timing](qsa-model-source/pins.json).

## P10: adjacent expert route-map reuse

Isolated m5-route-map over original m5-copy. Same activation/ID objects, Q2_0 gate/up[2560,640,512],T32–512, neighboring operations in one encoder partition and following SwiGLU consuming both outputs. Borrow only routing scratch; current scaling workspace remains separate. Physical allocation overlap guard and post-barrier tracking retain scratch until its consumer finishes. No shader math or scheduler reordering changed.

66 fixtures × three A/B/A rounds per engine (396 records total) match complete projection/activation/down/residual bytes. Every eligible record has the full encoding count; all fallbacks zero. Includes40/2048-byte ID strides, T31/513 boundaries, changed IDs/input, mixed precision and terminal-only lifetime checks. Performance uses two dependent complete blocks, terminal output only, ordinary optimizer/allocator, no callbacks, synchronized completion,500ms warmup and7×100ms blocks per fresh ABBA launch. Routes are synthetic, not captured model distributions.

| Tokens/route | Original two blocks | Reuse two blocks | Time quicker | Control drift |
| --- | ---: | ---: | ---: | ---: |
| 32/uniform | 6.530668ms | 6.515884ms | +0.226% | 0.071% |
| 32/shared | 0.776676ms | 0.774774ms | +0.245% | 1.251% |
| 32/mixed | 3.704607ms | 3.693848ms | +0.290% | 0.141% |
| 33/uniform | 6.733890ms | 6.736043ms | -0.032% | 0.090% |
| 33/shared | 0.987514ms | 0.979469ms | +0.815% | 0.749% |
| 33/mixed | 3.879228ms | 3.868767ms | +0.270% | 0.247% |
| 64/uniform | 10.255746ms | 10.310104ms | -0.530% | 0.032% |
| 64/shared | 1.150628ms | 1.132288ms | +1.594% | 0.497% |
| 64/mixed | 6.871442ms | 6.900279ms | -0.420% | 0.141% |
| 127/uniform | 10.577552ms | 10.700648ms | -1.164% | 0.081% |
| 127/shared | 1.996202ms | 1.983003ms | +0.661% | 0.463% |
| 127/mixed | 11.036952ms | 11.125402ms | -0.801% | 0.137% |
| 508/uniform | 12.978406ms | 12.877820ms | +0.775% | 0.155% |
| 508/shared | 7.343865ms | 7.291714ms | +0.710% | 0.043% |
| 508/mixed | 14.925437ms | 14.870336ms | +0.369% | 0.154% |
| 512/uniform | 13.011294ms | 12.904924ms | +0.818% | 0.268% |
| 512/shared | 7.379226ms | 7.313717ms | +0.888% | 0.271% |
| 512/mixed | 14.941417ms | 14.902315ms | +0.262% | 0.002% |

No model trial: T508/T512 uniform savings0.775%/0.818% are below the predeclared3% complete-block gate. Some shorter uniform/mixed cases regress. These are component times, not model TPS. Counter counts encodings, paired with successful synchronized graph completion. Forced overlapping allocations and encoder-partition boundary fixtures remain untested; those guards have static review only. All six accepted component launches have zero new swap; peak process RSS1.715GiB (not total unique Metal memory).

[Raw comparison](route-map/comparison.json), [plan captured before GPU execution](route-map/plan.json), [archived source](route-map/source/scripts/benchmark_m5_route_map.py).

## Excluded attempts and provenance

- X19: initial original-control QSA injected-score fixture wrongly made future pools live; it failed before scatter. Corrected injected masks and RAII cleanup; no candidate/model/TPS result accepted. [Raw failure](qsa/20261009T213413402049Z-check-control/result.json), [diagnosis/source](qsa/20261009T213413402049Z-check-control/exclusion.json).
- X20: original-model cold control stopped on589824bytes new swap before responses. Fresh retry kept the zero-new-swap guard. [Failed load](../20261009T214505Z-m5-qsa-all-pools-1-conv-direct/result.json), [exclusion](../20261009T214505Z-m5-qsa-all-pools-1-conv-direct/exclusion.json).
- X21: first candidate guard used Metal instead of the actual MTL registration name; no input marker appeared. Interrupted and excluded that bracket, archived source/build, fixed only the name and ran a fresh full bracket. [Rejected bracket](../20261009T214536Z-m5-qsa-all-pools/comparison.json), [diagnosis](../20261009T214536Z-m5-qsa-all-pools/exclusion.json), [old source](qsa-inactive-source/manifest.json).

Earlier valid component prototypes remain in component-initial/component-hardened; final102-case evidence is authoritative. Later engine registration added profiles; original component dependencies are preserved in before/, with unchanged native control receipts. No historical timings are pooled.

140 maintained offline tests pass. Both new native engine receipts verify; all22 original engine receipts remain unchanged. New route backend also passes572 math+16 residual cases. No model servers remain, no unrelated applications were stopped, and no commits/pushes/publication were performed.

[Final verification](final-verification.json), [raw checksums and parity](raw-evidence-verification.json), [independent reviews](INDEPENDENT-REVIEWS.md), [decision ledger](../../EXPERIMENT-LEDGER.md).

## Next queued: compact expert/token tile launches

R03 targets empty GPU groups inside the unchanged quantized matrix operation. AtT512 the original grid launches8192 expert/token pairs per output-channel tile; this synthetic uniform fixture needs512. Any valid512-expert/top10 route has at most656 pairs (T508:654). These are launch-count bounds, not measured runtime savings, captured routes, or decode-TPS estimates.

Implement independently over original m5-copy; keep P10 disabled. A GPU worklist reads original route counts, emits each expert/tile once, and dispatches a proven static upper bound with an actual-count guard. Preserve all math, own scaling workspaces, allocator accounting and barriers. Add capacity/skew/boundary fixtures; existing P10 adjacency negatives are not the new mechanism's shape negatives.

Astra recommends a predeclared >10% complete two-block gain above twice drift before a model trial (over1.30ms at the measuredT512 uniform baseline), including worklist construction and barriers. Test normal prompt exposure and first-token/whole-reply performance before making a model claim. Single-token generation is outside this initial prompt experiment.

