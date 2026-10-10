# Refreshed held campaigns

These campaigns include the memory-report path containment and non-overwrite fix found during PR review. The original campaigns are preserved under [the first preparation](../20261010-next-tests/README.md) and were never run.

Use the same sequential commands: `scripts/benchmark_input_cache.py --run` for the pinned 4B Service test, then `scripts/benchmark_m5_tile16.py --run` for the complete GPU-block screen. Their frozen rules, workloads and acceptance limits are unchanged. Source hashes and offline qualification are fresh. No model or GPU benchmark has run; all performance fields remain empty. The MLX environment receipt and helper-reuse design retain their previous boundaries.
