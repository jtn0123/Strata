# Small-gain validation: small-gains-p11-screen-resource-retry1-long

Fresh A/B/B/A; each task has an excluded warmup and three repetitions per launch. Each arm aggregates two launch medians. This is bracket confirmation, not a statistical-significance claim.

| Task/input | Baseline TPS | Candidate TPS | TPS change | First-token change | Reply change | Reply saved | Qualified scopes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| code/859 | 45.8333 | 45.6918 | -0.3087% | +0.0883% | -0.2807% | -20.177ms | inconclusive/negative |
| prose/1004 | 46.8932 | 46.8197 | -0.1566% | -1.0612% | -0.2979% | -21.533ms | inconclusive/negative |
| cached-ledger/512 | 70.6388 | 70.6288 | -0.0142% | -0.8006% | -0.3841% | -2.360ms | separate cached diagnostic |
| cached-ledger/2048 | 63.4933 | 63.5000 | +0.0106% | +1.9808% | +0.6135% | +4.028ms | separate cached diagnostic |

Decision: {"eligible_for_confirmation": false, "common_metric_scopes": [], "workload_scopes": {"code": [], "prose": []}, "memory_clean": true, "rule": "No fixed minimum gain. Positive gain above2x own control drift and both candidate launches better than both controls; no material TPS/TTFT/reply regression. Prompt latency also requires reply benefit. Two tasks for common scope; exact/resource/activation gates mandatory."}

Cached follow-up: {"required": false, "flags": [], "default_promotion_blocked": false, "note": "Cached timing is a separate diagnostic. Flagged losses require independent follow-up before default promotion."}

Exact fresh/warmup/cache output parity and feature encoding receipts verified. All launches zero new swap. Native allocation logs and raw variation retained; no automatic app default change.

[Raw comparison](comparison.json).
