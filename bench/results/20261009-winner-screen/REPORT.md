# Ideal helper consumer-removal screen

Unchanged `m5-copy` Q5_K packed head, K2560/M248320. Control computes head+top10+gather; the ideal floor computes the head alone. No winner selector was implemented in this screen and no model was loaded.

| Input | Control ms | Ideal head-only ms | Removed time | Control drift |
| --- | ---: | ---: | ---: | ---: |
| Mixed | 1.897290 | 1.690753 | 10.886% | 0.304% |
| Alternating | 1.900853 | 1.689099 | 11.140% | 0.173% |

Six accepted launches:16-case correctness for each scope, then fresh ABBA timing with pipeline prime,500ms warmup and seven100ms blocks per input. Complete score/input/packed-weight digests match; no new swap. This measures a component screening envelope with zero replacement cost. It is neither a deployable feature nor a model TPS upper bound.

The10% historical numeric reference was recorded after two timing launch directories existed. [The plan](screen-plan.json) explicitly preserves this fact; that reference was descriptive, not preregistered. The later actual exact-top10 experiment has a separate plan written before its GPU launches.

[Raw results](comparison.json), [actual implementation and qualification](../20261009-top10/REPORT.md).
