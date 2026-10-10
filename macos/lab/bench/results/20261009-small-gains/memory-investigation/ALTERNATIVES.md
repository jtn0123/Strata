# Alternatives to rebooting for benchmark memory

Research completed 2026-10-09 local time. This is a ranked investigation, not a cleanup run or accepted benchmark. No purge, simulated pressure, service restart, model load or protocol change was performed. The one resource-only model retry remains unused.

## Current evidence

[Read-only snapshot](alternatives-snapshot.json): 48 GiB physical RAM, 32.36 GiB psutil available, normal pressure level 1, 3.10 GiB wired, 1.58 GiB compressor occupancy and 529,137,664 bytes of existing swap. The current benchmark launch gate is 34 GiB, leaving a measured gap of about 1.64 GiB. This gate is a local conservative requirement, not an Apple hardware limit.

File-backed pages occupy 34.81 GiB and overlap the available estimate. Do not add these values. The separately reported volatile purgeable pool is only 135.69 MiB at this sample; it does not include every cache an application might voluntarily release.

## Ranked options

1. **Apple disk-cache purge: best immediate candidate.** `/usr/sbin/purge` exists on this Mac. Apple's manual describes flushing and emptying the disk cache; its kernel implementation requires administrator privileges. It does not free anonymous app allocations. Much of the cache is already included in our availability estimate, so a rise in free pages is not an equally large gain in available RAM. Whether it recovers the missing 1.64 GiB is unknown. It also makes model loading cold and can temporarily slow apps while they reread files. Candidate command, not executed: `sudo /usr/sbin/purge`.

2. **Brief simulated warning: experimental fallback.** Apple's `memory_pressure -S` sends pressure notifications without the tool allocating a large artificial workload. The published implementation also requests purgeable-cache cleanup, then resets the simulated state. This Mac's warning purge policy reports 2. Participating apps can release additional caches; the observed volatile pool alone is about 136 MiB, so do not promise multiple GiB. Candidate command, not executed: `sudo /usr/bin/memory_pressure -S -l warn -s 5`. A future wrapper must ensure a reset to normal even on interruption and verify actual pressure afterward. This is a system testing facility, not a guaranteed RAM-cleaning interface. Actual app responses and installed-kernel behavior still need validation.

3. **Reduce Strata's peak load allocations: longer-term engineering candidate.** This can address actual demand if cache cleanup is insufficient. First instrument allocation roles and lifetime, then investigate staging/releasing temporary load buffers with identical model/settings for control and candidate. The existing loader already avoids whole-file prefetch advice for lazy-table ranges; do not label that behavior a new saving. Context, KV precision or GPU-placement changes would need their own separately declared comparisons.

4. **Validate a cache-aware launch check: potential false-hold fix, not RAM reclamation.** Installed psutil counts inactive + free as available and excludes active file-backed pages. That warrants investigation, but does not prove all omitted pages are clean or safely reclaimable. A replacement check needs independent capacity evidence and a newly frozen protocol. Do not simply lower the existing gate, add file-backed bytes or accept swap-contaminated runs.

## Proposed next action

Start with one cache-purge trial, record identical counters immediately before/after and after a short quiet settle, and retain the existing swap guard. Success requires sustained available >=34 GiB with normal pressure and no new swap, not merely a larger free-pages counter. A cleanup-only success is not proof the full model fits. Only then can the existing unused model retry proceed with its original prerequisites. Record any purge consistently in later control/candidate cache preparation so cold-load timing cannot masquerade as a TPS gain.

Real allocation-based memory-pressure tools can cause compression/swap and defeat this experiment. There is no demonstrated multi-GiB service left to stop, so broad background-service restarts are not a useful first step. Keep T3, Codex and WiFiman running.

## Primary sources

- [Apple purge manual](https://github.com/apple-oss-distributions/system_cmds/blob/main/purge/purge.8): disk-cache purpose and anonymous-memory limitation.
- [Apple purge implementation](https://github.com/apple-oss-distributions/system_cmds/blob/main/purge/purge.c) and [kernel VFS implementation](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/vfs/vfs_syscalls.c): `vfs_purge`, administrator requirement and file-backed pager flushing.
- [Apple memory-pressure manual](https://github.com/apple-oss-distributions/system_cmds/blob/main/memory_pressure/memory_pressure.1) and [tool source](https://github.com/apple-oss-distributions/system_cmds/blob/main/memory_pressure/memory_pressure.c): simulated versus real allocation modes and reset sequence.
- [Apple pressure-notification kernel source](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/kern/kern_memorystatus_notify.c): notification and volatile-cache purge behavior.
- [Apple Activity Monitor memory guide](https://support.apple.com/guide/activity-monitor/view-memory-usage-actmntr1004/mac): cached, compressed and wired memory.

Published open-source implementations explain intended behavior; they are not a byte-for-byte verification of the installed macOS 27.2 kernel. Measured cleanup gains remain untested.

## Follow-up: non-admin cleanup tested

The user is remote and cannot complete a local administrator prompt. Global purge authentication was cancelled. A narrower method already used by this lab, read-only model mappings plus `MS_INVALIDATE`, then recovered **3.97 GiB of measured availability**, sustaining **>=35.97 GiB for 60 seconds with no new swap**. All model identities remained unchanged. This now ranks first for this remote setup. [Results and limitations](REPORT.md#authorized-remote-cleanup-2026-10-09-evening).
