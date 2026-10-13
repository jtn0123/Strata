# E06: optional long-document mode and runtime investigation

October13,2026;48GiB M5 Pro. The new optional Long Documents launcher selects batch/ubatch1536/1536 on the maintained P07/TensorAPI/sharedQ3/MTP3 stack. It uses the same fullQ2 model,4K/F16, mixed helper placement and eight helper CPU workers. Balanced and Code Editing retain512/512; the Code Editing guard continues to reject unqualified larger batches.

## App implementation and proof

- Separate executable `Start Strata - Long Documents.command`; choose it for reading long supplied text. Code Editing remains the faster supplied-file edit profile. Stop the current server before switching launchers.
- `run.py` now sets logical batch as well as physical chunk size and rejects invalid sizes before engine/model access. Native logs prove both target and helper use1536. Actual API Monitor/export settings include both limits; no silent clamp or inferred recipe.
- The real launcher passes greedy/sampled English facts, a complete file edit, SSE completion, long-document JSON facts, all integration groups, continuous memory guards and clean shutdown. No speed percentage is inferred from these API feature checks. Private proof: `bench/features/20261013-long-documents-api-v1/verification.json`.
-239 maintained load-free checks and JavaScript syntax validation pass. Existing normal launcher files remain unchanged; profile defaults are explicit512/512. No model or native math modification.

## Hardware investigation method

Two separate complete A/B/B/A brackets, each72normal-EOS answers: two English long inputs, three other complete Python/JavaScript/JSON files and short prose, three requests per task. All144answers match complete text/output IDs and rendered input identity. Normal pressure and zero new swap in every launch; sampler/native children stopped. Initial total swap about0.21GiB remains distinct from growth.

Both brackets use editing lookup16/width3 plus MTP on every arm. First exposure and two replays are separate. Prompt cache is off; native reused count is0. Replays can reuse learned draft lookups, so86TPS repeat prose is not a new-question chat rate. Complete original sources, engine/model/tool pins and raw metrics remain local and ignored. The two source versions are retained separately; their request samples are not pooled.

The owned sampler uses installed macmon0.8.2, pinned executable hash/version, at1Hz for GPU frequency, SMC temperatures/fans and CPU contention; [macmon source](https://github.com/vladkens/macmon). Public [NSProcessInfo thermalState](https://developer.apple.com/documentation/foundation/processinfo/thermalstate-swift.property) supplies the system thermal category. These are whole-device observations, not target GPU-kernel timing or per-process GPU attribution. CPU/ANE power fields are deliberately not interpreted.

The initial load-free sampler smoke fails when an idle/power-gated GPU reports clock0. The failed receipt is retained; a fresh3-sample capture confirms clock0/active ratio0. The corrected reader records frequency as unavailable and continues, with a fail-before/pass-after stream regression. A fresh four-sample smoke and both model brackets pass. Unknown readings are never presented as measured zero clocks.

## Clock/temperature pass

Raw local evidence: `bench/results/20261013-prompt-chunks-1536-hardware-v1/campaign.json`.

| Long task / phase | Prompt tok/s: control → candidate | Generation TPS: control → candidate | First text: control → candidate | Reply: control → candidate | Reply saved | Qualified prompt scope |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| long-retrieval / first-exposure | 517.41 → 557.96 | 65.43 → 64.30 | 4.508s → 4.181s | 4.967s → 4.648s | +6.43% | yes, this scope |
| long-retrieval / replay | 522.50 → 574.87 | 73.44 → 73.31 | 4.464s → 4.057s | 4.873s → 4.467s | +8.33% | yes, this scope |
| long-prose / first-exposure | 517.32 → 577.09 | 56.97 → 57.54 | 4.536s → 4.066s | 4.711s → 4.240s | +10.01% | yes, this scope |
| long-prose / replay | 521.62 → 576.26 | 57.72 → 57.31 | 4.498s → 4.072s | 4.672s → 4.250s | +9.04% | yes, this scope |

| Arm | Peak GPU °C | Active GPU median MHz | Peak system thermal category | Minimum available GiB | New swap bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1: 512 | 87.37 | 1607.0 | 0 (nominal) | 3.787 | 0 |
| 2: 1536 | 93.51 | 1619.0 | 0 (nominal) | 2.918 | 0 |
| 3: 1536 | 91.07 | 1619.0 | 0 (nominal) | 2.985 | 0 |
| 4: 512 | 84.31 | 1602.0 | 0 (nominal) | 3.806 | 0 |

## Fault/output-gap pass

Raw local evidence: `bench/results/20261013-prompt-chunks-1536-faults-v1/campaign.json`.

| Long task / phase | Prompt tok/s: control → candidate | Generation TPS: control → candidate | First text: control → candidate | Reply: control → candidate | Reply saved | Qualified prompt scope |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| long-retrieval / first-exposure | 516.29 → 559.78 | 65.92 → 62.95 | 4.518s → 4.167s | 4.974s → 4.644s | +6.64% | no |
| long-retrieval / replay | 522.67 → 572.51 | 73.62 → 72.99 | 4.463s → 4.074s | 4.870s → 4.485s | +7.91% | yes, this scope |
| long-prose / first-exposure | 522.49 → 575.74 | 57.81 → 55.97 | 4.491s → 4.075s | 4.664s → 4.254s | +8.79% | no |
| long-prose / replay | 522.29 → 575.87 | 57.82 → 57.43 | 4.493s → 4.075s | 4.666s → 4.249s | +8.93% | yes, this scope |

| Arm | Peak GPU °C | Active GPU median MHz | Peak system thermal category | Minimum available GiB | New swap bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1: 512 | 87.24 | 1602.0 | 0 (nominal) | 3.688 | 0 |
| 2: 1536 | 94.44 | 1619.0 | 0 (nominal) | 2.854 | 0 |
| 3: 1536 | 88.64 | 1619.0 | 1 (nominal) | 3.005 | 0 |
| 4: 512 | 83.82 | 1599.0 | 1 (nominal) | 3.937 | 0 |

## Findings and limits

- Long repeat replies improve8.33/9.04% in the clock pass and7.91/8.93% in the fault pass. Those rows pass their own drift/parity/resource gates. This corroborates the long-input use case; it does not qualify a general generation-TPS improvement or the Code Editing default.
- The clock pass has a single JSON replay at80.14TPS. That window reports GPU median1618MHz, range1579–1619, thermal category0/nominal, median GPU89.04°C and other CPU median1.7% of one core. The comparable JSON replay is89.92TPS in the other candidate launch and about89.9 in controls. No large GPU-clock reduction, swap growth or large CPU competitor explains this particular outlier; short CPU/driver pauses remain possible. Keep the outlier: aggregate JSON replay generation loses2.68% and reply takes2.52% longer, so that scope fails.
- Both clock-pass candidates and controls preserve identical ngram counts/outputs. The earlier sustained80TPS editing slowdown was not reproduced across the whole second candidate in this run. Hardware readings from this run cannot establish the cause of the earlier uninstrumented slowdown.
- The fault pass adds native-process page-fault/page-in counters and client SSE timestamps. Process page-ins rise in some1536file windows despite no swap growth; e.g. first Python increments209/132 across the two candidates, versus0 in the first control. These overlapping one-second observations can include adjacent request tails and measure counters, not SSD bytes or isolated gather wait. They cannot establish a disk bottleneck.
- The fault-pass file replies remain near86.6–90TPS; the80.14TPS JSON event does not recur. SSE often emits verified tokens in fast bursts; near-zero median inter-event gaps do not represent per-token model computation. Larger gaps include transport/client scheduling. Neither those gaps nor memory faults identify a repeatable native stall yet.
- Ordinary profiles remain unchanged. Optional Long Documents is available locally with the original strict34GiB admission,1GiB floor,normal-pressure and zero-new-swap policy. About40GiB is available again after stopping the tests.

## Fresh upstream check and next work

The parent remains at `ed4773eb7c8f`, already used in E04; no new engine change to import. The MLX fork adds a documentation-only [October13 commit](https://github.com/yibie/strata-mlx/commit/2f11ab3e752adc84525d82c75d598b5898f96060) based on [real64GB M5 Pro reports](https://github.com/yibie/strata-mlx/issues/8), including improved interrupted-conversation restore and layerwise/read-ahead prompt processing. Different model quantizations, helper formats, caches, memory budgets and numerical behavior prevent a direct speed claim here. Selective reads concern its partly resident IQ3_S path; our mainQ2 experts are already resident. No backend is switched or model downloaded.

[Five ordered next investigations](NEXT.md): actual helper QoS/scheduling, native wait envelopes, bounded Apple lookup prefetch, separate MLX qualification, and lower-priority parked-conversation caching. No ordinary setting is changed by that queue.

Both commands execute real model work; use new output directories. The benchmark requires explicit --run:

```sh
.venv/bin/python scripts/verify_runtime_profiles.py --profile long-documents --output bench/features/<new-name>
.venv/bin/python scripts/benchmark_prompt_chunks.py --candidate 1536 --draft-profile code-edit --telemetry --output bench/results/<new-name> --run
```

Raw prompts, generations, process names, identities and workstation paths remain ignored/local. This report contains synthetic task names and aggregate measurements only.
