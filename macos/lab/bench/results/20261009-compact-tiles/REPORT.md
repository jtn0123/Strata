# Compact expert/token scheduling: V1 and V2

Both isolated variants are built and fully screened. V1 has a real, modest long-prompt component gain; V2 loses time on the two required uniform-route cases. Neither clears the preregistered model-trial gate. No full model was loaded in this pass, no model TPS or first-token gain is established, and defaults remain unchanged.

Original control: m5-copy / conv-direct, pinned native d81235049384534c167caea52b85a694f6103d14. Each variant has its own fresh control/candidate/candidate/control bracket; controls from different brackets are not pooled. Synthetic top10 routing and deterministic Q2_0 weights exercise the actual gate/up/down geometry in two dependent complete prompt blocks.

## Decision and measured time

The gate, fixed before GPU execution, requires strictly more than 10% complete two-block time reduction on BOTH uniform T508/T512 cases, above twice each own absolute control drift, plus exact outputs and zero new swap. Timing includes original map0, compact worklist construction, barriers, matrix work, downstream operations and synchronization. These are elapsed component milliseconds, not model tokens per second.

| Variant | Tokens/route | Original two blocks | Candidate two blocks | Time reduction | Control drift |
| --- | --- | ---: | ---: | ---: | ---: |
| P11 / V1 compact tiles | 32/uniform | 6.530581 ms | 6.639264 ms | -1.664223% | 0.076272% |
| P11 / V1 compact tiles | 32/shared | 0.783754 ms | 0.766174 ms | +2.243061% | 0.628787% |
| P11 / V1 compact tiles | 32/mixed | 3.712726 ms | 3.757603 ms | -1.208723% | 0.066358% |
| P11 / V1 compact tiles | 33/uniform | 6.758211 ms | 6.762061 ms | -0.056967% | 0.300088% |
| P11 / V1 compact tiles | 33/shared | 0.984460 ms | 0.959498 ms | +2.535594% | 0.189781% |
| P11 / V1 compact tiles | 33/mixed | 3.884116 ms | 3.898719 ms | -0.375956% | 0.178454% |
| P11 / V1 compact tiles | 64/uniform | 10.259550 ms | 10.237483 ms | +0.215084% | 0.013727% |
| P11 / V1 compact tiles | 64/shared | 1.161505 ms | 1.106633 ms | +4.724189% | 0.366109% |
| P11 / V1 compact tiles | 64/mixed | 6.882304 ms | 6.903611 ms | -0.309591% | 0.016024% |
| P11 / V1 compact tiles | 127/uniform | 10.587054 ms | 10.524510 ms | +0.590756% | 0.020856% |
| P11 / V1 compact tiles | 127/shared | 1.998638 ms | 1.873143 ms | +6.279041% | 0.094964% |
| P11 / V1 compact tiles | 127/mixed | 11.041558 ms | 10.851483 ms | +1.721451% | 0.082299% |
| P11 / V1 compact tiles | 508/uniform | 13.010602 ms | 12.402137 ms | +4.676686% | 0.228479% |
| P11 / V1 compact tiles | 508/shared | 7.357305 ms | 6.627038 ms | +9.925744% | 0.179161% |
| P11 / V1 compact tiles | 508/mixed | 14.949974 ms | 14.206440 ms | +4.973479% | 0.209599% |
| P11 / V1 compact tiles | 512/uniform | 13.028599 ms | 12.560125 ms | +3.595735% | 0.110273% |
| P11 / V1 compact tiles | 512/shared | 7.381879 ms | 6.799204 ms | +7.893319% | 0.223973% |
| P11 / V1 compact tiles | 512/mixed | 14.955318 ms | 14.332273 ms | +4.166039% | 0.126338% |
| P12 / V2 channel-first tiles | 32/uniform | 6.529145 ms | 6.652499 ms | -1.889286% | 0.007777% |
| P12 / V2 channel-first tiles | 32/shared | 0.781827 ms | 0.782072 ms | -0.031322% | 1.017249% |
| P12 / V2 channel-first tiles | 32/mixed | 3.709212 ms | 3.854602 ms | -3.919689% | 0.124018% |
| P12 / V2 channel-first tiles | 33/uniform | 6.751260 ms | 6.829406 ms | -1.157500% | 0.067989% |
| P12 / V2 channel-first tiles | 33/shared | 0.983921 ms | 0.992170 ms | -0.838360% | 0.248540% |
| P12 / V2 channel-first tiles | 33/mixed | 3.878456 ms | 4.011578 ms | -3.432356% | 0.069269% |
| P12 / V2 channel-first tiles | 64/uniform | 10.259260 ms | 10.343127 ms | -0.817473% | 0.102928% |
| P12 / V2 channel-first tiles | 64/shared | 1.150339 ms | 1.169642 ms | -1.677961% | 0.229901% |
| P12 / V2 channel-first tiles | 64/mixed | 6.878733 ms | 6.992021 ms | -1.646923% | 0.095347% |
| P12 / V2 channel-first tiles | 127/uniform | 10.598598 ms | 10.643779 ms | -0.426295% | 0.068468% |
| P12 / V2 channel-first tiles | 127/shared | 2.000906 ms | 2.050350 ms | -2.471106% | 0.306557% |
| P12 / V2 channel-first tiles | 127/mixed | 11.051165 ms | 11.011544 ms | +0.358521% | 0.167279% |
| P12 / V2 channel-first tiles | 508/uniform | 13.000143 ms | 13.059383 ms | -0.455684% | 0.204317% |
| P12 / V2 channel-first tiles | 508/shared | 7.353920 ms | 6.984942 ms | +5.017433% | 0.098459% |
| P12 / V2 channel-first tiles | 508/mixed | 14.927435 ms | 14.597023 ms | +2.213451% | 0.251353% |
| P12 / V2 channel-first tiles | 512/uniform | 13.036513 ms | 13.326677 ms | -2.225780% | 0.336039% |
| P12 / V2 channel-first tiles | 512/shared | 7.386452 ms | 7.178382 ms | +2.816913% | 0.148248% |
| P12 / V2 channel-first tiles | 512/mixed | 14.940971 ms | 14.837122 ms | +0.695061% | 0.093554% |

V1: uniform T508/T512 4.676686%/3.595735% quicker, well above 0.228479%/0.110273% bracket drift but below 10%. Shared-route savings 9.925744%/7.893319% and mixed 4.973479%/4.166039% do not replace the preregistered uniform gate. At T32 uniform/mixed it loses 1.664%/1.209%, so this is not a universal prompt improvement.

V2: only the compact grid order changes. Uniform T508/T512 are 0.455684%/2.225780% slower than their own originals; both losses exceed twice own drift. Shared-route savings 5.017433%/2.816913% and mixed 2.213451%/0.695061% do not qualify it. No physical cache-locality explanation was measured; Metal scheduling order is not guaranteed.

## What was implemented

V1 builds a GPU worklist of nonempty expert/token 32 tiles after the unchanged original route map. It dispatches the static valid-top10 bound instead of all 8192 logical expert/token groups per channel at T512. Maximum capacity is 654 at T508 and 656 at T512; T512 appended list/header is 5,256 bytes. This reduces scheduled groups, not arithmetic for live tiles. Existing original MM body and precision remain identical.

Eligibility is private opt-in on the actual M5Pro device: Q2_0 gate/up [2560,640,512] and down [640,2560,512], contiguous F32 activations/output, I32 selected IDs [10,T], T32..512 and DEFAULT/F32 source precision with original MM eligibility. Allocation spans/stride/alignment guards fall back. Each operation keeps its own original scaling scratch; list allocation is appended, allocator tracked, and re-added after its internal barriers. No P10 route-map borrowing, graph reorder, new weights, precision change, helper width change or default launcher change.

V2 uses grid(channel_tiles,capacity,1), indexes worklist with y, and restores the original logical(token_tile,channel_tile,expert) before the unchanged arithmetic. Its overflow filler indexing matches that grid. It changes only dispatch/remap indexing in two native files relative to V1. This was an independent locality hypothesis, not another combined optimization.

## Correctness, resources and independent review

- 273 correctness records per engine per variant: 91 fixtures × 3 A/B/A phases, two dependent blocks, full finite terminal F32 byte digests and two diagnostic projection fixtures. Original and candidate outputs match exactly. Inputs, route IDs, coefficients and all three weight payloads are preserved; changed input/ID phases restore the original output.
- Six individual MM predicates and eligible encoding counts checked, including T1/31/32/33/64/127/508/512/513, 40/2048-byte ID strides, valid skew/permuted/654 and 656-capacity routes, mixed DEFAULT/F32, F16 fallback, changed IDs/inputs and unfused/intervening activation layouts. Shape/K fallbacks use supported strided quantized views and jointly test shape/stride guards.
- All graphs use normal optimizer/allocator, full Metal placement and one scheduler split, without CPU compute or tensor-evaluation callbacks. Timings use terminal-only outputs, 500 ms warmup and seven 100 ms blocks with at least eight executions each. 18 cases per fresh timing launch.
- Twelve accepted launches total: two correctness and four timed launches per variant. All add zero new swap. Peak process RSS: V1 1.686554 GiB; V2 1.686401 GiB. RSS is not unique total Metal memory; pre-existing swap is separate. System disk counters include unrelated activity and are not model SSD read/write speed.
- V1 general 572 GPU math cases and 16 residual cases pass. V2 coordinate-only change is covered by the full specialized correctness/fallback screen; the unrelated broad math suite was not repeated. 148 load-free tests pass; 26 built engine receipts verify, all 24 original engines and V1 native artifacts unchanged.
- Sol 6.1 authored the specialized probe; Astra authored isolated native changes; another Astra independently audited all raw records and independently recomputed all 18 aggregate rows per variant. See [review record](INDEPENDENT-REVIEWS.md).

Runtime counters establish eligible operations were encoded and graphs completed successfully; they do not measure GPU shader frequency or AI-accelerator occupancy. Routes are synthetic and do not establish real-model route distributions. Corrupt-header overflow and forced overlapping allocation/partition edge cases remain source-reviewed rather than runtime-injected.

## Provenance and excluded attempt

All raw logs/JSONL/receipts, native/probe binaries and archived sources reverified in [final-verification.json](final-verification.json); [frozen verifier](verify-final.py) starts no native/GPU/model workload. Both prepared model runners reject their current unqualified component prerequisites. No timing was rerun to change a threshold.

V1 source archive retains the pre-V2 engines.py and metal_environment.py. Current versions add only the isolated V2 registration after V1 timing. This explicit historical dependency difference is recorded in final verification; frozen V1 runner/probe/tests/native/manifest/patch/results are unchanged. V2 archives its own current closure.

X22: initial original-control correctness probe aborted after 168 records on unsupported Q2_0-to-Q2_0 CONT. No candidate or timing executed. Original source/runtime/raw bundle is preserved in [component-initial-excluded](component-initial-excluded/exclusion.json). Corrected only the fixture to keep supported strided weight views and truthful predicate receipts; fresh complete brackets above are canonical.

## Where this leaves the speed work

The preceding pass [Q02/S06/P10](../20261009-next-speed-pass/REPORT.md) also supplied no qualified model gain. Its latest full-model baseline was 59.387734 TPS for short English code and 39.871876 TPS for short English prose, with different prompt lengths; those historical numbers are not new measurements of this component pass. Percentages from separate patches/workloads must not be added.

Keep P11/P12 parked as component experiments. Revisit only with a different work-construction/math/data-reuse mechanism and a new preregistered bracket, or an explicitly redesigned latency-only trial rationale; unchanged scheduling should not be rerun to chase a smaller threshold. Real English contextual fixtures and independent prompt-latency/TPS gates are prepared for a future qualified candidate; their tokenizer lengths and model exposure have not yet been measured.

Astra also prepared [R05 stateless-checkpoint research](../../research/20261009-astra-stateless-checkpoint-plan.md). A request-level cache_prompt=false guard is unsafe for later cache-enabled slot reuse, and merely skipping a checkpoint changes later prompt splits. General implementation is held pending a defined safe lifecycle. Exact-format Q2 cooperative-input compute remains a separate unimplemented next avenue; this pass does not establish its feasibility or gain.

## Artifacts

- [V1 raw comparison](component/comparison.json), [V1 before-GPU plan](component/plan.json), [V1 manifest](../../../config/m5_compact_experiment.json).
- [V2 raw comparison](columns/comparison.json), [V2 before-implementation plan](columns-plan.json), [V2 before-GPU plan](columns/plan.json), [V2 manifest](../../../config/m5_compact_cols_experiment.json).
- [Decision ledger](../../EXPERIMENT-LEDGER.md) P11/P12 and X22;[offline log](columns-offline-validation.log); [final verifier log](final-verification.stdout.log).

Local work only. No commit, push, PR or publication. No model server remains running; no unrelated app/VM was stopped or restarted.
