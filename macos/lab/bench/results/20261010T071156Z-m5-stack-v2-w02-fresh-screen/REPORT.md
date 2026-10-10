# Small-gain validation: stack-v2-w02-fresh-screen

Fresh A/B/B/A; each task has an excluded warmup and three repetitions per launch. Each arm aggregates two launch medians. This is bracket confirmation, not a statistical-significance claim.

| Task/input | Baseline TPS | Candidate TPS | TPS change | First-token change | Reply change | Reply saved | Qualified scopes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| code/48 | 59.7203 | 60.0688 | +0.5835% | -1.5185% | +0.5245% | +23.866ms | generation, reply |
| prose/53 | 40.0623 | 40.3473 | +0.7114% | -2.1295% | +0.6680% | +44.523ms | inconclusive/negative |
| cached-ledger/512 | 70.4020 | 70.9704 | +0.8073% | -0.4790% | +0.2492% | +1.530ms | separate cached diagnostic |
| cached-ledger/2048 | 64.2911 | 64.3577 | +0.1036% | +2.3429% | +0.8510% | +5.575ms | separate cached diagnostic |

Decision: {"eligible_for_confirmation": false, "common_metric_scopes": [], "workload_scopes": {"code": ["generation", "reply"], "prose": []}, "memory_clean": true, "rule": "Positive gains above 2x own control drift; both candidate launches beat both controls; same scope on English code/prose; generation/reply regressions use original floor; Fixed 10 ms ceiling on every candidate/control launch pair; remaining criteria unchanged. Exact-output/resource/activation gates mandatory.", "ttft_policy": "Fixed 10 ms ceiling on every candidate/control launch pair; remaining criteria unchanged.", "safety_passed": false}

Cached follow-up: {"required": false, "flags": [], "default_promotion_blocked": false, "note": "Cached timing is a separate diagnostic. Flagged losses require independent follow-up before default promotion."}

Exact fresh/warmup/cache output parity and feature encoding receipts verified. All launches zero new swap. Native allocation logs and raw variation retained; no automatic app default change.

[Raw comparison](comparison.json).
