# Justin's Strata Mac experiment

This fork starts from Niko1221/Strata commit `82f46a8c8f475f001ad76d92f58f4a4f8ffb0253` (v0.1.40.1). The `main` branch tracks that parent checkpoint. Mac work lives on `mac-m5-lab`, under [macos/lab](macos/lab/README.md).

The lab was imported through Git subtree without squashing. Its original setup, conversation-caching, prediction-helper and source-review commits remain in this branch's ancestry. [Raw results](macos/lab/bench/RESULTS.md), [prediction tradeoffs](macos/lab/bench/PREDICTION.md) and the [October 6 source review](macos/lab/bench/UPSTREAM-SCAN.md) are preserved.

The tested profile uses the pinned Strata macOS API shell and native llama.cpp Metal engine defined in `macos/lab/config/runtime.json`. Importing the lab into this fresh parent fork does not upgrade either runtime. The actual benchmarks were measured from the original `Strata-Mac-Lab` directory; absolute paths in their immutable records describe that machine and run.

Current everyday result: full Qwen3.8-Flash-Next GSQ-RCO Q2_0, all experts, lazy SSD lookup, 4K context, batch 512 and conversation caching, about 37–39 output tokens/s on the 48 GB M5 Pro. The smaller prediction helper is an optional measured profile. Tools and images remain outside the verified adapter scope.

The next candidate is Meld Turbo's focused Q2_0 Metal math patch. It passes a source-compatibility check against our existing engine but has not been applied or benchmarked on this Mac. First record sustained baseline timings, then test it separately with numerical/answer checks and matching API workloads. The normal launcher stays on the tested engine while experimental binaries are compared.

Model weights, virtual environments, downloaded vendor trees and active runtime files are ignored. They are reproduced with the lab's pinned provisioning/download tools; no model weights are stored in this repository. The original running lab remains in place for this checkpoint.

The local `upstream` remote is fetch-only (`pushurl=no_push`) and `origin` points to Justin's fork. Future lab changes can be imported from the original local repository with another subtree update, preserving experiment history.
