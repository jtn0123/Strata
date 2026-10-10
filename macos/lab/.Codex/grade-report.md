# Codebase Grade Report

**Project:** Strata Mac Lab — Justin's M5 setup
**Audited:** 2026-10-06
**Stack:** Native ARM64 macOS; Python orchestration/Strata adapter; revision-pinned llama.cpp with Metal; local GGUF models; C++ diagnostic entry points.

## Summary

| ID | Category | Grade | Items |
|----|----------|-------|-------|
| A | Architecture & Design | B | 1 |
| B | Backend Quality | B− | 3 |
| C | Frontend Quality | N/A | 0 |
| D | Testing & Reliability | C+ | 1 |
| E | Security | B+ | 0 |
| F | Dependencies & Tech Currency | B− | 2 |
| G | Performance & Scalability | B− | 3 |
| H | Documentation & Onboarding | B+ | 1 |
| I | Developer Experience & Tooling | B− | 1 |
| **Overall** | | **B−** | **12** |

**Top 5 highest-leverage fixes from the original audit:** D1, G2, G1, B2, B1

**Follow-up, 2026-10-07:** A1, B1, B2, B3, D1, G1 and G2 are implemented locally and marked below; F2 has local dependency verification, with fresh-directory reproduction still pending. The offline suite now passes 72 tests, the native CPU self-test and five fatal-stop cases pass, and one bounded 4B control/split smoke passes with three matching response pairs and zero new swap. Full Flash routing/split behavior remains untested. The user has directed that OpenTaskManager's VM and local builds remain running; no further GPU/model tests will run in this preparation batch. See [current preparation and evidence](../bench/M5-AUDIT-PREPARATION.md). The grades above are the original audit grades, not a regrade of these changes.

This is a capable local research setup: the controls are isolated, raw evidence is retained, defaults remain separate from experiments, and the reports distinguish workload-specific gains from capacity and diagnostic observations. The grade is limited by concrete gaps in startup/resource accounting and the new diagnostic acceptance paths. These gaps do not, by themselves, invalidate the earlier workload-specific model speed results or establish a problem with the model's math.

**Scope and evidence:** Static audit of lab HEAD `0f30e8395e0599e47a7356872d16e843897f54ce`, mirrored under `Strata-Mac-Fork/macos/lab` at fork HEAD `f0234e4`. Hardware context is the M5 Pro, 18 CPU/20 GPU cores, 48 GiB unified memory; target is full Flash-Next GSQ-RCO Q2_0 with the packed mixed CPU/GPU helper. This is an audit of our provisioning, adapter, benchmark/diagnostic harness and future protocols, not a broad review of the downloaded Strata frontend or upstream llama.cpp. No model loads, GPU work, builds, package installation, benchmarks, services, downloads, source edits, commits or pushes were performed. Colima, Grafana and unrelated VM/build activity were left alone. Only this report was written.

The saved preparation receipt records 56 historical offline tests and a historical native CPU self-test, with `models_loaded`, `gpu_tests_run` and `benchmarks_run` false (`bench/features/20261006-m5-future-preparation.json:1163-1169`; offline log `:117-119`). The operation report records 23 historical CPU-reference GPU checks and 5520 historical matrix timings; its 34–42% projection is explicitly a cross-test estimate (`bench/M5-OPERATION-PROFILE.md:7-9,27,53-62,86-89`). Its first unchanged writing launch is clean; the second is excluded for 60.31 MiB new swap, so the refresh remains incomplete (`:64-82`). None of those suites was rerun during this audit. Dependency freshness, CVEs and present upstream PR status were not checked; no such claims are made here.

Two fresh, load-free, in-memory reproductions evaluated selected function definitions extracted from the current source: both diagnostic parsers accepted a fixture with an extra untimed computational GPU buffer, and the metric helpers accepted a NaN TPS gain. They used synthetic records, initialized no backend, ran no test-suite subprocesses and wrote no files. Static inspection of the two saved full-model phase logs found zero untimed completed buffers among their 1464 and 1631 records. G1 is therefore a demonstrated acceptance gap for future captures, not evidence that those historical phase runs were incomplete.

## Readiness verdict

**Full-model testing remains deferred.** Preparation and offline checks are complete for the existing local setup. A small-model smoke ran before the latest instruction to keep other work running; it validates diagnostic plumbing, not Flash expert reuse. No further model/GPU command should run during this preparation batch.

The original prerequisites D1, G1, B2, G2, B1, A1 and B3 are now implemented. Offline regressions, native CPU checks and a bounded small-model split smoke pass. The next authorized testing stage is full-model route capture, followed by bounded full-model split profiling. Each launch must pass a fresh headroom/quiet-host check and verify all required receipts. Existing swap and emergency stop thresholds are distinct from the acceptance rule of zero new swap.

The small smoke can establish callback/server plumbing and matched greedy output, not Flash expert reuse. Full-model routing and split behavior are still untested. Callback splitting deliberately changes synchronization and fusion; its timing must remain outside speed history. Any later speed candidate needs complete fresh control/candidate/candidate/control evidence, semantic checks, zero new swap and visible control drift; the incomplete historical refresh cannot substitute for it.

| Future experiment | Implementation today | Evidence still needed |
|---|---|---|
| Expert reuse | Diagnostic executable, padded-ID extraction, parser and matched-control runner staged; 4B server plumbing passes | Full-model target/helper roles, routing coverage, output parity and resource checks |
| Remaining GPU work | Split callback and submission-time attribution pass the bounded 4B smoke | Full-model GPU attribution, complete timestamp coverage, parity and measured perturbation |
| 8K context | Native context option plus protocol/fixture design | Long-input harness, recall fixture, allocation budget and matched timing |
| Mac SSD prefetch | Design only | File-specific waits, bounded implementation, isolated engine and correctness |
| Targeted GPU kernel | Design only; target intentionally unset | Measured target, actual patch/dispatch, reference math and fresh end-to-end comparison |
| Expert paging capacity | Feasibility design only | Selected capacity/speed goal, residency map, storage budget and correctness |

These distinctions agree with `config/m5_future_plan.json:24-110` and `bench/M5-FUTURE-TEMPLATES.md`. The last four are not ready-made candidates; the first two still need full-model proof.

---

## A — Architecture & Design — B

`scripts/engines.py:33-62,98-112` gives each optional engine a source/patch/build identity, and `scripts/metal_environment.py:15-30` clears inherited tuning/debug variables. The adapter is registered without editing the downloaded Strata checkout (`scripts/strata_server.py:1-9`), while future templates separate diagnostics, native candidates and capacity research (`config/m5_future_plan.json:24-110`). The main architectural gap is that the app and benchmark orchestration do not share the same exclusive model-running lease.

#### ~~A1~~ ✓ done 2026-10-07 — Make app launches participate in the benchmark lock
- **Where:** `scripts/run.py:54-85`, `scripts/benchmark.py:168-171`, `scripts/profile_m5_routes.py:298-302`, `scripts/check_memory.py:10-16`
- **What's wrong:** Benchmarks take `bench/.lock`, but `run.py` checks process names and launches without taking it. The process check and `Popen` are separate operations, so an app launch and benchmark can both pass the check before either server appears; the benchmark uses an ephemeral port and does not conflict with the app's fixed port.
- **Impact:** Major — two lab models can overlap, consuming the same 48 GiB budget and contaminating timings even though each launch passed its initial check.
- **Fix:** Give all model-loading lab entry points one shared nonblocking exclusive lease, held from preflight until their own child processes stop. Have the app use the same lease as benchmark/diagnostic commands; retain process scanning for servers outside that lease. Add a load-free contention test proving the loser never reaches `Popen`.
- **Effort:** S
- **Grade lift:** B → B+ (closes the gap between app and experiment isolation).

---

## B — Backend Quality — B−

The local adapter delegates tokenization/templates to the native engine and closes streaming transports on cancellation (`scripts/native_backend.py:13-39,53-128`). The new diagnostic checks exact prompt/output counts and matches greedy text/token IDs against an unchanged control (`scripts/profile_m5_routes.py:213-221,269-276`). Its remaining weaknesses concern observed input identity, persistent failure evidence and reliable termination after native diagnostic errors.

#### ~~B1~~ ✓ done 2026-10-07 — Tie captures to verified target/helper files and role geometry
- **Where:** `scripts/lab.py:11-16,27,38-45`, `scripts/profile_m5_routes.py:184-194,240-247,260-261`, `native/m5_eval_server.cpp:24-37,93-95`, `scripts/download_models.py:16-24`
- **What's wrong:** Launch resolution checks file existence, not an observed size/digest verification. The new capture records engine/build provenance but omits target/helper model specifications and verification receipts. Layer 48 is labeled helper and layers 0–47 target by hardcoded geometry; that matches the pinned Flash/MTP graph today, but the runner does not bind those assumptions to observed model identity or require helper coverage.
- **Impact:** Major — a changed local shard/helper can be presented as the intended experiment, or missing helper routing can leave an incomplete reuse result without a precise input identity.
- **Fix:** Create a trusted model-verification manifest for both target shards and the helper, recording observed file identity/stat metadata, size, initial verified SHA256 and expected architecture geometry. Rehash on identity/stat changes, with before/after identity checks; include those verification receipts and model registry specs in every capture/control pair and validate the expected target/helper routing coverage. Keep hash scans outside measured intervals and explicitly label their cache effects; do not reread tens of GiB immediately before every load merely to duplicate a valid verification.
- **Effort:** M
- **Grade lift:** B− → B (makes diagnostic conclusions traceable to actual inputs).

#### ~~B2~~ ✓ done 2026-10-07 — Enforce native diagnostic error and event-cap stop conditions
- **Where:** `native/m5_eval_server.cpp:68-102,151-153`, `scripts/profile_m5_routes.py:201-223`, `vendor/llama-m5-trace/ggml/src/ggml-backend.cpp:1964-1986,2001`
- **What's wrong:** The callback sets `failed` and returns false on an invalid event or the 300000-event cap. In the pinned scheduler, false on the ask callback means capture is unnecessary; false on completion breaks the current backend split, after which the scheduler can still return success. The server's failure flag is converted to an exit code only after `llama_server()` returns, while the Python runner does not watch diagnostic errors during the request.
- **Impact:** Major — a documented stop condition can instead disable capture or permit partial graph execution while the request continues; final rejection is useful but is not prompt termination.
- **Fix:** Add a diagnostic-local fatal-error path that immediately stops this child server, rather than using callback false as a general abort signal. Preserve one error marker, distinguish it from normal shutdown, and have the runner fail/stop its own child on that marker. Exercise ask/completion ordering, mismatched completion, cap exhaustion and extraction failure in a CPU-only callback-state harness; confirm the request cannot continue after the fatal flag. Preserve existing engine sources and launchers.
- **Effort:** M
- **Grade lift:** B− → B (turns diagnostic stop conditions into enforced behavior).

#### ~~B3~~ ✓ done 2026-10-07 — Persist failed captures even when cleanup verification fails
- **Where:** `scripts/profile_m5_routes.py:195-200,224-250`, `scripts/benchmark.py:189-222,347-364`
- **What's wrong:** `run_pass()` saves only after its unprotected cleanup and global `assert_no_model_server()` call. A failed stop check or cleanup error can prevent `capture.json` from being written and replace the original exception. The generic benchmark likewise creates its result directory before source/version checks but does not save the initial record until after those checks.
- **Impact:** Moderate — precisely the interrupted or failed runs that need investigation can leave incomplete evidence or lose their original cause.
- **Fix:** Write an initial running receipt as soon as the directory exists. Put final record persistence in the outermost `finally`; record cleanup/postflight errors separately from the primary run error, with explicit own-child exit status. A global refusal to proceed must still leave a failed receipt. Add mocked failures before launch, during load and during cleanup that assert a saved failed record and preserved primary cause.
- **Effort:** S
- **Grade lift:** B− → B (makes failure reporting as dependable as success reporting).
---

## C — Frontend Quality — N/A

N/A — this audit scopes our local lab and its setup/test harness; the UI is the downloaded Strata frontend, preserved by `scripts/strata_server.py:2-9`. No new frontend components or UI experiment are part of the staged work. Its broader accessibility and interface quality were not graded.

---

## D — Testing & Reliability — C+

Offline tests reject mismatched sources/settings, missing cases, small swap growth and bad GPU geometry (`tests/test_m5_preparation.py:62-92`; `tests/test_m5_operations.py:42-68,120-128`). The new tests exercise reuse arithmetic, parser ambiguity and honest empty templates (`tests/test_m5_future.py:22-89`), and the C++ self-test checks padded reads and six invalid inputs (`native/m5_eval_server.cpp:105-130`). However, the resource monitor's critical startup/error paths are not protected, and the new runner/native callback has no current end-to-end GPU/model proof; the report correctly treats that as the next gate rather than claiming that historical test counts establish it.

#### ~~D1~~ ✓ done 2026-10-07 — Make resource monitoring cover the entire launch and fail closed [BE]
- **Where:** `scripts/benchmark.py:43-55,57-97,227-231,347-356`, `scripts/profile_m5_routes.py:201-204,227-242`, `tests/test_m5_preparation.py:144-156`
- **What's wrong:** The initial swap value is taken in `Monitor.__init__`, after `Popen`, so immediate startup swap can be excluded. The monitor handles only `NoSuchProcess`; another sampling/file/permission error can end its daemon thread without setting a failure guard, and `finish()` does not report thread failure, sample count or complete coverage. The generic benchmark also stops monitoring before terminating the child.
- **Impact:** Major — a run can miss launch/teardown pressure or continue with its emergency guard no longer running, weakening the zero-new-swap evidence.
- **Fix:** Snapshot baseline swap and RAM before starting the child and pass that baseline into the monitor. Monitor through verified child exit; capture sampling exceptions as a fatal monitoring failure, terminate only the owned child, and require successful samples plus monitor-health/coverage evidence before accepting a run. Keep the emergency stop threshold separate from zero-growth acceptance. Add mocked startup growth, sampling failure, no-sample exit, ignored termination and teardown-growth cases; no model is needed for these regressions.
- **Effort:** M
- **Grade lift:** C+ → B (covers the safety and acceptance path that the existing one-threshold test misses).

---

## E — Security — B+

The lab uses loopback-only native and app bindings (`scripts/lab.py:27-34`; `scripts/run.py:67-89`) and explicitly restricts the backend destination to local HTTP (`scripts/native_backend.py:134-139`). The stop utility checks PID creation time, supervisor command and workspace before sending a signal (`scripts/stop.py:16-28`), avoiding accidental termination of a reused PID or another workspace. Downloads verify size/SHA256 before promoting files (`scripts/download_models.py:16-24,53-58`); no fresh exploit, dependency-advisory or network-exposure finding was established in this limited static scope. No filler security items are added.

---

## F — Dependencies & Tech Currency — B−

Native repositories and model revisions are pinned (`config/runtime.json:2-4`; `config/models.json:35-48`), Python packages use exact versions (`requirements.txt:1-6`), and optional engines verify source diffs and native artifacts (`scripts/engines.py:33-62,73-112`). That is strong provenance for local experiments. Reproduction is less complete for host-discovered dynamic dependencies and the baseline provisioning receipt; this grade concerns those observed gaps, not unverified package age or CVEs.

#### ~~F1~~ ✓ done 2026-10-07 — Make provisioning produce a verified baseline receipt
- **Where:** `scripts/provision.py:23-40`, `scripts/engines.py:78-112`, `scripts/prepare_m5.py:42`, `scripts/run.py:55`, `scripts/benchmark.py:181`
- **What's wrong:** Provisioning builds the baseline but never calls `write_receipt("baseline")`; a fresh provision therefore lacks the receipt required by later M5 preparation. App/generic benchmark launches explicitly allow a missing baseline receipt, while provisioning checks only checkout HEAD before rebuilding, not whether those sources are dirty. A reused virtual environment's Python version is also not checked even though creation requests 3.12.
- **Impact:** Moderate — a clean clone can stall on an undocumented prerequisite, and rerunning setup over modified native sources can build an unrecorded baseline before later verification refuses it.
- **Fix:** Validate both pinned checkouts' clean state and the intended Python version before dependency/build mutations. After a successful baseline build, generate its receipt and verify it; use the same receipt requirement for normal launches. Add load-free provisioning-command tests for dirty checkout, existing incompatible venv, successful receipt creation and a missing receipt.
- **Effort:** S
- **Grade lift:** B− → B (aligns recreated baselines with optional-engine provenance).

#### F2 — Include external dynamic dependencies in diagnostic provenance
- **Follow-up status, 2026-10-07:** Local diagnostic receipts now hash resolved linked dylibs (including OpenSSL 3.6.4) and record compiler/SDK provenance; execution rechecks those hashes. Fresh-directory reproduction and a portable dependency policy remain pending, so this item is not marked complete.
- **Where:** `scripts/profile_m5_routes.py:38-54,60-64`, `scripts/engines.py:73-75,98-108`, `bench/runtime/m5-eval/build.json:189-209`
- **What's wrong:** The diagnostic links Homebrew OpenSSL dylibs outside the engine directory, but its receipt hashes only static archives, the diagnostic executable and engine-local artifacts. Its verification can therefore succeed without checking a changed external library. The recorded command also embeds this checkout's absolute paths and a host-specific Homebrew version.
- **Impact:** Moderate — another Mac or an updated Homebrew installation can produce or execute a materially different diagnostic while the lab-local source/binary checks still appear sufficient.
- **Fix:** Record the resolved external dylib dependency set with identity/version/digest verification, compiler and SDK provenance; verify that set when executing the diagnostic. Represent lab files relative to the root and external dependencies separately. Choose and document either explicit dependency versions or an intentional feature-disabled build for the local diagnostic, and validate the resulting dependency set when later building in a fresh directory.
- **Effort:** M
- **Grade lift:** B− → B (extends provenance beyond libraries inside the checkout).
---

## G — Performance & Scalability — B−

The current M5 comparison checks planned settings, model/source identities, output counts, matched prompts and zero swap before aggregating fresh control/candidate passes, then reports control drift (`scripts/benchmark_m5.py:47-97`). The operation documentation correctly limits projections and excludes the swap-contaminated second baseline (`bench/M5-OPERATION-PROFILE.md:53-82`). This is good measurement discipline for one Mac; the weaknesses below concern acceptance/preflight logic, not evidence that a new shader is warranted or that a larger model will fit.

#### ~~G1~~ ✓ done 2026-10-07 — Reject untimed computational work in split-cost captures
- **Where:** `scripts/profile_m5.py:23-30,47-48`, `scripts/profile_m5_phases.py:42,56-62,79-83,116`, `scripts/profile_m5_routes.py:115,135-164`, `tests/test_m5_future.py:34-72`
- **What's wrong:** `parse_buffers()` drops completed zero-timestamp buffers into a separate untimed list regardless of their operation counts. Both the phase and split-cost parser subsequently use only timed buffers; the split parser's uncovered-work check cannot see a discarded computational buffer. A synthetic fixture with a completed untimed `ADD` alongside a timed matrix passes both parsers and reports all remaining generation buffers attributed.
- **Impact:** Major — future diagnostic costs can appear complete while some actual computational GPU work has no timing evidence. The two inspected historical full-model phase logs contain zero such buffers, so this reproduction does not invalidate those runs.
- **Fix:** Retain every raw buffer in phase/split coverage validation. Reject any untimed computational buffer for a cost capture, and explicitly count/report harmless metadata-only untimed buffers. Require the timed/untimed/attributed totals to reconcile against raw records, including role and request phase. Add the reproduced fixture as a regression to both parser paths.
- **Effort:** S
- **Grade lift:** B− → B (prevents incomplete GPU coverage from becoming a bottleneck claim).

#### ~~G2~~ ✓ done 2026-10-07 — Check RAM and host contention before every model launch
- **Where:** `scripts/profile_m5_routes.py:177-204,255-270`, `config/m5_future_plan.json:14-16,32,47`, `scripts/benchmark_tuning.py:114-132`, `bench/M5-OPERATION-PROFILE.md:78-82`
- **What's wrong:** The 34 GiB full-model RAM check runs once before a batch, although control/capture pairs repeatedly reload the model. Later launches have no fresh headroom check. Resource watchers record background CPU activity but do not classify contention or block a timed run; the recorded second baseline demonstrates that a background build and swap can overlap an otherwise successful launch.
- **Impact:** Major — the second or later launch can start under materially different memory/load conditions, risking pressure and making small speed differences unreliable.
- **Fix:** Immediately before each `Popen`, recheck the applicable full/small-model headroom threshold, pressure and no-server lease, and save that launch's preflight. Reuse the declared policy values rather than duplicating them. For speed comparisons, require a short observed quiet-host window and reject/label contention during measured passes; for deliberately perturbed diagnostics, retain the resource record and stop on pressure. Refuse or defer the lab launch without stopping unrelated VMs/builds. Add mocked decreasing-headroom and contention cases proving later passes never start.
- **Effort:** S
- **Grade lift:** B− → B (makes the stated memory/fairness prerequisites apply to every pass).

#### ~~G3~~ ✓ done 2026-10-07 — Validate numerical metrics before publishing percentages
- **Where:** `scripts/benchmark_vocab.py:29-44`, `scripts/benchmark_m5.py:85-97`, `config/m5_future_plan.json:18-19`
- **What's wrong:** The shared metric and percentage helpers accept nonfinite or nonpositive measurements. An in-memory fixture with NaN candidate TPS produces a NaN gain without rejection, despite the future plan expressly requiring finite positive matched metrics. Fresh-control aggregation validates identities/counts but not these numerical preconditions.
- **Impact:** Moderate — malformed timing evidence can enter a comparison instead of being rejected, and invalid percentages can reach JSON/Markdown reports.
- **Fix:** Validate each required TPS/time sample as finite and positive before median aggregation and again before division; validate acceptance counters separately while preserving legitimate absent draft-acceptance values. Reject invalid runs with a clear metric/case identifier. Add NaN, infinity, zero and negative fixtures and retain the existing fresh matched-control checks.
- **Effort:** S
- **Grade lift:** B− → B (makes the documented percentage rules executable).

---

## H — Documentation & Onboarding — B+

The README explains optional profiles and their workload limits, preserves defaults, and documents the lazy lookup table's difference from resident weights (`README.md:29-35,82-90`). The future cards honestly label staged versus unimplemented work and make `--run` opt-in (`bench/M5-FUTURE-TEMPLATES.md:7-38`; `scripts/prepare_m5_future.py:30-55`). The missing piece is one complete, fresh-clone route to the staged diagnostic, including prerequisite engine/receipt creation.

#### ~~H1~~ ✓ done 2026-10-07 — Document a complete clone-to-diagnostic preparation sequence
- **Where:** `README.md:39-54,94-110,148-154`, `bench/M5-FUTURE-TEMPLATES.md:26-38`, `scripts/prepare_m5.py:35-57`, `scripts/profile_m5_routes.py:34-45`
- **What's wrong:** The main recreation steps build only the baseline and derive Q3. Optional sharing/MMA steps are documented separately, but there is no complete sequence for recreating the packed helper, required baseline receipt, `m5-lab`, `m5-trace` and new diagnostic build. The documented `profile_m5_routes.py --build` assumes existing verified `m5-trace` build files.
- **Impact:** Moderate — a new checkout cannot reproduce the advertised staged diagnostic by following one documented path and may discover dependencies only through exceptions.
- **Fix:** Add one ordered preparation recipe listing prerequisites, engine/helper derivations, receipt checks and expected outputs, with separate labels for plan-only, build/CPU-self-test and model/GPU commands. Link that recipe from the future templates. State the intended Python version and external library policy after F1/F2. Validate the recipe later in a fresh directory without treating that validation as authorized during the current hold.
- **Effort:** S
- **Grade lift:** B+ → A− (connects otherwise careful documentation into a reproducible workflow).

---

## I — Developer Experience & Tooling — B−

Named experiment plans, isolated build scripts, command receipts and default plan-only behavior provide a useful local workflow (`scripts/prepare_m5.py:27-68`; `scripts/profile_m5_routes.py:287-302`; `scripts/prepare_m5_future.py:75-84`). Focused unittest files exist, but the lab/fork has no checked-in CI workflow, and the historical offline log is not a maintained validation entry point. The most useful tooling addition is a predictable load-free gate for these critical invariants, not a broad new lint/tooling project.

#### ~~I1~~ ✓ done 2026-10-07 — Provide an explicit offline validation gate
- **Where:** `tests/test_m5_future.py:1-92`, `tests/test_m5_preparation.py:44-61,144-156`, `tests/test_m5_phase_profile.py:52-83`, `bench/features/20261006-m5-future-offline.log:1-119`, project root (no checked-in CI/validation entry point)
- **What's wrong:** The saved 56-test result cannot be reproduced through one documented maintained command that clearly guarantees no model/GPU/build execution. Critical monitor, callback and cleanup regressions proposed above need a home in such a gate; currently they depend on manually selecting tests and understanding each file's behavior.
- **Impact:** Moderate — future changes can miss the safeguards that keep testing on hold and keep invalid evidence out of accepted results.
- **Fix:** Add one explicit offline validation command with a maintained test inventory and documented prerequisites. Include pure parser/template/aggregation tests and mocked lifecycle/resource checks; keep native CPU self-tests, sockets, builds and GPU/model suites clearly separate. Make a nonzero failure block experiment preparation acceptance, and wire the same gate into CI if CI is adopted. Do not add any background trigger or auto-resume behavior.
- **Effort:** S
- **Grade lift:** B− → B (makes the useful existing offline checks repeatable and hard to omit).

---

Projected grade lifts are category estimates for completed, validated fixes, not promised arithmetic increases in the overall grade. No fix was executed during the original static audit; the dated follow-up above records subsequent local work. The original grades remain unchanged pending a regrade. Full-model testing requires the user's later go-ahead and sufficient host resources.

**Remaining preparation follow-up, 2026-10-07:** F1, G3, H1 and I1 are now implemented and validated locally. The maintained gate passes 90 offline tests; provisioning prechecks pass, accepted cards require a current passing receipt, and the complete ordered recreation recipe documents the existing OpenSSL policy. F2 remains partial pending fresh-directory dependency reproduction; this is not a regrade. The separate upstream residual-fix candidate compiles, and 8K/SSD tools are staged, with GPU/model/read benchmarks still held. See [preparation evidence](../bench/M5-REST-PREPARATION.md).
