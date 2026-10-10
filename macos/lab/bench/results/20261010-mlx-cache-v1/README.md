# Warmed full-model MLX cache comparison

This campaign compares **6 GB versus 12 GB decimal expert-cache budgets** on the same full Qwen3.8-Flash-Next GSQ-RCO Q2_0 model, using F32 activations. It has four fresh processes in 6/12/12/6 order. Each gets identical English code/prose prompts (44/53 input tokens), two excluded warmup answers, then three measured answers per workload, capped at 128 output tokens. Conversation state resets before every answer; the expert cache stays warm within each process.

The runner passed the **184-test offline gate** before freezing. [Frozen inputs](frozen.json) record exact prompts/IDs, models, source revision, installed dependency versions and artifact hashes, native vocabulary helper and 165 archived validation/source inputs. Frozen inputs and archived sources are immutable. Real run status is in `comparison.json`; each attempted launch retains its log, pressure samples, memory samples and result even if it fails. No automatic retry or partial resume is supported.

The primary metric is decode TPS. Both candidate launch medians must beat both controls for both workloads, with improvement greater than twice the controls' drift. There is no fixed minimum percentage. First-token and complete-reply time must also avoid material regression. Exact input/output token sequences, finish reason, decoded token position and pending token must match, including warmups. These position checks do not establish equality of all internal state tensors or parity with the native engine.

Resource guards require 28 GiB available before each launch, normal pressure throughout, zero new swap and an 8 GiB sustained availability floor. Only the owned child is stopped on failure. No other jobs, services or caches are altered mid-bracket. Each child has a 900-second timeout.

Times cover engine prompt evaluation and synchronized generation. Rendering/tokenization, conversation reset, detokenization, HTTP and browser overhead are excluded. Cold warmup replies and loading are reported separately. OS file cache is uncontrolled. Expert read counters count logical pager requests, not independent SSD bandwidth.

This is a separate paged-MLX study. It does not add TPS or percentages to P07's native 60.084/40.375 TPS cohort. Native output/state compatibility and API/quality/context checks remain separate requirements; no default is promoted by this comparison.
