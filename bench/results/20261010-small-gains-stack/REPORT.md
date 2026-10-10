# Sequential W02 validation and P07 rollout

P07 is installed in the no-argument `Start Strata.command` launcher. Qwen3.8-Flash-Next Q2_0, packed shared Q3 helper, mixed placement, eight helper CPU workers, depth3/confidence0, Tensor API on, F16 KV, 4K context, batch 512. Explicit launcher arguments retain generic CLI behavior, including the small model.

W02 remains a possible throughput tradeoff. The new frozen screen gained 0.5835% code and 0.7114% prose TPS, but prose had a 12.659958 ms worst launch-pair first-token delay, above the prospectively declared 10 ms ceiling. Average delay was 4.254 ms code / 6.207 ms prose. No W02 confirmation or combination was launched. Old results and their relative rule remain unchanged.

P07 previously passed two independent short-prompt, 256-output brackets (+0.6107% code/+0.7921% prose TPS in confirmation). The new long-prompt and 32-output safety brackets pass resources, parity, cached policy and all material-regression guards. The new long cohort qualifies generation on both tasks in one bracket; it is not independently confirmed for that cohort. Short 32-output code has a positive aggregate gain below its variation gate, so claim safety rather than a confirmed gain there.

| Fresh test | Task/input | Output tokens | Baseline TPS | Candidate TPS | TPS gain | Reply quicker | Average first-token delay | Decision |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| w02-fresh-screen | code/48 | 256 | 59.7203 | 60.0688 | +0.5835% | +0.5245% | +4.254 ms | code-only screen qualifies |
| w02-fresh-screen | prose/53 | 256 | 40.0623 | 40.3473 | +0.7114% | +0.6680% | +6.207 ms | startup ceiling exceeded |
| p07-long-safety | code/859 | 256 | 45.8500 | 46.1872 | +0.7356% | +0.4477% | -4.322ms | safety passed |
| p07-long-safety | prose/1004 | 256 | 46.8321 | 47.1436 | +0.6651% | +0.9010% | -23.625ms | safety passed |
| p07-short-answer-safety | code/48 | 32 | 63.9946 | 64.5608 | +0.8848% | +0.4366% | +1.387 ms | safety passed |
| p07-short-answer-safety | prose/53 | 32 | 52.4660 | 52.8550 | +0.7415% | +0.6366% | -0.960ms | safety passed |

All 12 full-model benchmark launches passed 312 answer/cache checks and exact parity on 192 fresh/warmup/cache output signatures. 72 fresh measured records, 24 fresh warmups, 96 cached records. Zero new swap in every launch. No source, model, precision or workload changes during measurement; no pooling historical data or summing percentages.

Targeted non-admin model-cache cleanup recovered 2.795456 GiB before the campaign, with sustained 35.514 GiB minimum available and zero new swap. It ran once, before all arms. It preserves the model files and does not close T3 or WiFiman. The cold first load is not a throughput gain.

The promoted launcher passed 16 actual Strata API English answer checks at temperatures 0 / 0.6 plus SSE streaming, exact selected engine/profile/native command, zero new swap and clean shutdown with 8095 / 8096 closed. No model server remains running. `Start Strata - Original Baseline.command` retains the original launcher bytes. All changes are local; nothing committed or pushed.

Next W02 work: investigate and change the first-token path before another fresh validation. Keep this failed general-use screen in the ledger. Do not rerun unchanged source to seek a passing bracket or relabel it after changing tolerances.

[Frozen protocol](plan.json), [frozen source receipt](frozen.json), [model comparisons and decisions](tracking.json), [model verification](model-verification.json), [actual app verification](launcher-verification.json), [promotion/rollback](promotion.json).
