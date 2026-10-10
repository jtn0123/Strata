# Small-gain validation: small-gains-p07-confirmation-short

Fresh A/B/B/A; each task has an excluded warmup and three repetitions per launch. Each arm aggregates two launch medians. This is bracket confirmation, not a statistical-significance claim.

| Task/input | Baseline TPS | Candidate TPS | TPS change | First-token change | Reply change | Reply saved | Qualified scopes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| code/48 | 59.7194 | 60.0842 | +0.6107% | +0.2625% | +0.5953% | +27.085ms | generation, reply |
| prose/53 | 40.0582 | 40.3755 | +0.7921% | -0.4521% | +0.7631% | +50.791ms | generation, reply |
| cached-ledger/512 | 71.3150 | 71.7864 | +0.6610% | -0.9613% | +0.1700% | +1.037ms | separate cached diagnostic |
| cached-ledger/2048 | 66.7478 | 67.0017 | +0.3804% | +1.8573% | +0.9138% | +5.821ms | separate cached diagnostic |

Decision: {"eligible_for_confirmation": true, "common_metric_scopes": ["generation", "reply"], "workload_scopes": {"code": ["generation", "reply"], "prose": ["generation", "reply"]}, "memory_clean": true, "rule": "No fixed minimum gain. Positive gain above2x own control drift and both candidate launches better than both controls; no material TPS/TTFT/reply regression. Prompt latency also requires reply benefit. Two tasks for common scope; exact/resource/activation gates mandatory."}

Cached follow-up: {"required": false, "flags": [], "default_promotion_blocked": false, "note": "Cached timing is a separate diagnostic. Flagged losses require independent follow-up before default promotion."}

Exact fresh/warmup/cache output parity and feature encoding receipts verified. All launches zero new swap. Native allocation logs and raw variation retained; no automatic app default change.

[Raw comparison](comparison.json).
