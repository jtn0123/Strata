# Codebase Grade Report

**Project:** Strata — maintained Mac app, runtime and inference lab
**Audited:** 2026-10-14
**Source:** `e460a0f14491dbc3a13d79398b31936bf21e6049`
**Stack:** Python 3.12 / pinned llama.cpp Metal / static browser JavaScript; Node lint/test tooling.

Three delegated audits plus coordinator validation cover the Mac maintenance scope defined in `macos/lab/AGENTS.md`. Inherited PC source is outside this grade. The earlier tracked report, `macos/lab/.Codex/grade-report.md`, is preserved. New findings are plans, not implemented fixes; no application/vendor code, profile, model, service or power setting changed.

## Summary

| ID | Category | Grade | Items |
| --- | --- | --- | ---: |
| A | Architecture & Design | B+ | 1 |
| B | Backend Quality | B− | 5 |
| C | Frontend Quality | B | 2 |
| D | Testing & Reliability | B− | 9 |
| E | Security | C+ | 3 |
| F | Dependencies & Tech Currency | B+ | 2 |
| G | Performance & Scalability | B+ | 2 |
| H | Documentation & Onboarding | B− | 2 |
| I | Developer Experience & Tooling | B+ | 1 |
| **Overall** | **Maintained Mac scope** | **B−** | **27** |

**Top 5 highest-leverage fixes: D1, D2, E1, B5, H1.**

Working model speed, pinned sources, typed modules and substantive tests are real strengths. The largest weaknesses are how the HTTP integration handles bad clients, how validation publishes failed outcomes, and whether a new checkout can recreate the adopted default. Security and reliability weigh more heavily than the clean lint/format result in this overall grade.

## Evidence and limits

- Fresh local baseline: 356 guarded offline methods, 15 benchmark-signal methods, one app-signal method/six cases, two port checks, five protocol methods, 27 Node tests; all pass. All 21 maintained modules pass full Ruff/formatter/mypy/size; 14 strict, no size warnings; largest maintained Python file is 500 lines. Focused coverage passes 87.37% lines / 75.28% branches, floors 86%/74%; this is not whole-repo coverage.
- Six owned-file advisory API cases pass: initially 0/64 pages resident; MADV_WILLNEED and F_RDADVISE each load 64/64 at the first poll in both repetitions. All checksums match; measured peak RSS 2.906 MiB, no observed new swap. This is an API/residency feasibility proof, not model TPS or SSD bandwidth.
- CPU-only upstream route-geometry proof passes at 15.6 MiB RSS. Scratch/tile upper bounds are arithmetic, not actual GPU work or speed percentages. Initial classifier error was excluded and retained before the corrected proof.
- Exact-loopback mock-handler, native-stream, malformed-receipt, signal and classic-script DOM fixtures establish the listed failure paths. No full-model/GPU experiment or real browser/accessibility pass was performed for this audit; real-model evidence in the existing R0/R1 report is prior completed proof.
- Current npm audit reports zero advisories; exact-version OSV queries report zero matches for 15 Python pins. These queries omit native/OS components and do not prove an absence of vulnerabilities. [Node release support](https://github.com/nodejs/Release) supports the configured supported lines; no blind upgrades are proposed.
- Full historical receipts were not invalidated: the probes deliberately remove or contradict required evidence, and demonstrate that particular tools can accept it. Current R1/E01 campaigns have stronger frozen and resource contracts. Watchlist D9 is not a reproduced model failure.
- All owned probe children/listeners were closed/reaped; no unrelated app was closed. Raw probes, API error logs, source snapshots, registry responses and resource receipts remain ignored under `macos/lab/bench/features/20261014-repo-audit/`.

## Recommended sequence

1. D1/D2 before more heavy profile testing; then E1/E2 and B1/B2/B4/B5/B3/E3 at the maintained HTTP/native boundary. Include C1/C2 so Monitor clearly distinguishes current, stale, missing and historical measurements.
2. H1/F1/F2 and A1/I1 make setup, build policy and current research drivers reproducible; do not rebuild accepted control engines while doing this. D8 must be repaired before N01 reference checks if the shared `verify_q2.check_case` is reused; D3–D7 are required before their older tools are reused.
3. G1 attribution plus isolated integrated routed-map reference proof, then one trace-off full-model screen and independent confirmation. Separately G2 bounded Apple advice. D9 checkpoint validation comes before checkpoint-copy omissions or richer reuse.
4. Remaining researched ideas, exact pins, scope/stop gates and 20 prioritized bug/gap entries are in `macos/lab/bench/research/20261014-repo-audit/REPORT.md`.

---

## A — Architecture & Design — B+

The runtime has clear retained-vendor boundaries: `macos/lab/scripts/strata_server.py` installs the local adapter/service/UI around pinned source, while `macos/lab/scripts/engines.py:111-150,202-222` verifies exact native revision, modified-file inventory, source diff and build artifacts. Normal profiles have one explicit configuration (`macos/lab/scripts/runtime_profiles.py:13-59`), and opt-in native tracing/worker-pool settings are cleared from inherited environments (`macos/lab/scripts/metal_environment.py`). The main remaining structural problem is the divergent engine/build registries: a selectable engine is not necessarily reproducibly buildable through the public preparer.

#### A1 — Put experiment build requirements beside the engine manifest
- **Where:** `macos/lab/scripts/engines.py:11-40`, `macos/lab/scripts/prepare_m5.py:31,42-58`, `macos/lab/config/m5_waits_experiment.json`, `macos/lab/bench/research/20261014-baseline-and-helper-pool/REPORT.md:67-71`.
- **What's wrong:** `m5-waits` is registered as a selectable engine, but the generic builder excludes it and has no way to represent its known native-UI-off/physical-path requirements. The preceding two native builds failed on the symlinked UI asset path; the successful recipe currently survives as an ignored campaign driver and prose. Merely adding the alias to CLI choices would still reproduce the wrong policy.
- **Impact:** Moderate — each new engine requires manual edits and private build exceptions, making fresh setup and future experiments more error-prone.
- **Fix:** Give manifests explicit preparation support/build-policy metadata and derive eligible preparer choices from that registry. Validate/build with resolved source paths, per-engine native UI flags, target list and existing control pin checks. Add load-free tests for unsupported aliases, the waits build plan, existing source refusal, and an unchanged kept engine. Record the effective policy in the build receipt. Do not rebuild or promote current measured engines.
- **Effort:** M.
- **Grade lift:** B+ → A−, by making the experimental lifecycle reproducible without private driver knowledge.

---

## B — Backend Quality — B−

The retained native adapter maps transport faults to the actual shell exception type and preserves cancellation/EOF/final-drain semantics (`macos/lab/scripts/native_backend.py:23`, `:241`, `:271`, `:367`). All three profiles have real-model API and restart evidence. The typed core passes current lint/mypy, but reachable malformed API requests are not normalized before the pinned handler and malformed native completion packets/counters are still accepted. Grade reflects runtime boundaries, not observed wrong answers from the pinned model.

#### B1 — Malformed API objects drop the connection
- **Where:** `macos/lab/scripts/web_ui.py:14-21` (maintained wrapper); reachable pinned `macos/lab/vendor/Strata-macOS/serve/server.py:971-988`, `macos/lab/vendor/Strata-macOS/serve/frontend.py:132-160`.
- **What's wrong:** The wrapper delegates JSON shape validation to code that assumes mappings/lists. JSON `[]`, `null`, `messages:null`, a scalar message, and scalar `chat_template_kwargs` raise uncaught AttributeError/TypeError.
- **Proof:** `probes.json` keys `api_schema_*`, `api-errors.log`: actual `RemoteDisconnected` and matching stack traces; expected structured HTTP 400 before tokenizer/native work. Each error is independently reachable; grouped as one schema-boundary defect.
- **Impact:** Moderate — external clients get failed connections rather than actionable input errors and may retry.
- **Fix:** Add a typed request normalization/validation boundary in the maintained handler before delegating both APIs. Reject invalid containers/roles/content/kwargs and preserve explicit tool/image rejection. Do not patch vendor.
- **Effort:** M.
- **Validation:** Ephemeral-handler tests for both APIs and each malformed shape; assert 400, no backend calls, healthy subsequent valid request.
- **Grade lift:** B− → B for the API boundary, alongside B2.

#### B2 — Numeric API parameters are coerced or forwarded without a contract
- **Where:** `macos/lab/scripts/native_backend.py:343-365`; maintained handler boundary `macos/lab/scripts/web_ui.py:14`; reachable pinned `macos/lab/vendor/Strata-macOS/serve/server.py:1021`, `:1047`.
- **What's wrong:** `max_tokens:true` and `1.7` both become cap 1; nonfinite temperature and out-of-range top_p reach engine sampling. JSON decoder accepts NaN unless explicitly rejected. The adapter serializes these unchecked values to native completion.
- **Proof:** `api_max_tokens_bool`, `api_max_tokens_fraction`, `api_nonfinite_sampling`: HTTP 200 with cap 1 and engine sampling `{temperature:NaN,top_p:-1}`. Expected strict integer token cap and finite sampler values in supported ranges, with 400 before inference. NaN max_tokens already returns 400; documented nonpositive/unlimited semantics are not counted as a bug.
- **Impact:** Moderate — surprising truncation, backend errors or unreviewed settings; not proven wrong model math.
- **Fix:** Define request-level strict integers/non-bool scalars and finite range checks, retaining documented zero/-1 token-cap semantics where intended. Validate before queue/native transport, with `allow_nan=False` at serialization.
- **Effort:** M.
- **Validation:** Bool/fraction/Infinity/NaN/out-of-range cases for both APIs, exact zero handling, no backend call on reject.
- **Grade lift:** B− → B with B1.

#### B3 — Stop sequences are silently ignored
- **Where:** `macos/lab/scripts/native_backend.py:343-365`; maintained handler `macos/lab/scripts/web_ui.py:14`.
- **What's wrong:** The OpenAI-compatible API accepts `stop` but the completion payload never forwards it and the shell parser does not implement it. Anthropic stop_sequences similarly has no adapter path.
- **Proof:** `api_unsupported_stop`: request `stop:"STOP"` returns HTTP 200/content `hello STOP world`. Expected stop before the delimiter, or explicit unsupported-feature400. OpenAI case is socket-proven; Anthropic omission is source-confirmed only.
- **Impact:** Moderate — client delimiters/privacy boundaries or parsers expecting an early stop may see extra text.
- **Fix:** Initially reject nonempty unsupported stop/stop_sequences explicitly. Implement matching only after a declared contract for buffered/split chunks and bounded native cancellation.
- **Effort:** S (initial explicit rejection).
- **Validation:** Split-delimiter stream and non-stream tests, or explicit400/no backend invocation for unsupported requests.
- **Grade lift:** B− → B when supported capability reporting is truthful.

#### B4 — Native stream emits invalid token IDs
- **Where:** `macos/lab/scripts/native_backend.py:233-239`, `:254-269`.
- **What's wrong:** Tokenize responses are strictly validated, but completion packets accept boolean/negative token IDs unchanged. They can be yielded downstream for detokenization instead of failing at the native boundary.
- **Proof:** `native_bad_ids`: fixture emits `[true,-4]`, no error, final native timing retained; expected structured native error and no successful-rate record. Transport still closed, so this is not a leak.
- **Impact:** Moderate — native/schema regressions can corrupt usage/output handling or fail later with a less useful error.
- **Fix:** Validate completion JSON object, tokens list/nonnegative exact integers, stop flag shape, and error schema in the reader; convert rejection to EngineDied, clearing native metrics.
- **Effort:** S.
- **Validation:** Bad IDs/containers/stop types, valid grouped packets, EOF, cancellation and request reuse.
- **Grade lift:** B− → B alongside B5.

#### B5 — Impossible native counters can become UI performance facts
- **Where:** `macos/lab/scripts/native_backend.py:280-293`; `macos/lab/scripts/performance_metrics.py:51-67`.
- **What's wrong:** Final timings are accepted once nonempty, without checking emitted-token count, complete prompt/cache count or finite positive timing fields. Monitor treats a positive native rate as native facts even if its counters are impossible. Benchmark paths already contain the stronger reusable completion-count contract.
- **Proof:** `native_bad_counters`: two actual emitted IDs, request prompt1/cap8, but `predicted_n:800`, `prompt_n:20`, `cache_n:100`, `prompt_ms:-5`, TPS400000 all retained. Expected reject/unreported invalid native timing. This is a malformed-proof fixture, not a measured400000TPS result.
- **Impact:** Moderate — future engine changes could show convincing but wrong speeds/cache counts or silently accept an incomplete answer.
- **Fix:** Apply a runtime-specific final counter/timing contract (reuse common validators where appropriate). Preserve legitimate EOS-consumer-close semantics and native token counters; an invalid final record must not become a native rate.
- **Effort:** M.
- **Validation:** Counter mismatch, cached prompt conservation, cap overflow, nonfinite/negative times, grouped EOS and bounded final drain; verify failed rows have no native TPS.
- **Grade lift:** B− → B and improves trustworthy monitoring.

---

## C — Frontend Quality — B

The maintained interface gives missing counters explicit unknown states (`macos/lab/web/mac.js:306-329`), contains settings focus and preserves keyboard controls (`:193-265`), and prevents incomplete SSE EOF from becoming successful completion (`macos/lab/web/ui-state.js:48-100`). Metrics export uses explicit settings/request allowlists and bounded history (`macos/lab/web/performance.js:5-12,62-74,139-147`), with whole-script-order fixtures in `macos/lab/tests/ui_installation.test.cjs`. Two remaining failure states can display stale performance as current; the grade also stops short of an A because this audit did not exercise a real browser, layout or physical accessibility.

#### C1 — Detect a stalled telemetry response and expire its last readings
- **Where:** `macos/lab/web/ui-state.js:4-20,145-151`, `macos/lab/web/mac.js:268-298,342-355`, pinned poll contract `macos/lab/vendor/Strata-macOS/serve/web/app.js:145-162`; `macos/lab/tests/ui_installation.test.cjs:111-143`.
- **What's wrong:** The metrics request has no deadline, and the next poll is scheduled only after the awaited request finishes. A connected HTTP response that stalls therefore prevents all further polling. `updatedAt` is saved but is never consulted to mark an old sample stale. A tiny whole-script fixture observed a first successful Ready response, then an unresolved second metrics fetch with zero new poll timers, no cancellation/deadline signal and a still-Ready pill.
- **Impact:** Moderate — Monitor can look healthy while its RAM, swap and speed readings have stopped refreshing, precisely when those readings matter.
- **Fix:** Add a bounded timeout for `/metrics` only in the maintained fetch compatibility wrapper, preserving existing caller cancellation. Use the sample timestamp to mark the status/resources stale after an explicit freshness window; let one successful new sample recover state. Keep completion streams exempt because long prompt reading is expected. Add whole-installation tests for a hanging response, cancellation, visible stale state, and recovery.
- **Effort:** M.
- **Grade lift:** B → B+, by covering a missing monitoring failure state.
- **Evidence:** `ui-hang-probe.cjs` and `ui-hang-probe.json` in the ignored architecture audit directory. The fixture does not prove a stall occurs on the normal healthy server; it proves the implementation cannot recover if one occurs.

#### C2 — Clear old performance cards when the backend provides no performance block
- **Where:** `macos/lab/web/performance.js:123-135,150-157`, `macos/lab/tests/ui_installation.test.cjs:215-246,274-293`.
- **What's wrong:** The missing-performance branch updates only the mode label and returns, leaving generation, first-token, resource, settings and request data from the prior backend visible. A whole-script fixture first rendered 88 TPS and 25 ms from a model sample, then rendered a sample with no performance block: both numbers remained under “Performance data unavailable.” The current maintained server normally supplies this block; this is a degraded/older-backend boundary rather than normal request failure.
- **Impact:** Moderate — users can read measurements from an earlier engine as if they belonged to the newly selected or unsupported backend.
- **Fix:** Render explicit unknown/empty values for all performance cards, resources, settings and current-request rows when the block is absent; visually disable export of the missing current snapshot while preserving explicitly historical records. Test model→missing and missing→model transitions through the full classic-script installation.
- **Effort:** S.
- **Grade lift:** B → B+ together with C1, by making unknown and stale data consistently visible.
- **Evidence:** `ui-probes-v2.cjs` and `ui-probes.json`. The first probe version failed before app evaluation because its VM fixture did not inject Blob; the corrected fixture only adds the missing standard globals. Both runner versions remain local.

---

## D — Testing & Reliability — B−

The source-bound offline inventory passes 356 methods, plus 15 benchmark-signal methods, one app-signal method covering six stages/signals, two port methods, five campaign-protocol methods and 27 Node tests. Focused coverage is 87.37% lines/75.28% branches across 21 maintained Python modules (`macos/lab/scripts/check_coverage.py`, `macos/lab/config/coverage-baseline.json`). Active frozen brackets and failed receipts are strong, but real tiny-process probes exposed verifier cleanup and false-passed finalization; parked comparison tools have acceptance gaps. A green suite does not establish those missing failure contracts.

#### D1 — SIGTERM bypasses profile-verifier child cleanup [BE]
- **Where:** `macos/lab/scripts/verify_runtime_profiles.py:33-48`, `:134-140`.
- **What's wrong:** Unlike run.py and maintained benchmark drivers, this verifier has no cleanup-on-termination/deferred publication. Default SIGTERM kills it without its finally block and leaves its launched supervisor running.
- **Proof:** `lifecycle-probes.json/profile_verifier_sigterm`: actual subprocess exit−15, owned tiny launcher child survived, receipt remained `attempting` without exit field. Auditor subsequently terminated/reaped only that identified fixture child. Expected failed receipt and no owned children after stop.
- **Impact:** Major — cancelling a real verification can leave a full model consuming RAM and confuse later tests.
- **Fix:** Apply existing termination context and defer resource creation/publication; protect entire cleanup/finalization against repeated signals. Maintain bounded terminate→kill fallback and ownership.
- **Effort:** M.
- **Validation:** Actual SIGTERM/SIGINT/SIGHUP before, during and after Popen publication plus repeated stop during cleanup, using tiny owned fixtures.
- **Grade lift:** B− → B with D2.

#### D2 — Failed postflight can leave a saved passed profile receipt [BE]
- **Where:** `macos/lab/scripts/verify_runtime_profiles.py:131-159`.
- **What's wrong:** Successful API checks set passed, then finally saves that state before memory/activation/chunk/port/source postflight. An exception during later checks escapes without marking failed or saving updated data.
- **Proof:** `receipt-finalization-probe.json`: actual main with fake APIs/provenance raised missing-reduction-marker ValueError, but persisted `status:passed`, exit0, no activation/memory. Child cleaned up. Expected failed status/error with all available cleanup evidence.
- **Impact:** Major — a future interrupted or failed validation can be mistaken for complete proof. Complete existing R0 receipts are not invalidated by this deliberately incomplete receipt.
- **Fix:** Separate provisional success from accepted status. Run postflight inside its own exception-safe finalization and publish accepted only at end; always save failed status and original/cleanup errors on any postflight failure.
- **Effort:** M.
- **Validation:** Inject missing activation/chunk marker, missing memory file, bind failure, source change and snapshot failure; every saved receipt failed and owned children reaped.
- **Grade lift:** B− → B with D1.

#### D3 — Documented helper-app verifier conflicts with its own lock [BE]
- **Where:** `macos/lab/scripts/verify_helper_tuning.py:94-97`, `:24-41`; `macos/lab/scripts/run.py:140-143`; `macos/lab/README.md:175`, `:187`.
- **What's wrong:** The verifier holds exclusive macos/lab/bench/.lock while launching run.py, which independently tries the same nonblocking exclusive lock. It always fails before app execution.
- **Proof:** `lifecycle-probes.json/helper_verifier_nested_lock`: exact run.main under an isolated equivalent held parent lock returns BlockingIOError/exit1, `execute_entered:false`; source establishes the documented caller holds that lock. No shared real lock or model used.
- **Impact:** Moderate — a documented functional verification workflow is unusable; this is an older helper tool, not normal launcher.
- **Fix:** Let launched run.py own its runtime lock or create a narrow authorized lock-handoff mechanism; keep comparison drivers from launching competing models. Do not simply remove both locks.
- **Effort:** S.
- **Validation:** Tiny-process driver proving the documented parent→child flow starts, while a genuinely unrelated concurrent launcher is rejected.
- **Grade lift:** B− → B for documented workflow reliability.

#### D4 — Parked Q2 comparison accepts unbound engines/invalid math inputs [BE]
- **Where:** `macos/lab/scripts/benchmark_q2.py:24-56`.
- **What's wrong:** D01 remains open: settings engine labels and model/runtime equality do not prove each actual engine/source/artifact receipt. Missing model/runtime fields both compare None. Q2 numerical aggregation also bypasses common finite-positive validators.
- **Proof:** `q2_missing_identity`, `q2_changed_engine`, `q2_nan_metric`: missing identities and changed candidate artifact accepted with +25% synthetic summary; NaN accepted and published in summary. Expected contract rejection, not scored gains. Numeric issue is grouped into this parked comparator hardening item.
- **Impact:** Moderate — unsafe to reuse this parked comparison for adoption; current R1/E01 campaigns use stronger gates.
- **Fix:** Bind each arm to exact expected engine pin, baseline/candidate identities, actual sources and model proof, and use shared validated metric aggregation. Freeze prerequisite identity before/after runs.
- **Effort:** M.
- **Validation:** Missing/changed selected_engine/source/model, wrong actual engine and NaN/Infinity/bool/zero/negative metrics all rejected.
- **Grade lift:** B− → B for reusable old proof tooling, not historical score revision.

#### D5 — Parked tuning comparison derives required workload coverage from the data [BE]
- **Where:** `macos/lab/scripts/benchmark_tuning.py:42-58`.
- **What's wrong:** D02 remains open: first arm determines workload/length keys rather than the declared workload plan; later unrecognized extra keys are ignored. If every arm loses the2048 task, compare still succeeds despite unchanged settings.
- **Proof:** `tuning_missing_workload`, `tuning_extra_workload`: removal of required2048 cases from all arms or extra work only in later arms both accepted. Expected exact cohort/length/repetition completeness before metrics.
- **Impact:** Moderate — a favorable incomplete comparison can look complete when this parked tool is reused.
- **Fix:** Derive expected fresh and cached keys from frozen settings/fixture, reject missing/extra/duplicate keys and enforce per-arm repetitions/output counts before aggregation.
- **Effort:** S.
- **Validation:** Entire length removed across all arms, arbitrary later extra workload, duplicates replacing missing repeats, missing cached length and unchanged complete bracket.
- **Grade lift:** B− → B for old comparison contracts.

#### D6 — Parked comparison receipts need full resource/answer acceptance [BE]
- **Where:** `macos/lab/scripts/benchmark_q2.py:25-36`; `macos/lab/scripts/benchmark_tuning.py:28-38`.
- **What's wrong:** Both rely on status/guard instead of complete resource proof; tuning's `all` accepts empty answer checks. Zero new swap, healthy monitor, child exit, live coverage and actual check completeness are not required.
- **Proof:** `q2_swap`, `tuning_swap`: swap+1024/unhealthy monitor/child_exitedfalse accepted; `q2_missing_checks`, `tuning_missing_checks`: empty checks accepted. Expected reject. This is grouped across two old comparators as one acceptance-contract defect; current m5 comparator already has stronger checks.
- **Impact:** Moderate — a resource-compromised/unchecked old run could be scored if these parked tools are reused.
- **Fix:** Use a common complete launch/resource acceptance validator with required numeric counters and expected nonempty answer-check names, no bool/optional defaults. Preserve old raw receipts; do not retroaccept them.
- **Effort:** M.
- **Validation:** Mutate each required resource/check field independently and require fail-closed errors.
- **Grade lift:** B− → B for proof consistency.

#### D7 — Parked Q2 math proof does not bind the tester or final engine [BE]
- **Where:** `macos/lab/scripts/verify_q2.py:52-66`; comparison prerequisite consumption `macos/lab/scripts/benchmark_q2.py:95-103`.
- **What's wrong:** verify_q2 verifies engine only once; test-backend-ops is not included in engine artifact_hashes and no tester hash is stored or rechecked. A test executable or engine change after entry can still produce passed prerequisite proof. Maintained verify_m5 already freezes/rechecks tester and engine.
- **Proof:** `q2_math_identity`: actual main fixture records only one verify_engine call and returns passed despite test result signalling changed engine/tester; exact missing hash/recheck source confirms gap. No executable/GPU actually run.
- **Impact:** Moderate — this old prerequisite cannot safely authorize future changed builds.
- **Fix:** Bring verifier to verify_m5's before/after engine+tester contract; prerequisite consumer must check its bound tester and complete check list against current artifacts.
- **Effort:** S.
- **Validation:** Tiny synthetic tester replacement and engine change during checks; require failed proof with retained error and unchanged source pin success.
- **Grade lift:** B− → B for reusable correctness proof.

#### D8 — Shared synthetic checker misses swap at process exit [BE]
- **Where:** `macos/lab/scripts/verify_q2.py:17-47`; consumed by maintained `macos/lab/scripts/verify_m5.py:30-45`.
- **What's wrong:** Swap is sampled only inside `while process.poll() is None`. There is no final sample after wait; a quick process or late swap growth is reported zero and can pass verify_m5's zero-swap gate.
- **Proof:** `final-swap-probe.json`: synthetic finished-process fixture with baseline0/final1GiB makes only one swap read, returns passed/peakRSS0/newswap0. Expected final swap measurement and failure. This proves acceptance gap, not actual swap during past math runs.
- **Impact:** Moderate — future short correctness checks can claim resource cleanliness without a final measurement.
- **Fix:** Take bounded final swap/pressure observation after reaping in success/failure cleanup, enforce live measurement completeness appropriately for tiny checks, and publish rejected evidence even on guard exception.
- **Effort:** S.
- **Validation:** Swap grows between last live sample and wait, process exits before first poll sample, monitor read failure, normal successful fixture.
- **Grade lift:** B− → B for shared correctness-check resource coverage.

#### D9 — Add targeted MTP checkpoint restoration validation [BE; source watchlist]
- **Where:** `macos/lab/vendor/llama-m5-small-stack/common/speculative.cpp:214`, `:1415`, `:1518`, `:1588`, `:1828`; `macos/lab/vendor/llama-m5-small-stack/tools/server/server-context.cpp:2569`, `:3602`; maintained native test/patch integration.
- **What's wrong:** MTP has no get_state/set_state override while current profile logs prove context checkpoint restoration occurs. The carryover hidden row is not serialized by the base no-op hooks; turning prompt_cache off does not disable context checkpoints. No wrong output or throughput loss has been reproduced here, so this is a source-confirmed validation gap, not a proven app failure.
- **Impact:** Moderate — branch/restore behavior and accepted-draft counts need proof before expanding cache reuse or omitting checkpoint work.
- **Fix:** Inspect [upstream proposed state hooks](https://github.com/ggml-org/llama.cpp/pull/30141) at the recorded head, add bounded serializer/roundtrip/malformed-state tests and an isolated checkpoint model fixture, then validate current shared-helper branching, cancellation/reuse, target-token identity and draft acceptance. Preserve target verification and current checkpoints; do not backport blindly.
- **Effort:** M.
- **Grade lift:** B− → B for explicit native state-restoration coverage alongside D1/D2.

---

## E — Security — C+

Normal launch binds both servers to loopback (`macos/lab/scripts/run.py:155`, `macos/lab/scripts/lab.py:119`) and the adapter requires local HTTP (`macos/lab/scripts/native_backend.py:417`). Model/private/raw artifacts are excluded and maintained local assets avoid CDN dependence. The reachable handler lacks Host/Origin intake defenses and body/read limits, and a supported API-key configuration leaves live reply text reachable through /status. CPU socket probes establish missing defenses; no full browser exploit or LAN exposure was demonstrated.

#### E1 — Missing local browser Host/Origin access gate
- **Where:** `macos/lab/scripts/web_ui.py:14-21`; reachable pinned `macos/lab/vendor/Strata-macOS/serve/server.py:971-988`, `:998-1000`.
- **What's wrong:** Normal loopback binding limits network exposure, but does not authenticate HTTP Host. Inference also accepts simple cross-origin POSTs; only settings applies an Origin check, and even that checks against arbitrary Host. One integrated request-boundary fix should guard both.
- **Proof:** `api_host_rebind`: attacker Host+matching attacker Origin returns200. `api_foreign_simple_post`: foreign Origin+text/plain returns200 and runs mock engine. Expected disallowed Host/Origin rejection without inference. This is defense absence, not a browser exploit demonstration or claim that every browser allows it.
- **Impact:** Major — a browser-accessible local service lacks defenses against unwanted cross-site inference and possible rebinding-based access to local data.
- **Fix:** In maintained handler, enforce loopback Host allowlist with actual bound port and reject foreign browser Origins; keep legitimate CLI no-Origin access. Require appropriate JSON for API POSTs. Add no-store to private status/metrics as appropriate. Do not expose LAN or change pinned vendor.
- **Effort:** M.
- **Validation:** Host/Origin matrix forlocalhost/127.0.0.1/allowedport/disallowedhost/foreignnull-origin/no-origin and both APIs/settings/metrics, proving no backend calls on reject.
- **Grade lift:** C+ → B− with E2/E3.

#### E2 — HTTP bodies/read lifetime have no bound before allocation
- **Where:** `macos/lab/scripts/web_ui.py:14`; reachable pinned `macos/lab/vendor/Strata-macOS/serve/server.py:978`, `:994`; server thread boundary `macos/lab/vendor/Strata-macOS/serve/server.py:1119-1122`.
- **What's wrong:** Arbitrary Content-Length is read without an application maximum/read deadline. Threading server allows additional request threads; an oversized/slow local client can hold memory/threads before prompt context validation runs.
- **Proof:** `api_unbounded_body`: one owned connection with Content-Length2147483647 stayed in a read without413 or a short configured deadline; closed at ~0.4s fixture cutoff. Source confirms absence of cap and socket timeout. This was not a resource-exhaustion stress test and did not allocate/submit a huge payload.
- **Impact:** Moderate — accidental huge requests or malicious local/browser clients can pressure the app and model resources.
- **Fix:** Bound exact integer nonnegative Content-Length and received bytes before read, reject unsupported transfer/body framing, configure a finite intake timeout and bounded pending requests; response streaming deadlines need separate treatment.
- **Effort:** M.
- **Validation:** Oversized/negative/malformed/missing length, partial slow body, duplicate/ambiguous framing, max valid JSON payload and normal SSE without premature generation timeout.
- **Grade lift:** C+ → B− with E1.

#### E3 — /status bypasses configured API key and includes text
- **Where:** `macos/lab/scripts/web_ui.py:20-21`; reachable pinned `macos/lab/vendor/Strata-macOS/serve/server.py:954-964`; response tail publication in shell Service.
- **What's wrong:** /metrics and inference authorize when API key is enabled, but /status returns live reply tail without authorization.
- **Proof:** `api_status_without_key`: Service api_key enabled, unauthenticated GET200 contains `private fixture reply`. Expected401/no tail. This does not claim the normal launcher currently enables an API key; it affects the supported separately configured protected shell used through Mac wrapper.
- **Impact:** Moderate — configured protection does not cover live response text.
- **Fix:** Authorize sensitive status through the maintained wrapper and consider dropping tail from public health/status; keep safe health endpoint public if desired.
- **Effort:** S.
- **Validation:** Authenticated/unauthenticated status and metrics, busy private-tail fixture and mock normal UI access.
- **Grade lift:** C+ → B− for complete protected-route coverage.

---

## F — Dependencies & Tech Currency — B+

Both runtime and development versions are exact (`macos/lab/requirements.txt`, `macos/lab/requirements-quality.txt`); CI uses hash-frozen locks and the Node lock contains integrity digests (`.github/workflows/mac-lab-offline.yml:28-32`, `macos/lab/package-lock.json`). A current npm audit returned zero advisories, and an OSV exact-version query returned no matches for the 15 Python runtime/quality packages; this is limited registry evidence, not a claim that the whole native stack has no vulnerabilities. Python 3.12 and the configured Node 22/24 lines remain supported. The weak points are local runtime installation and mutable external native libraries, not a reason to blindly upgrade pinned packages.

#### F1 — Use the same hash-frozen runtime lock during local provisioning
- **Where:** `macos/lab/scripts/provision.py:60-63`, `macos/lab/requirements.txt`, `macos/lab/requirements-ci.lock`, `.github/workflows/mac-lab-offline.yml:28-32`, `macos/lab/tests/test_provision_receipt.py:67-84`.
- **What's wrong:** Local provisioning installs runtime packages from `macos/lab/requirements.txt` without `--require-hashes` or a wheels-only policy, then correctly applies both policies to development tools. CI already has the frozen runtime hashes, so local setup uses weaker artifact verification than the tests that validate it.
- **Impact:** Moderate — a recreated machine can install different distribution artifacts despite using the same package version, reducing reproducibility and install verification.
- **Fix:** Install runtime packages from the existing runtime lock using `--require-hashes --only-binary :all:` (rename the lock if its CI-only name is misleading). Extend provisioning command-capture tests to require identical policy for both installs and prove failure prevents builds/receipt publication. Keep package versions unchanged.
- **Effort:** S.
- **Grade lift:** B+ → A− together with F2, by aligning local and hosted dependency verification.

#### F2 — Verify external native libraries in the common engine receipt
- **Where:** `macos/lab/scripts/engines.py:160-198,202-222`, `macos/lab/scripts/provision.py:47,74-78`, `macos/lab/scripts/prepare_m5.py:54-59`, `macos/lab/bench/M5-PREPARATION-RECIPE.md:18-20`.
- **What's wrong:** Common receipts hash the executable and libraries inside `build/bin`, but the kept server currently links OpenSSL/crypto libraries outside that directory. A Homebrew update can therefore change a loaded native dependency while `verify_engine()` still reports the original local artifacts unchanged. The diagnostic-specific linker receipt addresses its own resolved libraries; it does not close the common app/engine boundary.
- **Impact:** Moderate — host dependency changes can escape experiment provenance or break a recreated engine without a clear drift error.
- **Fix:** Record and verify the resolved non-system dylib closure with versions/digests in common build receipts; represent external dependencies separately from lab-relative files. Define how optional local-HTTP-only builds propagate through eligible engine preparers. Preserve existing accepted receipts/history and never silently repin after a library change. Add tiny mocked Mach-O dependency tests for changed, missing and duplicate libraries, plus current receipt migration/refusal semantics.
- **Effort:** M.
- **Grade lift:** B+ → A− together with F1, by binding the runtime to the artifacts it actually loads.
- **Evidence:** Read-only `otool -L` on the kept server identifies external OpenSSL and crypto links; no engine was executed. This finding does not allege a current OpenSSL CVE.

---

## G — Performance & Scalability — B+

The current kept engine uses Tensor API and selected shared-helper/reduction settings, with explicit batch/context profiles (`macos/lab/scripts/runtime_profiles.py:13`, `macos/lab/scripts/metal_environment.py:22`). Actual full-model editing produces roughly 87–88 first-exposure tokens/sec and around 90 on replay; all profiles pass resource/exit validation. R1 uses complete output identity, independent frozen A/B/B/A brackets and rejects an unconfirmed small pool gain instead of inflating the result (`macos/lab/bench/research/20261014-baseline-and-helper-pool/REPORT.md`). Performance is B+: strong useful execution and careful current trials, with roughly 4.5 seconds before long-input replies, unfinished operation attribution and two concrete native first-response opportunities. These are different scopes, not one overall TPS number.

#### G1 — Profile actual prompt operations and qualify integrated routed-entry tiles
- **Where:** `macos/lab/scripts/benchmark_prompt_chunks.py:183`, `macos/lab/scripts/profile_m5_routes.py:198`; kept native `macos/lab/vendor/llama-m5-small-stack/ggml/src/ggml-metal/ggml-metal-ops.cpp:2828`, `macos/lab/vendor/llama-m5-small-stack/ggml/src/ggml-metal/kernels/mul_mm.metal:371`; isolated new engine/patch manifest.
- **What's wrong:** Current wait envelopes do not identify exclusive per-operation cost on actual 512/1536 prompt shapes. The routed-MM path still uses the older fixed expert×token map/grid, while [merged upstream #30373](https://github.com/ggml-org/llama.cpp/pull/30373) integrates compact entries/tiles during mapping. The earlier P11 separate compaction pass is off and is a different mechanism.
- **Impact:** Moderate — a specific long-prompt latency lead remains unmeasured; there is no established new speed gain.
- **Fix:** First capture operator shape/type/fusion/dispatch without new waits or callbacks that break fusion. Backport only integrated mapping/tiling in an isolated clone, retaining Q2 arithmetic, consumer row order and reduction/fusion. Validate duplicate/skew/tail/stride/reference and dependent blocks, then trace-off English first/replay brackets and independent confirmation; preserve guards. Stop if inactive, not repeatably beneficial or a required scope regresses.
- **Effort:** L.
- **Grade lift:** B+ → A− if trustworthy profiling and a qualified improvement are delivered; the lift is contingent, not promised.

#### G2 — Test bounded Apple lazy-row prefetch independently
- **Where:** kept native `macos/lab/vendor/llama-m5-small-stack/src/llama-mmap.cpp:837`, `macos/lab/vendor/llama-m5-small-stack/src/llama-impl.cpp:23`, `macos/lab/vendor/llama-m5-small-stack/src/models/qwen4exp.cpp:1291`; isolated candidate patch/experiment harness.
- **What's wrong:** The existing row-hint entry point excludes Apple. A prior first-document lookup envelope was 145 ms; actual storage wait/overlap was not isolated. A new owned-file probe proves advice loads requested pages here, but no sparse-model latency benefit has been shown.
- **Impact:** Moderate — some first-input blocking reads might be overlapped or coalesced, while warm-case cost and page pressure can offset the benefit.
- **Fix:** Prove mapping/file lifetime, alignment/overflow/page-byte caps and readonly identities; compare one advisory API on actual bounded eligible sparse spans, retaining returns/residency/requested-read bytes. Run independent first/replay comparisons with unchanged model/precision/guards and no cache purge or loader rewrite. Stop on no useful overlap, warm regression or memory pressure.
- **Effort:** M.
- **Grade lift:** B+ → A− only with confirmed scoped benefit and unchanged accuracy/resource proof.

---

## H — Documentation & Onboarding — B−

The reports are unusually candid about measured scopes, failed attempts and parked optimization ideas (`macos/lab/bench/EXPERIMENT-LEDGER.md`; `macos/lab/bench/research/20261014-baseline-and-helper-pool/REPORT.md:1-80`). The README explains resident model memory versus lazy lookup storage and complete API scope (`macos/lab/README.md:111-133`), and QUALITY describes the exact maintained scope rather than claiming whole-repo coverage. The main onboarding route is now behind the actual default profile: it still prepares baseline + standalone Q3, while normal launchers require the kept small-stack engine and packed shared helper. Historical status paragraphs also obscure the current next-action route.

#### H1 — Give the maintained default profile a complete fresh-clone recipe
- **Where:** `macos/lab/README.md:13,43,59-86`, `macos/lab/scripts/runtime_profiles.py:13-41`, `macos/lab/bench/M5-PREPARATION-RECIPE.md:3-5,26-50`, `macos/lab/scripts/provision.py:73-78`.
- **What's wrong:** The main recreation commands build `baseline` and derive the standalone Q3 helper, but the normal launcher selects `m5-small-stack` and `mtp_shared_packed_q3`. The linked recipe stops at the older diagnostic/correctness chain and still says the preparation is local/uncommitted. Running the documented setup does not yet produce the dependencies named by the default launcher.
- **Impact:** Major — a new checkout can complete the advertised preparation and still fail at the primary Run action.
- **Fix:** Write one ordered maintained-profile setup path: prerequisites/disk policy, hash-locked provisioning, verified Flash/BF16 downloads, derived Q3, shared engine/helper packing, required prerequisite receipts, kept small-stack build, offline checks, then an explicitly separate authorized model/API smoke. Add a dry-run dependency-plan test covering the actual default profile. Validate the non-model stages in a clean exported directory and state which download/build/model stages were actually run; keep diagnostics and archived optional profiles in separate links.
- **Effort:** M.
- **Grade lift:** B− → B+, by making the normal application reproducible without reconstructing its history.

#### H2 — Put current measurements and queue ahead of archived progress
- **Where:** `macos/lab/README.md:19-33`, `macos/lab/web/README.md:83-104` and historical validation sections, `macos/lab/bench/research/20261014-baseline-and-helper-pool/REPORT.md:1-25,73-80`.
- **What's wrong:** Top-level “Latest”/“Current” labels still point to earlier passes, while the fresh baseline and parked helper-pool decision live only in a newer detailed report. The lengthy chronological documentation has several old run counts/hold statements, making it hard to see which settings are currently adopted and which apparent TPS numbers refer to different workloads.
- **Impact:** Moderate — readers can confuse the 60-TPS fixed-output code baseline with 87–88-TPS supplied-file edits or assume a completed hold still applies.
- **Fix:** Make the README opening a concise dated status with adopted profiles, separate workload-specific benchmark rows, latest qualification links and the next experiment queue. Move chronological checkpoint descriptions to a dated history section/index; keep all failures and old reports intact. Replace wording implying current holds with explicit historical dates. Add link checks for the compact current landing page, without demanding that ignored raw local evidence be public.
- **Effort:** S.
- **Grade lift:** B− → B+ with H1, by clarifying current state without erasing evidence.

---

## I — Developer Experience & Tooling — B+

The Mac CI pins actions and Python/Node tools, runs explicit load-free checks, and retains receipts (`.github/workflows/mac-lab-offline.yml`). The quality scope and mypy targets must agree, there are no blanket suppressions, and code size is reported after Ruff/format/types (`macos/lab/scripts/check_quality.py:39-71,91-123`; `macos/lab/QUALITY.md:9-28`). Core runtime/environment/provenance modules have full checks, but several current experiment and validation entrypoints remain outside that fuller gate, creating a weaker development loop precisely where new performance research is happening.

#### I1 — Extend the full quality gate to the active experiment entrypoints
- **Where:** `macos/lab/config/quality_modules.json:3-24`, `macos/lab/scripts/benchmark_prompt_chunks.py`, `macos/lab/scripts/benchmark_editing.py`, `macos/lab/scripts/verify_runtime_profiles.py`, `macos/lab/scripts/check_quality.py:115-123`.
- **What's wrong:** These currently used long-prompt/editing/profile-validation drivers receive broad syntax/undefined-name checks but are not in the maintained formatter, full Ruff or mypy manifest. Their 11, 17 and 2 functions respectively have no complete parameter/return signatures in a fresh AST inventory. This is a concrete scope gap, not a request to spend effort cleaning every archived trial.
- **Impact:** Moderate — new work can copy untyped command/receipt dictionaries across the active drivers without the checks that already protect the core runtime.
- **Fix:** Add those three active entrypoints to the explicit manifest and mypy scope, use shared launch/workload/response receipt types at boundaries, apply the existing formatter/rules, and include their meaningful protocol branches in focused coverage while preserving all original per-file floors. Retain existing commands, measured source identity, failure receipts and termination contracts. Leave inactive historical tools outside expansion until reused.
- **Effort:** M.
- **Grade lift:** B+ → A−, by making the active research loop use the same checks as its runtime.

---
