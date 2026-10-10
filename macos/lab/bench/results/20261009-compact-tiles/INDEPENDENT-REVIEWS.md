# Independent reviews of compact expert/token scheduling

## Native author: Astra

Implemented V1 in an isolated pinned engine with unchanged original MM arithmetic and original route-map/amax ownership. Implemented V2 as an isolated coordinate-only scheduling variant. Native author launched no build, GPU operation or model.

## Probe author: Sol 6.1

Built the two-dependent-block fixture, independent top10/capacity route validation, exact output oracle, per-MM activation/fallback checks, changing A/B/A data and sustained component ABBA. Root owns all real GPU/model execution. Corrected X22's unsupported Q2_0 CONT fixture before accepted rerun; preserved the rejected bundle.

## Independent Astra review: V1 raw

All six accepted receipts, logs, JSONL and hashes agree. 273 correctness records per engine and 18 timing cases per ABBA launch. Full finite output digests match the original engine, A/B/A restoration and input/weight preservation pass, all expected eligible-encoding counts pass, and capacity fixtures reach654/656. Recomputed all18 aggregate rows exactly. All launches add zero swap; peak process RSS1.686554GiB is not unique total Metal memory.

Uniform T50813.0106015625→12.4021365556ms (4.676686% quicker), drift0.228479%; T51213.0285988750→12.5601250000ms (3.595735%), drift0.110273%. Both gains are real above twice bracket drift, but fail the preregistered strictly-greater-than10% model-trial threshold. No model-TPS gain established.

## Independent Astra review: V2 before GPU

Only two files differ from V1: dispatch in ggml-metal-ops.cpp and compact remap/overflow indexing in mul_mm.metal. Grid(channel_tiles,capacity,1), worklist index/guard y, preserved channel x, and remap restore the original logical(token_tile,channel_tile,expert). Overflow indexing uniquely covers output under the new grid. Patch/config/source match8b817ede2aa0625a38aab9904f772c9ab3e6f0bfa91a45dcd8734a98079888df. Separate columns runtime/results/model archive, exact profile mapping, original control and identical gates are correct; no pre-GPU blocker.

V1 native/probe/runner/tests/manifest/patch/results remain untouched. The historical V1 source archive retains the earlier engines.py and metal_environment.py; their current hashes change only to register the isolated V2 engine/profile after V1 timing. This is recorded explicitly, not represented as current V1 dependency equality.

## Evidence boundaries

Routes are synthetic. The private counter counts eligible encodings, not GPU shader frequency. Physical cache locality and accelerator occupancy are hypotheses, not measured hardware attribution. Shape/K fallback fixtures jointly exercise strided weight fallback. Forced corrupt header and cross-partition/overlap guards remain source-reviewed, not injected at runtime. No external review posting or PR was performed.

## Independent Astra review: V2 raw

Verified all six receipts against logs, JSONL, source archives, native/probe binaries and memory samples; all18 aggregate rows reproduce exactly.273correctness records per engine and exact checked F32 digests match. Candidate encoded counts:1284correctness;39516/39696timing;controls0. All six launches add zero swap; peak process RSS1.686401GiB. All15archived source hashes match, original control and frozenV1 intact.

UniformT50813.000143188→13.059382813ms(-0.455684%quicker),drift0.204317%;T51213.036513000→13.326677063ms(-2.225780%),drift0.336039%. Model-trial gate correctly fails. Shared+5.017433%/+2.816913%;mixed+2.213451%/+0.695061% do not substitute for the required cases. No model TPS or shader-frequency gain established; no corrections or execution by reviewer.
