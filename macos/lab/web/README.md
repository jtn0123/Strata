# Mac workspace

The Mac launcher serves this page over the pinned API shell. `scripts/web_ui.py` checks each request before the
pinned handler sees it: the Host and Origin headers, the body's size and arrival time, and the shape of chat
requests (`scripts/api_requests.py`), answering 400, 403, 408, 413 or 415 instead of passing a bad request on.
Of the page's files it replaces only the homepage and `/web/mac.css`, `/web/mac.js`, `/web/ui-state.js` and
`/web/performance.js`; API routes, authentication, sampling, cancellation, native engine settings and the shell's
original assets stay with the pinned server. The upstream download is not modified.

`index.html` derives from `jinzy0623/Strata-macOS` at `2cc4153409edb3f859187bdf10f13e34972d6ffb`, retaining its
control IDs and all original chat/monitor/settings behavior. Original Strata attribution and MIT licensing
apply; the local Outfit font retains its SIL OFL license in the pinned shell. No CDN, new font download,
JavaScript framework or model download is needed. `mac.js` uses the pinned shell's classic-script functions;
refresh this compatibility layer and its control-ID test when changing that dependency.

The interface adds draft-only prompt shortcuts, responsive layouts, light/dark colors, keyboard tab selection,
and a settings dialog with focus containment, keyboard radio selection and focus restoration. The closed dialog is inert. Reduced-motion
preferences disable the added transitions. Unreported GPU counters are hidden and explained; system memory
comes from the server's existing hardware sampler, not a new free-memory estimate. The chart floor adopts
upstream's [6a7c6f82](https://github.com/Niko1221/Strata/commit/6a7c6f8275a551ae3940d7d434dd2e88a1ee59f4).

For UI development without loading a model, run from `macos/lab`:

```sh
.venv/bin/python scripts/strata_server.py --engine mock --host 127.0.0.1 --port 8116
```

Mock replies and speeds are not model performance measurements. Run `scripts/validate_offline.py` after editing:
its receipt fingerprints HTML, CSS and JavaScript too. Screenshots and raw verification receipts remain local.

## Chat behavior

Chat EOF needs an explicit terminal SSE record; interrupted replies keep their partial text beside the error,
while Stop remains cancellation. Numeric sampling fields reject invalid values before saving, and late
shared-settings responses cannot replace a user's choice. Applying before that read completes explicitly writes
the selected sharing state.

Attached file contents remain transient: reload keeps their names, shows a reattachment notice, and warns
on the first follow-up. Markdown export includes available file contents and identifies unavailable restored
files. Response tables scroll locally; narrow/coarse-pointer copy, removal, close and radio targets are 44px.
The user-message foreground follows the selected theme, and input names retain their visible labels.

## Monitor and performance tracking

Monitor shows generation speed and its timing source, server first-token/full-response time, native prompt
reading, draft acceptance and prompt reuse. Chat replies show browser first-text/full-request timing, including
transport and queue wait. These scopes are deliberately labeled separately. Mock previews are marked as test
data and unavailable counters stay blank. Draft acceptance covers all proposed tokens, including lookup drafts;
it does not isolate the MTP helper's acceptance.

The local server keeps 30 recent requests; this browser keeps up to 200 timing/settings records across reloads.
Export includes numerical measurements and a settings whitelist, with no prompts, replies, file paths or API
keys. Its resource snapshot is current, not a per-request peak. Available RAM and total system swap are sampled
locally; model RSS, pressure and swap growth reuse the existing owned launch guard when available. No extra
pressure subprocess or native profiling callback is added.

The maintained API shell's metrics payload is extended additively through a Service subclass; authentication,
queueing, cancellation, sampling and generation still use the pinned implementations. Normal/native/mocked
timing sources must be kept separate when comparing measurements. The default model/profile is unchanged.
The backend retains the final native timing packet when the shell closes at EOS, with an EOS-only 0.5 second
deadline and responsive cancellation. Missing/cancelled counters remain unknown; a cancelled new request cannot
inherit the preceding request's metrics. See the [research queue and metric definitions](../bench/research/20261013-performance-tracking/REPORT.md).

### Stale and missing readings

The pinned shell polls `/metrics` once a second and starts the next poll only after the previous one settles.
`ui-state.js` gives each `/metrics` request, including its body, a 5 second deadline
(`STRATA_METRICS_TIMEOUT_MS`), so a stalled reply is abandoned and polling continues. A caller's own abort
signal still cancels the request with its own reason. Chat completion and `/v1/messages` requests get no
deadline, because reading a long prompt is expected to take a while.

When the last sample is more than 10 seconds old (`STRATA_TELEMETRY_FRESH_MS`), the status pill shows
"Not updating", Monitor dims its readings and says they are stale, and the model name is marked "last seen".
The window is longer than one poll wait plus one full deadline (6 seconds), so a slow reply that arrives within
its deadline does not expire a sample. Cached tab renders keep the stale state; one new sample clears it. After
three failed polls the pinned shell still reports "Server not reachable" with the reconnect banner.

If a sample has no performance block (an older or degraded backend), the performance cards, resources and
settings show "–" or "Not reported" instead of the earlier values. Request rows keep only time, status and
token counts, and nothing is added to the browser history. The export button becomes "Export history": the file
has `performance: null` and no current request rows, but keeps the earlier recorded requests and browser
timings. With no history the button is disabled. The next sample with a performance block restores everything.

## Checks

Run all JavaScript suites from `macos/lab` with `node --test tests/*.test.cjs`. `tests/ui_state.test.cjs` covers
the pure status state and can run on its own, separately from the network-free Python gate:

```sh
node --test tests/ui_state.test.cjs
```

`tests/ui_behavior.test.cjs` reproduces the pinned chat's unsafe Undo, omitted attached-file export and
premature-stream completion before checking the maintained fixes. `tests/ui_installation.test.cjs` runs the real
pinned and maintained scripts in page order over a small DOM double. The CI workflow runs the JavaScript checks
under Node 22.

The maintained JavaScript also has a scoped ESLint gate. From `macos/lab`, use Node 22.13+ on the
Node 22 line, or Node 24+:

```sh
npm ci --ignore-scripts
npm run lint
```

The lockfile pins the lint dependencies. `web/mac.js`, `web/ui-state.js`, `web/performance.js` and
all Node test suites are checked; downloaded vendor sources keep their pins. The gate catches undefined names and writes,
redeclarations, unreachable code, unused bindings and unsafe evaluation. Its explicit per-file contracts
distinguish readonly shell data from writable hooks/state. `loadShared` is an exported classic-script hook
called by the pinned drawer; `sharedOn` and `settings` remain the shell's global lexical bindings.
Production function complexity is limited to 15. The gate also enforces immutable bindings, useful
expressions, promise-executor returns and shadowing rules. Named installers/render helpers retain
startup order and sampling, cancellation, attachment and export behavior.
Python type and lint checks are separate from this JavaScript gate.

Browser and full offline verification are separate from these tests. They do not establish physical
VoiceOver or mobile-keyboard acceptance.

## Validation history

Each entry records what was checked in that pass. Counts are as of that pass and were not updated later;
later passes added tests, so earlier totals are lower.

### 2026-10-13: first maintained workspace

Browser checks covered both themes, desktop/mobile layouts, prompt drafting, a complete mock SSE reply, tabs and
dialog focus. Separate HTTP checks validated authentication and path rejection. No new TPS claim accompanied
this change.

### 2026-10-13: polish loop

Two programmatic, read-only Opus 5.5 reviews moved the subjective overall assessment from B- to B+.
The main fixes keep offline/API-key failures visible through cached tab renders, mark readings stale until a
fresh response arrives, announce phase changes rather than every speed update, preserve an existing draft,
and stabilize the welcome text against the older shell's health callback. Empty speed charts no longer imply
zero; memory uses GiB. Copper button shadows and distinct starter icons remove inherited visual leftovers.

The mobile composer measured 212.5 to 139 pixels (-34.6%); the desktop conversation composer measured 178.5
pixels (-16.0%). Main mobile toolbar controls and the theme control measure 44 pixels at 320/390px widths.
The settings body scrolls to Apply on a 320x640 viewport and returns focus after closing. These are browser
layout/interaction measurements, not generation performance gains. Physical VoiceOver and mobile soft-keyboard
behavior remain manual checks; the announcer's DOM behavior was checked directly.

Validation for this pass: 178 Python offline tests, five campaign-protocol tests and four JavaScript state tests
passed. Review prompts, model responses, detailed grades and screenshots live under the ignored
`.Codex/ui-ux-audit/` and `.Codex/ui-ux-grade-report.md` paths.

### 2026-10-13: performance tracking

No new model or GPU benchmark was run for this UI change. Validation for this pass: 185 offline tests, five
campaign-protocol tests, seven JavaScript regression tests and eight actual HTTP smoke groups using a mock engine.

### 2026-10-13: real-model field check

A later October 13 real-model check verified the Monitor fields in the maintained editing app. Real
complete-file API requests, all nine API/lifecycle integration groups, browser timing badges and numeric export
privacy passed with normal pressure/zero new swap. Validation for this pass: 207 offline tests, five campaign
protocol checks, seven JavaScript tests and 18 CPU-only native matcher cases. Browser observations and controlled
editing benchmarks use different prompts/thinking settings and are not interchangeable speed comparisons.
Detailed results and exclusions are in the [decision ledger](../bench/EXPERIMENT-LEDGER.md).

### 2026-10-13: PR readiness audit

The PR audit corrected supported JSON/CLI config handling, premature hardware-sampler
exit detection and parent protocol-reader error propagation. Every new benchmark entry point
now unwinds through owned-child shutdown and guard finalization on Ctrl-C, SIGTERM or SIGHUP.
Stops during process creation are deferred until child/guard ownership is published. A separate
CI check exercises the real parent driver with tiny Python children; it never loads a model or
runs GPU work. The network/native-denying offline gate remains separate.

Audit checks for this pass: 253 load-free Python tests, six tiny-child termination tests, five campaign
protocol tests and seven JavaScript tests. Physical VoiceOver/mobile-keyboard validation and a new full-model
performance comparison were not part of this audit; as of this audit, previously recorded model results were
the performance evidence.

### 2026-10-13: bug and polish follow-up

This pass added `tests/ui_behavior.test.cjs` and the chat behavior described above. The
[follow-up report](../bench/research/20261013-bug-polish/REPORT.md) records 22 corrected findings and two deferred
parked-tool findings. Local checks for this pass: 281 load-free Python tests, 27 JavaScript tests, 12
benchmark-termination tests, six app-launch signal cases, two port checks and five campaign-protocol checks.
The six app signal cases share one test method.

Real browser checks covered mock completion, retained partial failure, intentional Stop, quick-link
startup, settings validation, reattachment notices and narrow/desktop layouts. Dark user-message
contrast is 11.4:1; 320 px chat/table fixtures fit the viewport. Review screenshots and detailed
receipts remain ignored, and no real model/GPU benchmark ran in this pass.

### 2026-10-13: quality and coverage gates

Focused local validation for this pass: 33 JavaScript cases, including five whole-installation contracts, and
15 web/performance Python cases.

### 2026-10-14: stale and missing Monitor readings

This pass added the `/metrics` deadline, the freshness window and the missing-performance rendering described
under Monitor. On Node 26.8.1, `npm run lint` reported no problems and `node --test tests/*.test.cjs` passed
46 tests, ten of them new: three status-state cases, one fetch-wrapper case and six whole-installation cases.
Run against the previous scripts, the ten new tests failed and the other 36 passed. No browser, HTTP server,
model or GPU check ran for this change. The 5 and 10 second bounds are design choices from the 1 second poll
interval, not measured `/metrics` latency.
