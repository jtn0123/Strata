# Coordinator checks on Opus A

Opus A completed successfully with substantive `claude-opus-5-5` usage; the Claude CLI also reported a Haiku auxiliary call. Raw prompt/response/model-usage receipt are saved. The reviewer had tools disabled and reasoned only from the supplied dossier; it did not browse or run tests. Its raw answer is advisory, not a benchmark or source of verified new upstream facts.

Useful conclusions retained: preserve depth/target verification, prove tie behavior before winner-only helper sampling, retain QSA indexer cache writes, require mask/dispatch equality and budget-crossing continuation, measure exposed graph overhead rather than count rebuilds, and defer helper replay batching behind stricter state proof.

Corrected assumptions:

- **Helper sampling is already backend top10.** A's CPU-only/top10/full-candidate-array description is not the current normal mechanism. Source `common/speculative.cpp:1467` installs the backend sampler; current N02 log confirms backend_sampling=1. R02 removes GPU bitonic/merge selection and unnecessary consumer work, not a presumed full CPU sort.
- **Active experts do not imply active token tiles.** A lacked the actual `kernels/mul_mm.metal` source because the first dossier used the wrong path, explicitly marked unavailable. The coordinator later located/pinned the correct path and supplied it to reviewer B. An expert with10 assigned tokens still has15 empty tiles in a16-tile T512 grid. The proven upper bound is656 useful expert/token tiles out of8192; no runtime saving has been measured.
- **Catch-up currently runs before acceptance.** `server-context.cpp:4069` precedes sampling/acceptance around4235. Host API timings do not establish all phases as serial critical-path GPU costs; work can be enqueued and its wait charged later. A's proposed overlap may already exist and is not an approved new experiment.
- **No cache-gate conflict is implied by a per-request guard.** R05 suppresses prompt-reuse saves only for cache_prompt=false, preserving cache-enabled requests and speculative rollback. The current normal logs already prove112.571MiB checkpoint saves despite RAM cache0. Cached behavior still requires qualification.
- **Matched helper IDs/row counts are necessary, not sufficient proof by construction.** Cache ownership, inputs, masks, allocation lifetime, fused dispatch and future continuation need direct exactness checks. Avoid asserting exactness solely from draft IDs.
- A's cycle estimates mix a multi-request633-token diagnostic aggregate with a workload TPS. They are illustrative only and are not used to forecast local gains.
- A's new target CPU sampler front-end idea lacks the relevant sampler source in its dossier. It is an unqualified lead for later source/cost research, not ranked above the source-backed current cards.

No code, benchmark setting or model state was changed based on this review.
