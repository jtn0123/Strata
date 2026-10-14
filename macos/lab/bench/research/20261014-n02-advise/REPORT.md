# N02: Apple advisory reads for the lazy lookup-table rows

October 14, 2026. MacBook Pro M5 Pro (20 GPU cores), 48 GiB, AC power, Automatic power mode. Same model, helper and settings as [N15](../20261014-n15-helper-overlap/REPORT.md): the full Qwen3.8-Flash-Next GSQ-RCO Q2_0 model (61.85 GiB file), packed shared Q3 MTP helper in mixed placement with eight helper CPU workers, depth 3, 4K context, F16 KV cache, default 512-token prompt chunks.

The model keeps one large table, `per_layer_token_embd.weight`, mapped from the file without loading it. Each prompt token reads 16 rows from it (a 512-token chunk reads 8,192 rows). A row whose page is not in memory is read from disk when the target gathers it. The pinned `llama_prefetch` does nothing on Apple.

The engine is `m5-advise`, an isolated diagnostic clone: the kept `m5-small-stack` patch plus one changed file, `src/llama-mmap.cpp`, with switches that are off unless set. The kept engine and its build were not touched.

**Result:** asking macOS to read a chunk's lookup rows before the gather halves the cost of reading a document for the first time. Warm reads cost about 1% more.

- **First reads** of a 2,088-token document, against a replay of the same document (median of 10 documents per mode):

  | Mode | Penalty (ms) | Change |
  | --- | ---: | ---: |
  | no advice | 333 | — |
  | `MADV_WILLNEED` (madvise) | 189 | −43% |
  | `F_RDADVISE` (rdadvise) | 168 | −50% |

  The whole first read took a median 4,433 ms with no advice, 4,313 ms with madvise (−2.7%) and 4,299 ms with F_RDADVISE (−3.0%).
- **Per 1,000 pages that were not in memory**, the first read cost 17.8 ms with no advice, 10.8 ms with madvise and 8.8 ms with F_RDADVISE. The two launches of each mode agree: 17.5 and 18.1, 11.1 and 10.5, 9.1 and 8.5 ms.
- **Warm replays** (the same document again, its rows in memory) took a median 4,078 ms with no advice, 4,114 ms with madvise (+0.9%) and 4,129 ms with F_RDADVISE (+1.3%). Advising pages that are already in memory took 5.5–14.4 ms per replay.
- **Replies:** reply speed on the four standard prompts was within −0.1% to +1.0% of no advice. Reply text was identical in all 48 warm replies across the modes, and each document's first read and replay gave the same reply.
- **Both calls finish their reads before returning.** In a check run, no advised page was missing from memory when either call returned (40 calls). On calls with more than 1,000 missing pages, reading took about 5.1–6.0 µs per missing page with madvise and 3.7–4.7 µs with F_RDADVISE. Without advice, each missing page cost about 17.8 µs of first-read time.
- **Memory:** peak process RSS 38.84–39.14 GiB in every mode, at least 2.84 GiB available, and swap grew by 0 in every passed launch.

This is a diagnostic engine. No default changes (see Next).

## What the switches do

- **`GGML_M5_LAB_ADVISE=madvise`:** before each gather, the rows' pages are passed to `madvise(MADV_WILLNEED)`, which asks the virtual-memory system to read them. This is the mechanism llama.cpp PR 30405 enables on Apple.
- **`GGML_M5_LAB_ADVISE=rdadvise`:** the same byte spans go to `fcntl(F_RDADVISE)`, which asks the file system to read them. It uses a duplicate of the lazy table's file descriptor, opened at load.
- **Spans** are whole pages inside the lazy mapping, with adjacent rows merged, at most 256 MiB per call. In the six measured launches (2,197 calls) no call reached the cap (the largest asked for 122 MiB), failed, or asked for a page outside the mapping.
- **`GGML_M5_LAB_ADVISE_TRACE=1`:** prints one line per call with the rows and pages asked for, how many pages were not in memory beforehand (`mincore`), and how long the advice took. `=2` also counts the pages still not in memory when the advice returns.

With the switches unset, the engine behaves as the kept engine. Kernels, fusion, weights, arithmetic, loader mapping, allocator and context policy are unchanged.

## Method

- **Launches:** six, in the order no advice, madvise, F_RDADVISE, F_RDADVISE, madvise, no advice. Each had the trace at level 1. The trace's `mincore` count runs in every mode, including no advice, so all modes pay its cost (a median 17–20 ms per 2,088-token request).
- **Documents:** excerpts of the pinned llama.cpp checkout's Markdown files, each cut to 2,048 tokens behind a one-sentence instruction (2,087–2,088 prompt tokens). Every launch read five excerpts that no earlier request had read. Each was sent twice in a row with a 32-token reply limit:
  - first exposure;
  - then an exact replay, whose rows are in memory.

  The penalty is the first read minus its own replay, so the document's length and content cancel out. The prompt cache was off, so both reads processed the whole prompt.
- **Warm replies:** the four standard prompts, two replies each of up to 128 tokens at temperature 0.
- **Warm-up:** one request first in every launch, not compared.
- **Guards:** 34 GiB available before loading, a 1 GiB running floor, normal memory pressure, zero new swap, a quiet CPU and AC power. The owned server was stopped before the next launch. The server was ready 2.1–2.3 s after each start.

## First exposure

Medians over 10 documents per mode (two launches of five).

| Mode | First read (ms) | Replay (ms) | Penalty (ms) | Pages not in memory | ms per 1,000 such pages | Advice, first / replay (ms) | Disk read, first (MiB) |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| no advice | 4,433 | 4,078 | 333 | 19,717 | 17.8 | — | 317 |
| madvise | 4,313 | 4,114 | 189 | 17,087 | 10.8 | 125 / 8.9 | 301 |
| F_RDADVISE | 4,299 | 4,129 | 168 | 18,514 | 8.8 | 101 / 11.4 | 329 |

- The "ms per 1,000 pages" column divides each mode's summed penalty by its summed count of pages that were not in memory.
- The number of pages not in memory on a first read varied from 7,241 to 26,589 per document, because the file cache before each launch was not controlled. Replays found a median 92–130 such pages.
- A least-squares line through each mode's ten documents is noisier. Its slopes are 12.6, 13.6 and 8.5 ms per 1,000 pages, with intercepts of 99, −48 and 5 ms. On that view madvise lowers the fixed part, not the per-page part. Ten documents per mode cannot separate the two.
- The advice calls take time of their own: 38–156 ms per first read. They save more than that because they read pages in bulk, rather than one fault at a time during the gather.

## Warm replies

Reply speed in tok/s, median of four replies per prompt and mode.

| Prompt | No advice | madvise | F_RDADVISE |
| --- | ---: | ---: | ---: |
| long-retrieval (31 tokens) | 63.94 | 64.47 (+0.8%) | 64.56 (+1.0%) |
| long-prose (11 tokens) | 57.08 | 57.32 (+0.4%) | 57.23 (+0.3%) |
| python-client (128 tokens) | 73.12 | 73.06 (−0.1%) | 73.12 (0.0%) |
| short-prose (128 tokens) | 42.50 | 42.47 (−0.1%) | 42.58 (+0.2%) |

- During a reply each step gathers one token's 16 rows. Their advice took a median 0.3–1.0 ms per request.
- In three of the six launches, the first warm read of a long standard prompt still found 2,942–3,788 of its pages not in memory. Those prompts had been read in earlier launches and runs. Between launches, macOS had dropped lookup pages from its file cache. So first exposure also follows a server restart, not only new text.

## Engine checks

- **Source:** a separate clone at the pinned revision with the kept stack's patch and the advice code in `src/llama-mmap.cpp`. The patch is bound by hash in `config/m5_advise_experiment.json`. The kept engine and the vendor checkout are unchanged.
- **Build:** `llama-mmap.cpp` compiles without warnings under the build's own flags.
- **GPU math on the measured build** (Tensor API on, kept tuning): 572/572 matrix checks and 16/16 fused-residual checks pass.

## Check run and held attempt

None of these is used in the numbers above.

1. **Check run:** one launch per advice mode at trace level 2, two documents each. It confirmed that both calls return with every advised page in memory. It also found one of the 64 excerpts too short to cut to 2,048 tokens; the full runs left that excerpt and the four the check read out.
2. **First full run, stopped:** the zero-new-swap guard stopped the third launch (F_RDADVISE) on its third document.
   - Swap grew by 512 KiB, with 2.64 GiB still available. At that launch's start, Apple's `mediaanalysisd` was the largest other process (about 890 MB); it was not among the three largest at the first two launches' starts.
   - The first two launches of that run had passed with 2.71–2.77 GiB available.
   - Its documents had now been read, so they were no longer first exposures. The rerun left out all 24 excerpts that run had been given. That left 35 unseen excerpts, so the rerun read five per launch instead of eight.

## Limitations

- **Synchronous reads.** On this Mac both calls return only after the pages are in memory, so the reading still happens on the thread about to gather. Advice from another thread, one chunk ahead, was not tried; it could hide more of the reading.
- **Warm cost.** Every request pays for advice, even when its pages are already in memory: +0.9% and +1.3% on warm 2,088-token replays.
- **Uncontrolled file cache.** Nothing was purged or preloaded. Comparisons rely on each document's own replay and the trace's page counts.
- **Ten documents per mode,** all English Markdown excerpts. Code or other languages may read other rows.
- One machine; one request at a time.

## Next

N02 does not change a default. Two steps could turn it into a candidate:

1. **Skip advice for pages already advised** since load, using an in-process record of those pages, so warm reads pay nothing. Pages macOS drops later would be missed until the record is cleared.
2. **Advise one chunk ahead from a helper thread,** so the reading overlaps the previous chunk's GPU work instead of preceding the gather.

Either would be measured like this run: first exposure, warm replays, reply speed, text and memory. N06 comes first in the queue.

## Reproduce

Each command is a plan only until `--run` is added. Use a new output directory each time.

```sh
.venv/bin/python scripts/prepare_m5.py --engine m5-advise --build --jobs 2
.venv/bin/python scripts/verify_m5.py --engine m5-advise --tensor-api on --tuning small-reduce --run
.venv/bin/python scripts/profile_advise.py --check --output bench/features/<check-name> --run
.venv/bin/python scripts/profile_advise.py --output bench/features/<new-name> --exclude bench/features/<check-name> --run
```

Native logs, per-request rows, memory samples, the check run and the stopped run stay local and ignored under `bench/features/20261014-n02-advise*`. This report contains only aggregate numbers and the names of public documentation files.
