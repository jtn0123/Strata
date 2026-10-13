# UI and nearby forks — 2026-10-13

Inspected current GitHub API data for the parent and a sample of active/popular forks. This is a targeted sample,
not an audit of all 2,333 forks. Checked web commit history for `jinzy0623/Strata-macOS`,
`migueldevops-real/Strata-Apple-Silicon-16GB`, `architectds/Strata`, `perronemirko/Strata`,
`eddoursul/Strata` and `MistVVK/XeStrata`. Raw API metadata and local hardware captures are not included.

| Source | Finding | Decision |
| --- | --- | --- |
| [Parent chart fix](https://github.com/Niko1221/Strata/commit/6a7c6f8275a551ae3940d7d434dd2e88a1ee59f4) | Tiny disk noise could fill an unlabelled sparkline; minimum axis scale is now 1. | Adopted through a small wrapper over the pinned chart function. |
| [Parent web history](https://github.com/Niko1221/Strata/commits/main/serve/web) | Favicon and prefill-rate reporting are newer than the pinned Mac UI. | Prefill columns are useful later, once native timing field parity is checked; no wholesale server update. |
| [Original Mac fork](https://github.com/jinzy0623/Strata-macOS) | The maintained Mac runtime still uses this earlier web shell. | Keep its API and existing assets; own a small local UI layer. |
| [Apple Silicon MLX fork](https://github.com/migueldevops-real/Strata-Apple-Silicon-16GB/commit/35e4396fc3) | Adds local PDF extraction, Apple GPU telemetry and macOS integration alongside a different inference backend. | PDF support and telemetry are promising separate features. Do not substitute MLX or import the entire patch. PDF requires a compatible extraction endpoint and dependency; telemetry needs independent validation. |
| [Usage proposal #2204](https://github.com/Niko1221/Strata/pull/2204) | Per-day/model token usage and optional energy/pricing persistence. Open proposal. | Keep as a follow-up. Accurate token totals are useful; electricity estimates must not be presented as measured Mac power. Use user-selected currency if pricing is added. |
| [PCIe proposal #2272](https://github.com/Niko1221/Strata/pull/2272) | Engine-side staging byte counters fill driver telemetry gaps on discrete GPUs. Open proposal. | The principle is useful; CUDA/PCIe staging counters do not describe this Metal unified-memory path. Missing counters are now explained in the UI. |
| [XeStrata](https://github.com/MistVVK/XeStrata) | Recent web work normalizes telemetry for several GPU vendors and exposes engine errors. | Useful error/availability semantics, but depends on its own engine/server changes. No direct transplant. |
| [architectds](https://github.com/architectds/Strata), [perronemirko](https://github.com/perronemirko/Strata), [eddoursul](https://github.com/eddoursul/Strata) | Sampled web history mostly tracks parent web changes, with GPU-specific work elsewhere. | No additional independently qualified Mac UI change found in that sample. |

Current pass: clearer chat workspace/composer, draft shortcuts, keyboard/dialog accessibility, both themes,
responsive layout, accurate missing-telemetry messaging and the small chart fix. Inference parameters, weights,
model size and benchmark results are unchanged. Suggested next UI work: real Mac telemetry, then PDF text
attachments, then request timing/token totals. Each requires feature tests before adoption.
