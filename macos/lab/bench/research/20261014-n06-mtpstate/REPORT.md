# N06: MTP draft state across context checkpoint restores

October 14, 2026. MacBook Pro M5 Pro (20 GPU cores), 48 GiB, AC power, Automatic power mode. Same model, helper and settings as [N02](../20261014-n02-advise/REPORT.md): the full Qwen3.8-Flash-Next GSQ-RCO Q2_0 model, packed shared Q3 MTP helper in mixed placement, depth 3, 4K context, F16 KV cache, default 512-token prompt chunks.

**The question.** The MTP draft pairs the first token of each prompt batch with the last hidden row of the previous target batch. The pinned engine does not save that row with a context checkpoint. So when the server restores a checkpoint, the next batch's first token is paired with whatever row the previous request left behind. llama.cpp PR 30141 saves the row, plus the last verification rows, with each checkpoint and restores them. The [repo audit](../20261014-repo-audit/REPORT.md) found that restores happen but had not shown any harm from the stale row.

The engine is `m5-mtpstate`, an isolated diagnostic clone: the kept `m5-small-stack` patch plus changes to one file, `common/speculative.cpp`, with switches that are off unless set. The kept engine and its build were not touched.

**Result:** the stale row is real, but restoring it changed nothing measurable here.

- **Restores happened** 16 times per mode: on every regenerated reply (8) and every edited follow-up (8). Plain follow-up turns reused the whole cache and needed no restore.
- **The row in use was stale** at every restore. Its distance from the saved row was 0.93–1.46 times the saved row's own size (median 1.12): about as far as an unrelated row.
- **Drafting did not change.** With the saved row restored or left stale, every request drafted the same tokens and had the same number accepted: 1,082 of 1,604 drafts (67.5%) in both modes. Every request wrote the same text in all four launches (17 requests per launch, warm-up included).
- **Repeatable:** both launches of each mode matched request for request. A regenerated reply drafted, accepted and wrote exactly what the first reply did, in both modes.
- **Speed:** a regenerate re-read 4 tokens in 49.4–55.4 ms and an edit 26 tokens in 257.7–272.2 ms in both modes, apart from one 406.6 ms edit in the first launch. Applying the saved state did not show in these times.
- **Memory cost of the PR's layout:** the saved verification rows make checkpoints up to 19.9 MiB larger. A checkpoint after a long prompt grew from 112.6 to 132.5 MiB (+17.6%). After a decode step it saves 1–4 rows, so it grew by 0.2 MiB or less.
- **Memory:** peak process RSS 38.04–38.31 GiB, at least 3.11 GiB available, and swap grew by 0 in all four launches. At most 5 checkpoints were held at once.

The fix is not adopted. It fixed a real stale state but changed no draft or output measured here, and its saved rows cost memory. No default changes (see Next).

## What the switches do

- **Saving, always on in this engine:** with each context checkpoint, the MTP draft saves its pending row and its last verification rows, in PR 30141's layout. Both modes save the same, so checkpoints are the same size in both.
- **`GGML_M5_LAB_MTP_STATE=restore`:** on a checkpoint restore, the saved rows are applied, as PR 30141 does. Unset keeps the pinned behaviour: the saved state is ignored and the row the previous request left is used.
- **`GGML_M5_LAB_MTP_STATE_TRACE=1`:** prints one line per save (rows and bytes) and per restore. A restore line reports whether the state was applied, and how far the row in use is from the saved one, as a relative difference: the size of the difference divided by the size of the saved row.

With the switches unset, the engine behaves as the kept engine, except that each checkpoint also holds the saved MTP rows. Kernels, weights, arithmetic, loader, allocator and server code are unchanged.

## Method

- **Launches:** four, in the order stale, restore, restore, stale, each with the trace on.
- **Requests:** each launch held one conversation per standard prompt, through the chat endpoint with the prompt cache on, as a chat app uses it. Replies were greedy (temperature 0), up to 128 tokens. Each conversation had four requests:
  1. the first reply;
  2. the same request again (regenerate);
  3. a follow-up turn after the first reply;
  4. the same follow-up with its question edited.

  One warm-up request came first in every launch and is not compared.
- **Matching:** trace lines were matched to requests by monotonic time. Requests were compared between modes by conversation and turn.
- **Guards:** 34 GiB available before loading, a 1 GiB running floor, normal memory pressure, zero new swap, a quiet CPU and AC power. The owned server was stopped before the next launch. The server was ready 2.1 s after each start.

## Restores and drafting

Totals over both launches of each mode (8 requests per row and mode).

| Request | Restores | Drafted | Accepted | Rate | Same in both modes |
| --- | ---: | ---: | ---: | ---: | --- |
| first reply | 0 | 574 | 394 | 68.6% | yes |
| regenerate | 8 | 574 | 394 | 68.6% | yes |
| follow-up | 0 | 138 | 98 | 71.0% | yes |
| edited follow-up | 8 | 318 | 196 | 61.6% | yes |

- **Where restores land.** A regenerate restores the checkpoint 4 tokens before the end of the prompt and re-reads those 4 tokens. An edit restores the checkpoint at the start of the last user message and re-reads that message. A follow-up turn extends the cached conversation, so no restore is needed.
- **Saved rows at those restores.** After a long prompt the checkpoint held 508 verification rows; after the 307-token prompt 303, after the 48-token prompt 44, and after a decode step 1–4.
- **Why one stale row did not matter here.** By code reading, the stale row feeds only the first position re-read after the restore, in the draft head's own cache. The restores here came after 44–2,364 cached positions. In these 16 restores per mode it changed no drafted token. This run does not show a case where it would.

## Reply speed

Reply speed in tok/s, median of the four conversations in each launch.

| Launch | First reply | Regenerate | Follow-up | Edited follow-up |
| --- | ---: | ---: | ---: | ---: |
| 1, stale | 59.12 | 62.46 | 51.50 | 49.61 |
| 2, restore | 61.85 | 62.41 | 54.50 | 52.70 |
| 3, restore | 61.61 | 62.34 | 54.62 | 52.65 |
| 4, stale | 61.79 | 62.24 | 54.61 | 52.70 |

The first launch was slower in three of the four request kinds, including first replies, which involve no restore. Launches 2–4 agree within 0.6%. The drafts were identical, so the modes could only differ by the cost of applying the state, which these times do not show.

## Engine checks

- **Source:** a separate clone at the pinned revision with the kept stack's patch and the state code in `common/speculative.cpp`. The patch is bound by hash in `config/m5_mtpstate_experiment.json`. The kept engine and the vendor checkout are unchanged.
- **Build:** `speculative.cpp` compiles without warnings under the build's own flags.
- **GPU math on the measured build** (Tensor API on, kept tuning): 572/572 matrix checks and 16/16 fused-residual checks pass.
- **State checks in the run:** all 32 restores read a valid saved state (0 rejected). The 16 in restore mode applied it, and the 16 in stale mode did not.

## Limitations

- **Greedy, single-slot chat.** Sampled replies, several slots and cancelled requests were not tried.
- **16 restores per mode,** all at the end of a prompt or the start of the last user message. The position-0 case was not traced: there, a fresh prompt pairs its first token with the previous request's row too, and PR 30141 does not change that.
- **One checkpoint layout.** A smaller layout that saves only the pending row (40 KiB) was not built or measured.
- One machine with a warm file cache.

## Next

1. **N06 does not change a default.** If llama.cpp merges PR 30141, the stale state is fixed as part of that upgrade. Its extra checkpoint memory (up to 19.9 MiB each, at most 5 here) is then part of that upgrade's memory check.
2. **N07** (helper-only checkpoint copy omission) was waiting on N06 and can proceed. It still has to measure the bytes it would remove, and check drafts and text across regenerate and edit restores as N06 did.
3. Qualify N15 as a candidate at 512, adding regenerate and edit requests like these to its checkpoint-restore checks.

## Reproduce

Each command is a plan only until `--run` is added. Use a new output directory each time.

```sh
.venv/bin/python scripts/prepare_m5.py --engine m5-mtpstate --build --jobs 2
.venv/bin/python scripts/verify_m5.py --engine m5-mtpstate --tensor-api on --tuning small-reduce --run
.venv/bin/python scripts/profile_mtpstate.py --output bench/features/<new-name> --run
```

Native logs, per-request rows and memory samples stay local and ignored under `bench/features/20261014-n06-mtpstate*`. This report contains only aggregate numbers and synthetic workload names.
