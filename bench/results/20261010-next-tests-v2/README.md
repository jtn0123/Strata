# Sequential campaigns: preparation and execution

The campaigns prepared here have now executed. [Results and decisions](REPORT.md), [machine-readable metrics](REPORT.json), and [post-run verification](post-run-verification.json) supersede the earlier held status. U10-03 is parked, U10-02 is rejected for performance, and U10-01 has bounded MLX feasibility evidence. No new candidate is promoted.

The original preparation was superseded before execution by the memory-report path containment fix. Its frozen inputs remain under [the first preparation](../20261010-next-tests/README.md). Both v2 `frozen.json` records and the archived source remain unchanged. The earlier empty result sheets and preparation verification are historical preparation receipts, not current results.

The original sequential commands were `scripts/benchmark_input_cache.py --run` and `scripts/benchmark_m5_tile16.py --run`. They deliberately reject automatic retry or partial resume. Further work requires a newly declared campaign; do not rerun these unchanged attempts. MLX device, loader and response source/protocol/receipts are in their respective directories. R08 remains a design awaiting exposed helper-planning cost.
