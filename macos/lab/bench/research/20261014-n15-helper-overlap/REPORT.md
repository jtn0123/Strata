# N15: running the helper's prompt work while the target reads the next chunk

October 14, 2026. MacBook Pro M5 Pro (20 GPU cores), 48 GiB, AC power, Automatic power mode. Same model, helper, settings and prompts as [N00](../20261014-n00-prompt-ops/REPORT.md) and [N00b](../20261014-n00b-segments/REPORT.md): the full Qwen3.8-Flash-Next GSQ-RCO Q2_0 model (61.85 GiB file), packed shared Q3 MTP helper in mixed placement with eight helper CPU workers, depth 3, 4K context, F16 KV cache, and the four balanced prompts from [E05](../20261013-prompt-chunks/REPORT.md).

The engine is `m5-overlap`, an isolated diagnostic clone: the kept `m5-small-stack` patch plus two switches that are off unless set. The kept engine and its build were not touched.

**Result:** with both switches on, the default 512-token chunks read long prompts 10.6–10.8% faster, with the same outputs and the same memory.

- **Long prompts at 512** (2,332 and 2,346 tokens):
  - prompt time fell from 4,535–4,567 ms to 4,057–4,076 ms (about 575 instead of 514 tok/s);
  - the whole reply (prompt plus answer) finished 9.5–10.4% sooner;
  - this matches serial Long Documents mode (1,536-token chunks, 4,080–4,156 ms here), which uses about 0.6 GiB more memory ([E05](../20261013-prompt-chunks/REPORT.md)).
- **Short prompts at 512:** the 307-token prompt was read 6.7% faster and the 48-token prompt 4.5% faster.
- **GPU idle time** per long prompt fell from 517–536 ms to 110–119 ms. 97% of the helper's prompt GPU time now runs while the target is also on the GPU. Sharing the GPU costs something: per long prompt, the target's GPU time rose by 101–103 ms (2.6%) and the helper's by 81–87 ms.
- **Outputs:** in every launch, each prompt returned the same token and top-8 probabilities, and the same reply text, length and draft counts, with overlap on or off (96 prompt reads and 96 replies).
- **Memory:** peak process RSS 37.43–38.10 GiB with overlap and 37.77–38.15 GiB without; swap grew by 0 in every launch.
- **Reply speed:** once a reply is under way, decode steps cost the same as before. In all eight launches the median step takes 53.5–57.5 ms, with 40.3–42.5 ms of GPU time, in both modes. The first helper draft after a long prompt takes 2.5–3.5 ms longer, once per reply. At 512, replies after the long prompts therefore report 0.9–1.4% lower tok/s; replies after short prompts are unchanged (−0.6% to +0.1%).
- **At 1,536** the gain is smaller and noisy: long prompts were read 0.0–4.6% faster (median), short ones 3.6–5.3% faster. With only three chunks, the last large helper chunk (1,532 tokens) has just the 4-token chunk to hide behind.

This is a diagnostic engine. Nothing in the app changes until a candidate passes the full qualification (see Next).

## What the switches do

- **`GGML_M5_LAB_CONTEXT_QUEUE`:** each Metal context gets its own command queue. Without it, the target and the helper share one queue, so the helper's work waits behind the target's queued chunk.
- **`GGML_M5_LAB_HELPER_OVERLAP`:** for a prompt chunk that samples no token, the MTP helper prepares the chunk (it copies its input rows) but does not decode it yet. The decode runs right after the server has queued the target's next chunk, on the same thread. The target's next chunk and the helper's previous one then share the GPU, and the helper's CPU experts run on the CPU while the target computes.
  - Every other helper call, and every server step that reads or changes the helper's memory, runs the waiting chunk first. These include drafting, accepting tokens, saving, loading or copying state, context shifts, releasing a slot, and any new task. Status reads (`NEXT_RESPONSE`, metrics and slot queries) are exempt.
  - A context checkpoint taken while a helper chunk is waiting saves its helper part after that chunk has run.
- **`GGML_M5_LAB_OVERLAP_TRACE`:** prints a host timestamp when each helper or target prompt step is deferred, queued or run. It was used to find the early-flush fault below and was off in the measured launches.

With all three unset, the engine behaves as the kept engine. Kernels, fusion rules, weights, arithmetic, allocator and context policy are unchanged. The chunk rule is unchanged too: at 512 a 2,332-token prompt reads as 512, 512, 512, 284, 508 and 4 tokens; at 1,536 as 796, 1,532 and 4.

## Method

- **Launches:** eight, on the `m5-overlap` engine with GPU timestamps on:
  - at 512: overlap, serial, serial, overlap;
  - at 1,536: serial, overlap, overlap, serial.

  "Overlap" sets the first two switches; "serial" sets neither.
- **Requests per launch:** for each prompt, three fresh one-token reads with the N00 settings plus the top 8 probabilities, then three fresh replies of up to 128 tokens at temperature 0. The replies stop at the model's end token: 31 tokens for long-retrieval, 11 for long-prose, 128 for the two short prompts.
- **Medians:** prompt times use the second and third read of each prompt in each launch (4 per mode, prompt and batch size). Reply speeds use all six replies per mode, prompt and batch size.
- **GPU timeline:** for each prompt read, the command buffers of both contexts inside the request window are merged. Target and helper busy time are the union of their intervals. Overlap is the time both were busy. Idle is the time between the first and last command buffer when neither was. Under overlap, the helper's work on chunk k runs during the target's chunk k + 1, so per-chunk helper times move one chunk later; request totals do not.
- **Guards** on every launch, as in earlier campaigns:
  - 34 GiB available before loading, a 1 GiB running floor and normal memory pressure;
  - zero new swap, a quiet CPU and AC power;
  - the owned server stopped before the next launch.
- **Launch outcomes:** all eight launches passed.
  - Minimum available RAM was 2.59–2.95 GiB at 512 and 2.15–2.32 GiB at 1,536.
  - Swap grew by 0; the 160 MiB that existed before stayed unchanged.
  - The server was ready 2.1–2.8 s after each start (warm file cache).

## Prompt reading

Medians in ms. Change is overlap against serial on the same engine.

| Batch | Prompt (tokens) | Serial | Overlap | Change | GPU idle serial → overlap | Helper during target |
| --- | --- | ---: | ---: | ---: | --- | --- |
| 512 | long-retrieval (2,332) | 4,535.4 | 4,056.8 | −10.6% | 517.0 → 109.6 | 262.5 of 269.6 |
| 512 | long-prose (2,346) | 4,567.3 | 4,075.6 | −10.8% | 536.1 → 118.5 | 259.4 of 266.8 |
| 512 | python-client (307) | 655.8 | 611.8 | −6.7% | 73.3 → 43.5 | 21.7 of 23.7 |
| 512 | short-prose (48) | 286.4 | 273.3 | −4.5% | 18.6 → 8.5 | 7.0 of 7.7 |
| 1,536 | long-retrieval (2,332) | 4,156.4 | 4,156.4 | 0.0% | 612.5 → 619.1 | 100.1 of 217.4 |
| 1,536 | long-prose (2,346) | 4,079.6 | 3,891.6 | −4.6% | 562.5 → 378.1 | 141.4 of 240.9 |
| 1,536 | python-client (307) | 653.1 | 618.4 | −5.3% | 70.9 → 45.2 | 21.6 of 23.6 |
| 1,536 | short-prose (48) | 285.4 | 275.1 | −3.6% | 17.1 → 8.3 | 6.8 of 7.5 |

- **At 512** the repeats are tight: every long-prompt read after the first took 4,039–4,080 ms with overlap and 4,525–4,587 ms without.
- **Where the helper's time goes:** most of each helper chunk now runs during the target's next chunk. The 508-token helper chunk runs during the final 4-token target chunk, which takes about 80 ms of GPU time instead of 50 ms.
- **At 1,536** long prompts varied in both modes. Counting every read, serial reads took 4,030–4,294 ms and overlap reads 3,830–4,314 ms. Those launches read 593–676 MiB from disk during their requests, against 25–304 MiB at 512, and had less free memory (above). Page-cache misses fit this pattern, but were not traced. The 1,536 long-prompt figures are therefore weaker than the 512 ones.

## Reply speed

| Batch | Prompt | Reply tokens | Serial tok/s | Overlap tok/s | Change |
| --- | --- | ---: | ---: | ---: | ---: |
| 512 | long-retrieval | 31 | 65.73 | 65.16 | −0.9% |
| 512 | long-prose | 11 | 57.25 | 56.43 | −1.4% |
| 512 | python-client | 128 | 73.12 | 73.20 | +0.1% |
| 512 | short-prose | 128 | 43.48 | 43.24 | −0.6% |
| 1,536 | long-retrieval | 31 | 65.70 | 65.03 | −1.0% |
| 1,536 | long-prose | 11 | 56.56 | 54.79 | −3.1% |
| 1,536 | python-client | 128 | 73.19 | 71.29 | −2.6% |
| 1,536 | short-prose | 128 | 43.35 | 40.49 | −6.6% |

Two checks on the GPU timeline separate the steady decode from one-off costs:

- **Steady decode is unchanged.** In every launch, in both modes, the median time from one target decode step to the next is 56.5–57.5 ms after the long prompts and 53.5–54.0 ms after the short ones. Each step's GPU time is 42.3–42.5 ms and 40.3–40.7 ms. At 512, the helper's later draft steps take a median 10.2–10.8 ms in both modes.
- **The first draft after a long prompt is slower.** At 512 it takes 17.0–18.1 ms with overlap and 14.5–14.8 ms without, once per reply. After the 307-token prompt it takes 14.0–14.8 ms and 13.9–14.0 ms. With 11 and 31 tokens per reply, 2.5–3.5 ms is enough to explain the 0.9–1.4% lower tok/s at 512. The cause was not established.
- **At 1,536, the lower medians come from occasional slow steps.** Some steps took more than 1.5 times the median: 7 across the two overlap launches and 2 across the two serial ones, with the disk reads above. One overlap launch accounts for 6 of the 7. Its replies included 35.95–42.45 tok/s for short-prose and 40.03 tok/s for one long-prose reply. The other overlap launch was in line with serial. This run cannot tell whether overlap makes those slow steps more frequent, so it makes no claim about reply speed at 1,536.

Whole replies (prompt plus answer, from the server's timings) at 512: 4,524 instead of 5,000 ms for long-retrieval (−9.5%), 4,250 instead of 4,743 ms for long-prose (−10.4%), 2,354 instead of 2,395 ms for python-client (−1.7%), and 3,211 instead of 3,207 ms for short-prose (+0.1%).

## Engine checks

- **Source:** a separate clone at the pinned revision with the kept stack's patch and the overlap changes in `common/speculative.cpp`, `common/speculative.h`, `tools/server/server-context.cpp` and `ggml-metal-context.m`. The patch is bound by hash in `config/m5_overlap_experiment.json`. The kept engine and the vendor checkout are unchanged.
- **Build:** the three changed source files compile without warnings under the build's own flags. The measured binaries are the ones checked below: after the manifest's description was updated, a rebuild changed no binary hash.
- **GPU math on the measured build** (Tensor API on, kept tuning): 572/572 matrix checks and 16/16 fused-residual checks pass.

## Held and corrected attempts

None of these is used in the numbers above. Each smoke test kept its own folder of evidence.

1. **First smoke test (one long prompt at 512):** the helper never ran during target work (0.0 ms), and prompts were 1–2% slower than serial.
   - The trace showed the waiting helper chunk running about 2 ms after it was deferred, before the target's next chunk was queued. The server posts a `NEXT_RESPONSE` status task on every pass of its loop, and the "run the waiting chunk before any task" rule ran it there.
   - Fix: status reads (`NEXT_RESPONSE`, metrics and slot queries) no longer run the waiting chunk. The engine was rebuilt.
   - After the fix, smoke tests at 512 and 1,536 showed the overlap and identical outputs. That led to the guarded run above.
2. **Comparison step of the accepted run:** all eight launches passed, but the run's own comparison divided by a zero serial median (serial launches have no helper time during target work).
   - The tool now reports a percent change only when the serial median is not zero, and reports the difference in ms as well.
   - It also no longer pools all replies into one speed median, because the four prompts reply at 43–73 tok/s.
   - The comparison was recomputed offline from the eight saved launch results. The launches and their measurements are unchanged.

## Limitations

- **One request at a time.** All requests were single-slot, fresh prompts. Not exercised:
  - concurrent slots;
  - cancelling a request while a helper chunk is waiting;
  - cached prompts and restoring a checkpoint taken while a helper chunk was waiting.

  These paths run the waiting chunk first by design, but no test here checks them. N06 (MTP checkpoint restore validation) covers part of this.
- **Both switches together.** The switches were not measured separately. In the faulty first smoke test, the separate queues were on but the deferral never took effect, and no helper time overlapped.
- **Short replies.** The long prompts' replies were 11 and 31 tokens. The standard app suite's 256-token replies on its real workloads were not run.
- **The 2.5–3.5 ms first-draft cost** after a long prompt is measured but not explained.
- **Batch 1,536 is noisy.** Disk reads were higher in all four 1,536 launches, in both modes. The 1,536 results are weaker than the 512 ones, and reply speed at 1,536 is undecided.
- One machine with a warm file cache.

## Next

1. **Qualify overlap as a candidate.** Use the kept settings at 512 and run the standard app suite: fresh and cached workloads, 256-token replies, output parity, and the editing and Long Documents profiles. Add checks for cancelling a request mid-prompt and for checkpoint restores, after or with N06. Only a passing candidate can change a default.
2. **Chunk order at 1,536.** Reading the 1,532-token chunk first would leave the smaller chunk's helper work as the one to hide. That changes the chunk rule, so it is a separate experiment.
3. **First-draft cost.** Time the helper's first draft graphs after a long prompt, to find the 2.5–3.5 ms.

## Reproduce

Each command is a plan only until `--run` is added. Use a new output directory each time.

```sh
.venv/bin/python scripts/prepare_m5.py --engine m5-overlap --build --jobs 2
.venv/bin/python scripts/verify_m5.py --engine m5-overlap --tensor-api on --tuning small-reduce --run
.venv/bin/python scripts/profile_prompt_ops.py --mode overlap --profile 512 --profile 1536 --output bench/features/<new-name> --run
```

Native logs, per-request rows, memory samples and the smoke tests stay local and ignored under `bench/features/20261014-n15-helper-overlap*` and `bench/features/20261014-overlap-smoke/`. This report contains only aggregate numbers and synthetic workload names.
