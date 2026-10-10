# RAM cleanup, 2026-10-10

Current available RAM: **33.846 GiB of 48 GiB**. Full native admission remains **34 GiB**; the separate paged MLX comparison plan requires **28 GiB**. No benchmark was started.

| Action | Measured outcome | Decision |
| --- | --- | --- |
| Release idle Qwen3.5 4B model cache | 2.553 GiB visible mapped residency cleared; available RAM gained 0.462 GiB, from 33.384 to 33.846 | Completed; file identity unchanged |
| Release idle native build/bin cache | 0.627 GiB visible mapped residency; available delta -0.090 GiB | No meaningful headroom gain; do not repeat unchanged |
| Inspect remaining registered helper models | No visible mapped cache in the six remaining helper models | No release needed |
| Inspect idle compiler object cache | 3,258 files of at least 64 KiB inspected; only 5.80 MiB visible resident | Too small to justify another cleanup pass |
| Identify largest WebKit process | PID 86592 is WiFiman Desktop Web Content, about 1.28 GiB RSS | Preserved because it supports the remote connection |

Both release trials recorded normal memory pressure and **zero new swap** throughout their 60-second settles. Existing swap remains 0.493 GiB. Neither trial maintained the 34 GiB native gate. Process RSS is approximate and may overlap; it is not the full physical-memory accounting.

No applications or services were stopped in this pass. No VM, Java build, native model server, or MLX model job was found active. T3, Codex, WiFiman, and system services remain running. The cleanup used read-only mappings and MS_INVALIDATE on idle lab files; it changed no model or build file identities and required no administrator prompt.

Small-model release evidence: `bench/results/20261009-small-gains/memory-investigation/small-model-cache-trial-20261010T133040486778Z/result.json`.

Idle-build release evidence: `bench/results/20261009-small-gains/memory-investigation/idle-build-cache-trial-20261010T133248164957Z/result.json`.

Detailed final memory/process evidence: [receipt.json](receipt.json).

The native benchmark remains held until its normal preflight passes. The paged MLX plan has sufficient admission headroom at this snapshot, but its planned warmed comparison runner still needs implementation; this cleanup is not a completed capacity or speed benchmark.
