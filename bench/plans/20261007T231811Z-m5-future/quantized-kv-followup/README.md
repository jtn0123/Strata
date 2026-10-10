# Consider quantized cache after 8K measurements

Status: prepared; testing is on hold.

Protocol only. Upstream quantized-FA overflow fix #29340 is a prerequisite; no candidate, patch or precision change staged.

Hypothesis: Smaller KV storage may recover headroom if actual logs show meaningful savings.

Only change: A later isolated F16-versus-Q8 KV precision trial, keeping context and all other settings fixed.

## Before testing

- Explicit testing go-ahead for any --run command
- Offline validation receipt matches current sources
- Quiet host; leave unrelated VM/build work alone

## Required evidence

- Backport and GPU math validation of applicable quantized attention fix first
- Actual KV savings separated from recurrent/QSA state
- Recall/continuation/rollback parity and fresh ABBA complete-task metrics

## Stop conditions

- Invalid evidence or source drift
- Unexpected quality failure or new swap

## Record results

Use `result-template.json`; all numbers remain empty until measured.

TPS gain = 100*(candidate/control-1). Time reduction = 100*(1-candidate/control). Requires finite positive matched metrics. Do not add percentages from separate experiments.

At least 5 percent median complete-task improvement on the chosen workload, or useful capacity gain with an explicitly accepted speed tradeoff; no unexplained quality failure or new swap. Report control drift and all raw passes.

Historical results are reference only. Record a new complete matched baseline for a speed candidate.

## Limits

A KV precision change does not shrink expert weights or all recurrent state. Current F16 profile is unaffected by the quantized-FA issue.

No executable candidate/testing command exists yet. Implement and validate the stated prerequisites first.
