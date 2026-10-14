# Parent native Metal trial on M5 Pro48GiB

The existing Flash-Next Q2 target was reused byte-for-byte. The parent is pinned at `ed4773eb7c8f1f1531ba2bc70e0e1987de2661af`; its CPU ggml dependency is `3cf03257f219afbe7334045ff7c6a06ac68c627d`. The engine, Python environment, dense/tokenizer pack,32GiB expert copy and launcher are isolated locally. No new model checkpoint was downloaded. Current launchers/defaults remain unchanged.

## Completed comparison

Four independent launches in current/parent/parent/current order; two requests per workload per launch,48 complete normal-EOS replies. The current arm is balanced P07/shared Q3/MTP3/mixed/eight helper workers. The parent arm streams experts with a20decimal-GB cache, no MTP and its default rounded Q8 hyper-connection read. Both use4K context, greedy sampling, the identical rendered prompt IDs and no prompt cache. Native timing definitions/transports differ: current HTTP SSE, parent stdin/stdout. OS cache state is unknown. First encounter and exact replay are retained separately in raw results; the table averages each launch's two-request median. Prose is the first request after startup, so its first-text average includes lazy parent initialization.

| Workload | Current TPS | Parent TPS | Parent TPS change | Current full reply | Parent full reply |
| --- | ---: | ---: | ---: | ---: | ---: |
| prose | 38.83 | 26.17 | -32.60% | 5.579s | 9.822s |
| code | 67.30 | 22.89 | -65.98% | 3.576s | 10.940s |
| python-client | 73.71 | 25.66 | -65.18% | 3.860s | 10.050s |
| javascript-queue | 73.31 | 26.12 | -64.37% | 4.042s | 10.288s |
| json-workers | 73.68 | 25.89 | -64.86% | 3.786s | 9.792s |
| long-retrieval | 64.77 | 31.48 | -51.40% | 5.064s | 3.912s |

**Long prompt:** first text4.600→2.967s (35.50% sooner); native prompt processing507.14→797.31tokens/s (+57.22%). Full reply5.064→3.912s (22.74% sooner) for this short retrieval answer. All four launches returned identical retrieval token IDs, but the original strict owner-string checker rejects both engines' correct `team Grove` spelling against expected `Grove`. Both other numeric facts are correct. This is a measured engine/workload difference; it does not qualify a transplanted optimization or a general decode improvement.

**Files:** all24 full-file outputs across Python/JavaScript/JSON match the expected edit and each other exactly, including token IDs. Parent generation is64.4–65.2% slower than balanced; full file replies take roughly2.5–2.6times as long. The separate kept editing profile has additional lookup drafting; its same-day functional observation is recorded below when complete.

**Other quality limits:** prose answers differ. Both engines add Markdown fences to the code despite the request; their original strict syntax checker therefore fails. Removing those fences exposes Python code, but this trial does not establish functional code equivalence or a broad quality grade. Missing protocol/final records or non-EOS/capped responses cannot enter the comparison; syntax/format checks are reported separately.

## Memory and safety

| Launch | Peak process RSS | Minimum available system RAM | New swap | Highest pressure level |
| --- | ---: | ---: | ---: | ---: |
| 1/current | 37.49GiB | 3.58GiB | 0bytes | 1 |
| 2/parent | 24.17GiB | 10.44GiB | 0bytes | 1 |
| 3/parent | 24.57GiB | 10.52GiB | 0bytes | 1 |
| 4/current | 37.51GiB | 3.72GiB | 0bytes | 1 |

All four monitors are healthy, observe continuous normal pressure and verify owned-child exit. Total system swap was already about0.20GiB at entry; accepted launches added zero. RSS can count shared mappings and is not unique VRAM. The parent's observed peak RSS is about13.1GiB lower; its minimum available RAM is about7GiB higher. Startup-to-ready is not complete startup-to-answer: the parent initializes its real Metal window/arena lazily on its first request. Source, binary, model and generated-pack identities are frozen and preserved locally.

## Attempts kept out of the performance comparison

- Q8 smoke v1/v2: RAM admission held for90seconds; no child or output. Preparing/reading the large expert copy promoted clean file cache.
- Q8 smoke v3, automatic arena26.58GB: the normal-pressure guard stopped the owned engine at pressure level2 before any answer. The launch itself recorded no additional swap. Total swap had risen to0.20GiB during the preceding unmonitored cache-settle interval; the exact attribution is unknown. No default-arena TPS result.
- Q8 reduced20GB smoke: all six normal-EOS requests completed with normal pressure and zero new swap. This is an initial observation, separate from the completed four-launch bracket.
- Comparison v1: first current/parent launches completed; third admission remained just below34GiB. The partial bracket is excluded. Repeated SHA scans of the1.38GiB dense pack promoted cache pages; maintained tooling now caches exact hashes only while device/inode/size/mtime/ctime match, and rescans changed files. A mutation regression test passes. A new full bracket was run without pooling partial timings.
- BF16-HC20GB smoke: one prose reply completed; the next request was stopped for11.0625MiB of new swap. Entire attempt excluded from speed claims. No approximation-free parent engine is qualified on this48GiB configuration.
- Editing supplement v1: admission held; no child or reply. A bounded read-only invalidate of the private expert-copy cache released about2.4GiB, with no data/identity change or new swap. The independent v2 supplement uses a new directory.

System-wide purge was unavailable without privileges. Cleanup used owned, read-only file mappings outside the accepted bracket, with identity checks and pressure/swap observations. `MADV_DONTNEED` deactivates pages but is not proof of physical eviction; a bounded `msync`/`mincore` probe verifies removal of clean mapped pages. Cache state remains unknown. No apps/VMs were stopped or restarted. Source model files, precision and the34GiB/normal-pressure/zero-new-swap guards were not weakened.

## Practical difference

Our resident target and small shared draft helper produce several verified tokens per full-model pass. The parent's safe cache here holds14361of24576expert slots; it fetches missing experts and waits between layers, and its48GiB setup omits MTP. Its dedicated long-prompt matrix kernels/chunking nevertheless read this long prompt faster. The parent's reported108–120TPS uses an M5 Max128GB with resident weights and MTP, a different resource configuration from this trial.

**Decision:** keep our current engine for normal generation and editing. Preserve the parent trial for memory/capacity and long-prompt work. Investigate its prompt kernels separately; do not switch the normal app or add the prompt improvement to decode percentages. Rounded Q8 HC, different batching, streaming and lack of MTP are explicit differences rather than an isolated one-variable optimization.

Raw evidence and private configurations stay local under `bench/results/20261013-parent-metal-comparison-q8-20gb-v2` and `bench/private/parent-metal-20261013`. Reproduce the comparison with `scripts/benchmark_parent_metal.py --mode comparison --hc q8 --arena-gb 20 --output bench/results/<new-directory> --run`. Without `--run`, it only prints the plan.

## Same-day kept editing supplement

One additional guarded current-engine launch uses the existing code-edit profile on exactly the three comparison files, with two normal-EOS requests each. All six whole-file edits pass. This is a functional/current-rate observation, not an independently confirmed new gain or part of the balanced/parent bracket.

| File | First edit TPS | Replay TPS |
| --- | ---: | ---: |
| javascript-queue | 88.34 | 90.58 |
| json-workers | 86.30 | 89.31 |
| python-client | 87.15 | 90.93 |

Normal pressure, zero new swap, minimum available RAM4.11GiB and healthy owned-child shutdown.

## Interactive app differs from the performance configuration

The parent web/OpenAI-compatible API is separately prepared at localhost8097. A20GB-cache API request
returned the exact Python edit, but the normal-pressure guard stopped that session during idle at level2,
with no new swap. Its resident footprint fell while its anonymous arena stayed allocated; idle compression
is a separate issue from continuously active benchmarks. Do not treat the20GB bracket as proof of stable
interactive operation.

The interactive-only cache was reduced to12GB, preserving Q8 HC/no MTP/4K and every guard. Its first admission
was held below34GiB, with no model. Startup can now invalidate only the verified private expert-copy cache
when admission needs room, then waits on the unchanged threshold. It refuses cache cleanup while any model
is active, checks source/file identities, performs no model payload read or anonymous allocation, and never
clears caches within the performance bracket. A regression check covers refusal before file access.

Two actual JSON-file API edits end normally and match verbatim with12GB; observed whole requests10.28/12.10s.
Those API timings are functional observations with different frontend/transport, not the20GB engine table.
The guard persists a failed-session marker so a server retry cannot silently relaunch after a resource stop.
The private launcher and config are generated locally, contain local paths, and stay out of Git.

To try the UI again, double-click `bench/private/parent-metal-20261013/Start Parent Metal Trial.command`.
Only one Strata engine may run. Use Ctrl-C in its terminal to stop it. The normal Strata shortcuts still run
our existing engine. This trial has its own parent UI; our custom Monitor/performance history was not moved
into it.

The12GB app remains loaded/healthy across idle checks separated by149.1s. A fresh app session after the shutdown correction returns another exact normal-EOS API edit. The local API/native processes are stopped and port8097 is closed. Its final guard reports normal pressure, zero new swap, minimum available RAM19.72GiB, peak process RSS17.25GiB and healthy child exit.

The guard originally waited inside its signal handler, which can reenter `Popen.wait` while its lock is held. Nonblocking termination forwarding and a bounded kill timer replace that path. A held-wait-lock regression fails with the previous handler and passes after the fix; actual app signal closure now writes a healthy guard receipt. Shutdown process matching resolves the local vendor symlink before identifying owned processes.222 maintained load-free checks pass.

Arena-fill throughput printed by the parent includes cached reads and is not a raw SSD bandwidth measurement. Native prompt/reply timings in the table are the measured results; no disk-speed percentage is inferred.
