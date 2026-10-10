# Sequential M5 experiments

[Central experiment decision ledger](../../EXPERIMENT-LEDGER.md) records this pass as S01–S05, older unsuccessful settings and explicit revisit conditions; [machine-readable index](../../experiment-ledger.json).

Astra evaluated the future queue. Experiments run one at a time with unchanged model weights, precision, context and draft depth. Defaults remain unchanged.

## 1. Parallel activation epilogue: parked

All 58 cases and 11,162,880 F32 values matched the practical control bit for bit. Six native runs used A/B/C/C/B/A: practical control, parallel activation, and old serial activation ablation. Accepted runs had zero new swap.

The real R4 complete block averaged **297.497 → 296.937 microseconds**, a **0.19% time reduction**; control drift was **0.23%**. Conservative bracket reduction was only **0.016%**, below the predeclared 3% qualification gate. Real R5 was effectively flat (-0.019% time reduction). Distinct-expert cases regressed about 0.93–1.13%. No model TPS claim and no full-model trial are warranted.

[Raw first-experiment evidence](gate-lanes.json) · [Ranked future queue](../../research/20261009-astra-future-queue.md)

## 2. GPU command preparation: retain existing one extra worker

Two independent fresh ABBA model suites: 1/0/0/1 and 1/2/2/1. These counts mean **extra Metal encoding workers**, unrelated to the helper's eight CPU workers. All 168 tested fresh/cached output records matched exactly; all 256 answer/cache checks passed; all eight accepted model launches had zero new swap. The prerequisite covered 234 dependent/state graphs across both constructors, malformed inputs and stats override, with exact CPU output/state/padding checks. Quantized operator prerequisites also passed.

| Setting | Workload | Control TPS | Candidate TPS | TPS change | Whole reply faster |
| --- | --- | ---: | ---: | ---: | ---: |
| 0 | Code | 59.442 | 56.135 | -5.56% | -5.71% |
| 0 | Prose | 39.943 | 37.750 | -5.49% | -5.62% |
| 0 | Chinese | 40.669 | 38.390 | -5.61% | -5.75% |
| 2 | Code | 59.467 | 59.325 | -0.24% | -0.21% |
| 2 | Prose | 39.949 | 39.882 | -0.17% | -0.12% |
| 2 | Chinese | 40.607 | 40.583 | -0.06% | -0.06% |

Zero workers is consistently slower; two provides no useful improvement. Defaults remain one. No adoption occurred. Each suite uses its own controls, so percentages are not additive or compared against unrelated older TPS figures. Prompt, TTFT and cached metrics are in the raw summaries.

Actual target/helper startup counts and stats=false were verified in each model log. Count2 is **restricted to the pinned callback-free server path**: the existing non-null cancellation callback path can leave its main command buffer uncommitted. Queue/commit behavior was preserved; this experiment does not establish general callback compatibility. Initially null callbacks are established by the pinned calloc context; every later assignment is instrumented and any non-null event is rejected.

The first diagnostic baseline added 983,040 bytes (0.94 MiB) swap and is excluded. The clean mode0 suite initially failed only its postcheck due to application logger prefixes and absent unused callback-setter events. That original rejection is preserved; the corrected log analysis used the same unchanged raw runs/native hashes/settings and did not rerun performance. Astra independently confirmed this scope. Reply-time gain must also beat its own bracket drift before adoption.

[Zero worker evidence](encoders0.json) · [Two worker evidence](encoders2.json)

## 3. Single-token full-vocabulary head: parked

Both variants passed all16 cases: 4,966,398 full-vocabulary F32 output scores each were bit-identical to stock (9,932,796 values compared across variants), including cancellation, one-hot block boundaries, zero/scaled inputs, separated and tied top10 cutoffs, dense views, T2/T4 and unsupported shapes/strides/names. Streaming CPU references covered all logits. Every fallback retained the exact kernel, pipeline cache key, returned tile geometry and tensor metadata.

Each perf variant used a fresh ABBA bracket, one dependent head -> top10 -> gather graph, one terminal synchronization per iteration, an untimed pipeline prime, >=500ms sustained GPU warmup and seven >=100ms blocks for each input pattern. Full shape is Q5_K [2560,248320] (437,043,200 stored bytes), F32 single-token input. No expanded-weight cache, callback profiling, vocabulary trimming, SSD timing or precision change. Probe RSS stayed below3GiB; all accepted launches had zero new swap.

| Variant | Input | Control complete operation | Candidate | Time change |
| --- | --- | ---: | ---: | ---: |
| 2 rows | Mixed | 1.9047ms | 1.9577ms | 2.79% slower |
| 2 rows | Alternating | 1.9082ms | 1.9455ms | 1.95% slower |
| 4 rows | Mixed | 1.9102ms | 1.9312ms | 1.10% slower |
| 4 rows | Alternating | 1.9107ms | 1.9343ms | 1.24% slower |

Control drift was only0.10–0.26%. Both variants failed the predeclared >=10% complete-operation improvement gate. They stay disabled; no full-model trial or TPS gain is claimed. Actual model T1 stride/dispatch capture remains required if revisiting this idea; it was not warranted by this failed screen. The guard can cover both target and helper single-token heads, and does not claim helper-only execution.

[Head correctness and timing evidence](head.json)

## Working setup and remaining queue

No candidate from this pass was adopted. The established `m5-copy` + `conv-direct` practical setting remains, TensorAPI on, depth3, shared packed Q3 helper/mixed placement with8 CPU workers, F16 KV and4K context. New matched controls measure about59.4 TPS code,39.9 TPS prose,40.6 TPS Chinese,48.4 TPS synthetic512 and49.8 TPS synthetic2048. These workload-specific numbers are not a percentage gain against older prompts or shorter tests.

Astra ranked seven ideas in [the research queue](../../research/20261009-astra-future-queue.md). The remaining order is:

1. Static speculative sampling graph + eligible target backend sampling (newly merged upstream prerequisite).
2. Embedding graph ordering, only after proving actual CPU/GPU crossings are reduced.
3. Cost-aware draft length within the current maximum3, based on accepted-prefix and cycle cost.
4. Cooperative-input quantized prompt kernels, after proving exact format/precision support.

All estimates in that queue are hypotheses, not promised or additive gains. These next ideas were not implemented or benchmarked in this pass.

Final verification:120 load-free tests passed; all19 engine source/build receipts verified; all16 preexisting engines unchanged. Model servers stopped. No unrelated process was stopped or restarted. No commit, push or PR. [Verification receipt](../../runtime/m5-sequential-pass/final-verification.json).
