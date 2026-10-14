# N15 qualification: the helper overlap as an app setting

October 14, 2026. MacBook Pro M5 Pro (20 GPU cores), 48 GiB, AC power, Automatic power mode. Same model, helper and settings as [N15](../20261014-n15-helper-overlap/REPORT.md): the full Qwen3.8-Flash-Next GSQ-RCO Q2_0 model, packed shared Q3 MTP helper in mixed placement, depth 3, 4K context, F16 KV cache.

**The question.** [N15](../20261014-n15-helper-overlap/REPORT.md) found that running the MTP helper's prompt work while the target reads the next chunk reads long prompts 10.6–10.8% faster at the default 512-token chunks. Could it become the app's default? This run tests that in the three app settings that use 512 or 1,536-token chunks, with the switches set as a real app setting. Every launch also cancels a request, resumes it, and holds conversations with regenerated and edited replies.

**Result: not qualified.** The app is unchanged. The overlap passed every output, lifecycle and memory check. It failed the fixed rule on reply speed in two rows, each decided by one slow reply.

- **Prompts were read sooner in all three apps**, with the same outputs:
  - at 512 (default and Code Editing apps), long prompts showed first text 9.5–12.6% sooner and finished the whole reply 8.6–11.5% sooner;
  - at 1,536 (Long Documents app), 4.6–7.1% and 4.4–6.6% sooner;
  - short prompts showed first text 3.4–12.2% sooner. Their whole replies, mostly answer time, finished between 0.05% later and 4.1% sooner.
- **Same outputs:** in each app, every timed and chat reply, and its draft counts, were identical in all four launches. Every quality check passed.
- **Lifecycle checks passed in all 12 launches:**
  - a request cancelled 0.5 s after sending stopped mid-prompt, at 1,024 of 2,332 tokens (512) or 796 (1,536);
  - its resume reused those tokens and wrote the same answer as a fresh read;
  - the server restored context checkpoints 8 or 12 times per launch; every regenerated reply drafted and wrote exactly what its first reply did;
  - a fresh repeat at the end matched the launch's earlier replies token for token.
- **Memory:** peak process RSS 37.86–38.72 GiB, at least 2.46 GiB available, and swap grew by 0 in every launch.
- **Why it failed:** two rows lost more reply speed than the rule allows.
  - Default app, long-prose replay: −4.95% tok/s, where up to −2.06% was allowed. One 11-token reply took 197.6 ms; the other five overlap replies took 173.8–178.4 ms.
  - Long Documents app, python-client first exposure: −2.58% tok/s, where up to −1% was allowed. The overlap launch's one first-exposure reply took 3,380 ms; the other three launches took 3,194–3,201 ms.
- **Those slow replies were not specific to the overlap.** Counting every timed reply more than 4% slower than the kept engine's median for its prompt, 8 of 84 kept-engine replies and 7 of 84 overlap replies were that slow. What the overlap does change is the first draft after a long prompt: at 512, replies after long prompts took a median 2.3–3.3 ms longer, as N15 found. On an 11-token reply that is 1.5–1.9%, more than the rule's 1% by itself.

## Settings compared

Each app ran as one A/B/B/A bracket: the kept engine, the overlap, the overlap, the kept engine.

| App | Chunks | Drafting | Kept arm | Overlap arm |
| --- | ---: | --- | --- | --- |
| Default | 512 | balanced | `m5-small-stack`, `small-reduce` | `m5-overlap`, `overlap-reduce` |
| Code Editing | 512 | code-edit | same | same |
| Long Documents | 1,536 | balanced | same | same |

`overlap-reduce` is the kept `small-reduce` switches plus `GGML_M5_LAB_CONTEXT_QUEUE=1` and `GGML_M5_LAB_HELPER_OVERLAP=1`. It is defined as an app setting that only the `m5-overlap` engine accepts. Every launch's log was checked for both overlap markers in overlap launches and for neither in kept launches.

## Method

- **Timed requests:** the prompt-chunk protocol from [E05](../20261013-prompt-chunks/REPORT.md), with the prompt cache off. Each prompt was sent three times, with up to 768 tokens and a normal end:
  - default and Long Documents: the two long prompts (2,332 and 2,346 tokens), one 307-token edit and a 48-token prose prompt;
  - Code Editing: the two long prompts, three code edits (304–342 tokens) and the prose prompt.

  The first request is first exposure; the second and third are replays.
- **Lifecycle checks** after the timed requests in every launch:
  1. **Conversations:** for each prompt, through the chat endpoint with the prompt cache on and up to 256 tokens: a first reply, a regenerate, a follow-up and an edited follow-up, as in [N06](../20261014-n06-mtpstate/REPORT.md);
  2. **Cancel:** the long retrieval prompt, streamed with the prompt cache on; the client closed the connection 0.5 s after sending. The server checks for a closed connection once a second;
  3. **Resume:** the same prompt again, to completion;
  4. **Repeat:** a fresh copy of the 48-token prompt, with the prompt cache off.
- **Rule, fixed in `qualify_ops.py` before the run.** Each bracket needs exact output parity, passing quality checks, passing lifecycle checks, clean memory and no regressed row. A row regresses if first text, whole reply or reply tok/s is worse than max(1%, twice the drift between the two kept launches). In the default app, both long prompts must also show first text and the whole reply sooner, in first exposure and replay. That gain must exceed twice the kept launches' drift, with both overlap launches better than both kept launches. Memory is clean if the overlap launches' average peak RSS is at most max(128 MiB, twice the kept launches' spread) above the kept launches'.
- **Guards:** 34 GiB available before loading, a 1 GiB running floor, normal memory pressure, zero new swap, a quiet CPU and AC power. The owned server was stopped before the next launch.
- **Run:** 12 launches in 23 minutes. The server was ready 2.1–7.2 s after each start. The first launch read 9.0 GiB from disk; the other 11 read 48–934 MiB.

## Prompt reading and whole replies: long prompts

First text and whole reply in ms: the mean of each arm's two launch medians. Changes are overlap against the kept engine.

| App | Prompt | Phase | First text | Change | Whole reply | Change |
| --- | --- | --- | --- | ---: | --- | ---: |
| Default (512) | long-retrieval | first exposure | 4,682 → 4,103 | −12.4% | 5,157 → 4,566 | −11.5% |
| | | replay | 4,485 → 4,057 | −9.5% | 4,940 → 4,515 | −8.6% |
| | long-prose | first exposure | 4,545 → 4,067 | −10.5% | 4,725 → 4,243 | −10.2% |
| | | replay | 4,505 → 4,071 | −9.6% | 4,679 → 4,254 | −9.1% |
| Code Editing (512) | long-retrieval | first exposure | 4,682 → 4,090 | −12.6% | 5,155 → 4,571 | −11.3% |
| | | replay | 4,517 → 4,049 | −10.4% | 4,928 → 4,463 | −9.4% |
| | long-prose | first exposure | 4,545 → 4,061 | −10.6% | 4,722 → 4,243 | −10.1% |
| | | replay | 4,534 → 4,062 | −10.4% | 4,708 → 4,237 | −10.0% |
| Long Documents (1,536) | long-retrieval | first exposure | 4,216 → 3,917 | −7.1% | 4,694 → 4,384 | −6.6% |
| | | replay | 4,079 → 3,832 | −6.1% | 4,535 → 4,288 | −5.4% |
| | long-prose | first exposure | 4,045 → 3,816 | −5.7% | 4,228 → 3,991 | −5.6% |
| | | replay | 4,011 → 3,826 | −4.6% | 4,184 → 4,000 | −4.4% |

- **At 512 the repeats are tight.** In server timings, every long-prompt replay was read in 4,043–4,077 ms with the overlap and 4,423–4,561 ms without.
- **At 1,536 the gain is larger than in N15** (0.0–4.6% there). Kept replays varied more (3,998–4,175 ms in server timings), so the long-retrieval replay gain (6.1%) was not more than twice the drift of the kept launches (3.6%). That row would not count as a gain, but the rule needs gains only in the default app.
- **Long Documents with the overlap** read long prompts fastest of all six arms: 3,813–3,850 ms per replay in server timings.

## Reply speed

Median reply time in ms over all six timed replies per arm (three per launch). The reply time excludes prompt reading.

| App | Prompt | Reply tokens | Kept | Overlap | Change |
| --- | --- | ---: | ---: | ---: | ---: |
| Default (512) | long-retrieval | 31 | 456.9 | 459.3 | +2.3 ms |
| | long-prose | 11 | 174.0 | 177.3 | +3.3 ms |
| | python-client | 236 | 3,190.8 | 3,189.1 | −1.7 ms |
| | short-prose | 204 | 5,142.4 | 5,119.4 | −23.1 ms |
| Code Editing (512) | long-retrieval | 31 | 413.1 | 416.2 | +3.1 ms |
| | long-prose | 11 | 173.7 | 176.3 | +2.6 ms |
| | three code edits | 235–270 | 2,603.7–3,003.4 | 2,594.9–2,994.9 | −8.9 to +4.5 ms |
| | short-prose | 204 | 2,343.0 | 2,339.4 | −3.7 ms |
| Long Documents (1,536) | long-retrieval | 31 | 458.8 | 457.7 | −1.1 ms |
| | long-prose | 11 | 173.0 | 174.1 | +1.1 ms |
| | python-client | 236 | 3,189.1 | 3,187.9 | −1.2 ms |
| | short-prose | 204 | 5,138.0 | 5,135.5 | −2.6 ms |

- **After long prompts at 512,** replies took 2.3–3.3 ms longer: the first-draft cost N15 measured (2.5–3.5 ms). Its cause is still not established. At 1,536 the median change was −1.1 to +1.1 ms.
- **After short prompts** there was no consistent change (−23.1 to +4.5 ms on replies of 2.3–5.1 s).
- **The two failed rows** each rest on one slow reply in an overlap launch, listed above. With one request per launch in first exposure and two in replay, a single slow reply moves a row by several percent.
- **Slow replies by arm:** 15 of 168 timed replies were more than 4% slower than the kept engine's median for their prompt: 8 in kept launches and 7 in overlap launches. Four of them are the Code Editing app's first short-prose reply, which took 5.1–5.2 s, against 2.3 s for its replays, in all four launches.

## Lifecycle checks

Per launch. All four launches of each app gave the same values.

| App | Cancel stopped at | Resume reused | Resume drafts accepted | Restores | Chat requests | Drafts accepted |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Default (512) | 1,024 of 2,332 | 1,024 | 23 of 24 | 8 | 16 | 780 of 1,236 |
| Code Editing (512) | 1,024 of 2,332 | 1,024 | 22 of 24 | 12 | 24 | 1,726 of 1,915 |
| Long Documents (1,536) | 796 of 2,332 | 796 | 23 of 24 | 8 | 16 | 780 of 1,236 |

- **Cancel.** In every launch the server stopped after its first chunk or two, well before the end of the prompt. It samples the first reply token only after the whole prompt, so no reply existed yet. Under the overlap a helper chunk can be waiting at that point; by design the server runs it first. The trace was off, so this run does not show that step, but the resume below drafted the same in both arms.
- **Resume.** The resumed request read the remaining 1,308 or 1,536 tokens and wrote the same JSON answer as the fresh reads, with the same drafts in all four launches.
- **Restores.** Every regenerate re-read 4 tokens and every edited follow-up 26 tokens, as in N06: 49.4–56.6 ms and 252.1–281.3 ms, with medians of 49.9–51.0 and 260.0–260.9 ms per app.
- **Chat reply speed** (median per launch, against the kept launches' average). First replies were 1.0–1.4% slower in the overlap launches of the default and Long Documents apps, and 0.1% faster in Code Editing. Regenerates were within 0.4%. Follow-ups and edited follow-ups were 3.1–6.6% slower in the first launch of every app than in its other three, as in N06; the first launch is a kept launch. The other three agreed within 3.2%.

## Memory

| App | Peak RSS, kept | Peak RSS, overlap | Overlap extra (average) | Allowed | Least available |
| --- | --- | --- | ---: | ---: | ---: |
| Default (512) | 37.86, 38.00 GiB | 38.10, 38.30 GiB | +271 MiB | 287 MiB | 2.73 GiB |
| Code Editing (512) | 38.24, 38.18 GiB | 38.17, 38.30 GiB | +22 MiB | 128 MiB | 3.06 GiB |
| Long Documents (1,536) | 38.56, 38.72 GiB | 38.60, 38.69 GiB | +6 MiB | 327 MiB | 2.46 GiB |

The default app's +271 MiB fit only because its two kept launches differed by 143 MiB. The other two apps show +22 and +6 MiB, and N15 measured no difference. Swap stayed at 160 MiB in every launch.

## Held and corrected attempts

**The first scoring of this run failed every launch on the cancel check, the kept engine's included.** The check counted any byte the client had received by 0.5 s as a reply that had started. This server version sends its HTTP headers as soon as it starts reading a streamed prompt. So every launch had bytes waiting, though each stopped mid-prompt.

- **Fix:** the check now uses the stop point alone: a stop before the end of the prompt means no reply token existed. The client now also records whether reply data (`data:` events), not just headers, had arrived.
- **Recomputation:** the decision was recomputed from the 12 saved launches with `--analyze`. The measurements are unchanged, and the recorded decision is kept alongside the new one in the run's summary.
- **Effect:** the recorded decision listed three lifecycle failures and the same two regressions. The recomputed one lists only the regressions. The decision did not change.

## Limitations

- **Two launches per arm and one to two requests per row.** A single slow reply decided both failed rows. This run cannot say whether the overlap makes such replies more frequent; it had 7 against the kept engine's 8.
- **One request at a time.** Concurrent slots and sampled (non-greedy) replies were not tried.
- **One cancel point per launch,** after the first one or two chunks. Cancels in the last chunks, or during a reply, were not tried.
- One machine with a warm file cache after the first launch.

## Next

1. **The app stays unchanged.** N15 remains a diagnostic engine; the switches stay off unless set.
2. **Find the first-draft cost after a long prompt** (2.3–3.3 ms here, 2.5–3.5 ms in N15), for example with N15's overlap trace (`GGML_M5_LAB_OVERLAP_TRACE`). With it removed, replies after long prompts would no longer be near the rule's 1% limit.
3. **Then qualify again,** with these checks. The rule for that run should be fixed before it starts. It needs enough replies per row that one slow reply cannot decide a row. One option is more requests per row.
4. N01 (llama.cpp #30373) and the router's 42.4 ms split remain next in the queue.

## Reproduce

Each command is a plan only until `--run` is added. Use a new output directory each time.

```sh
.venv/bin/python scripts/prepare_m5.py --engine m5-overlap --build --jobs 2
.venv/bin/python scripts/qualify_overlap.py --output bench/features/<new-name> --run
.venv/bin/python scripts/qualify_overlap.py --output bench/features/<that-name> --analyze
```

The last command recomputes the summary of a finished run from its saved launches, without a model.

Native logs, per-request rows, conversation text and memory samples stay local and ignored under `bench/features/20261014-n15-qualify*`. This report contains only aggregate numbers and synthetic workload names.
