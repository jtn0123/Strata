# PR 3 readiness audit

Reviewed the full branch against `mac-m5-lab`, base `d9b88ec16b6b0b5fe53a394e1c751997c8efa012`
and original PR head `f89a249bccbe5dcd6a3b701226c13835ec6e69d0`. An independent skeptical
review also inspected the UI, native adapter, metrics and benchmark failure paths. CI passing
was treated as test evidence, not proof that every runtime failure path was correct.

## Confirmed issues and corrections

| Issue | Consequence before the fix | Correction and evidence |
| --- | --- | --- |
| Benchmark driver termination | SIGTERM bypassed `finally`, leaving an owned inference child alive and skipping guard finalization. An interrupt during child creation could also occur before ownership was assigned. | Shared Ctrl-C/SIGTERM/SIGHUP handling unwinds through existing bounded cleanup in all four new trial entry points and restores caller handlers. Process and sampler creation briefly defer stops until child/guard references are published. The real parent driver, with a tiny owned Python fixture, now reaps the child and finalizes the monitor for each signal, including stops during creation. Before/after receipts and regression tests preserve the failures. |
| Config parsing diverged from the retained shell | `--config=path` omitted performance settings; BOM JSON crashed startup; repeated configs selected the first value. | A small argparse pre-parser preserves supported forms, last-value precedence, BOM decoding and help behavior. Split/equals and BOM checks failed before the correction and pass afterward. |
| Premature sampler exit counted as healthy | A stopped hardware sampler could supply one valid reading and still satisfy the health gate. | Requested stopping is explicit; unexpected EOF and a child already dead at stop fail health. Normal owned shutdown remains valid. Both failure cases were reproduced before correction. |
| Protocol-reader errors stalled the waiter | A log/reader error ended its background thread without notifying the benchmark, leaving it waiting for the protocol timeout. | Errors and EOF are always queued to the waiting driver, which raises promptly and reaches cleanup. A refused-log regression failed before correction and passes afterward. |
| Thermal label 1 called nominal | Two summary rows understated the observed system thermal category. | Corrected to fair/slightly elevated using the public Apple SDK enum. Values remain 0 nominal, 1 fair, 2 serious, 3 critical; no new causal throttling claim is made. |

## Validation and boundaries

253 load-free Python tests, six tiny-child termination tests, five campaign-protocol tests and
seven JavaScript tests pass locally. The two subprocess checks run separately in CI; the
offline gate continues to deny real sockets and native execution. JavaScript and launcher
syntax checks and `git diff --check` also pass. Final hosted results are visible on the PR.

The full new branch history is audited for model/binary artifacts, credential signatures and
personal machine paths. Model weights, raw trials, local screenshots, process snapshots,
private configs, dependency/build trees and detailed audit receipts remain ignored. Committed
tests use synthetic content and generate disposable fixture paths at runtime.

No model/GPU benchmark was run for this audit, and no normal inference settings or model bytes
changed. Earlier measured performance reports remain the speed evidence. Physical VoiceOver,
mobile soft-keyboard behavior and a fresh real-model end-to-end run are separate acceptance
checks; this audit does not turn mock or tiny-child results into new TPS measurements.
