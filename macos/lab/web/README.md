# Mac workspace

The Mac launcher serves this page over the pinned API shell. `scripts/web_ui.py` replaces only the homepage and
`/web/mac.css`, `/web/mac.js`, `/web/ui-state.js` and `/web/performance.js`; API routes, authentication, sampling, cancellation, native engine settings and
the shell's original assets stay with the pinned server. The upstream download is not modified.

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

Mock replies and speeds are not model performance measurements. No new TPS claim accompanies this change.
Run `scripts/validate_offline.py` after editing: the receipt now fingerprints HTML, CSS and JavaScript too.
Browser checks cover both themes, desktop/mobile layouts, prompt drafting, a complete mock SSE reply, tabs,
dialog focus. Separate HTTP checks validate authentication and path rejection. Screenshots and raw verification receipts remain local.

## Polish loop

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

Run the pure status-state regression tests separately from the network-free Python gate:

```sh
node --test tests/ui_state.test.cjs
```

The later bug/interaction pass adds `tests/ui_behavior.test.cjs`. Its focused checks reproduce the pinned
chat's unsafe Undo, omitted attached-file export and premature-stream completion before checking the maintained
fixes. Chat EOF now needs an explicit terminal SSE record; interrupted replies keep their partial text beside
the error, while Stop remains cancellation. Numeric sampling fields reject invalid values before saving, and
late shared-settings responses cannot replace a user's choice. Applying before that read completes explicitly
writes the selected sharing state.

Attached file contents remain transient: reload keeps their names, shows a reattachment notice, and warns
on the first follow-up. Markdown export includes available file contents and identifies unavailable restored
files. Response tables scroll locally; narrow/coarse-pointer copy, removal, close and radio targets are 44px.
The user-message foreground follows the selected theme, and input names retain their visible labels.

Run both JavaScript suites with `node --test tests/ui_state.test.cjs tests/ui_behavior.test.cjs`.

The maintained JavaScript also has a scoped ESLint gate. From `macos/lab`, use Node 22.13+ on the
Node 22 line, or Node 24+:

```sh
npm ci --ignore-scripts
npm run lint
```

The lockfile pins the lint dependencies. Only `web/mac.js`, `web/ui-state.js` and `web/performance.js`
are checked; downloaded vendor sources keep their pins. The gate catches undefined names and writes,
redeclarations, unreachable code, unused bindings and unsafe evaluation. Its explicit per-file contracts
distinguish readonly shell data from writable hooks/state. `loadShared` is an exported classic-script hook
called by the pinned drawer; `sharedOn` and `settings` remain the shell's global lexical bindings.
Python type and lint checks are separate from this JavaScript gate.

Focused local validation is 28 JavaScript cases and 15 web/performance Python cases. Browser and full offline
verification are separate; these tests do not establish physical VoiceOver or mobile-keyboard acceptance.

Final local validation: 178 Python offline tests, five campaign-protocol tests and four JavaScript state tests
pass. The CI workflow runs the JavaScript checks under Node 22. Review prompts, model responses, detailed grades
and screenshots live under the ignored `.Codex/ui-ux-audit/` and `.Codex/ui-ux-grade-report.md` paths.

## Performance tracking

Monitor now shows generation speed and its timing source, server first-token/full-response time, native prompt
reading, draft acceptance and prompt reuse. Chat replies show browser first-text/full-request timing, including
transport and queue wait. These scopes are deliberately labeled separately. Mock previews are marked as test
data and unavailable counters stay blank.

The local server keeps 30 recent requests; this browser keeps up to 200 timing/settings records across reloads.
Export includes numerical measurements and a settings whitelist, with no prompts, replies, file paths or API
keys. Its resource snapshot is current, not a per-request peak. Available RAM and total system swap are sampled
locally; model RSS, pressure and swap growth reuse the existing owned launch guard when available. No extra
pressure subprocess or native profiling callback is added.

The maintained API shell's metrics payload is extended additively through a Service subclass; authentication,
queueing, cancellation, sampling and generation still use the pinned implementations. Normal/native/mocked
timing sources must be kept separate when comparing measurements. The default model/profile is unchanged.

[Research queue and metric definitions](../bench/research/20261013-performance-tracking/REPORT.md). No new model
or GPU benchmark was run for this UI change. Latest local validation: 185 offline tests, five campaign-protocol
tests, seven JavaScript regression tests and eight actual HTTP smoke groups using a mock engine.

The later October13 real-model check now verifies these fields in the maintained editing app. The backend
retains the final native timing packet when the shell closes at EOS, with an EOS-only0.5second deadline and
responsive cancellation. Missing/cancelled counters remain unknown; a cancelled new request cannot inherit
the preceding request's metrics. The Monitor's draft acceptance covers all proposed tokens, including lookup
drafts. It does not isolate the MTP helper's acceptance.

Real complete-file API requests, all nine API/lifecycle integration groups, browser timing badges and numeric
export privacy passed with normal pressure/zero new swap. Current validation:207 offline tests, five campaign
protocol checks, seven JavaScript tests and18 CPU-only native matcher cases. Browser observations and controlled
editing benchmarks use different prompts/thinking settings and are not interchangeable speed comparisons.
Detailed results and exclusions are in the [decision ledger](../bench/EXPERIMENT-LEDGER.md).

## PR readiness audit

The later PR audit corrected supported JSON/CLI config handling, premature hardware-sampler
exit detection and parent protocol-reader error propagation. Every new benchmark entry point
now unwinds through owned-child shutdown and guard finalization on Ctrl-C, SIGTERM or SIGHUP.
Stops during process creation are deferred until child/guard ownership is published. A separate
CI check exercises the real parent driver with tiny Python children; it never loads a model or
runs GPU work. The network/native-denying offline gate remains separate.

Final audit checks: 253 load-free Python tests, six tiny-child termination tests, five campaign
protocol tests and seven JavaScript tests. Historical counts above describe their earlier passes.
Physical VoiceOver/mobile-keyboard validation and a new full-model performance comparison were
not part of this audit; previously recorded model results remain the performance evidence.

## Latest bug and polish validation

The [follow-up report](../bench/research/20261013-bug-polish/REPORT.md) records 22 corrected
findings and two deferred parked-tool findings. Local checks pass 281 load-free Python tests,
27 JavaScript tests, 12 benchmark-termination tests, six app-launch signal cases, two port checks
and five campaign-protocol checks. The six app signal cases share one test method.

Real browser checks cover mock completion, retained partial failure, intentional Stop, quick-link
startup, settings validation, reattachment notices and narrow/desktop layouts. Dark user-message
contrast is 11.4:1; 320 px chat/table fixtures fit the viewport. Review screenshots and detailed
receipts remain ignored, and no real model/GPU benchmark ran in this pass.
