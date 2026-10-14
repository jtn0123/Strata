# Maintained Mac code checks

Sonar's PR analysis, tests, lint and type checks answer different questions. A
green Sonar gate alone is not proof of clean code or complete test coverage.
The PR's initial 21 Sonar findings were corrected and a fresh scan of
`77b9ad6` reported zero open findings and zero security hotspots. Subsequent
changes are checked again at their exact PR head.

## Scope

Ruff checks Python syntax and undefined names across all lab scripts/tests.
Its fuller error/style/bug checks cover eight maintained modules: native adapter,
app runner/stopper, profiles, telemetry, model provenance, cancellation helpers
and Metal environment isolation. Those modules use named types for model/cache
receipts, profiles, streaming events and service telemetry instead of relying
on conflicting inferred dictionary types.

Mypy checks those same eight modules and requires complete function signatures.
Cancellation and Metal environment helpers also enable the additional strict
checks. Local dependencies supply inferred types; older experiment/build helpers
are not claimed as fully type-checked. Revision-pinned `serve` and `gguf` imports
are explicit external boundaries. Dynamic JSON and vendor service factories still
use documented `Any` types; there is no blanket `ignore-errors` setting.

ESLint checks all three maintained browser scripts with recommended correctness
rules and additional guards against unsafe evaluation, undefined writes and
readonly-state mutation. Each script has an explicit browser/shell contract.
The global lexical settings supplied by the pinned API shell remain intact.

These checks do not cover the inherited CUDA/HIP/SYCL engines or installer, do not
establish physical mobile/VoiceOver behavior, and do not measure inference speed.
Model bytes, runtime settings and memory limits keep their separate qualification.

## Run

Use a separate development environment for quality tools; the model runtime's
dependency pins are unchanged. Python 3.12 and supported Node 22.13+ or Node 24+
are required. The CI installs hash-locked Python tools and lockfile-pinned Node
tools, then runs the same checks.

```sh
python -m pip install --only-binary :all: --require-hashes -r requirements-quality.lock
ruff check --config config/ruff.toml --select E9,F63,F7,F82 scripts tests
ruff check --config config/ruff.toml scripts/native_backend.py scripts/run.py scripts/stop.py scripts/runtime_profiles.py scripts/performance_metrics.py scripts/model_provenance.py scripts/benchmark_signals.py scripts/metal_environment.py
mypy --config-file config/mypy.ini
npm ci --ignore-scripts --no-audit --no-fund
npm run lint
```

Detailed local receipts, fault-injection checks, dependency caches and source
snapshots stay in ignored benchmark feature directories. Tests and exact-head
hosted checks remain separate evidence from lint/type success.

[QUALITY-PLAN.md](QUALITY-PLAN.md) lists the measured follow-on work, including
stricter checks, staged typing and benchmark-function separation.
