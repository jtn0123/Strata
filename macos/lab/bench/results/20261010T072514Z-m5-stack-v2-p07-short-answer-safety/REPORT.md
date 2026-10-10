# Small-gain validation: stack-v2-p07-short-answer-safety

Fresh A/B/B/A; each task has an excluded warmup and three repetitions per launch. Each arm aggregates two launch medians. This is bracket confirmation, not a statistical-significance claim.

| Task/input | Baseline TPS | Candidate TPS | TPS change | First-token change | Reply change | Reply saved | Qualified scopes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| code/48 | 63.9946 | 64.5608 | +0.8848% | -0.4971% | +0.4366% | +3.334ms | inconclusive/negative |
| prose/53 | 52.4660 | 52.8550 | +0.7415% | +0.3330% | +0.6366% | +5.599ms | generation, reply, prompt-latency |
| cached-ledger/512 | 71.5737 | 72.5559 | +1.3723% | -0.2156% | +0.6240% | +3.804ms | separate cached diagnostic |
| cached-ledger/2048 | 66.3057 | 65.5975 | -1.0680% | -0.5160% | -0.3086% | -1.965ms | separate cached diagnostic |

Decision: {"eligible_for_confirmation": false, "common_metric_scopes": [], "workload_scopes": {"code": [], "prose": ["generation", "reply", "prompt-latency"]}, "memory_clean": true, "rule": "Positive gains above 2x own control drift; both candidate launches beat both controls; same scope on English code/prose; generation/reply regressions use original floor; Original relative regression rule. Exact-output/resource/activation gates mandatory.", "ttft_policy": "Original relative regression rule.", "safety_passed": true}

Cached follow-up: {"required": false, "flags": [], "default_promotion_blocked": false, "note": "Cached timing is a separate diagnostic. Flagged losses require independent follow-up before default promotion."}

Exact fresh/warmup/cache output parity and feature encoding receipts verified. All launches zero new swap. Native allocation logs and raw variation retained; no automatic app default change.

[Raw comparison](comparison.json).
