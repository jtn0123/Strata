# Mac quality work and next targets

Maintenance is Mac-only. Inherited PC engine/server/installer files are preserved
and outside the cleanup queue. `mac-m5-lab` is the normal working branch, with one
temporary branch while a PR is open. Unique older work is preserved in local
archive refs before branch retirement; worktree/model files are retained.

## Completed implementation

| ID | Change | Qualification |
| --- | --- | --- |
| Q1 | Stronger lint and formatting | More Python rule families, C901 at most 10, configured formatting, explicit manifest/type-scope agreement, stronger production/test ESLint and JS complexity at most 15. |
| Q2 | Wider meaningful typing | 20 maintained Python targets, 13 with additional strict checks; named registry/build/memory/metric/launch/workload contracts and preserved pinned bootstrap order. |
| Q3 | Benchmark responsibilities separated | Shared `memory_monitor` removes app admission's dependency on the whole benchmark driver; `trial_workloads` owns workloads behind typed callbacks. Resource/receipt ownership stays visible in the benchmark coordinator. |
| Q4 | Cache and launcher orchestration separated | Preparation, owned execution, measurement and publication phases retain their cancellation windows, thresholds, cache state and failed receipts. |
| Q5 | Browser contracts and helpers strengthened | Five whole-installation tests run actual pinned plus maintained scripts. Named installers/formatting helpers retain lexical settings, startup streaming, cancellation, attachments, Undo and numeric export privacy. |
| Q6 | Focused branch coverage baseline | Source scope and freshness are verified alongside a measured line/branch baseline. This is independent of Sonar automatic analysis and of Node's partial coverage report. |
| Q7 | Size and complexity reporting | Manifest-selected Python source receives file/function counts and hashes, warning above 500/80 lines; CI retains the report. Existing experiment/third-party snapshots do not enter these file limits. |

The initial comparison is commit `39e5a997`; physical lines include comments and
blanks. Function spans include signatures. File length remains a signal, while
responsibility boundaries and retained behavior determine whether a split helps.

| Code / metric | Before | After |
| --- | ---: | ---: |
| Main benchmark file | 532 | 365 |
| `benchmark.run` function | 247 | 68 |
| `benchmark_cache.run` function | 166 | 42 |
| `run.execute` launcher function | 159 | 37 |
| Monitor render cyclomatic complexity | 23 | 10 |
| Performance render cyclomatic complexity | 42 | 8 |
| Explicit Python lint/type targets | 8 | 20 |
| Python targets with additional strict checks | 2 | 13 |

Some files grow when named contracts and previously compressed code are expanded.
The cache file is 463 lines after this pass; the main UI file is 365. Containing
private JS IIFEs include their nested named helpers and are not claimed below 80
physical lines. Their complexity and individual helpers are checked separately.

## Retained behavior and evidence

Implementation ownership was divided across Python helpers, benchmark structure,
browser contracts and coordinator tooling/launcher changes. A separate reviewer
checked the combined implementation without editing it. Coverage has its own
implementation and review lane.

Focused comparisons include 5,400 command/error cases, 5,288 metric/counter cases,
18 bootstrap/config forms and 17 complete benchmark/cache campaigns. The
campaign comparisons preserve each receipt publication, payload/cache trace,
warmup pairing, AB/BA order, outcome/error and CSV. Parity cases are not additional
test-method counts or new model-speed measurements.

The offline inventory denies network/sockets/native execution. Tiny-process
termination, port ownership and campaign protocol checks are run separately.
Mock browser checks retain startup, complete responses, settings, Monitor's mock
label/requests and narrow layout. All raw receipts, source snapshots, coverage
artifacts, screenshots and private machine data stay ignored. Check current
hosted CI and Sonar against the exact PR head before calling the work qualified.

## Remaining work

1. Use the new coverage report to select real untested failure branches. Add
   meaningful reproductions and raise floors as those gaps close.
2. Extend fuller checks from the maintained core to experiment drivers when a
   driver is actively changed; preserve each experiment's benchmark protocol.
3. Consider CSS/HTML semantic checks and additional browser accessibility
   contracts. Physical VoiceOver/mobile-keyboard behavior still needs its own
   testing.
4. Reassess parent/current and editing campaign extraction when it provides a
   concrete ownership or reuse benefit. Avoid wrapper files just to reduce LOC.

No new runtime/tool upgrades are inferred from a green gate. Model weights,
memory limits, native kernels and inference presets retain separate qualification.
