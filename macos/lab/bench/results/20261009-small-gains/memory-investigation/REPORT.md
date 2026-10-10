# Memory investigation after the full-model hold

The user reports no other work is running. Current process evidence supports that: no large VM, Docker, Java/Gradle, Ollama or native model process was identified. Closing more ordinary apps is not a demonstrated solution to this hold.

## Measured state

The final diagnostic snapshot reports 48 GiB physical RAM, about 32.58 GiB psutil available, normal macOS pressure (level 1), 34.58 GiB file-backed pages, 6.93 GiB anonymous pages, 3.12 GiB wired pages and 1.82 GiB occupied by the compressor. These kernel counters are sampled, not an atomic partition of every physical byte.

**File-backed memory overlaps the active/inactive counters and the available estimate. Never add 34.58 GiB to 32.58 GiB.** File-backed pages include mapped file data and code; the counter does not establish that every page is clean, idle or immediately reclaimable. Earlier in this investigation it measured 36.23 GiB; it is not a fixed model reservation.

The installed psutil macOS implementation calculates `available = inactive + free`; `used = active + wired`. It does not include active file-backed pages in available. Apple identifies file cache as memory used to improve performance that can be overwritten, and distinguishes wired and compressed memory from cache. Thus psutil is a conservative proxy here, not a complete measure of all capacity macOS can make available without swapping.

The final overlap calculation establishes at least 2.63 GiB of file-backed pages outside the inactive/speculative lists. It **does not establish 2.63 GiB of clean immediately reclaimable memory**, nor justify adding it to the benchmark metric or bypassing the existing launch gate. This is a reason to investigate a better preflight, not proof the model can load with zero new swap.

Native `proc_pid_rusage` data were readable for 408 processes; 259 denied/gone entries were retained as an explicit coverage limitation. Largest reported process footprints were WebKit around 0.89 GiB, T3 renderer around 0.44 GiB, WiFiman around 0.31 GiB and mediaanalysisd around 0.23 GiB. These footprints can include compressed backing and are not additive unique resident RAM. No hidden multi-gigabyte user job was identified. WiFiman remains running as previously requested for connectivity.

## Actions and conclusions

- Read-only kernel/process/counter investigation, with bounded metadata queries. No model benchmark, forced memory pressure, cache purge, unrelated app closure or system-service restart was performed.
- Activity Monitor was launched for a diagnostic cross-check, but the computer-use binding could not obtain its window. The owned diagnostic process was then closed, releasing roughly 92 MiB of reported RSS. Its unavailable UI is not evidence for any capacity estimate.
- The 34 GiB minimum is a deliberately conservative local preflight setting, not an Apple hardware limit. The X24 initial load's 3.0625 MiB of global swap growth proves the strict resource gate failed; it does not identify the source of that growth or prove the machine lacked physical capacity. All old exclusions and the one resource-only retry allowance remain intact.
- A user-controlled restart is the simplest clean reset of accumulated process/compressed/kernel state. It can recover headroom, but no quantity or zero-swap success is guaranteed, and it makes the file cache cold again. Reopen only T3 and keep the required networking service. No reboot was initiated.
- A potential future change is a separately preregistered cache-aware preflight using verified native counters and pressure. Do not add overlapping file-backed bytes, treat dirty pages as freely discardable, relax the zero-new-swap rule, silently change historical protocol, or claim the existing model tests passed. Such a change needs independent resource validation and a fresh source/plan closure before model testing.
- The pinned loader already excludes lazy-table ranges from whole-file prefetch advice. Its separate `llama_prefetch` implementation is active only on Linux/Windows, so the model log's "enabling prefetch" line alone does not establish a giant lazy-table prefetch on macOS. No loader change or memory saving was made or claimed.

The campaign remains held below its existing 34 GiB preflight. The new finding changes the explanation: **there is no obvious large app left to close, and the conservative availability figure is not proof that all other RAM is occupied by applications.**

## Evidence

- [Non-reboot alternatives and proposed measured trial](ALTERNATIVES.md) — researched without running cleanup or changing benchmark gates.
- [Initial VM/process snapshot](initial.json)
- [Final VM/process-footprint snapshot](final.json)
- [Owned diagnostic cleanup](actions.json)
- [Small-gain validation and exclusions](../REPORT.md)
- Installed psutil source: `.venv/lib/python3.12/site-packages/psutil/_psosx.py`, `virtual_memory()`.
- [Apple memory-pressure and cache definitions](https://support.apple.com/guide/activity-monitor/view-memory-usage-actmntr1004/mac)
- [Apple kernel VM counter definitions](https://github.com/apple-oss-distributions/xnu/blob/main/osfmk/mach/vm_statistics.h)
- [Apple virtual-memory page-list behavior](https://developer.apple.com/library/archive/documentation/Performance/Conceptual/ManagingMemory/Articles/AboutMemory.html)

## Authorized remote cleanup, 2026-10-09 evening

The user authorized the cache-reclamation trial and then clarified that they are remote. The administrator-only global `purge` could not be authenticated: its owned AppleScript client was cancelled, and no global purge completed. [Attempt](purge-trial-20261010T033134499882Z/result.json), [owned-client cancellation](purge-auth-cancelled.json).

Instead, the previously used non-administrator `MS_INVALIDATE` method was applied only to the verified target model's two shards and packed Q3 helper. Files were opened read-only, mapped read-only, and neither read nor written through those mappings. All three cache calls returned zero and all model identities remained unchanged. `mincore` observes residency visible to the new mappings, not all system-cache capacity.

**Measured available RAM rose from 32.09 to 36.06 GiB, a gain of 3.97 GiB.** All 30 settle samples over 60 seconds stayed between 35.97 and 36.06 GiB with normal pressure and zero new swap. The roughly 29.20 GiB reduction in observed mapped cache is not an equal gain in available RAM: most of that cache was already included in availability. T3, Codex, WiFiman and unrelated services remain running. Colima remains stopped.

[Raw cleanup evidence](model-cache-trial-20261010T033512403513Z/result.json) and [exact cleanup driver](model-cache-trial.py) are retained. This passed cleanup eligibility for the unchanged canonical preflight; it is not proof the full model fits or a TPS measurement. The existing resource-only retry driver was then started with the same source closure and guards; see the campaign report for its outcome. Cache preparation and the original retry-driver hash were recorded in `../host-preparation-20261010T033702104144Z.json`.

The model campaign subsequently completed all **16 full-model launches with zero new swap**, 416 passing answer/cache checks and exact tested-output parity. The final source closure and native prerequisites remained valid. This provides model-fit evidence for these exact settings and runs, beyond the cleanup-only result. [Campaign report](../REPORT.md), [final verification](../final-model-verification.json).

[Post-benchmark resources](post-benchmark-resources.json): 38.49 GiB available, normal pressure, swap still 529,137,664 bytes, no model/VM/Java jobs identified and Colima stopped. The later 38.49 GiB reading also includes natural model-process cleanup; do not attribute its entire difference from the original availability to explicit cache invalidation.
