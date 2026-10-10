# Native monitoring baseline

Status: **passed**

No optimization or adoption. Instrumented timings measure monitoring overhead; controls establish the baseline. Small-model diagnostics cannot identify full-model helper bottlenecks.

| Workload | Control TPS | First token (s) | Reply (s) | Monitor TPS change |
| --- | ---: | ---: | ---: | ---: |
| code | 77.8864 | 0.0795 | 1.7102 | -2.3511% |
| prose | 77.8183 | 0.0802 | 1.7124 | -2.0986% |

[Frozen protocol](frozen.json), [all results](result.json). Raw per-arm logs, outputs and resource samples retained.
