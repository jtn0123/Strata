# Maintained M5 profiles

`Start Strata.command` runs the balanced full Flash-Next Q2_0 profile. `Start Strata - Code Editing.command` enables bounded lookup plus MTP fallback for edits to supplied code. The older lookup-trial shortcut forwards to the maintained editing profile. Run one app at a time; both use localhost8095/8096, and Ctrl-C or `Stop Strata.command` stops the owned processes.

Both profiles include the previously validated GPU MMA path, packed shared Q3 helper, Tensor API and P07 reduction, with depth3, eight helper workers, confidence0, F16 cache,4K context and batch512. Conversation prefix caching uses one engine slot. Model files and native math are unchanged. Original baseline and narrow historical tuning launchers remain available; W02 and High Power are disabled.

| Measured improvement | Result and scope |
| --- | --- |
| Earlier GPU MMA | About16.8% higher generation TPS in matched depth-three code/prose comparisons. |
| Shared helper weights | Removes521MiB of duplicated helper tables; all target experts retained. |
| P07 | Independently confirmed +0.61% code/+0.79% prose generation, with reply and safety checks. |
| Editing lookup | Independent first-file confirmation71.3 to84.4TPS (+18.4%); complete replies11.2% sooner, first token61ms later. One Python-file speed fixture; broader coverage pending. |

The percentages come from separate matched experiments and are not added together. Editing is a dedicated option, not a general chat-rate claim.

## Resource policy and validation

App launches verify native/model provenance, require34GiB available before the full model (4GiB for the small model), and enforce continuous normal pressure, zero new swap and a1GiB ongoing floor. Unsupported lookup combinations are rejected before launching a native process.

Current PR-branch checks:171 load-free tests plus five existing campaign-protocol checks. Both real app profiles passed temperature0/0.6 answers, verbatim normal-EOS file editing, SSE and nine API/lifecycle groups each, including cancellation and disconnect recovery. Five reply texts matched across profiles; both monitors remained healthy at normal pressure with zero new swap, and owned processes stopped with ports closed. These are functional adoption checks; earlier lab checks had different inventories and are not this branch's total.

Raw outputs, machine/process snapshots and model files are local-only. Generate validation receipts locally with `scripts/validate_offline.py` and `scripts/verify_runtime_profiles.py --profile balanced|code-edit --output bench/results/<new-run>`. `.gitignore` excludes these generated artifacts; tests and synthetic fixtures remain tracked.

[Next research ideas](research/20261013-post-adoption-ideas/REPORT.md).
