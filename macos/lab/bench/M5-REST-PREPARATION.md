# Remaining M5 preparation — October 7, 2026

The [11-card queue](plans/20261007T231811Z-m5-future/preparation.json) is staged. **90 offline tests pass**, provisioning prechecks pass, and the separate correctness candidate compiles. No model/GPU test, real SSD payload probe or inference benchmark ran during this preparation. No TPS gain is claimed. Changes remain local/uncommitted; the fork's older lab snapshot has not been synchronized.

| Added | Validation and limit |
| --- | --- |
| Isolated `m5-correctness` engine | Original `m5-lab` plus upstream #30100 residual-source fix. Combined patch/source hashes match; server and operation tester compile. GPU CPU-reference regression and fresh model ABBA comparison are held. Current Qwen graph exposure is unproved. |
| 8K context runner | Four launches in 4K/8K/8K/4K order; identical shorter speed inputs plus three separate 6144-token recall fixtures. Offline exact-token geometry, full mocked lifecycle and comparison rejection cases pass. Real tokenizer/recall/continuation/rollback and 8K peak memory remain untested. F16 unchanged. |
| RAM accounting | Saved headers plus the earlier accepted baseline log. Weight/helper/private-buffer components separated from mapped file spans. Accounting estimates are not physical peak/RSS or admission decisions. |
| Lookup-file probe | Up to 128 page-aligned offsets, three passes, at most 8 MiB total read-only `pread` I/O; bounds/short-read/default-hold tests pass. Plan saved without reading model payload. Cache state is uncontrolled; native mmap waits and TPS remain unmeasured. |
| Metric checks | Every required TPS/time sample must be finite and positive before aggregation/division; bad counters, NaN/infinity/zero/negative values and percentage overflow are rejected. Applies to fresh and cached cases. |
| Provisioning and offline gate | Clean source pins/Python 3.12 prechecked; builds produce a required baseline receipt. Explicit offline inventory denies unmocked sockets/network/native launches. A failed/stale receipt blocks accepted plan-card creation. |
| Recreation documentation | One ordered [recipe](M5-PREPARATION-RECIPE.md) covers source/build/helper/header/diagnostic/gate steps and external dependencies. Fresh-directory reproduction remains untested. |

All **seven original engine receipts match the prior preparation**, and the existing diagnostic executable/libraries still verify. The new engine is an eighth isolated build. Existing app launchers/defaults remain unchanged. No unrelated VM/build/app was stopped; Colima and Grafana were not restarted. No background benchmark waiter was installed.

## Saved memory accounting

[Header/log report](features/20261007-rest-memory-budget.json), using the previously accepted `20261007T052606Z-m5-decision-baseline-1` server log:

- Target unique weight tensors: **35.03 GiB**.
- Packed helper file: **1.17 GiB**, plus **0.44 GiB** observed CPU repacking.
- Logged non-model buffers: about **0.92 GiB**.
- Separate lazy lookup table: **26.82 GiB on disk**, with touched pages still consuming RAM.

The conservative component sum is about **37.55 GiB** before OS/background/driver overhead and resident lazy pages. It is an accounting estimate and may include overlapping/nonresident file pages. It is neither a measured lower bound nor proof that an 8K context fits. Native allocation logs and actual headroom/zero-swap behavior must establish that during the held trial.

## Next test sequence

After the user's testing go-ahead and a passing quiet-host/34-GiB full-model preflight: complete the two-launch unchanged baseline refresh; validate the correctness candidate separately; capture real expert routes and split remaining GPU work; then try 8K capacity and the bounded lookup-file fixture. Record raw receipts, TPS, first-token and complete-reply time, drift, memory and percentage differences from fresh controls.

Native prefetch, a targeted kernel, larger-model paging and quantized KV remain dependency-gated designs. Their cards are concrete protocols and stop criteria, not implemented optimizations. Quantized KV needs the applicable upstream attention-overflow fix first. The current F16 cache is unaffected by that proposed precision experiment.

## Evidence

- [Preparation receipt](features/20261007-rest-preparation.json).
- [Dated offline log](features/20261007-rest-preparation-offline.log) and [receipt](features/20261007-rest-preparation-offline.json).
- [Candidate CPU build log](features/20261007-m5-correctness-build.log) and [build/source receipt](features/20261007T231313Z-m5-preparation.json).
- [Lookup read plan](features/20261007-rest-lookup-plan.json); no actual read timing results exist.
- [Astra source-level review](research/20261007-astra-macos-deepdive.md).

Audit F1, G3, H1 and I1 are completed locally; F2 remains partial pending fresh-directory dependency reproduction. Original grades remain unchanged pending a regrade.
