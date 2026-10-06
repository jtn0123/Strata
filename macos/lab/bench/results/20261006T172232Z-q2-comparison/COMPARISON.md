# Q2 Metal comparison

Status: passed

Same full model, 4K context, batch/ubatch 512, F16 cache, temperature 0.6, prediction off. Order: baseline, candidate, candidate, baseline. Each prompt has one excluded warmup and 3 measured replies of 512 tokens. Fresh prompts disable prompt reuse. OS file cache is uncontrolled. Percentages compare this fresh baseline, not historical runs.

| Input tokens | Baseline output TPS | Candidate output TPS | Output change | Baseline input TPS | Candidate input TPS |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 512 | 35.03 | 31.94 | -8.83% | 629.39 | 571.01 |
| 2048 | 35.31 | 32.74 | -7.30% | 580.50 | 555.37 |

| Input tokens | Baseline first token (s) | Candidate first token (s) | Less waiting | Baseline reply (s) | Candidate reply (s) | Reply time reduction |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 512 | 0.815 | 0.900 | -10.42% | 15.399 | 16.971 | -10.21% |
| 2048 | 3.529 | 3.695 | -4.69% | 18.017 | 19.334 | -7.31% |

Raw runs contain prompt throughput, exact source/patch/binary hashes, normal-EOS answer checks, memory/swap samples and server logs.

- [baseline / 20261006T172232Z-q2-1-baseline](../20261006T172232Z-q2-1-baseline/result.json): passed; swap growth 0.002 GiB
- [q2-masked / 20261006T172507Z-q2-2-q2-masked](../20261006T172507Z-q2-2-q2-masked/result.json): passed; swap growth 0.247 GiB
- [q2-masked / 20261006T172754Z-q2-3-q2-masked](../20261006T172754Z-q2-3-q2-masked/result.json): passed; swap growth 0.142 GiB
- [baseline / 20261006T173022Z-q2-4-baseline](../20261006T173022Z-q2-4-baseline/result.json): passed; swap growth 0.000 GiB
