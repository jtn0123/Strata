# Reviewer A: new performance paths for Strata M5

**Scope.** This is reasoning from the dossier only. Nothing was built, run or measured. Every percentage below is a hypothetical conditional bound, and the planning baseline for each is **0%**. Workloads are English prose and code only.

## 1. Cycle model and Amdahl framing

Each speculative cycle runs these steps in order. All of them sit on the host's critical path:

1. **Target verify forward.** This is 1+3 rows, because confidence0 with max3 almost always drafts 3 (`speculative.cpp:1743`, `:1761`).
2. **Target CPU sampling** of the accepted rows plus one.
3. **Helper catch-up decode** over **all** verify rows, including rejected ones (`speculative.cpp:1583-1593`, `:1610`).
4. **Three sequential helper draft decodes**, each followed by CPU top-10 sampling (`:1710`, `:1728`).
5. **Graph rebuilds** whenever topology changes (`llama-context.cpp:1428-1465`).

A rough scale, valid as an order of magnitude only: the D01 diagnostic set had 633 tokens over 240 cycles, about 2.6 tokens per cycle. At code's 59.48 TPS, a cycle is roughly 44 ms. The 1% gate therefore needs about 0.45 ms of serial time removed per cycle, assuming acceptance is unchanged. Prose cycle composition is unknown and must be measured.

Overlap opportunities are structurally limited:

- The helper needs target `h_nextn` (`:1581`, `:1682`).
- The target needs the drafts.
- There is one sequence.

So most real wins must come from **removing work or removing synchronization or rebuilds**, not from GPU/CPU overlap.

### The exactness lesson from D02

The emitted tokens come from sample-and-match (`:1666`). They are therefore a function of target logits plus RNG, **provided the target verify row widths and chunk boundaries are unchanged**. D02 changed those widths (942→788 rows) and diverged at the 228th token.

This gives a strong cheap gate for any helper-side change: **per-cycle draft token IDs, and therefore target row sequences, must be identical to control.** If they are, outputs are exact by construction. If any draft ID changes, the D02 risk class applies.

## 2. Challenging the proposed ideas

**(a) Topology-keyed graph cache.**
- The target barely benefits, because its verify topology is nearly constant (always 4 rows), so last-graph reuse already hits.
- The **helper** alternates topologies within each cycle:
  - Catch-up uses N rows with no logits (`:1586`, outputs false).
  - Draft steps use 1 row with logits.
- That implies about two helper rebuilds per cycle. Supporting evidence: in N02, each engine logged 139 helper plan dumps versus 23 target plan dumps over six 32-token requests. That is roughly 23 per request, or about two per cycle (ledger N02).
- Caveat: those dumps are plans, not execution counts. The cost of `build_graph` plus `sched_alloc_graph` (`:1448`, `:1458`) is unmeasured.
- Implementation risk: two cached graphs share one scheduler and compute buffer. A true cache probably needs a scheduler or allocation per topology, or a re-alloc-only path. The input-overwrite hazard noted at `:1431-1436` applies.
- The math is unchanged (same ops and kernels), so exactness risk is low once correct.
- **Verdict:** viable for the helper only, and only after measurement.

**(b) Deferring and merging catch-up.** This is real work removal: about 1.3 rejected rows per cycle (inferred from roughly 3.9 verify rows and 2.6 tokens per cycle) plus one helper launch. But it carries **high exactness risk**:
- The helper would see batches of n_acc+1 or n_acc+2 rows instead of 4.
- Few-row kernel selection is width-thresholded (T08: Q2 threshold 3, BF16 threshold 4). Accumulation order can therefore change.
- That can change helper logits, and with them draft IDs, and with them target widths: the D02 failure mode.
- It also removes any existing chance to overlap catch-up with target CPU sampling.
- Server-side helper `seq_rm` handling of rejected positions is not in the dossier.
- **Verdict:** park behind a helper bit-identity proof. It is not a first probe.

**(c) Exact argmax for greedy helper.** This is a solid, distinct idea:
- In greedy mode, `id_sampled` is computed and then discarded (`:1728` vs `:1740`). Only `cur_p->data[0].id` is used.
- With p_min=0, `p < 0` never fires (`:1743`), so probabilities are unused.
- Each draft step still builds a full-vocabulary candidate set and runs top-10 (`:1455-1458`).
- Replacing this with a single-pass argmax (only when `p_min<=0 && !result_q`) is pure CPU work removal.
- Exactness hinges on **tie order**: argmax must pick the same index the top-k sort places first. The sampler source is not in the dossier, so this cannot be assumed.
- This differs from P08 (target retrieval view), N01 (target backend min-p) and T04/T05 (which changed confidence).
- **Verdict:** cheap and exact-provable. The open question is magnitude.

**(d) QSA all-visible shortcut.** This is the strongest structural idea:
- When `n_top_pool == n_pool` (`qwen4exp.cpp:816`), the top-k selects every pool. The mask *should* reduce to `kq_mask`.
- If so, the following can be skipped:
  - `index_q_proj` matmul, norm and rope (`:801-807`)
  - the lightning indexer (`:812`)
  - top-k (`:817`)
  - roughly 20 mask-construction ops (`:821-870`)
- The raw-key cache write (`:763-768`) and new-pool scatter (`:774-796`) must be **retained**, so contexts that later exceed the budget see identical caches.
- This is target-side work on every verify forward, at every QSA layer.
- Two caveats:
  - Equality is not proven. A partially visible complete block could have an invisible pool score, dropping visible cells. The pool-visibility semantics are not in the dossier.
  - `build_attn_mha(..., n_sel, ...)` (`:924`) must not select a different kernel when given the plain mask.
- It also removes the "large compute buffer" flagged at `:830`, which helps memory headroom.

**(e) Compact routed-expert MMA grid.** The mm_id dispatch is `(ne21+31)/32 × (ne01+63)/64 × ne02` over **all** experts (`ggml-metal-ops.cpp:3009`). Empty experts presumably early-exit, but `mul_mm.metal` is unavailable, so I cannot assume how.
- For 512-row prompts, most experts are active, so the empty-tile fraction is likely small.
- Few-row verify most likely goes through `mul_mv_id` (`:3011`), though the branch condition is not in the dossier.
- Prompt changes cannot move the decode-TPS gate.
- **Verdict:** low priority until a normal dispatch inventory shows verify batches on `mm_id` with many empty expert slices.

**(f) Avoiding checkpoints when `cache_prompt=false`.** This is at most a one-time cost per request, not decode work.
- It only applies if real clients disable caching, which conflicts with the cache and continuation gates.
- No source is in the dossier.
- **Verdict:** fold a timer into Probe 1, and drop it unless checkpoint time is at least 1% of reply time.

**(g) Exact Q2 cooperative-input prompt kernels.**
- This is legitimately untested (it is queue item 2, and P09 does not rule it out).
- But adoption requires at least 1% **TPS**, and decode TPS excludes prefill. It cannot pass unless 4-row verify uses the affected mm path. Even Astra's high case (+8% prompt) maps to well under 1% of whole-reply time for short English prompts.
- The OS/SDK format support on macOS 27.2 and the precision equality are both unproven.
- **Verdict:** keep it as a separate long-prompt profile, not this pass's speed path.

## 3. Additional ideas

**(h) Streaming top-k front end for target CPU sampling.**
- At temperature 0.6, every target row sampled builds a 248,320-entry candidate array before top-k, top-p, min-p and dist run.
- A fused "logits → bounded heap → existing chain" approach is exact if:
  - the post-top-k candidate order is byte-identical, including ties;
  - the penalty samplers are no-ops at the configured values;
  - RNG consumption is unchanged.
- This is distinct from P08 (retrieval), N01 (backend min-p) and (c), which covers the helper.
- It shares (c)'s tie-order proof, so build both on one verified tie-preserving primitive.

**(j) Overlapping catch-up with target CPU sampling.**
- Catch-up needs only `h_tgt` (`:1581`), not the sampled tokens.
- Its GPU part could be issued before CPU sampling of the verify rows.
- This is overlap only, not removed work, and it is bounded by min(sampling time, helper GPU time).
- It conflicts with (b) and contends with the eight helper CPU workers.
- **Verdict:** consider only if Probe 1 shows both phases are non-trivial and strictly serialized.

**Rejected by me: removing the `verify_h` copy (`:1636-1638`).** It moves about 40 KB per cycle, which is negligible.

## 4. Ratings

| Idea | Mechanism | Hypothetical conditional bound (plan 0) | Exactness risk | Difficulty |
|---|---|---|---|---|
| (a) Helper topology cache | Rebuild/alloc removed | 0 to ≤ measured helper rebuild share (guess ≤1.5%) | Low math, medium buffer-aliasing | Medium |
| (b) Defer and merge catch-up | Work + launch removed | 0 to ~2% if helper share is large; can be negative | **High** (width-dependent numerics) | Medium-high |
| (c) Greedy helper argmax | CPU work removed | 0 to ≤ measured helper-sampling share | Low-medium (ties) | **Low** |
| (d) QSA all-visible shortcut | Target GPU work removed | 0 to ≤ indexer subgraph share; guess ≤3% at <2K context | Medium (mask proof, kernel choice) | Medium |
| (e) Compact mm_id grid | Empty dispatch removed | ~0 for TPS until dispatch proof | Low | Medium |
| (f) Checkpoint avoidance | One-time work | <0.5% of reply, TPS ~0 | Cache-gate conflict | Low |
| (g) Q2 cooperative prompt | Prompt work | TPS ~0; whole reply small | High (format/precision) | High |
| (h) Streaming target sampler | CPU work removed | 0 to ≤ measured target-sampling share | Medium (ties, RNG) | Low-medium |
| (j) Catch-up/sampling overlap | Overlap | ≤ min(overlapped phases) | Low if no draft change | Medium |

## 5. Selection

### Probe 1 (cheap): cycle-phase envelope plus argmax shadow check

**Purpose.** This one diagnostic-only build decides (a), (c), (f), (h) and (j).

**Instrumentation:**
- Host `ggml_time_us` timers placed **only at points where the host already waits**. Do not add syncs; profiling callbacks distort fusion (C03).
- Phases to time:
  - target verify (to logits retrieval)
  - target CPU sampling
  - helper catch-up (`:1610`)
  - each helper decode (`:1710`)
  - helper sampling (`:1728-1731`)
  - graph build vs `sched_alloc` separately (re-enable the commented timers at `llama-context.cpp:1446/1450`, add one around `:1458`)
  - checkpoint creation
- Per-context `n_reused` (`:1438`) and rebuild counts.
- **Argmax shadow:** at every draft step, compute the candidate argmax with the proposed tie rule and log it against `cur_p->data[0].id`. Add synthetic tie fixtures (equal max logits at varied indices, NaN-free).

**Workloads.** English code and prose, 256 tokens, the exact control settings, plus a 512-token English fixture (the D02 lesson).

**Gates:**
- **Gate 0 (non-perturbation):** timer-build token IDs, text, acceptance and row sequences match control exactly. Otherwise discard the build.
- **Stop for (a)/(c)/(h):** park any candidate whose attributed envelope is below **2% of whole-reply time on both code and prose**. The 2× margin covers the 1% gate because envelopes overcount, following the P06 method.
- **Stop for (c):** any shadow mismatch or tie-fixture disagreement parks (c) until the tie rule is fixed.
- **Not a speed result:** no TPS claim can come from this probe.

### Probe 2 (cheap): QSA all-visible equivalence screen

**Equivalence check.** In an isolated diagnostic engine, whenever `n_top_pool == n_pool`, compute both the existing `sel` (`:870`) and `kq_mask`, and compare them **bitwise**, including the sign of zero. Cover:
- the 512-row prompt ubatch
- 4-row verify and 1-row decode
- cached continuation
- contexts straddling the budget, where fallback must be the unchanged path

**Normal dispatch inventory.** Use an uninstrumented normal dispatch inventory (C03-style) to confirm that the indexer ops actually execute in the fused runtime (`:813`). Confirm which attention kernel is selected for both masks.

**Gates:**
- Stop on any mask bit mismatch or any attention-dispatch difference.
- Stop if the removable subgraph, timed in a dependent-graph component bracket, saves less than 2% of a target verify forward above 2× drift.

### Big bet (if Probe 2 passes): QSA all-visible shortcut in the target graph

**Change.** Branch at graph build on the host-known `n_top_pool == n_pool`. Keep the `k_raw`/pool cache writes and pass `kq_mask` directly.

**Gates before ABBA:**
- Bit-identical raw and pooled cache bytes after N steps.
- Exact tokens through 512+ English tokens.
- A seeded continuation that **crosses** the budget and must match control from the first post-crossing token.
- 588-case math suite, zero new swap.

**Then:** a fresh independent ABBA under the standard gate (≥1% TPS **and** whole-reply improvement, above drift, on both code and prose).

**Falsification:** any divergence, a cache-byte mismatch at the crossing, or a sub-drift result parks it. Do not relax the gates.

### Contingent follow-on

If Probe 1 shows the helper phases (rebuild plus sampling) are at least 2% on both workloads, run (c) first, since it is exact by ID identity and cheapest. Then run (a) as a two-slot helper cache, with re-alloc-only as a fallback variant. (b) waits for proof of bit identity of helper per-row hidden states and logits across the changed widths.

## 6. Why none of this repeats the ledger

- **(c)/(h)** keep confidence0 and max3, and change no draft count. They are not T04/T05 (confidence), P08 (target retrieval, 0.067 µs/row), N01 (target backend min-p) or D01/D02 (draft caps).
- **(a)** targets helper graph rebuilds. It is not the S02/S03 encoder sweep, and N02's plan counts motivate it rather than answer it.
- **(d)** has no ledger entry. The QSA indexer has never been screened.
- **(b)** keeps three drafts. Its gate is built from D02's failure rather than repeating D02.
- **(e)** is grid compaction, not P03/P04 pair grouping, S01 epilogues or T08 dense thresholds (T08 states that dense knobs don't control `MUL_MAT_ID`).
- **(g)** remains queue item 2. P09 explicitly does not rule it out. I am only arguing that it cannot pass this decode-TPS gate.
- **Constraints observed:** no stacked percentages, no comparisons against historical 128-token rates, and no claimed gains.
