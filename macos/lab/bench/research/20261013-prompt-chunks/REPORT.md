# E05: prompt chunks on the maintained M5 Pro engine

October 13, 2026. MacBook Pro M5 Pro,48GiB,AC/Automatic. Same full Qwen3.8-Flash-Next GSQ-RCO Q2_0, all main experts resident, packed sharedQ3 helper, mixed placement/eight helper CPU workers, MTP3/confidence0, Tensor API on, P07 small-reduce,4K/F16. No model conversion, parent backend or target sampling change.

**Decision:** larger chunks are a real long-input candidate. Preserve the current512-token app defaults. The balanced1536 recipe improves repeat long replies8.53–10.03%, but editing validation has substantial timing drift and does not qualify a general speed keeper.256 is rejected for speed. No new general generation-TPS gain or summed percentage is claimed.

## Method

- Four separate A/B/B/A campaigns, two independent launches per arm. Three normal-EOS requests per task: first exposure and two replays scored separately. Balanced trials have two synthetic English documents, one complete Python edit and short prose; editing validation uses three other complete Python/JavaScript/JSON files with the kept ngram-mod16/width3+MTP policy.
- Control batch/ubatch512/512. Smaller recipe512/256; larger1024/1024 and1536/1536. Larger recipes change both logical capacity and physical chunk limit, including the helper context. This does not isolate target-only chunk size or a new matrix kernel. Native logs confirm the requested sizes in both contexts; no silent clamping.
- Greedy,seed1234,768-token safety cap, normal EOS required. All prompts fit4K; long inputs2332/2346tokens. Prompt caching is disabled and native cache_n is0. Replays still share file/kernel caches and, in editing mode, learned draft lookups. They are not cold SSD measurements or typical new-question chat rates.
- One34GiB admission/normal-pressure requirement per launch; continuous zero-new-swap/normal-pressure/1GiB floor guards and quiet CPU preflight. No purge, forced eviction or interventions inside a bracket.
- Original runner source and identities frozen for each campaign and archived before execution. After all runs, the maintained harness gained an explicit target/helper chunk-log checker; a separate postflight receipt checks every original log/source snapshot without rewriting the campaigns.
- Positive gains must exceed twice their own closing-control drift and both candidate launch medians must beat both controls. No arbitrary1%/3% minimum. First exposure and replay remain separate; isolated wins cannot qualify all workloads or add to previous percentages.

**Validation:** 216 complete answers across16launches. Complete text/output token IDs and rendered input hashes match within every comparison, all factual/verbatim-file checks pass. All guards healthy, normal pressure throughout, zero new swap, owned children stopped. Minimum available RAM2.83GiB; maximum process RSS38.78GiB. RSS is not unique total GPU memory. About0.21GiB total swap existed at entry and stayed unchanged.229 maintained load-free tests pass.

## 1024 balanced

Local raw evidence: `bench/results/20261013-prompt-chunks-1024-v1/campaign.json` and original `source/` snapshots.

| Task / phase | Control prompt tok/s | Candidate prompt tok/s | Prompt gain | Control generation TPS | Candidate generation TPS | First text: control → candidate | Whole reply: control → candidate | Reply saved | Qualified prompt scope |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| long-retrieval / first-exposure | 501.41 | 540.95 | +7.89% | 62.24 | 64.86 | 4.654s → 4.313s | 5.137s → 4.776s | +7.03% | no |
| long-retrieval / replay | 521.64 | 556.98 | +6.77% | 66.13 | 65.98 | 4.472s → 4.188s | 4.926s → 4.643s | +5.75% | yes, this task/phase only |
| long-prose / first-exposure | 517.03 | 557.31 | +7.79% | 56.57 | 57.69 | 4.538s → 4.210s | 4.715s → 4.384s | +7.03% | yes, this task/phase only |
| long-prose / replay | 522.20 | 557.30 | +6.72% | 57.97 | 57.60 | 4.494s → 4.211s | 4.667s → 4.384s | +6.05% | yes, this task/phase only |
| python-client / first-exposure | 449.97 | 464.35 | +3.20% | 73.64 | 73.62 | 0.684s → 0.662s | 3.875s → 3.854s | +0.55% | no |
| python-client / replay | 472.91 | 467.97 | -1.05% | 73.71 | 73.73 | 0.650s → 0.657s | 3.838s → 3.844s | -0.16% | no |
| short-prose / first-exposure | 164.44 | 168.88 | +2.70% | 38.28 | 39.55 | 0.292s → 0.285s | 5.601s → 5.418s | +3.27% | no |
| short-prose / replay | 168.49 | 169.36 | +0.51% | 39.51 | 39.59 | 0.285s → 0.284s | 5.424s → 5.412s | +0.22% | no |

Peak process RSS by launch: 37.431GiB, 38.158GiB, 38.267GiB, 37.902GiB. Candidate average difference+0.546GiB. Available-RAM floors are preserved in each memory receipt.

## 256 balanced

Local raw evidence: `bench/results/20261013-prompt-chunks-256-v1/campaign.json` and original `source/` snapshots.

| Task / phase | Control prompt tok/s | Candidate prompt tok/s | Prompt gain | Control generation TPS | Candidate generation TPS | First text: control → candidate | Whole reply: control → candidate | Reply saved | Qualified prompt scope |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| long-retrieval / first-exposure | 512.23 | 429.24 | -16.20% | 65.56 | 65.68 | 4.554s → 5.434s | 5.013s → 5.891s | -17.51% | no |
| long-retrieval / replay | 517.94 | 435.24 | -15.97% | 65.93 | 66.01 | 4.503s → 5.359s | 4.959s → 5.814s | -17.23% | no |
| long-prose / first-exposure | 518.08 | 435.18 | -16.00% | 57.55 | 57.67 | 4.529s → 5.392s | 4.703s → 5.565s | -18.33% | no |
| long-prose / replay | 517.68 | 435.06 | -15.96% | 57.61 | 57.68 | 4.533s → 5.393s | 4.706s → 5.567s | -18.28% | no |
| python-client / first-exposure | 467.75 | 371.36 | -20.61% | 73.65 | 73.61 | 0.657s → 0.828s | 3.848s → 4.020s | -4.48% | no |
| python-client / replay | 468.87 | 379.21 | -19.12% | 73.70 | 73.60 | 0.655s → 0.810s | 3.844s → 4.004s | -4.14% | no |
| short-prose / first-exposure | 165.80 | 168.51 | +1.63% | 39.39 | 39.52 | 0.290s → 0.285s | 5.444s → 5.421s | +0.41% | no |
| short-prose / replay | 168.61 | 168.33 | -0.17% | 39.55 | 39.58 | 0.285s → 0.286s | 5.417s → 5.414s | +0.06% | no |

Peak process RSS by launch: 37.901GiB, 37.765GiB, 37.765GiB, 37.902GiB. Candidate average difference-0.136GiB. Available-RAM floors are preserved in each memory receipt.

## 1536 balanced

Local raw evidence: `bench/results/20261013-prompt-chunks-1536-v1/campaign.json` and original `source/` snapshots.

| Task / phase | Control prompt tok/s | Candidate prompt tok/s | Prompt gain | Control generation TPS | Candidate generation TPS | First text: control → candidate | Whole reply: control → candidate | Reply saved | Qualified prompt scope |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| long-retrieval / first-exposure | 514.83 | 551.98 | +7.22% | 64.91 | 64.78 | 4.531s → 4.227s | 4.993s → 4.690s | +6.07% | yes, this task/phase only |
| long-retrieval / replay | 520.55 | 574.80 | +10.42% | 66.02 | 65.78 | 4.481s → 4.058s | 4.935s → 4.514s | +8.53% | yes, this task/phase only |
| long-prose / first-exposure | 520.36 | 577.01 | +10.89% | 57.58 | 56.91 | 4.509s → 4.067s | 4.683s → 4.242s | +9.41% | no |
| long-prose / replay | 519.69 | 580.12 | +11.63% | 57.72 | 57.75 | 4.515s → 4.045s | 4.689s → 4.218s | +10.03% | yes, this task/phase only |
| python-client / first-exposure | 470.92 | 460.41 | -2.23% | 73.74 | 73.59 | 0.652s → 0.667s | 3.839s → 3.861s | -0.56% | no |
| python-client / replay | 471.27 | 464.33 | -1.47% | 73.61 | 73.61 | 0.652s → 0.662s | 3.845s → 3.855s | -0.26% | no |
| short-prose / first-exposure | 168.36 | 166.83 | -0.91% | 39.55 | 39.34 | 0.286s → 0.288s | 5.419s → 5.449s | -0.56% | no |
| short-prose / replay | 168.85 | 168.51 | -0.20% | 39.57 | 39.53 | 0.285s → 0.285s | 5.416s → 5.421s | -0.10% | no |

Peak process RSS by launch: 37.902GiB, 38.277GiB, 38.784GiB, 37.921GiB. Candidate average difference+0.619GiB. Available-RAM floors are preserved in each memory receipt.

## 1536 editing validation

Local raw evidence: `bench/results/20261013-prompt-chunks-1536-edit-confirm-v1/campaign.json` and original `source/` snapshots.

| Task / phase | Control prompt tok/s | Candidate prompt tok/s | Prompt gain | Control generation TPS | Candidate generation TPS | First text: control → candidate | Whole reply: control → candidate | Reply saved | Qualified prompt scope |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| long-retrieval / first-exposure | 516.80 | 545.54 | +5.56% | 65.80 | 62.82 | 4.514s → 4.277s | 4.970s → 4.755s | +4.32% | no |
| long-retrieval / replay | 522.12 | 550.52 | +5.44% | 72.08 | 72.16 | 4.467s → 4.240s | 4.884s → 4.656s | +4.67% | yes, this task/phase only |
| long-prose / first-exposure | 521.63 | 554.98 | +6.39% | 57.78 | 54.85 | 4.498s → 4.231s | 4.671s → 4.414s | +5.51% | no |
| long-prose / replay | 517.97 | 554.39 | +7.03% | 57.06 | 54.54 | 4.530s → 4.236s | 4.706s → 4.420s | +6.07% | yes, this task/phase only |
| python-ledger / first-exposure | 450.87 | 454.68 | +0.85% | 85.47 | 83.35 | 0.702s → 0.696s | 3.535s → 3.607s | -2.05% | no |
| python-ledger / replay | 464.27 | 455.77 | -1.83% | 85.76 | 83.11 | 0.682s → 0.695s | 3.511s → 3.629s | -3.35% | no |
| javascript-catalog / first-exposure | 456.67 | 465.58 | +1.95% | 84.02 | 82.64 | 0.750s → 0.736s | 3.957s → 4.005s | -1.20% | no |
| javascript-catalog / replay | 478.26 | 471.91 | -1.33% | 85.26 | 84.30 | 0.716s → 0.726s | 3.880s → 3.930s | -1.29% | no |
| json-client / first-exposure | 446.08 | 451.02 | +1.11% | 82.57 | 81.89 | 0.682s → 0.676s | 3.522s → 3.544s | -0.62% | no |
| json-client / replay | 458.35 | 452.85 | -1.20% | 85.37 | 84.81 | 0.664s → 0.673s | 3.413s → 3.442s | -0.86% | no |
| short-prose / first-exposure | 161.99 | 160.48 | -0.93% | 37.68 | 37.38 | 0.297s → 0.300s | 5.698s → 5.748s | -0.87% | no |
| short-prose / replay | 162.31 | 160.76 | -0.95% | 82.34 | 78.93 | 0.297s → 0.300s | 2.769s → 2.880s | -4.01% | no |

Peak process RSS by launch: 38.000GiB, 38.394GiB, 38.601GiB, 37.999GiB. Candidate average difference+0.498GiB. Available-RAM floors are preserved in each memory receipt.

## Decisions, failed qualification and next evidence

- **256:** correct output and safe resources, but repeat long replies17.23–18.28% slower, first text about19% later and file-edit reply4.14% slower. Saves only about0.14GiB process RSS in its bracket. Do not retry unchanged for speed; revisit only for a materially different memory-constrained use case.
- **1024:** balanced repeat long prompt throughput+6.72–6.77%, first text6.31–6.35% sooner, full replies5.75–6.05% sooner. Exact outputs; no qualified generation gain. One first-exposure retrieval result does not exceed its drift gate. Candidate for long inputs, not an independently confirmed editing/default profile.
- **1536 balanced:** repeat long prompt throughput+10.42–11.63%, first text9.44–10.42% sooner, full replies8.53–10.03% sooner. Saves about0.42–0.47seconds per long reply. First-exposure prose generation loses1.16% and short-edit first-text timing loses about1.5–2.3%, so these rows do not pass the declared gate. Average process RSS increases about0.62GiB; memory remained safe.
- **1536 editing validation:** all72responses and all36complete files match exactly; long repeat replies remain4.67–6.07% faster. Performance confirmation is mixed, not a global promotion. The second candidate slows and the closing control also slows on edits/prose. Python replay controls fall89.98→81.54TPS; JavaScript89.73→80.79; JSON89.79→80.93. Candidate launch variation and own-control drift must remain visible.
- Draft work is identical across the four editing launches: ngram-mod652generated/649accepted drafts,1950proposed/1929accepted tokens each. Per-request Python and prose draft counts also match despite timing changes. This establishes that the observed slowdown does not come from missing lookup activation or fewer accepted lookup tokens. It does not prove a hardware/power cause.
- During the slowdown: normal pressure,new swap0,AC attached, no large background CPU consumer in the captured snapshot; pmset reports no recorded thermal/performance warning. No GPU clock or temperature trace was captured. Thermal/power/scheduling causes remain unproven. Preserve this mixed confirmation; collect clock/thermal and continuous contention evidence before repeating it, rather than selecting favorable arms.
- Ordinary balanced/code-edit app launchers and their512-token qualification guards remain unchanged. The app currently passes the default logical batch through `run.py`; a future larger-chunk app profile must set both batch and ubatch and validate the maintained API/UI path. Merely changing --ubatch would not reproduce these recipes.
- Next: instrument sustained clock/thermal/contention behavior and qualify an optional long-document profile with a new whole bracket. Separately inspect the parent prompt matrix path; this sweep does not explain or port its entire57% prompt-throughput lead.

## Reproduce

Use a new output directory for every run. Each invocation is preparation-only until --run is supplied.

```sh
.venv/bin/python scripts/benchmark_prompt_chunks.py --candidate 1024 --output bench/results/<new-name> --run
.venv/bin/python scripts/benchmark_prompt_chunks.py --candidate 256 --output bench/results/<new-name> --run
.venv/bin/python scripts/benchmark_prompt_chunks.py --candidate 1536 --output bench/results/<new-name> --run
.venv/bin/python scripts/benchmark_prompt_chunks.py --candidate 1536 --draft-profile code-edit --output bench/results/<new-name> --run
```

Raw generations, source snapshots, model identities, native logs and postflight checks remain local/ignored. This report contains aggregate measurements and synthetic workload names only. No weights, personal prompts or absolute workstation paths are included.
