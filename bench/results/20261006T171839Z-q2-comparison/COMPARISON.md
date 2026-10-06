# Q2 Metal comparison

Status: failed

Same full model, 4K context, batch/ubatch 512, F16 cache, temperature 0.6, prediction off. Order: baseline, candidate, candidate, baseline. Each prompt has one excluded warmup and 3 measured replies of 512 tokens. Fresh prompts disable prompt reuse. OS file cache is uncontrolled. Percentages compare this fresh baseline, not historical runs.

| Input tokens | Baseline output TPS | Candidate output TPS | Output change | Baseline input TPS | Candidate input TPS |
| ---: | ---: | ---: | ---: | ---: | ---: |

| Input tokens | Baseline first token (s) | Candidate first token (s) | Less waiting | Baseline reply (s) | Candidate reply (s) | Reply time reduction |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |

Raw runs contain prompt throughput, exact source/patch/binary hashes, normal-EOS answer checks, memory/swap samples and server logs.


RuntimeError: Server exited during load with code -15; see server.log
