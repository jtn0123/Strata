# Small-gain validation: small-gains-w02-screen-short

Fresh A/B/B/A; each task has an excluded warmup and three repetitions per launch. Each arm aggregates two launch medians. This is bracket confirmation, not a statistical-significance claim.

| Task/input | Baseline TPS | Candidate TPS | TPS change | First-token change | Reply change | Reply saved | Qualified scopes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| code/48 | 59.6769 | 60.1036 | +0.7151% | -1.2651% | +0.5308% | +24.164ms | inconclusive/negative |
| prose/53 | 40.0954 | 40.3542 | +0.6453% | -1.3894% | +0.5189% | +34.508ms | generation, reply |
| cached-ledger/512 | 71.4969 | 72.1622 | +0.9306% | -1.3398% | -0.8827% | -5.375ms | separate cached diagnostic |
| cached-ledger/2048 | 66.8705 | 67.4224 | +0.8253% | +0.2762% | +0.5861% | +3.713ms | separate cached diagnostic |

Decision: {"eligible_for_confirmation": false, "common_metric_scopes": [], "workload_scopes": {"code": [], "prose": ["generation", "reply"]}, "memory_clean": true, "rule": "No fixed minimum gain. Positive gain above2x own control drift and both candidate launches better than both controls; no material TPS/TTFT/reply regression. Prompt latency also requires reply benefit. Two tasks for common scope; exact/resource/activation gates mandatory."}

Cached follow-up: {"required": false, "flags": [], "default_promotion_blocked": false, "note": "Cached timing is a separate diagnostic. Flagged losses require independent follow-up before default promotion."}

Exact fresh/warmup/cache output parity and feature encoding receipts verified. All launches zero new swap. Native allocation logs and raw variation retained; no automatic app default change.

[Raw comparison](comparison.json).
