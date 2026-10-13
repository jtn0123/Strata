# Mac workspace

The Mac launcher serves this page over the pinned API shell. `scripts/web_ui.py` replaces only the homepage and
`/web/mac.css` and `/web/mac.js`; API routes, authentication, sampling, cancellation, native engine settings and
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
