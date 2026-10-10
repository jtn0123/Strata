# Warmed full-model MLX: 6 GB versus 12 GB expert cache

**Decision: the 12 GB cache qualifies for follow-up in this MLX configuration.** Both English workloads improve decode speed beyond twice the controls' variation, and first-token/reply time improves too. All four launches completed with normal pressure and zero new swap. This is one complete comparison, with two fresh launches per arm; an independent confirmation campaign has not run. No ordinary launcher is changed.

| Workload / engine metric | 6 GB control | 12 GB candidate | Improvement | Control drift |
|---|---:|---:|---:|---:|
| code / Decode TPS | 12.9696 | 14.5361 | 12.0782% | 1.4771% |
| code / First token (s) | 1.5245 | 1.1918 | 21.8269% | 0.9127% |
| code / 128-token reply (s) | 11.3157 | 9.9363 | 12.1901% | 1.3902% |
| prose / Decode TPS | 13.0559 | 15.7287 | 20.4717% | 0.1653% |
| prose / First token (s) | 1.9812 | 1.5189 | 23.3324% | 0.5736% |
| prose / 128-token reply (s) | 11.7125 | 9.5946 | 18.0816% | 0.0257% |

Each cell is the mean of the two launch medians, each median from three measured answers. Higher TPS is better; lower latency is better. Improvement percentages are against these fresh 6 GB MLX controls only. Both candidate launch medians beat both controls for every listed metric. No fixed minimum gain was required.

## Individual launches and resources

| Fresh launch | Code TPS | Prose TPS | Peak MLX arrays (GiB) | Minimum host available (GiB) | New swap |
|---|---:|---:|---:|---:|---:|
| 00-6GB | 12.8739 | 13.0451 | 13.5773 | 17.4308 | 0 |
| 01-12GB | 14.5943 | 15.5296 | 19.3372 | 13.4310 | 0 |
| 02-12GB | 14.4780 | 15.9278 | 19.3372 | 13.3396 | 0 |
| 03-6GB | 13.0654 | 13.0667 | 13.5773 | 17.1615 | 0 |

The expert-cache budgets use decimal GB. Allocation and host memory use GiB. MLX array peaks exclude other host allocations; process RSS is not total unified-memory use. The old 0.493 GiB of swap was unchanged. All launches met the original 28 GiB admission rule and stayed above the 8 GiB sustained floor; no guard was relaxed. Pressure was normal in all 803 samples. The host used AC power; recorded thermal/power status showed no warnings.

## Why more cache helped

| Workload | 6 GB logical expert data per decode | 12 GB logical expert data per decode | Reduction | Cache hit rate, 6 → 12 GB |
|---|---:|---:|---:|---:|
| code | 16.8266 GB | 8.4036 GB | 50.06% | 80.03% → 90.03% |
| prose | 14.9216 GB | 5.8434 GB | 60.84% | 82.29% → 93.07% |

These are logical expert-pager reads over the 127 decode steps after the first token, averaged across six measured answers per workload/arm. They are not SSD hardware bandwidth or NAND bytes: macOS can serve requests from its own file cache. More experts remain in the engine's cache, reducing miss/read work. The macOS file cache was uncontrolled and was not purged mid-comparison. System disk counters include unrelated host activity and are not used to claim SSD speed. No model-weight writes were measured.

## What was checked

The full pinned Q2_0 model retains 48 layers, all 512 experts and ten selected experts per layer. The pinned MLX revision is `4b6ce302ef41d9cab54985e4aa99fe52f4fd89f2`. Every floating parameter array was F32. Prediction helpers, suffix lookup and guess rows were disabled. Greedy sampling used temperature zero and seed 1234. Exact rendered English inputs were 44/53 tokens, output was capped at 128, context at 512, prompt chunks at 32. Each launch began with an empty expert store; conversation state reset before each answer, while the expert cache stayed warm within the launch.

All 32 input/output token lists, finish reasons, decoded positions and pending tokens agree across budgets, warmups and repeats. Eight fixed warmups were excluded, leaving 24 measured answers. Every response stopped at the length cap: these are complete capped measurements, not proof of a complete runnable code answer or an end-of-sequence response. The position/pending-token checks do not compare every internal state tensor. Equality with the original native engine, sampled output quality, API behavior and longer contexts remain untested.

The 184-test offline gate passed before freezing. Post-run analysis revalidates all 165 archived source/config/test files, source revisions, model identities, native vocabulary helper and 5,028 installed dependency artifacts. The saved comparison recomputes exactly. Only the owned child was cleaned up. No model server remains running.

## Cold load and excluded warmups

| Launch | Load (s) | First code TTFT / reply (s) | First prose TTFT / reply (s) |
|---|---:|---:|---:|
| 00-6GB | 15.5056 | 2.2559 / 12.0310 | 2.0514 / 11.5837 |
| 01-12GB | 12.7507 | 1.7166 / 10.2167 | 1.6234 / 9.6741 |
| 02-12GB | 13.1758 | 1.7203 / 10.2893 | 1.4809 / 9.6356 |
| 03-6GB | 13.1552 | 1.7413 / 11.4480 | 1.9579 / 11.3557 |

These warmups start from the launch's initially empty expert store, but the OS file cache may already be warm. No cold SSD latency or loading speed percentage is claimed. Timings include prompt evaluation and synchronized generation; rendering, tokenization, reset, detokenization, HTTP and browser work are excluded.

## Current keeper and next step

The normal P07 launcher retains its independent short-prompt/256-output **60.0842 TPS code / 40.3755 TPS prose** measurements. This paged F32, greedy, 128-output MLX experiment is a separate configuration and workload. Its gains cannot be added to P07 or treated as a direct native comparison. It establishes a useful cache improvement within the alternative engine, not a faster replacement for the app.

Next: implement a separate native/MLX compatibility diagnostic before adoption; then investigate a bounded 16 GB cache under fresh resource gates. A 16 GB cache is only a proposal, not a measured gain. R08 helper-planning reuse remains a separate native-path design. [Future requirements](NEXT-PLAN.json) retain these holds. Do not rerun this completed campaign unchanged or overwrite its evidence.

## Evidence

- [Frozen preregistration and pins](frozen.json), [archived source](source/), [live campaign receipt](comparison.json), [machine report](REPORT.json), [post-run verification](post-run-verification.json).
- [6 GB control 0](00-6GB/result.json), [12 GB candidate 1](01-12GB/result.json), [12 GB candidate 2](02-12GB/result.json), [6 GB control 3](03-6GB/result.json). Each folder also retains raw output, memory samples and pressure samples.
