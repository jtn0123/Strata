# Independent Astra evaluation of the next experiment

October 9, 2026. A fresh `gpt-6-astra` agent independently reviewed the current queue, decision ledger, pinned source and accepted raw control evidence. Read-only source/evidence review: no build, model/GPU run or performance result. The coordinator saved this review and revised the preparation card; code and runtime settings are unchanged.

**Verdict: investigate actual early stopping and fixed cap two; defer an adaptive controller.** The original card identifies a plausible mechanism, but its1–4% estimate is not an evidence-backed expectation. Use zero gain as the planning baseline. The exact speed-only gates remain in force.

## What the existing measurements can tell us

The accepted current-control [code/prose/Chinese log](../results/20261009T172830Z-m5-encoders2-1-conv-direct/server.log) records roughly54ms per completed generation cycle and about10ms in the entire draft timer. Rounded per-position prefix acceptance gives the following illustrative thresholds, **assuming unchanged first-two acceptance probabilities**:

| Workload | Expected emitted tokens/cycle, depth3 → depth2 | Complete-cycle reduction required to break even |
| --- | ---: | ---: |
| Code | 3.228 → 2.658 | 17.7%, about9.5ms |
| Prose | 2.161 → 1.992 | 7.8%, about4.2ms |
| Chinese | 2.199 → 2.009 | 8.6%, about4.7ms |

These are calculations from a depth-three control, not measured depth-two outcomes. Depth changes cycle starting positions, and request tails constrain some offers. They justify measuring marginal cost; they do not establish a counterfactual speedup. For scale only, saving6ms from a54ms cycle would imply approximately+3.7% prose and+2.8% Chinese throughput, but-7.4% code under this simplified model, before learning/exploration costs. The original1–4% range is possible conditionally, with no defensible central estimate yet.

Source of archive values: measured code near log738–796, prose844–904, Chinese952–1012. Consecutive native cumulative draft-stat deltas give draft time per request; cumulative totals are not request costs.

## Verified implementation issues

1. **The current per-cycle cap trims output after paying for helper work.** MTP's inner stop at `vendor/llama-m5-copy/common/speculative.cpp:1761` checks configured `params.n_max`. The wrapper near2913–2920 applies `dp.n_max` afterward. The simple drafter near439–443 already demonstrates actual early-stop semantics. Keep configured maximum three; never change its global value per cycle or use zero as a stop override.
2. **Draft-only timing omits consequential work.** The timer near speculative.cpp2891–2895 covers `impl->draft`. The helper reset/truncation near `tools/server/server-context.cpp:3268–3278`, target verification, sampling, checkpoint restore/replay and helper catch-up near4069–4075 also affect completed cycles. Helper catch-up can enqueue work whose wait appears later. Include request totals and outstanding final catch-up accounting without adding timing-only synchronization; individual host-call durations are not isolated GPU costs.
3. **Changing cap can change actual arithmetic.** The pinned MMA thresholds in `ggml/src/ggml-metal/ggml-metal-common.cpp:132–167` are four rows for BF16 and three for Q2_0. Target verification4→3 can cross the BF16 threshold; cap one, with two target rows, can cross Q2_0. Actual affected tensors still need normal-path proof. Do not cite the later generic Q5_K fallback threshold as actual dispatch—the earlier patched MMA route normally handles it. Fixed precision/weights alone do not prove exact output parity.
4. **Ordinary fixed-depth flags have an allocation confound.** `common/common.h:399–404` derives recurrent-state allocation from configured maximum. `--spec-draft-n-max 2` is a cheap coarse screen, not an isolated test of cap two with maximum-three allocation. Confirm calibration with true per-cycle caps and the same maximum-three engine.
5. **Exactness includes continuation state.** Preserve target sampler clone/copy and rollback near server-context.cpp4248–4314 and MTP `pending_h`/`verify_h` near speculative.cpp1627–1642/1814–1826. Forced/mixed caps need seeded, greedy, cached, acceptance and cancellation/context-boundary checks before performance.

## The smaller prerequisite has a limited payoff

The server already caps drafts for output/context budgets at server-context.cpp517–535, and already sends those shortened drafts to verification. Honoring those **existing caps inside MTP** removes discarded helper steps while preserving the control's target verification widths. This is narrower than an adaptive policy and should be the first isolated candidate.

In the measured archive, `3 × drafting calls − reported draft tokens` identifies one discarded step for code and two for prose/Chinese. Illustratively splitting the roughly10ms draft timer into equal thirds suggests only3–7ms saved per256-token reply, around0.1% of generation time. Marginal step costs are not measured. Known short output limits could benefit more; an unpredictable natural EOG is not solved by this repair. Do not promise a general adoption-threshold gain.

## Why the controller should wait

The original16-cycle learning period consumes roughly52 code tokens or35 prose/Chinese tokens. The archived short cached follow-up near log1832–1838 completes in six drafting cycles and would never adapt. Sixteen prose observations imply only about three third-position successes; a3% point-estimate advantage is not a reliable decision rule by itself.

Separate denominators for offered positions prevent counting unoffered positions as rejected, but do not remove policy-selection bias or changing context. Every-eighth-cycle exploration is not established as representative. Use calibration observations chosen independently of recent acceptance and evaluate on held-out prompts/seeds. Charge all learning/exploration time, and compare the controller against **both** fixed settings. If two wins broadly, prefer fixed two; if three wins throughout, stop.

The catch-up reuse TODO is a separate state-correctness research task. Draft continuation feeds helper-generated hidden rows near speculative.cpp1728–1729/1784–1787; catch-up uses target-generated rows near1581–1592. Matching accepted token IDs does not prove matching hidden states/KV. Removing this work is not a safe obvious substitute.

## Ordered next sequence

1. Isolate the existing-cap early-stop repair; keep maximum-three allocation and all other settings unchanged. Prove fewer actual helper steps and identical target row counts.
2. Verify exact outputs and continuation/rollback across forced caps1/2/3 and changing schedules, greedy/seeded temperature0.6, zero/partial/full acceptance, cache/fresh, EOG, cancellation/reuse and limits. The narrower tail fix and policy-cap work get independent decisions.
3. Measure fixed per-cycle cap2/cap3 complete costs in the same maximum-three engine, with minimal bounded records, no callbacks or added sync. Require a repeatable request benefit above drift before controller work.
4. Build a controller only if held-out workloads show complementary advantages that repay switching, calibration and exploration costs. Use a conservative calibrated rule and keep three when evidence is insufficient.
5. Only after qualification, fresh independent ABBA: current256-token protocol, three repeats, exact output/state checks, zero new swap, and >=1% fresh TPS **and** complete-reply improvement on two real workloads above their respective control drift. Short replies remain separately reported.

The revised [preparation card](20261009-astra-adaptive-depth-plan.md) captures this order. No stage has been implemented or tested. [Decision ledger](../EXPERIMENT-LEDGER.md), [last completed screens](../results/20261009-sampling-embedding/REPORT.md).
