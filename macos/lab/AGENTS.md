# Mac lab maintenance

This user's maintenance scope is the Mac app, its runtime helpers, benchmark
harness and browser UI. Leave inherited PC CUDA/HIP/SYCL engine, PC server and
installer code outside quality cleanup. Preserve those files for upstream history.
Revision-pinned vendor source stays unchanged; integration tests and source
receipts verify that boundary.

Use `mac-m5-lab` as the normal working branch, with at most one temporary branch
for an open PR. Implementation agents share that active branch with separate file
ownership. Remove merged PR branches afterward; preserve unique work in local
archive refs before retiring an older branch. Branch cleanup must preserve working
tree files, ignored models and runtime data.

`config/quality_modules.json` defines maintained Python lint, formatting and size
scope. Its paths must agree with the explicit mypy targets. Check commands:

```sh
python scripts/check_quality.py
python scripts/validate_offline.py
python -m unittest discover -s tests -p test_benchmark_termination.py
python -m unittest discover -s tests -p test_run_termination.py
python -m unittest discover -s tests -p test_profile_verifier_termination.py
python -m unittest discover -s tests -p test_runtime_ports.py
python -m unittest discover -s tests -p test_web_intake_sockets.py
npm run lint
node --test tests/*.test.cjs
```

Use the frozen Python/Node locks and the configured formatter. Critical Python
syntax/name checks apply throughout scripts/tests; fuller checks apply to the
manifest targets. Keep type boundaries explicit. Correct findings rather than
adding blanket ignores, suppressions or skipping failed tests.

Refactoring must preserve process ownership, signal publication windows, memory
guards, measurement scopes, failed receipts and normal-EOS correctness. Browser
changes must preserve classic-script lexical settings and documented writable
hooks. Run contract and tiny-process cleanup checks alongside lint/type checks.

Quality fixtures do not establish real model TPS, GPU correctness, physical
mobile behavior or full code coverage. Keep raw measurements, machine-specific
paths, model weights and local configuration ignored. Verify clean exported
source and hosted CI/Sonar at the exact PR head before reporting completion.
