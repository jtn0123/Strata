# Full Flash-Next benchmark — October 8 local / October 9 UTC

Outcome: two complete matched launches of the unchanged optimized writing preset passed. This completes a repeatable full-model baseline; no new shader, model quantization, or native runtime change was introduced by this batch.

Qwen3.8-Flash-Next GSQ-RCO Q2_0 uses the 37.62 GB main GGUF and 28.80 GB SSD lookup shard, plus the 1.25 GB shared packed Q3 helper. It ran on the 48 GiB M5 Pro with the verified mtp-mma engine, full target Metal offload, Tensor API on, 4K context, F16 cache, batch/ubatch 512, depth-three MTP, eight helper workers, confidence zero and mixed helper placement. Both native logs confirm borrowed target embeddings/output and separate helper KV.

Each launch excludes one warmup per workload and measures three repeats. Fresh timings request exactly 128 tokens with EOS ignored only for timing, seed 1234 and temperature 0.6. Every workload has six measured samples across the two launches; input token hashes match. Answer checks retain normal EOS, including greedy and sampled multilingual/code/JSON checks. Cached ledger answers are short replies following an immediately primed history, with no cross-session cache.

| Workload | Generation tokens/s | Input tokens/s | First token | Complete reply |
|---|---:|---:|---:|---:|
| chinese | 39.99 | 188.03 | 0.298 s | 3.474 s |
| code | 56.14 | 168.68 | 0.285 s | 2.553 s |
| prose | 42.60 | 180.54 | 0.294 s | 3.277 s |
| synthetic / 512 tokens | 48.48 | 547.60 | 0.936 s | 3.553 s |
| synthetic / 2048 tokens | 49.87 | 535.97 | 3.822 s | 6.372 s |
| cached-ledger / 512 tokens | 68.71 | 151.79 | 0.277 s | 0.627 s |
| cached-ledger / 2048 tokens | 62.31 | 144.67 | 0.291 s | 0.662 s |

Cached TPS describes those short structured replies and should not be advertised as the general writing rate.

| Launch | Ready | Whole run | Peak process RSS | Minimum available RAM | Answer/cache checks | New swap |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 15.49 s | 131.69 s | 32.68 GiB | 2.15 GiB | 32/32 | 0 bytes |
| 2 | 2.32 s | 118.75 s | 37.94 GiB | 2.24 GiB | 32/32 | 0 bytes |

Process RSS can include shared or overlapping mapped pages and is not total unique Metal memory. Load times have different cache states: the first launch followed cache invalidation, while the second reused warmed files. Both passed the ordinary 34 GiB admission check immediately before launch (36.15 and 38.24 GiB available). Every recorded memory-pressure level remained normal. The owned-child memory monitor sampled every 250 ms, stopped on any new swap or increased pressure, and retained the 1 GiB minimum-available guard for four seconds.

All 64 checks passed; all 42 measured fresh/cached timing samples were validated against native counters. Fresh generation drift between launches was at most 0.95%. Model identities, verified artifact receipts and harness hashes matched before and after. The maintained 90-test offline receipt was current throughout.

The initial exploratory attempt started with 31.85 GiB, below the usual 34 GiB target, and stopped during loading. It generated no benchmark samples and is excluded. The zero-new-swap guard observed 2.625 MiB of new system swap; pressure remained normal. No specific process was proven responsible for those swapped pages. A target-only fallback was deferred before launch because headroom had not recovered.

After the stopped attempt, read-only model mappings with documented MS_INVALIDATE released cached pages belonging to our unused GGUF files. Available RAM increased from 27.74 to 36.28 GiB, enabling the successful retries with the normal admission requirement and the same zero-swap guard. The file sizes, inodes, modification times and change times remained unchanged. No administrator cache purge was performed and no files were deleted.

## Historical reference only

The October 7 single clean launch used the same native writing preset. This table is a temporal reference, not a bracketed optimization comparison; differences cannot be attributed to a new code change or cache cleanup. The old second launch with new swap remains excluded.

| Workload | October 7 single-launch TPS | Current two-launch TPS | Observed difference |
|---|---:|---:|---:|
| chinese / 56 | 38.99 | 39.99 | +2.56% |
| code / 48 | 54.19 | 56.14 | +3.61% |
| prose / 53 | 41.68 | 42.60 | +2.22% |
| synthetic / 512 | 47.61 | 48.48 | +1.83% |
| synthetic / 2048 | 48.91 | 49.87 | +1.96% |

At final verification, the model server was stopped and 37.83 GiB was available. T3 Code, its active Codex process and WiFiman remained running. Chrome, the separate ChatGPT/Codex desktop app, Docker Desktop and otm-vm stayed stopped.

Raw evidence: [trial, provenance and summaries](trial.json), [resource samples](resources.jsonl), [runner](runner.py).

- [First successful launch](../20261009T042336Z-heavy-trial-optimized-mtp-1/result.json)
- [Second successful launch](../20261009T042548Z-heavy-trial-optimized-mtp-2/result.json)
- [Initial stopped capacity attempt](../20261009T041819Z-heavy-guarded-trial/trial.json)
- [Read-only cache reset](../../features/20261009T042221Z-heavy-cache-reset.json)

The full-model residual-correctness candidate, expert-routing/split captures and full-model 8K trial remain separate work. This batch does not establish a speed gain for those pending ideas.
