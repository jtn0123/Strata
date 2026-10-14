# Post-merge baseline and MTP helper pool experiment

Status: R0 validated; R1 diagnostics and one independent speed confirmation completed. Persistent helper pools remain experimental and off by default. No new speed improvement is adopted.

Hardware: 48 GiB M5 Pro Mac, AC power, Automatic mode. Same full Flash-Next Q2 target and packed shared Q3 helper; resident Metal target, mixed helper placement, eight helper workers, width three/confidence zero, kept `m5-small-stack/small-reduce` settings, Tensor API, 4K/F16.

## R0: actual app validation and baseline

Balanced, Code Editing and Long Documents each pass the existing real-model API/integration checks and clean shutdown. The latter uses actual target/helper batch 1536/1536; the other profiles use 512/512. Real cancellation, request reuse, streaming, both API formats and input rejection were exercised. These functional checks are not speed benchmarks.

The native endpoint inside the owned Code Editing app then completed 18 normal-EOS English answers (six tasks, three repetitions), plus three complete-file app API edits. Greedy token IDs/text remain identical across each task’s repetitions; prompt cache is disabled and native counts match emitted tokens.

First encounter below follows functional validation: it is not a cold launch or cold SSD measurement. Prose uses the Code Editing drafting policy, so these numbers are not a refreshed Balanced-chat benchmark. Replays share learned lookup/kernel/OS state and are reported separately.

| Task | Output tokens | First generation TPS | Input TPS | First text (s) | Full reply (s) | Replay generation TPS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| javascript-catalog | 270 | 88.02 | 457.10 | 0.749 | 3.805 | 90.01 |
| json-client | 235 | 86.93 | 454.79 | 0.669 | 3.361 | 90.22 |
| long-prose | 11 | 55.67 | 519.29 | 4.518 | 4.698 | 58.35 |
| long-retrieval | 31 | 62.10 | 501.49 | 4.651 | 5.134 | 73.79 |
| python-ledger | 243 | 87.35 | 440.30 | 0.718 | 3.489 | 90.23 |
| short-prose | 204 | 36.76 | 162.74 | 0.295 | 5.818 | 86.57 |

R0 Code Editing admission was 34.010 GiB available, minimum during that launch 2.615 GiB; normal pressure and zero new swap. Both other profiles passed their unchanged resource guards. After owned model shutdown, macOS released enough memory for subsequent isolated runs without closing user apps or changing the 34 GiB admission/1 GiB running floor.

## R1: mechanism, correctness and observer limits

An isolated `m5-waits` clone adds opt-in diagnostics around existing MTP process/draft/accept scopes, CPU graphs, pool creation/free, bounded worker observations and the four existing Metal completion waits. It adds no GPU waits or graph evaluation callbacks. Both `GGML_M5_WAIT_TRACE` and `GGML_M5_HELPER_POOL` are off by default; maintained launch environments discard incoming values. The kept engine and ordinary profile settings remain unchanged.

The candidate attaches owned persistent pools to the MTP context through the existing common-threadpool API. It preserves helper worker/poll/priority/mask parameters, model state, draft width, precision and arithmetic. Context/model teardown precedes pool destruction.

Qualification completed 506 matrix CPU-reference checks and 16 fused-residual checks, followed by 48 full native answers across kept/untraced/traced/traced-with-pool variants. Every prompt, complete output token ID and text matches. All four variants also pass actual adapter whole-file parity, cancellation and subsequent request reuse, then owned shutdown. Both untraced speed brackets below complete 72 answers each; all 144 outputs match across arms and resource/activation gates pass.

The traced control creates and frees 2,002 disposable helper pools across 12 requests; the enabled candidate has zero disposable helper graphs in its matching 12 requests. Lifecycle wall envelopes total 108.345 ms across the control requests. First-file lifecycle envelopes are 9.468–9.616 ms (about 0.25–0.29% of those replies); first short prose is 39.483 ms (0.72%). These are observer-affected envelopes, not isolated CPU time or a promised speed gain. Helper CPU/GPU waits overlap and must not be added; waits can include completion of previously submitted GPU work.

Worker observations inside the first retrieval helper scopes capture requested QoS class 21 on auxiliary workers and 33 on worker 0. Apple’s SDK defines 21 as Default and 33 as User Interactive ; 17 would be Utility. Requested QoS does not measure effective boosts or prove an under-priority bottleneck. The 512-sample cap is exhausted after early requests; later empty observations are not proof that workers disappear. See [Apple’s public definitions](https://github.com/apple-oss-distributions/libpthread/blob/main/include/sys/qos.h). No QoS, FIFO/realtime or affinity change was made.

## Same-binary speed comparison

Each independent bracket is control/candidate/candidate/control, one model at a time, tracing off, identical binary/settings/model/workload order. Only persistent-pool enablement changes. Three complete replies per task per launch; first encounter and replay remain separate. No cache cleanup occurs within either bracket. A small gain must be positive, exceed twice its own closing-control drift, and have both candidate launches beat both controls; there is no fixed 1% minimum.

| Task / phase | Screen control TPS | Screen pool TPS | TPS change | Reply quicker | Confirm TPS change | Confirm reply quicker |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| long-retrieval / first-exposure | 65.710 | 65.878 | +0.256% | -0.742% | -0.946% | -0.727% |
| long-retrieval / replay | 73.501 | 73.493 | -0.012% | -0.738% | -0.106% | -0.857% |
| long-prose / first-exposure | 57.679 | 57.856 | +0.307% | -0.678% | -1.244% | -0.875% |
| long-prose / replay | 57.490 | 58.034 | +0.946% | -0.483% | +0.288% | -0.985% |
| python-ledger / first-exposure | 87.724 | 87.682 | -0.049% | -0.080% | -0.427% | -0.866% |
| python-ledger / replay | 89.987 | 89.877 | -0.123% | -0.143% | -0.155% | -0.163% |
| javascript-catalog / first-exposure | 88.024 | 88.002 | -0.025% | -0.136% | +0.197% | -0.022% |
| javascript-catalog / replay | 89.709 | 89.787 | +0.087% | +0.078% | -0.086% | -0.144% |
| json-client / first-exposure | 86.981 | 86.939 | -0.048% | -0.038% | -0.026% | -0.238% |
| json-client / replay | 90.028 | 89.966 | -0.069% | -0.054% | +0.044% | +0.049% |
| short-prose / first-exposure | 39.554 | 39.667 | +0.286% | +0.261% | +0.355% | +0.319% |
| short-prose / replay | 86.670 | 86.737 | +0.078% | -0.104% | +0.038% | -0.065% |

First short prose passes the screen’s generation/reply gates: 39.554→39.667 TPS (+0.286%), with 0.261% quicker full reply. Confirmation averages 39.374→39.514 TPS (+0.355%), with 0.319% quicker reply, but its control drift is −0.193% TPS: twice the drift exceeds the gain, and one candidate (39.401) is slower than the opening control (39.412). Confirmation therefore does not qualify. This is retained as a possible small first-prose signal, not rejected merely because it is below 1%.

Editing is effectively flat. Some long/prompt-latency scopes regress in confirmation (including first long-prose −1.244% generation and Python first-text 2.641% longer). The candidate is not promoted to normal inference. Revisit only with a distinct mechanism, stronger independent evidence or a targeted investigation of the slower prompt path; do not repeat unchanged pool toggles hoping for a broad gain.

All 12 accepted qualification/screen/confirmation launches pass normal pressure, zero new swap and final child-exit checks; the minimum available RAM across them is 2.801 GiB. Model/engine/source/runner identities are frozen per campaign; old existing swap is not reported as new swap.

## Rejected attempts and reproducibility

- Two R0 verifier launches were held below 34 GiB before loading a model. Both receipts remain excluded. A direct normal launcher later met the original threshold with less coordinator startup memory.
- Cache-release helpers initially refused unexpected symlink-resolved paths before touching them; the corrected helper was restricted to exact verified model/engine files, read-only mappings and unchanged file identities. Its small cache recovery was not a speed experiment.
- Two isolated native builds failed at the bundled UI gzip path through a checkout alias. Their logs/build trees remain preserved. A fresh build using the physical source path and native bundled/prebuilt UI disabled succeeded. The maintained Python app/UI was not changed; both speed arms use the same isolated build.
- Qualification v1 completed 12 native answers but rejected an adapter assertion that included the EOS marker in displayed text. The runner was corrected to follow the actual shell: require the final supported stop token, compare all token IDs including that token, then decode visible IDs before it. V1 remains failed/excluded. A separately frozen v2 campaign passes the corrected checks.
- No failed, traced or capped response is folded into accepted speed results. Native responses, per-request trace slices, failed receipts and original campaign runner snapshots stay ignored locally.

Public source is bound by `config/m5_waits_experiment.json` and the complete `patches/mtp-m5-waits.patch` at base `d81235049384534c167caea52b85a694f6103d14`. An isolated build requires Release/Metal/embedded shaders/tests, native UI/prebuilt UI off, physical source paths and a verified build receipt. The older generic preparer does not yet expose this alias; do not describe it as one-click provisioning.

## Remaining ordered work

1. R2 stays conditional: helper workers were observed at Default, not Utility/background. A helper-only User Initiated QoS trial needs a separate Apple pthread implementation, observed successful application and unchanged target/caller QoS. Current `--prio` branches use FIFO and are not substitutes. No demonstrated scheduling bottleneck or speed estimate is claimed.
2. R3 needs operation/shape attribution on actual 512/1536 prompt chunks before transplanting one parent-inspired matrix operation. These wait envelopes cannot identify a dominant shader or transfer the parent backend’s 57% input improvement.
3. R4 remains a distinct bounded Apple advisory-read candidate for eligible lazy rows: prove page bounds, file lifetime, returns, residency/page-ins and useful overlap, then match first-exposure and warm replies. Current results do not show physical SSD wait.
4. R5 retains failure-contract and parked D01/D02 harness repairs before those tools are reused. They are quality work, not TPS gains.

Local quality: 356 guarded offline test methods; all 21 maintained modules pass Ruff/format/mypy/size, 14 strict; focused coverage 87.37% lines/75.28% branches. The new parser has 100% line/branch coverage, original 20 per-file floors stay unchanged and expanded aggregate floors are 86%/74%. Hosted CI/Sonar and public PR readiness remain separate gates.
