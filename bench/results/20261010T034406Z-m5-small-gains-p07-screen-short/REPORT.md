# Small-gain validation: small-gains-p07-screen-short

Fresh A/B/B/A; each task has an excluded warmup and three repetitions per launch. Each arm aggregates two launch medians. This is bracket confirmation, not a statistical-significance claim.

| Task/input | Baseline TPS | Candidate TPS | TPS change | First-token change | Reply change | Reply saved | Qualified scopes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| code/48 | 59.6869 | 60.0008 | +0.5259% | +0.2404% | +0.5198% | +23.667ms | generation, reply |
| prose/53 | 40.0938 | 40.3294 | +0.5878% | +0.1893% | +0.5968% | +39.705ms | generation, reply |
| cached-ledger/512 | 72.0152 | 71.6450 | -0.5141% | +0.7517% | +0.1163% | +0.708ms | separate cached diagnostic |
| cached-ledger/2048 | 65.0287 | 65.4071 | +0.5819% | -0.2242% | +0.4757% | +3.058ms | separate cached diagnostic |

Decision: {"eligible_for_confirmation": true, "common_metric_scopes": ["generation", "reply"], "workload_scopes": {"code": ["generation", "reply"], "prose": ["generation", "reply"]}, "memory_clean": true, "rule": "No fixed minimum gain. Positive gain above2x own control drift and both candidate launches better than both controls; no material TPS/TTFT/reply regression. Prompt latency also requires reply benefit. Two tasks for common scope; exact/resource/activation gates mandatory."}

Cached follow-up: {"required": false, "flags": [], "default_promotion_blocked": false, "note": "Cached timing is a separate diagnostic. Flagged losses require independent follow-up before default promotion."}

Exact fresh/warmup/cache output parity and feature encoding receipts verified. All launches zero new swap. Native allocation logs and raw variation retained; no automatic app default change.

[Raw comparison](comparison.json).
