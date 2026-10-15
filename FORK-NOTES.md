# Justin's Strata fork

A fork of [Niko1221/Strata](https://github.com/Niko1221/Strata) at v0.1.40.1 (commit `82f46a8`). It does two
things: runs Strata's model on an Apple M5 Pro Mac (48 GiB) in the Mac lab, and fixes the parent's server, installer
and docs here first.

## Branches and remotes

| | |
| --- | --- |
| `mac-m5-lab` | The default branch: all of the fork's work. Pull requests go here. |
| `main` | The parent's v0.1.40.1, unchanged. |
| `origin` | [jtn0123/Strata](https://github.com/jtn0123/Strata) |
| `upstream` | Niko1221/Strata, fetch only (`pushurl` is `no_push`) |

## Run it on the Mac

From `macos/lab`, double-click `Start Strata.command` (or run it in a terminal) and open http://127.0.0.1:8095.
`Stop Strata.command` releases the memory. The other launchers, what each profile does, and how to rebuild the
environment on a fresh clone: [macos/lab/README.md](macos/lab/README.md). Model weights, virtual environments and
vendor trees are not in the repository; the lab's pinned tools fetch them.

## Where things are

- **What runs now, and how fast:** [macos/lab/README.md](macos/lab/README.md#current-status--october-14-2026),
  each number with the workload it was measured on.
- **Every experiment, kept or dropped, and when to try it again:**
  [the experiment ledger](macos/lab/bench/EXPERIMENT-LEDGER.md).
- **The adopted profiles and their checks:** [PERMANENT-PROFILES.md](macos/lab/bench/PERMANENT-PROFILES.md).
- **Raw results and reports:** `macos/lab/bench/results/` and `macos/lab/bench/research/`.
- **Earlier checkpoints of this page (October 6-13):** [FORK-HISTORY.md](FORK-HISTORY.md).

## Working on it

Tests, checks and pull-request rules: [CONTRIBUTING.md](CONTRIBUTING.md). The lab's own rules:
[macos/lab/AGENTS.md](macos/lab/AGENTS.md). CI runs the server, installer, tools and web tests, the lint and
SonarCloud on each pull request, and the Mac lab's offline checks when `macos/` changes.
