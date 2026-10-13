# Mac workspace

The Mac launcher serves this page over the pinned API shell. `scripts/web_ui.py` replaces only the homepage and
`/web/mac.css`, `/web/mac.js` and `/web/ui-state.js`; API routes, authentication, sampling, cancellation, native engine settings and
the shell's original assets stay with the pinned server. The upstream download is not modified.

`index.html` derives from `jinzy0623/Strata-macOS` at `2cc4153409edb3f859187bdf10f13e34972d6ffb`, retaining its
control IDs and all original chat/monitor/settings behavior. Original Strata attribution and MIT licensing
apply; the local Outfit font retains its SIL OFL license in the pinned shell. No CDN, new font download,
JavaScript framework or model download is needed. `mac.js` uses the pinned shell's classic-script functions;
refresh this compatibility layer and its control-ID test when changing that dependency.

The interface adds draft-only prompt shortcuts, responsive layouts, light/dark colors, keyboard tab selection,
and a settings dialog with focus containment and focus restoration. The closed dialog is inert. Reduced-motion
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
