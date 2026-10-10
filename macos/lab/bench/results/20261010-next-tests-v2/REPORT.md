# Sequential next-test results — October 10, 2026

**No new keeper was promoted.** The existing P07 launcher, model, quantization, helper and settings remain unchanged. The retained full-model short-prompt / 256-output confirmation is **60.084 TPS code / 40.375 TPS prose**; it was not rerun here. Percentages from different models, prompts, output lengths or components are not stacked.

## U10-03 — whole-input tokenization cache

Four fresh 4B Qwen3.5 Q4_K_M native launches (A/B/B/A), English code/prose, cold/identical/unique full inputs, one warmup and three measured repeats per case. All **96 full Service answers** have exact input/output IDs, parser events and finish parity, real cache activation, bounded retained storage, healthy monitoring and zero new swap. Native prompt reuse and MTP were disabled.

| Repeated input | First content control → cache | Reduction | Complete reply control → cache | Reduction | Native TPS control → cache |
|---|---:|---:|---:|---:|---:|
| code | 80.889 → 80.513 ms | +0.4648% | 1710.889 → 1711.244 ms | -0.0208% | 77.8968 → 77.8894 |
| prose | 81.275 → 81.083 ms | +0.2371% | 1712.297 → 1709.673 ms | +0.1532% | 77.8734 → 77.9924 |

Code first-content saving is 0.376 ms; prose is 0.193 ms. Code does not exceed twice its own control drift; prose first content qualifies narrowly, but its complete reply does not. The preregistered shared first-content/reply criterion fails. No material cold/unique regression was found. **Parked; disabled.** Native TPS attribution is zero because tokenization caching does not change native generation, and no aggregate keeper gain qualifies. Unique inputs have no hits; their raw improvements do not establish cache benefit.

Service times include rendering/encoding and omit incoming HTTP overhead/browser rendering. A future long-prefix trial requires measured tokenizer exposure and a new workload declared beforehand; do not repeat the same small prompts to chase noise. [Raw comparison](input-cache/tracking.json).

## U10-02 — sixteen-row expert prompt tiles

All three 273-case correctness arms passed (**819 fixtures**), including exact complete F32 outputs, A/B/A mutation, eligibility/fallback counters, Metal placement and scheduler gates. Four fresh ABBA timing arms each completed 18 dependent full-block cases. Every launch has healthy monitoring and zero new swap.

| Uniform routing | Original complete block | Sixteen-row complete block | Extra time | Own control drift |
|---|---:|---:|---:|---:|
| 508 rows | 12.9640 ms | 14.5413 ms | 12.1667% | 0.0022% |
| 512 rows | 12.9999 ms | 14.5843 ms | 12.1878% | 0.0798% |

All 18 timed cases are slower, by 5.61–41.13%; all fail the regression guard. **Rejected for this implementation; no full-model trial.** These are complete synthetic-block times, not model TPS percentages. The original already skips unused upper sixteen-row arithmetic; extra dispatch/weight work is a plausible mechanism, not a measured attribution. Revisit only a materially changed dispatch/worklist design or distinct measured exposure. [Raw comparison](tile16/tracking.json).

## U10-01 — independent MLX feasibility

The pinned MLX source and isolated dependencies pass the Apple M5 Pro device/import check and 1,024 exact F32 GPU values. The full Q2_0 loader then passes all 48 layers / 512 experts / ten selected experts and 1,298 floating parameter arrays at F32. Loading took 15.360 seconds, active MLX arrays 7.067 GiB, peak 8.216 GiB. This initial-state check has an empty expert cache; its nominal 12 GB budget is not a filled-cache fit proof. [Loader receipt](mlx-load/receipt.json).

A separate prerecorded 6 GB expert-cache / F32 pilot produces one English answer using the same complete full-model shards, with no MTP/suffix guesses/guess rows, chunk 32, context bound 512 and greedy sampling. Input has 25 tokens; output is capped at 16 and ends by length:

> An SSD is a storage device that uses flash memory to store data electronically without moving

| Paged pilot metric | Result |
|---|---:|
| Model load | 12.473 s |
| First token after load | 5.218 s |
| Subsequent decode | 15 tokens / 1.164 s = 12.889 TPS |
| Complete capped reply after load | 6.382 s |
| Peak MLX arrays | 13.575 GiB |
| Expert cache retained | 5.999616 decimal GB |
| Logical expert bytes read, prompt / decode | 6.222 / 2.188 GB |
| Minimum host availability | 16.228 GiB |
| New swap | 0 bytes |

This is **empty expert-cache startup, one prompt, 15 subsequent tokens, no warmup/control/helper**. OS file-cache warmth is uncontrolled. The first token includes lazy GPU compilation and paging; 12.889 TPS is not comparable with the keeper’s separate workload. Logical pager bytes and pager read timers are not an SSD sequential-bandwidth benchmark. The sensible truncated answer establishes a bounded response, not original sampler/state equivalence, long-context stability, API/cancellation correctness or answer-quality qualification. **Feasible for more testing; not adopted.** [Preregistered plan](mlx-reply/plan.json), [raw receipt](mlx-reply/receipt.json).

## Failures, resources and next work

- Vocabulary-helper preparation first failed because the pinned model API no longer has `use_mmap`. Original source/build log and the ensuing preflight rejection are preserved. The corrected helper compiles against the actual header, loads vocabulary only and verifies exact prompt roundtrip; no benchmark was launched by the failed preparation. [Attempt record](mlx-reply/preparation-attempts.json).
- First unused-model-cache cleanup recovered only 0.055 GiB after 60 seconds; most pages were already clear. It did not meet the unchanged 34 GiB full-model admission rule. Existing swap remained distinct from zero new swap.
- `launchctl` refused a media-analysis service signal without privilege; a subsequent exact same-user PID received graceful SIGTERM, recovering 1.067 GiB at the five-second observation. No service was disabled. T3, Codex and WiFiman connectivity remain running. [Both cleanup attempts](memory-cleanup/pid-attempt.json).
- All current 28 engine receipts and the completed frozen campaign source/build/archive pins verify. The unchanged source closure retains its 177-test offline pass; this is not a fresh rerun. Native test programs/model processes have exited. [Verification](post-run-verification.json).
- Next useful MLX work: a newly declared warmed English code/prose response study, bounded 6/12 GB cache comparison, actual state/output checks and longer replies. A single feasibility answer does not authorize a keeper or a 24 GB budget assumption. R08 helper critical-path exposure remains unimplemented.
- Do not rerun the unchanged cache/tile screens. Neither produces a validated new TPS addition. Preparation receipts and frozen rules remain immutable; the earlier held v1 campaigns remain superseded, never executed.

## Final memory cleanup

After all model tests exited, the same read-only clean-model-cache method freed **3.451 GiB** of observed availability. All model identities remain unchanged. The 60-second settle stayed at **33.481–33.642 GiB available**, normal pressure and zero new swap. No service/app/files were removed. The retained native 34 GiB prelaunch gate is still not met; no full native speed run was attempted. This does not limit the completed smaller-model/component/paged-MLX tests, which use their distinct predeclared budgets. [Cleanup receipt](../20261009-small-gains/memory-investigation/model-cache-trial-20261010T130657113307Z/result.json), [final snapshot](final-resources.json).

[Next proposed MLX comparison](NEXT-PLAN.json) defines fresh warmed 6/12 GB ABBA work; the runner and frozen workload remain to be implemented.
