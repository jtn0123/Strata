# Maintained Mac code checks

The user maintenance scope is the Mac app, runtime helpers, benchmark harness and
browser UI. Inherited PC CUDA/HIP/SYCL code, PC server and installer remain intact
and outside this quality pass. Sonar sources are scoped to `macos/lab`; existing
third-party/evidence/test classification stays intact.

## Enforced checks

`config/quality_modules.json` defines 35 maintained Python targets. The checker
requires that scope to match mypy, validates that paths stay in Mac scripts, and
rejects missing modules and escaping symlinks. The targets include the active
editing, prompt-chunk and N00 prompt-operation drivers, the N00 native-log parser
`prompt_ops.py`, the N00b segment-timer parser `segment_ops.py`, the N15 helper-overlap timeline `overlap_ops.py`,
the N02 lookup-advice parser `advise_ops.py` and its driver `profile_advise.py`,
the N06 MTP-state comparison `mtpstate_ops.py` and its driver `profile_mtpstate.py`,
the runtime-profile verifier and their shared `trial_support.py` launch/response
helpers, and `api_requests.py`, the chat request contract checked before the pinned API shell. Critical syntax/undefined-name checks
still cover all lab scripts and tests, including older experiment drivers.

The fuller Ruff gate uses `E4,E7,E9,F,B,UP,C4,ISC,PIE,RET,PLW,C90`, with cyclomatic
complexity at most 10. The pinned formatter uses Python 3.12 and 120-column
wrapping. Mypy requires complete function signatures across all 35 targets;
20 enable the additional strict checks listed in `config/mypy.ini`. Named types
cover model/build receipts, launch configuration, memory policy/process snapshots,
metric evidence and workload callbacks. Dynamic JSON/vendor interfaces retain
explicit boundaries; revision-pinned `serve`/`gguf` traversal stays external.
There are no blanket ignore-errors settings or lint suppressions.

ESLint checks three production scripts and every Node test suite. Recommended
correctness rules are supplemented by undefined-write, readonly-state, unsafe
evaluation, shadowing, immutable-binding and promise guards. Production functions
have a cyclomatic complexity limit of 15. Classic-script settings and writable
hooks remain explicit; the pinned shell owns its lexical `settings`/`sharedOn`.
Whole-installation fixtures run the real pinned and maintained scripts in order.

Python file/function size is reported after the gate, with warnings above 500
physical lines per file or 80 per function. Source hashes and counts are saved in
ignored `bench/features/code-quality/latest-sizes.json` and retained by CI.
JavaScript's private containing IIFEs include nested helpers; their physical span
is not claimed as an 80-line pass. Named UI helpers and complexity are measured
separately.

Focused Python branch coverage has its own measured baseline and freshness gate:
93.61% of lines and 87.06% of branches across the 35 targets in the N06
MTP-state pass, with aggregate floors of 93%/87%. The N00b segment-timer pass
re-recorded every module's counts; some had not been refreshed since earlier changes. Floors are the
recorded percentages rounded down, so each module keeps its measured per-file
floors; the wait-diagnostic parser, `prompt_ops.py`, `segment_ops.py`, `overlap_ops.py`,
`advise_ops.py`, `mtpstate_ops.py`, `api_requests.py` and `trial_support.py` require 100% line/branch coverage. It uses the maintained
manifest, the native/network-denying offline inventory and source/config
fingerprints. Line/branch floors describe this measured scope; they are not a
whole-repository coverage claim. Node's experimental coverage currently reports
`ui-state.js` only (85.92% lines, 88.78% branches). Its browser-only `/metrics`
deadline wrapper runs in the whole-installation fixtures' VM contexts, which that
report does not count, so it cannot be reported as coverage of the complete UI.
Sonar's automatic analysis and the coverage gate are separate checks.

## Run

Use frozen runtime/quality locks in a development environment. Lab provisioning
installs the runtime lock and the quality lock with hashes and wheels only, as CI
does, so its mandatory offline coverage tests work in `.venv`; existing
environments can install those locks without rebuilding native code, using
the command in the lab README. Model runtime pins remain unchanged; quality tools
are development dependencies. Python 3.12 and
supported Node 22.13+ or Node 24+ are required.

```sh
python -m pip install --only-binary :all: --require-hashes -r requirements-ci.lock -r requirements-quality.lock
python scripts/check_quality.py
npm ci --ignore-scripts --no-audit --no-fund
npm run lint
node --test tests/*.test.cjs
```

Run the offline inventory under the configured coverage context, then check the
coverage receipt, using the exact commands in `.github/workflows/mac-lab-offline.yml`.
Tiny-process termination, socket ownership and campaign-protocol checks remain
separate from the network/native-denying inventory. Test methods, parity probes,
coverage percentages and lint/type results are separate measurements.

Raw logs, machine-specific paths, screenshots, coverage data, model bytes and local
configuration stay ignored. Verify a clean export and exact-head hosted CI/Sonar
before reporting completion. These checks do not establish real-model TPS, GPU
correctness or physical VoiceOver/mobile-keyboard behavior.

[QUALITY-PLAN.md](QUALITY-PLAN.md) records the completed work and remaining targets.
