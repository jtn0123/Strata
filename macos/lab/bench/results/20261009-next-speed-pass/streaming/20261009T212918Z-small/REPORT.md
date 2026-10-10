# Token-piece cache: actual service response comparison

One engine, fresh cache-off native requests. Each tokenizer cache is empty per request. Independent ABBA for code/prose, excluded warmup then three repeats. Native TPS is distinct from app reply latency. No final-display latency claim.

| Task | Control reply s | Candidate reply s | Quicker | Control drift | Qualified |
| --- | ---: | ---: | ---: | ---: | --- |
| code | 3.364070 | 3.365691 | -0.048% | -0.228% | False |
| prose | 3.373194 | 3.367038 | +0.182% | +0.525% | False |

All timed token IDs/parser events match; no new swap. >=1% complete-reply improvement on both tasks above twice their own drift is required for adoption. Native TPS changes are observations, not an attributed native acceleration.

[Raw evidence](comparison.json)
