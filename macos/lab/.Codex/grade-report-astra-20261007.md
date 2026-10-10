# Codebase Grade Report — independent Astra audit

**Project:** Strata Mac Lab, M5 Pro / 48 GiB benchmark preparation  
**Audited:** 2026-10-07  
**Stack:** Python 3.12 orchestration, pinned llama.cpp/Metal engines, C++ diagnostics, local GGUF models.  
**Scope:** Current benchmark, diagnostic, capacity and storage preparation, including the 11-card packet `bench/plans/20261007T231811Z-m5-future`. The downloaded frontend and upstream codebase as a whole are outside scope.  
**Report identity:** These IDs belong to this dated report. `.Codex/grade-report.md` remains unchanged; its original grades and completion IDs are historical.

## Summary

| ID | Category | Grade | Items |
|---|---|---|---:|
| A | Architecture & Design | B | 0 |
| B | Backend Quality | C+ | 2 |
| C | Frontend Quality | N/A | 0 |
| D | Testing & Reliability | B− | 1 |
| E | Security | B+ | 0 |
| F | Dependencies & Tech Currency | B− | 2 |
| G | Performance & Scalability | C+ | 3 |
| H | Documentation & Onboarding | B | 1 |
| I | Developer Experience & Tooling | B | 1 |
| **Overall** | | **B−** | **10** |

**Top 5 highest-leverage fixes:** **G2, B1, G1, F1, D1**.

Isolation, raw evidence, testing holds and lifecycle safeguards are strong. Result acceptance and capacity accounting still need correction: the saved RAM report loses **104 MiB of separate KV allocations**, and comparisons accept incomplete or malformed evidence in reproduced cases.

### Separate readiness verdicts

| Question | Verdict |
|---|---|
| Preparation readiness | **B — substantially staged.** The 90-test offline receipt supports preparation. Correct accounting and acceptance/coverage gaps before relying on held trials. |
| Benchmark fairness | **C+ for small-gain decisions.** ABBA order, matched prompts and zero-swap checks are good; sustained contention, per-launch sample coverage and statistical uncertainty remain gaps. |
| New throughput benefit | **Unproved. No measured new TPS gain.** Compilation, synthetic/diagnostic preparation and storage plans do not establish it. |
| New capacity benefit | **Unproved.** The 8K runner/6144-token fixtures are staged; real tokenizer, memory, recall, continuation and rollback remain untested. Paging is a design. |
| Runtime state | **Full-model/GPU/SSD tests remain held.** No backend/model/native-test/build/download/socket/payload activity or service/process changes occurred. |

The historical clean baseline was approximately 47.61/48.91 synthetic TPS. Its next launch added **60.31 MiB** of swap and was already excluded; the two-clean-launch refresh remains incomplete. Fresh inspection found the expected workloads, repeats, positive cache reuse, matching native counts and 30 passing checks in both raw records. **The acceptance loopholes below do not establish malformed historical samples.**

## Evidence and validation boundary

- Independently read current scripts/tests/manifests, native source and saved receipts/logs using the `grade-codebase` rubric. No applicable `AGENTS.md` was found. Existing dirty preparation was preserved.
- Ran **22 pure/mocked audit probes**, denying native subprocesses, sockets and URL opens. They reproduce acceptance/lifecycle defects and inspect saved data; they are not runtime product validation.
- Reproduce with `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python .Codex/astra-audit-20261007/validate_audit.py`; see [validation.json](astra-audit-20261007/validation.json). `mock-coverage.log` is synthetic, not GPU evidence.
- The 90-test gate was **not rerun** or its receipt rewritten. The parent review verified its current fingerprint/preparation hashes. Native self-tests, historical 4B smoke and compilation were not repeated. No fresh CVE/upstream-status claim is made.
- Only this report and audit files under `.Codex/astra-audit-20261007/` were written. Original report SHA256 remains `5ace2cff62fc0ecf5e62ff7ef9ab3314c0b2fdb9a3a662f798121eced8a64759`.

## A — Architecture & Design — B

Optional engines have distinct source directories, exact patches and receipts (`scripts/engines.py:9-13,34-63,99-113`). App and current experiment entry points now share the exclusive lease (`scripts/run.py:53-55`; `scripts/benchmark_m5.py:187-190`; `scripts/benchmark_context.py:102-104`), while plan creation remains separate from execution (`scripts/prepare_m5_future.py:77-88`). Central numerical helpers reduce duplication, but broader acceptance and provenance rules still diverge between speed, baseline, context and diagnostic wrappers; B1 and F1 address that existing architectural seam without proposing an unrelated rewrite.

No separate architectural item duplicates those fixes.

## B — Backend Quality — C+

The generic producer records prompts, responses, counters and quality checks, validates fixed fresh token counts, and preserves failures through an outer save (`scripts/benchmark.py:307-360,364-417,425-457`). Finite-positive rate validation and strict draft-counter validation are real improvements (`scripts/benchmark_metrics.py:8-31,44-54`). The acceptance contract remains substantially weaker than the documented experiment: matching records to one another does not establish complete planned coverage, and native cache/count evidence is not fully validated.

#### B1 — Validate complete per-launch evidence before comparing results
- **Where:** `scripts/benchmark_m5.py:50-102`; `scripts/benchmark_context.py:28-60`; `scripts/benchmark_m5_decision_baseline.py:20-28,51-60`; `scripts/benchmark_metrics.py:20-31`; `scripts/benchmark_cache.py:22-37`; `tests/test_m5_preparation.py:23-41`; `tests/test_context_preparation.py:26-47`.
- **What's wrong:** Coverage is inferred from the first record, and samples are pooled before counts are checked. Reproductions accepted omitted real/2048-token workloads, one-plus-three duplicate candidate repeats instead of two per launch, truthy `passed: "false"`, and contradictory counters. The live cache helper accepted 512 input IDs with `prompt_n=513, cache_n=-1, predicted_n=0`. Baseline acceptance accepted missing monitor-health/teardown/quality evidence.
- **Impact:** Major — an incomplete or incorrectly parsed result can produce ordinary performance percentages. Reproductions lost three of seven required summary rows without rejection; missing evidence can therefore look like a valid narrower experiment. Actual historical records inspected here did not show those omissions.
- **Fix:** Share a required result contract across baseline/M5/context: canonical workload/check IDs, unique per-launch repeats, warmups, typed settings/booleans, monitor health and teardown. Validate every token/cache counter and reconcile input/output IDs and cache behavior. Bind commands/observed properties to the profile. Add the reproduced rejections using complete valid fixtures instead of empty timings and one anonymous check.
- **Effort:** M
- **Grade lift:** C+ → B− (turns comparison agreement into a complete evidence check).

#### B2 — Preserve the baseline batch receipt when postflight fails
- **Where:** `scripts/benchmark_m5_decision_baseline.py:35-41,43-50,64-70`; related outer-wrapper cleanup in `scripts/benchmark_m5.py:161-166` and `scripts/profile_m5_routes.py:354-356`.
- **What's wrong:** There is no initial save, and final `assert_no_model_server(); save()` skips persistence if postflight fails. A mocked launch failure followed by postflight failure left **zero batch receipts**; the primary error survived only in exception context. Generic run/route persistence is stronger.
- **Impact:** Moderate — precisely a failed first launch or failed cleanup can lose the batch-level reason, links and acceptance record. A generic child receipt may still exist; that does not replace the missing batch evidence.
- **Fix:** Save `running` immediately; retain primary/cleanup errors separately and persist from an outermost `finally`. Add mocked first-launch-plus-postflight and final-snapshot failures.
- **Effort:** S
- **Grade lift:** C+ → B− (extends dependable failure evidence to the outer experiment wrappers).

## C — Frontend Quality — N/A

N/A — this audit concerns benchmark/diagnostic preparation, not the downloaded Strata frontend. No interface or accessibility grade is inferred from backend evidence.

## D — Testing & Reliability — B−

The maintained offline gate has an explicit inventory and rejects unclassified tests and stale source fingerprints (`scripts/validate_offline.py:23-44`). Launch-monitor regressions cover startup swap, sampling failure, teardown and kill escalation (`tests/test_resource_monitor.py:21-77`); route lifecycle tests cover preflight and failure persistence (`tests/test_route_lifecycle.py:13-98`). Native callback errors now emit a marker and terminate the owned diagnostic immediately (`native/m5_eval_server.cpp:73-78`), with saved historical CPU fixtures. Those are meaningful safeguards, but test counts do not compensate for unrealistic comparison fixtures or a native correctness gate that accepts an unspecified surviving subset.

#### D1 — Require the intended CPU-reference case inventory, not merely a nonzero pass count [BE]
- **Where:** `scripts/verify_m5.py:14,27-37`; `scripts/verify_q2.py:14-47`; `vendor/llama-m5-correctness/tests/test-backend-ops.cpp:7249-7261,10387-10411,12249-12263,12325-12332`; `tests/test_m5_preparation.py:44-55`.
- **What's wrong:** Skipped/unsupported native cases disappear from the total, and `check_case()` accepts any positive all-passed count: mocked **1/1 passes** despite 16 selected cases. The filter selects rows 2/3/5/8 across four types (**16 of 28** available cases); requested 1/4/32 do not exist. A declared subset is valid, but depth-3's four-row verification shape is absent. Actual execution/fusion remains unproved.
- **Impact:** Major — a green correctness prerequisite can certify only a fraction of the intended dispatch/type/shape coverage. Compilation is not evidence that the residual fix works or that the faulty operation is used by the current Qwen graph.
- **Fix:** Pin expected case identities/counts per Tensor API mode and reject missing/skipped/duplicate required cases. Add required row shapes or accurately declare the subset. Later, when authorized, prove dispatch/fusion and fail-before/pass-after against an isolated control with identical tests and CPU reference. Establish Qwen graph exposure separately.
- **Effort:** M
- **Grade lift:** B− → B (makes the native prerequisite prove a defined scope).

The exact-token fixture preserves beginning/middle/end facts, hashes and three seeds (`context_fixture.py:9-38`), checking actual count and JSON (`:47-63`). Tests use a byte-level mock (`tests/test_context_preparation.py:15-24`). Real tokenizer behavior, long-history continuation/editing and targeted rollback remain untested; independent uncached recall requests do not prove them. This is a coverage limit, not a demonstrated tokenizer bug.

## E — Security — B+

Native services bind loopback and default to the local interface (`scripts/lab.py:27-34`; `scripts/run.py:74-77,95-97`). Launch leases and owned-child termination limit accidental interference, while model verification checks size, SHA256 and file identity (`scripts/model_provenance.py:12-24,43-77`). The audit's scope found no new security defect; the stronger needed provenance and validation checks are tracked under B and F. This is not an internet-facing security assessment or a fresh advisory scan.

## F — Dependencies & Tech Currency — B−

Runtime/model revisions and Python requirements are pinned, baseline provisioning now checks clean sources and Python 3.12 and writes a required receipt (`scripts/provision.py:20-38,69-74`). The diagnostic verifies its resolved external dylibs and compiler/SDK record (`scripts/profile_m5_routes.py:60-76`). The equivalent evidence is not consistently bound to ordinary speed runs or all native test inputs, and exact fresh-directory dependency reproduction remains honestly untested.

#### F1 — Bind speed and baseline results to observed model files and harness sources
- **Where:** `scripts/benchmark.py:238-282`; `scripts/benchmark_m5.py:126-156`; `scripts/benchmark_m5_decision_baseline.py:31-63`; `scripts/lab.py:11-16`; contrast `scripts/benchmark_context.py:65-85` and `scripts/profile_m5_routes.py:231-247,308-311`; `scripts/model_provenance.py:43-77`.
- **What's wrong:** Context/routes verify observed model files, but speed/baseline paths copy registry metadata and check existence only. Matching registries cannot establish identical GGUF bytes. `actual_sources` also omits local runner/quality/template code, leaving the dirty harness unbound to each result.
- **Impact:** Major — the same profile name and registry hash can describe different observed inputs, or different orchestration code, across a purported matched comparison. No current model corruption or in-run harness change was found; this is an unclosed provenance path.
- **Fix:** Reuse cached target/helper verification outside measurements; attach the receipt and recheck before launches/after completion. Hash the local runner/helpers/fixtures/configs and reject drift. Retain hash-scan/cache-effect disclosure and the existing identity/F_NOCACHE policy.
- **Effort:** M
- **Grade lift:** B− → B (extends the already implemented model-proof path to the experiments that publish speed results).

#### F2 — Close native tool and external-library provenance for ordinary engines
- **Where:** `scripts/engines.py:74-95,99-112`; `scripts/verify_m5.py:19-24,38-39`; `vendor/llama-m5-correctness/build/tools/server/CMakeFiles/llama-server.dir/link.txt:1`; `scripts/profile_m5_routes.py:60-76`; `bench/M5-PREPARATION-RECIPE.md:18-20`.
- **What's wrong:** Ordinary receipts hash the server/local dylibs but omit `test-backend-ops` and external OpenSSL 3.6.4. `verify_m5` records a stable current tester hash without checking the build's expected hash. Diagnostic-specific external checks do not cover other engines. Portable fresh-directory reproduction remains pending.
- **Impact:** Moderate — a replaced test executable or changed external dependency can escape ordinary engine verification while a comparison retains the same apparent build identity. Recording an arbitrary current hash is weaker than verifying it against the build receipt.
- **Fix:** Bind required testers and resolved external dependencies to build/execution receipts with compiler/SDK/options. Apply one reviewed policy throughout the chain and later verify a fresh-directory reproduction. Preserve measured engines and original F2's partial status.
- **Effort:** M
- **Grade lift:** B− → B (makes build provenance cover what actually executes).

## G — Performance & Scalability — C+

The plan distinguishes synthetic kernels, instrumented diagnostics, normal throughput, capacity and storage tests; that prevents invalidly adding unrelated percentages (`config/m5_future_plan.json:27-49`; `bench/M5-FUTURE-TEMPLATES.md:21-25,42-46`). Fresh comparisons preserve one changed setting, prompt hashes and control drift. The remaining limitations materially affect the trustworthiness of small gains and the capacity estimate, rather than establishing a need for a particular optimization.

#### G1 — Check launch headroom at the final boundary and classify contention during measurements
- **Where:** `scripts/profile_m5_routes.py:201-216`; `scripts/benchmark.py:290-300,80-94`; `scripts/benchmark_tuning.py:114-133`; `scripts/benchmark_m5.py:73-77,133-135,156-157`; `scripts/benchmark_context.py:35-37,64-87`; `scripts/profile_lookup_io.py:99-104`.
- **What's wrong:** RAM/pressure precede the three-second CPU window, and the fresher launch baseline is not checked against 34 GiB. A mock accepted stale 40-GiB headroom after conditions changed to 10 GiB. Measured CPU contention is recorded but never classified; context has no process watcher. Lookup's `small=True` bypasses its card's quiet-host rule.
- **Impact:** Major — a later memory-consuming build can invalidate admission or contaminate a timed pass without triggering zero-swap rejection. A pre-run quiet window cannot establish a quiet measured interval. No current held run was started or observed to suffer this condition during this audit.
- **Fix:** Check final headroom/pressure immediately before `Popen`. Classify timestamped measured-window contention, excluding owned-server work; reject/mark affected samples inconclusive without stopping unrelated work. State unmeasured GPU/thermal/power limits. Mock headroom drops, background work and watcher failure.
- **Effort:** M
- **Grade lift:** C+ → B− (extends fairness checks over the interval whose performance is being compared).

#### G2 — Keep separate attention and indexer KV allocations in the RAM report
- **Where:** `scripts/memory_budget.py:14-31,49-52`; `tests/test_memory_budget.py:11-29`; `bench/results/20261007T052606Z-m5-decision-baseline-1/server.log:219-227,408-415`; `bench/features/20261007-rest-memory-budget.json`; `scripts/benchmark_context.py:81-83`.
- **What's wrong:** `(role, backend, kind)` deduplication overwrites target attention KV **96 MiB** with indexer KV **24 MiB**, and helper **8 MiB** with indexer **2 MiB**. The actual saved report retains **26 of 130 MiB**, losing **104 MiB / 109,051,904 bytes**. Logged private components should total **1046.24 MiB**, not **942.24 MiB**.
- **Impact:** Moderate — total component accounting is understated by about 0.10 GiB and the KV component by **80%**, obscuring the very state growth/savings the 8K and later cache-precision trials need to assess. The report correctly says it is not physical peak memory or an admission decision, so this does not by itself prove unsafe launches or an 8K failure.
- **Fix:** Distinguish attention and QSA/indexer allocation identities. Deduplicate only repeated reservations of the same allocation. Regress against the actual four-cache log and later regenerate accounting/overview. Keep mappings, weights, private allocations and physical peak separate.
- **Effort:** S
- **Grade lift:** C+ → B− (repairs the present numerical basis for capacity review).

#### G3 — Give small-gain decisions an uncertainty and drift rule
- **Where:** `config/m5_future_plan.json:24-25,47-48`; `scripts/benchmark_metrics.py:34-40`; `scripts/benchmark_m5.py:90-102,106-117,156-157`; `scripts/benchmark_context.py:53-60,86-87`.
- **What's wrong:** Four pooled samples per arm come from only two launches. No launch variability, interval, drift limit or inconclusive verdict qualifies the 5% adoption threshold. Within-launch same-seed repeats are not independent host conditions. A synthetic **900% control drift** still produces a summary; interpretation is manual.
- **Impact:** Moderate — percentages around the adoption threshold, or the plan's 2–3% exploration cutoff, cannot be distinguished from launch variation with the current automatic result. A `passed` result means checks passed, not a statistically established gain.
- **Fix:** Use launches/paired blocks as independent units; retain both arms' per-launch summaries/dispersion. Predeclare effect/drift rules, report uncertainty and mark overlapping noise inconclusive. Add independent blocks only when authorized and needed; retain the short suite for screening.
- **Effort:** M
- **Grade lift:** C+ → B− (makes small differences interpretable without claiming precision the experiment does not have).

### Capacity and storage limits that should remain explicit

- The **35.03-GiB unique target tensors**, **1.17-GiB packed helper file**, **0.44-GiB observed repacking** and **26.82-GiB disk lookup table** are different quantities. Correcting G2 gives roughly **37.66 GiB** for the same component sum, not measured peak resident memory. File-page residency, driver memory, background apps and 8K state/scratch still need measurement. The 34-GiB admission threshold is a policy, not proof those components fit in the then-available RAM.
- At 8K, the candidate adds three 6144-token recall requests after the matched shorter speed/quality work (`scripts/benchmark.py:413-417`). This correctly avoids a fake 4K long-input TPS comparison. It also means total launch duration/load differs; speed acceptance and capacity/recall evidence should stay separately labeled. The fixture does not reach the entire configured 8192-token boundary.
- The storage plan uses at most 128 page-aligned ranges and **8 MiB total** across three passes, preserving bounds and repeated read digests (`scripts/profile_lookup_io.py:19-46,49-80`). This is a useful bounded `pread` microprobe. First-pass cache state is unknown; the same offsets repeat, sorting is always the third pass, checksumming and the prior pass affect subsequent conditions, and there is no native mmap-fault attribution or inference overlap. It cannot establish cold SSD throughput, lookup stall contribution, effective prefetch or TPS benefit. The default prepared plan has not read model payloads.
- Route/split callbacks deliberately synchronize and alter fusion. Their validated attribution is diagnostic ranking, not ordinary kernel cost or a speed gain (`scripts/profile_m5_routes.py:197-198`). Full Flash routing and full-model split coverage are still held; the earlier dense 4B smoke established plumbing only.

## H — Documentation & Onboarding — B

The current overview accurately distinguishes 90 offline tests, compiled candidates, held runtime work and unimplemented designs (`bench/M5-REST-PREPARATION.md:3-15,28-32`). The ordered recreation recipe documents local uncommitted source, Python, helper derivation and external-library limits (`bench/M5-PREPARATION-RECIPE.md:3-20,22-64`). Historical sections of the original report still refer to 72 tests and the earlier 8K design; those are dated history, not evidence the latest runner is missing. One real clean-recreation dependency mismatch remains.

#### H1 — Align diagnostic execution dependencies with the recreation recipe
- **Where:** `bench/M5-PREPARATION-RECIPE.md:26-34,42-50`; `scripts/profile_m5_routes.py:36-38,329-333`; `scripts/engines.py:9-13`.
- **What's wrong:** Build checks required/already-built engines, but `execute()` verifies **all eight**. The recipe omits unrelated `q2-masked` and `draft-vocab`, so a fresh setup cannot execute route/split diagnostics. Existing local builds hide this mismatch.
- **Impact:** Moderate — the prepared diagnostic can work locally yet stop at an undocumented prerequisite on recreation. Fresh-directory reproduction is still untested, and this source-level mismatch must be resolved before claiming it.
- **Fix:** Use required-plus-existing engines consistently, preserving every present engine. Mock a fresh setup containing only the recipe's dependencies and verify it reaches the authorized execution boundary.
- **Effort:** S
- **Grade lift:** B → B+ (removes a concrete obstacle in the otherwise useful ordered recipe).

## I — Developer Experience & Tooling — B

The explicit offline inventory, denied native/socket operations, source fingerprint and passing-receipt requirement for card generation make the held work repeatable (`scripts/validate_offline.py:23-44,65-96`; `scripts/prepare_m5_future.py:84-88`). Default plan commands and separate `--run` actions are understandable. The remaining tooling gap is that the execution paths do not bind themselves to the current gate that their cards require.

#### I1 — Require and retain the current offline receipt at each runnable queue entry
- **Where:** `scripts/prepare_m5_future.py:84-88`; `scripts/validate_offline.py:39-44`; `scripts/benchmark_m5.py:170-190`; `scripts/benchmark_context.py:94-104`; `scripts/benchmark_m5_decision_baseline.py:75-89`; `scripts/profile_m5_routes.py:360-375`; `config/m5_future_plan.json:72-75`.
- **What's wrong:** `require_pass()` gates card creation, not `--run`. Changed code or a failed suite after preparation does not block execution, despite the current-source prerequisite. This is separate from user test authorization.
- **Impact:** Moderate — the valuable 90-test gate is not an enforced prerequisite at the point where the current preparation becomes a real experiment.
- **Fix:** Require/attach the current passing receipt before native/model/storage execution. Reuse the verifier without automatically running tests or resuming work. Mock stale/failed receipts and assert no launch.
- **Effort:** S
- **Grade lift:** B → B+ (connects the maintained gate to the action it is meant to protect).

## Recheck of the original report's completed items

| Original item | Fresh assessment |
|---|---|
| A1 shared launch lease | Implemented in app/current benchmark entry points; contention test exists. No competing model or service was started here. |
| B1 model identity/route geometry | Implemented for routes, and reused by the new context wrapper. Ordinary speed/baseline paths still need it: new F1. |
| B2 fatal diagnostic errors | Implemented with immediate diagnostic-child exit 86 and error marker; CPU failure fixtures are present. Full-model behavior remains unproved. |
| B3 failure persistence | Implemented in generic run and route capture. Outer baseline batch still has the demonstrated cleanup hole: new B2. |
| D1 launch/teardown monitor | Substantially implemented: prelaunch baseline, fatal sampler error, child-only stop, final sample and coverage health. Sampling at 250 ms is not continuous physical-memory proof. |
| F1 baseline provisioning receipt | Implemented: source/Python prechecks and required post-build receipt. Fresh-directory execution remains unrun. |
| F2 external dependencies | Correctly remains partial. Diagnostic dylib verification exists; ordinary engine/tool closure and fresh reproduction remain open: new F2. |
| G1 untimed computational GPU buffers | Rejection is present in current parser paths and covered by regressions. No inference that earlier valid logs were corrupt. |
| G2 launch headroom/quiet host | Per-launch checks exist, but the original requested classification of contention during measured passes is incomplete. Final-boundary headroom also needs tightening: new G1. |
| G3 numeric metric validity | Finite-positive TPS/time and strict draft counters are implemented; fresh audit rejection controls confirmed them. This does not cover all token/cache counters or complete evidence: new B1. |
| H1 recreation documentation | The new recipe is useful and substantially complete for preparation; execution still requires two undocumented optional engines: new H1. |
| I1 maintained offline command | Implemented with 90 recorded tests and explicit exclusions. Binding the gate to later execution is a separate remaining step: new I1. |

## Practical next sequence

During the hold, address **G2, B1, G1, F1 and D1** with saved-data/pure/mocked validation; also close B2 and the small recipe/gate gaps. Preserve the original seven engines, the isolated eighth candidate, defaults, historical raw records and the current preparation receipts as historical evidence. Regenerate affected accounting/receipts only as part of an explicitly authorized fix, with an explained correction.

After a later testing go-ahead and suitable live conditions, complete the clean unchanged baseline, execute a defined CPU-reference residual case inventory, then perform bounded full-model route/split trials and the separate 8K trial. Real tokenizer/recall/state validation, sustained no-new-swap/headroom evidence and fresh matched throughput results are still required. Native prefetch, targeted kernels, expert paging and quantized KV remain later dependency-gated work. **This audit establishes no new TPS or capacity improvement.**
