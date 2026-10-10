# Strata speed-direction audit (reviewer B)

## Bottom line

The planning baseline stays at zero. Only R01, R02 and R08, plus R07 conditionally, can move native decode TPS, which the adoption gate requires.

- **Prompt-only items (R03, R04, R05, R09):** these change only TTFT. With roughly 48-token English prompts and 256-token outputs, they cannot meet the "≥1% TPS" clause by construction, whatever their TTFT gain.
- **Outside the native benchmark (R06, R10):** these do not run in the native benchmark at all.

Adopting any of these requires a separate, explicitly declared latency or memory gate, not a speed claim.

## Premise audit

**R01 (QSA all-visible bypass).** The core premise is correct.
- `n_top_pool = min(n_pool, 2048/4 = 512)`. `n_pool` is padded: `max(64, pad(n_real+1, 64))`. Eligibility is therefore `n_real ≤ 511`, roughly ≤2047 sequence positions, not "≤512 tokens." The current benchmark replies stay inside this bound throughout.
- When eligible, `top_k` returns every pool. Ordering is irrelevant because set_rows scatters constant zeros. Liveness then depends only on finite versus −inf score.
- **Missing condition:** in `by_order` mode (lines 980 and 1005), coverage is rank-based while `kq_mask` is position-based. A cell sharing a position but holding a higher rank is kq-visible but unselected. So `sel ≠ kq_mask` even with all pools chosen. The bypass must require `!by_order`, and must also require contiguous positions, because the tail formula at 1007 assumes no holes.
- **Unverified:** what `build_attn_mha` does with `n_sel`. If it selects a gathered or sparse kernel, "same dispatch" must be shown rather than assumed.
- **Not mentioned:** a topology switch at the 512-pool boundary requires a graph-reuse key change. Reusing a bypass graph after crossing the boundary would silently attend over unselected cells. That is a correctness failure, not a speed regression.
- **Removable work:** `index_q_proj`, the q norm and rope, `gather_pooled`, the lightning indexer, `top_k`, `get_rows`, about 12 mask-building ops, and `set_rows`, for each QSA layer and each target forward. The `k_raw` and pooled-key writes must stay.

**R02 (helper winner-only selection).**
- The dispatch premise checks out: ncols 248320, k 10, nrows 1, so the bitonic path is used. Note that `ggml_top_k` output is **unordered** (line 817). Today's "candidate0" is therefore whatever CPU-side sorting of 10 entries yields. Tie semantics are inherited from that sort and are not a GPU property.
- **Plain argmax cannot implement the gate.** Detecting a unique maximum needs either the second value or a count of entries equal to the maximum.
- **Possible regression:** stock ggml Metal argmax is one threadgroup per row. On one 248320-wide row it may be *slower* than multi-threadgroup bitonic.
- **Hard prerequisite:** line 1740 uses `id_sampled` whenever `result_q` is non-null, and line 1758 stores all candidates. If the target's acceptance uses draft distributions, winner-only is dead. Prove `result_q == nullptr` in the benchmark path.
- **Ceiling:** S04 measured head→top10→gather at about 1.90 ms, dominated by a ~437 MB Q5_K head read. R02 can only recover the top10 and gather residual.
- S04 and S05 do not answer R02 and must not be cited as evidence either way.

**R03 (active expert/token tiles).**
- The exact maximum of useful tiles is ⌊(5120 + 31·512)/32⌋ = **656**, and it is tight. One construction reaching it: every expert has n_e ≡ 1 (mod 32), with Σm = 144. The figure of 671 is merely loose. The agent's floor form is correct.
- **Key simplification:** you need neither CPU readback nor indirect dispatch. Launch the static bound ⌊(T·k + 31·min(E, T·k))/32⌋ instead of ⌈T/32⌉·E. Map each tile to (expert, r1) with a prefix sum over `tpe`, which `map0` already computes. Surplus tiles early-exit as they do today.
- At T=48 the bound is 480 against a grid of 1024. The absolute savings are trivial for current workloads.
- P04's lesson applies: each tile's per-element accumulation must remain byte-identical.

**R04 (shared route map).** Content equality is plausible: `map0` reads only `src2`, `ne21`, `ne20`, `nb21` and the thread count `ne02`. The real blocker is lifetime. Scratch sits at `bid_dst + nbytes(op)`, so it lives inside the gate output's allocation. The allocator can reuse that region before the down projection runs. Reuse therefore needs a graph-level map tensor, which changes topology, fusion matching and the CPU fallback. Payoff: two single-threadgroup `map0` dispatches per layer, per prompt ubatch. Park it.

**R05 (skip checkpoints when `cache_prompt=false`).** The 15% "high" estimate depends on removing the 44+4 split. That is an arithmetic change:
- The 4-token ubatch likely takes a different mat-vec path than an unsplit 48-token ubatch. This is D02's mechanism, which says width changes can change exact output.
- Stage 2 would make `cache_prompt=false` and `true` produce different outputs for identical prompts. Divergence from the control under Stage 2 is expected and must not be relabeled a bug or a pass.
- Stage 1, suppressing serialization while keeping the split, is about a 112 MiB copy, likely ~0.2–0.5% of reply time. Treat it as memory hygiene.
- Check whether this fork's speculative rollback uses the checkpoint mechanism that PR 30188 (draft, unmerged) skips.

**R06 (per-token detokenize calls).** The premise is correct: there are N HTTP calls, and Σ IDs is about 33k for 256 tokens.
- **Zero-benefit case:** at about 60 tok/s the consumer has ~16 ms per token, against roughly 1 ms per call. It keeps up, and only the final call's latency is exposed.
- The realistic costs are CPU contention with the 8 helper workers, and two latent bugs:
  - A legitimately emitted U+FFFD stalls output (line 425).
  - The slice `text[self.sent:]` assumes full re-decode is prefix-stable.

**R07 (deferred accepted-only catch-up).** The premise is confirmed: the catch-up processes every verification row (1583–1610), and `accept()` only repoints `pending_h`.
- **Hidden state change:** "target verify width unchanged" is insufficient. If helper KV differs at all, drafts change, acceptance changes, and target batch composition and positions change. That reproduces the D02 divergence path.
- The real predicate is bit-identity of helper KV and `h_nextn` for committed rows under a narrower batch.

**R08 (cached alternating plans).**
- The arena premise is correct. Index `n_outputs > 0` alternates, and `gf_res_prev_active` is a single pointer.
- **Missed:** `ggml_backend_sched_reset` and `sched_alloc_graph` are shared. Two cached `llm_graph_result`s still clobber each other's scheduler allocation. Caching both needs two scheduler states, which means duplicated compute buffers and a risk to the zero-swap gate.
- **Missed:** target verify widths of 1–4 are distinct topologies and also force rebuilds. R08 as written ignores them.

**R09 / R10.**
- R09 is prompt-only with unproven compile eligibility. It cannot clear the TPS clause on 48-token prompts.
- R10 is off-workload with cache RAM 0.
- Park both.

## Explicit three-way rating

| | Decode reach | Exact-output risk | Cost to first answer | Rating |
|---|---|---|---|---|
| **R01 QSA bypass** | Every target forward and every QSA layer; removes a weight-bearing projection plus about 20 dispatches | Low if the predicate holds; high if the reuse key is wrong | Census plus GGUF size arithmetic | **Best** |
| **R02 winner-only** | Helper steps only (about 2.9 per cycle); capped by the top10 residual | Tie and `result_q` semantics | S04 harness already exists | **Second; small ceiling** |
| **R03/R04 prompt map/dispatch** | None | Low (R03) / allocator lifetime (R04) | New kernels or graph op | **Last; zero adoption-path benefit on current workloads** |

## Three NEXT low-regret probes (ranked)

### 1. R01 correctness census, then bound, then build

**Step 0 (no run).** From GGUF metadata, compute the bytes removed per target forward: `index_q_proj` (+ q norm) × the number of QSA layers. Multiply by forwards per reply and divide by measured bandwidth. This is an *upper bound* used for stopping only, never a TPS claim.

**Step 1 (diagnostic launch).** Callbacks are allowed here because only correctness is measured. For every eligible graph (padded `n_pool ≤ indexer_top_k/kpool`), record and assert:
- `by_order == false`;
- contiguous positions per sequence;
- every visible pool score is finite;
- for every row i, `{c : kq_mask[i,c] finite}` equals `{live selected cells}`, which makes `sel == kq_mask` bitwise because 0+0=0 and x+(−inf)=−inf.

Cover English code, prose, 256-token continuations, speculative verify rows, rejection/`seq_rm` rollback, cache reuse, and a synthetic sequence crossing pool 511→512 both inside a prompt ubatch and during decode.

**STOP gates:**
- Any row mismatch, by_order case, non-contiguous eligible graph, or non-finite visible score halts the probe.
- STOP if the Step 0 bound is below 1% of reply time *and* `build_attn_mha` turns out to take `n_sel`-dependent dispatch.
- After implementation, logits must be bitwise identical on every verify row. The reuse key must include the bypass flag, proven by forcing the boundary crossing on a reused graph.

**Zero-benefit case:** the Metal concurrency sets already overlap the indexer branch with Q/K/V projection, and decode is bound by expert-weight bandwidth. Removal then frees no critical path. Only an ABBA run decides.

### 2. R08 rebuild census (no arithmetic change)

**Step 1.** In a separate diagnostic launch with no eval callback, log per context and per cycle:
- `n_reused` versus rebuild count;
- the cause of each rebuild: helper output toggle, target width change, or other;
- host wall time for `build_graph` + `sched_alloc_graph`, using the existing commented timers at 1446–1450.

**STOP gates:**
- STOP if total exposed build+alloc time is below the ledger's own 2% critical-path threshold.
- STOP if most of it comes from target width changes. Those need a different mechanism: per-width cached plans with bounded memory.

**Prerequisite before any implementation:** measure the memory cost of duplicated scheduler buffers under zero-swap.

**Zero-benefit case:** the helper graph is one MTP layer plus the head, so a rebuild costs on the order of 100 µs.

### 3. R02 component bracket in the existing S04 harness

**Step 0.** From the normal-run log, prove three things:
- no "backend offload failed" warning;
- `result_q == nullptr` in the greedy-helper path;
- the top_k dispatch is the bitonic path with ncols 248320, k 10, nrows 1.

Also document how today's tie-breaking actually behaves, using an injected exact-tie logit fixture.

**Step 1.** Run ABBA over three arms: head→top10→gather (control), head only (floor), and head→parallel unique-max (a multi-threadgroup kernel returning max, first index and max-count).

**Predicate:** for a unique finite maximum, the winner ID equals control candidate0. For ties or non-finite values, a full fallback to the original path reproduces control exactly. No full-logit readback is added.

**STOP gates:**
- STOP if (control − unique-max arm) × measured helper steps per reply is below 1% of measured reply time. This is an upper bound used only for stopping.
- STOP if the unique-max arm is no faster than control.

**Zero-benefit case:** bitonic top-10 already sits near the read floor of the ~1 MB logits, and the head matmul dominates.

## Bigger bet: R07, only behind a width-invariance census

**Step 1 (offline replay).** Capture real verify batches. Re-run the helper catch-up twice: once on all rows (control) and once on committed rows only. Compare helper KV bytes and `h_nextn` for committed positions bit-for-bit, across widths 1–4 and across both the GPU-dense and CPU-expert portions.

**Step 1 outcomes:**
- **Any mismatch: STOP permanently for this mechanism.** It is D02's failure mode under a new name.
- **Identical:** implement deferral. Gate it on identical drafts, acceptance, target row sequence, RNG draw count and exact outputs (D02's 228th-token fixture, extended English, EOS, cancel, cache reuse). Only after that, ABBA.

**First-draft fusion** changes the draft step's batch width as well. It needs its own separate bit-identity census and must not be bundled.

**Upside source:** helper catch-up rows fall from about 942 to about 633 per 633 tokens (D02's diagnostic counts).

**Zero-benefit case:** catch-up cost is dominated by per-launch overhead and synchronization, not per-row CPU expert work. Fusion is then the only lever, and it carries the highest risk.

## Disposition of the rest

- **R05 Stage 1:** acceptable as memory hygiene with exact-output proof. **Stage 2 is barred** without explicit quality-change authorization.
- **R06:** a reasonable app fix outside the speed gate. Qwen uses byte-level BPE, so local incremental UTF-8 decoding over cached per-token bytes is exact only if `/detokenize` applies no special-token or cleanup transforms; verify that over full outputs. Parser events must be chunk-invariant.
- **R03, R04, R09:** defer until a declared long-prompt English workload exists.
- **R10:** do not pursue on the current workload.
