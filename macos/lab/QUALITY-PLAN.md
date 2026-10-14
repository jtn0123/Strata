# Mac code quality plan

Start with the code used by the Mac app and benchmark harness. Strengthen checks
in small steps, split functions by responsibility, and verify each change before
the next. File length is an investigation signal; it is not a quality grade.

## Measured starting point

The 2026-10-13 quality pass has full configured Ruff checks on eight maintained
Python modules, mypy on the same eight (two with extra strict checks), critical
syntax/name checks across lab scripts/tests, and ESLint on three browser scripts.
The local executable inventory has 294 offline Python tests. The separately run
campaign, termination, socket and browser inventories bring the total to 342.
Fresh archive validation and hosted CI must agree before treating a PR as ready.
Sonar must be checked at the exact PR head, including open findings and hotspots.

Physical lines include comments and blanks. Pinned vendor trees, model files and
raw experiment snapshots are excluded from this maintained-code comparison.

| File | Physical lines | Ownership / next action |
| --- | ---: | --- |
| `src/program/generate.cpp` | 11,102 | Inherited PC engine; separate qualification |
| `sycl/src/program/generate.cpp` | 8,380 | Inherited SYCL engine; separate qualification |
| `serve/server.py` | 5,015 | Inherited PC server; not the pinned Mac API shell |
| `setup.py` | 4,971 | Inherited PC installer; not the Mac launcher |
| `scripts/benchmark.py` | 532 | First maintained function-splitting target |
| `scripts/native_backend.py` | 444 | Refactored streaming/cache responsibilities |
| `scripts/benchmark_parent_metal.py` | 413 | Later campaign orchestration target |
| `scripts/benchmark_editing.py` | 406 | Later paired-run orchestration target |
| `web/mac.js` | 302 | Preserve classic-script shell ownership |
| `scripts/run.py` | 281 | Preserve owned-child lifecycle and signal cleanup |

The benchmark's `run` function is approximately 247 lines with cyclomatic
complexity 39. `benchmark_cache.run` is 166 lines with complexity 29. In contrast,
the refactored native adapter's longest function is 43 lines. Fix the concentrated
branching in benchmark orchestration first.

## Ordered work

Each item is a separate reviewable change. The proposals below are not yet new CI
requirements; [QUALITY.md](QUALITY.md) describes the checks currently enforced.

| ID | Improvement | Evidence and completion check |
| --- | --- | --- |
| Q1 | Strengthen lint and formatting in the existing eight-module scope | Prospective Ruff `UP,C4,ISC,PIE,RET,PLW,C90` checks currently pass. Review the four `RUF,SIM` suggestions before selecting rules. Normalize formatting using the pinned configuration, then enforce it: an explicit format check currently finds five of eight files would change. Keep all executable checks passing. |
| Q2 | Extend meaningful Python types to direct runtime helpers | `runtime_profiles` and `model_provenance` already pass strict mypy independently, allowing strict coverage to grow from two to four. Next targets: `benchmark_metrics`, `runtime_memory`, `check_memory`, `lab`, `engines`, then the `strata_server` bootstrap. Initial probing found 23 mypy gaps in five of these six files. Add signatures and named configuration/receipt contracts, then narrower native packet/timing types; do not hide dynamic interfaces behind blanket ignores. |
| Q3 | Split `benchmark.run` by job | Separate preparation, one owned native trial, response/metric validation and receipt publication. Extract the 156-line `Monitor` class so app admission does not import the entire benchmark harness. Preserve memory admission, signal ownership, failed receipts, prompt/output qualification and measured timing boundaries. Existing real-process cancellation and receipt regressions must pass unchanged. |
| Q4 | Simplify other campaign and launch orchestration after Q3 | Start with `benchmark_cache.run`, then editing and parent/current comparisons. Separate the launch plan, configuration/receipt preparation and lifecycle in the 159-line `run.execute`. Share only proven common lifecycle/receipt behavior; retain each experiment's pairing, cache state, correctness checks and measurement scope. Compare exact fixture receipts before and after. |
| Q5 | Strengthen browser checks and contracts | Production scripts already pass prospective `prefer-const`, `no-unused-expressions`, `no-promise-executor-return`, `no-shadow`. Extending recommended lint to the two Node suites finds one redundant assignment. Split Monitor/performance render functions with measured cyclomatic complexity 23/42, then ratchet complexity down. Keep readonly data, writable hooks, request/Stop/stale-reply and Monitor contracts explicit. A passing Node VM test and an actual browser check remain separate evidence. |
| Q6 | Measure focused branch coverage and dependency health | Current Node coverage reports `ui-state.js` only: 94.51% lines and 87.78% branches. Fragment execution does not establish `mac.js`/`performance.js` coverage. Establish coverage for maintained error/cancellation/cache/telemetry paths, then fill specific gaps. Keep coverage separate from tests run and Sonar's gate. Audit frozen dependency locks without silently upgrading runtime dependencies. Review any scanner-workflow change explicitly; automatic analysis and a CI scanner cannot simply be combined. |
| Q7 | Introduce size and complexity guardrails gradually | Start with reports/warnings around 500 physical lines per maintained file and 80 lines per function. Enforce cyclomatic complexity 10 in code that already meets it; retain Sonar's cognitive complexity limit 15. Ratchet existing hotspots down after tested splits. Do not create empty wrapper modules just to satisfy a length target. |
| Q8 | Revisit inherited giant files separately | Map natural engine/server/installer boundaries before changing them. Preserve upstream mergeability and require their own CPU/GPU/platform checks. Their LOC is visible debt, but splitting the PC engine does not establish a Mac speed improvement. Do not edit revision-pinned vendor sources to satisfy local lint. |

## Agent responsibilities and proof

- Python/type agent: rule probes, contracts and runtime-helper typing.
- Architecture agent: file/function inventory, separation boundaries and parity.
- Browser/test agent: JavaScript contracts, runtime tests and CI additions.
- Independent reviewer: check another agent's final diff and retained behavior.

Every item records its initial findings, exact changes, failed checks, resulting
checks and reviewed commit. Raw logs, machine-specific paths, coverage artifacts,
model bytes and screenshots stay in ignored feature directories. Reviewable
code/tests/configuration and concise qualification summaries belong in Git.

The native extraction was cross-reviewed using 5,000 tokenizer steps and 120
stream scenarios, including cancellation and downstream decoder failure. Metal
settings used 48,000 baseline comparisons; provenance used 17 tiny-file cases.
These are behavioral parity probes, not additional test-method totals or TPS
measurements. The new run-port guards intentionally reject malformed values
before resource checks; the import contract is also exercised by the offline
gate that replaces native process creation with a denying fixture.

Execute Q1, Q2 and Q3 first. Reassess the remaining order with their measured
findings. This quality pass makes no new model-performance claim.
