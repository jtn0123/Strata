# Small-gain validation: stack-v2-p07-long-safety

Fresh A/B/B/A; each task has an excluded warmup and three repetitions per launch. Each arm aggregates two launch medians. This is bracket confirmation, not a statistical-significance claim.

| Task/input | Baseline TPS | Candidate TPS | TPS change | First-token change | Reply change | Reply saved | Qualified scopes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| code/859 | 45.8500 | 46.1872 | +0.7356% | +0.2650% | +0.4477% | +32.187ms | generation |
| prose/1004 | 46.8321 | 47.1436 | +0.6651% | +1.2956% | +0.9010% | +65.515ms | generation |
| cached-ledger/512 | 70.1092 | 70.6644 | +0.7920% | -0.0449% | +1.0703% | +6.633ms | separate cached diagnostic |
| cached-ledger/2048 | 63.4737 | 63.6955 | +0.3495% | -0.5354% | +0.6568% | +4.306ms | separate cached diagnostic |

Decision: {"eligible_for_confirmation": true, "common_metric_scopes": ["generation"], "workload_scopes": {"code": ["generation"], "prose": ["generation"]}, "memory_clean": true, "rule": "Positive gains above 2x own control drift; both candidate launches beat both controls; same scope on English code/prose; generation/reply regressions use original floor; Original relative regression rule. Exact-output/resource/activation gates mandatory.", "ttft_policy": "Original relative regression rule.", "safety_passed": true}

Cached follow-up: {"required": false, "flags": [], "default_promotion_blocked": false, "note": "Cached timing is a separate diagnostic. Flagged losses require independent follow-up before default promotion."}

Exact fresh/warmup/cache output parity and feature encoding receipts verified. All launches zero new swap. Native allocation logs and raw variation retained; no automatic app default change.

[Raw comparison](comparison.json).
