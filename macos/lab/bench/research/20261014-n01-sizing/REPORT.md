# N01: llama.cpp #30373 on the model's expert matrices, without the model

October 14, 2026. MacBook Pro M5 Pro (20 GPU cores), 48 GiB, macOS 27.2, AC power, Automatic power mode. No model was loaded. Every number comes from `test-backend-ops` timing the expert matrix operation (`MUL_MAT_ID`) alone on the Metal backend, at the model's shapes: Q2_0 experts, 512 per layer, 10 per token.

[llama.cpp #30373](https://github.com/ggml-org/llama.cpp/pull/30373) ("metal : fix mul_mat_id with duplicate ids", merged October 12 as 073b7403) changes how Metal schedules this operation. It lists the 32-token tiles of the experts that have tokens and starts one group per possible tile: at most 671 per column block at 512 tokens, where the pinned source starts 8,192, most of which find no tokens.

**Result:** not worth porting. The app is unchanged.

- On our shapes, #30373 speeds up the down matrix and slows the gate and up matrices. Summed over the 48 layers' gate, up and down matrices, with each token's experts picked at random from all 512:
  - 32 tokens: 117.1 → 120.1 ms (+2.6%);
  - 512 tokens, the default chunk: 294.9 → 298.9 ms (+1.4%);
  - 1,536 tokens, the Long Documents chunk: 562.2 → 552.8 ms (−1.7%).
- The kept engine already has a similar path of its own: P11's compact tiles (`GGML_M5_LAB_COMPACT_TILES`, off by default, up to 512 tokens). At 512 tokens it takes 283.8 ms, 4.0% less than the kept engine without it and 5.1% less than #30373. On the full model it still gave no gain: with 859- and 1,004-token English prompts, reply speed changed by −0.31% and −0.16% (the [P11 screen](../../results/20261009-small-gains/REPORT.md)).
- About half of the matrix time at 512 tokens depends on how many experts the chunk uses. With the same arithmetic (512 tokens × 10 experts each), moving the work from 10 experts to all 512 adds 137.1 ms per chunk on the pristine source (134.6 → 271.7 ms). That is 1.90–2.04 µs per extra expert per matrix, about the same in all four setups. Neither #30373 nor the compact tiles change it: both only skip experts that have no tokens.

## Settings compared

| Setup | Source | Switches |
| --- | --- | --- |
| pristine | pinned `vendor/llama.cpp` at d812350, unchanged | none |
| #30373 | pristine plus the PR's merged diff (5 files, +182/−59); it applies cleanly | none |
| kept | pristine plus `patches/mtp-m5-small-stack.patch` | `small-reduce`: `GGML_M5_LAB_CONV_DIRECT=1`, `GGML_M5_LAB_REDUCE10=1` |
| kept + compact | the same kept build | `small-reduce` plus `GGML_M5_LAB_COMPACT_TILES=1` |

Each setup is a scratch copy made with `git archive` from the pinned vendor tree. Each got the same added test cases (see Reproduce) and was built only for `test-backend-ops`, with the runtime's flags (Release, Metal, embedded Metal library) and tests on. No engine used by the app or earlier experiments was rebuilt.

#30373 conflicts with the kept patch in `ggml-metal-common.cpp`, `ggml-metal-ops.cpp` and `mul_mm.metal`, so "kept plus #30373" was not built. #30373 is compared against the pristine source it was written for. The kept engine's numbers match the pristine source's within 0.3% at every random-route case, so either works as a reference.

## Method

- **Cases:** `MUL_MAT_ID` with F32 activations and 10 experts per token, at 32, 512 and 1,536 tokens:
  - gate and up: experts [2560, 640, 512]. Each token's one input row is shared by its 10 experts. Gate and up have the same shape, so one case times both.
  - down: experts [640, 2560, 512], one input row per used expert.
- **Random routes:** upstream's own. Each token picks 10 distinct experts at random, redrawn after every timed batch. At 512 tokens this uses nearly all 512 experts.
- **Expert-count sweep, at 512 tokens:** each token's 10 experts are distinct and taken in turn from the first 10, 32, 64, 128, 256 or 512 experts. Every expert in use gets the same number of tokens, and the arithmetic is the same at every count.
- **Timing:** `test-backend-ops perf` repeats the operation in one graph for at least one second per case and reports the mean time per operation. Each setup ran four times in the order pristine, #30373, kept, compact, compact, kept, #30373, pristine, done twice. Tables show the mean of the four runs; ± is their range divided by the mean. A difference counts only if it is larger than twice the larger range of the two setups.
- **Per chunk:** 48 layers × (2 × gate/up + down). This covers the routed expert matrices alone under synthetic routes. It is not a prediction for the model.
- **Correctness:** `test-backend-ops test` compares each setup's Metal output with the CPU backend (normalized error at most 5×10⁻⁴). All six random-route cases and four sweep cases (10 and 64 experts, both shapes) passed in all four setups.
- **Compact path in use:** every kept + compact run loaded the compact pipeline and printed its marker; no kept run did.
- **Machine:** no model and no server ran. Swap was 160.56 MiB before and after.

## Random routes

Time per operation in µs.

| Matrix | Tokens | pristine | #30373 | kept | kept + compact | #30373 vs pristine | compact vs kept |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| gate/up | 32 | 817.5 ±2.6% | 834.0 ±1.5% | 817.8 ±1.1% | 804.1 ±0.8% | +2.02% (within range) | −1.67% (within range) |
| down | 32 | 804.8 ±0.4% | 834.7 ±1.5% | 803.9 ±2.4% | 809.5 ±1.6% | +3.72% | +0.69% (within range) |
| gate/up | 512 | 1,959.9 ±0.5% | 2,051.7 ±0.3% | 1,962.0 ±0.3% | 1,945.3 ±0.5% | +4.68% | −0.85% (within range) |
| down | 512 | 2,224.8 ±1.3% | 2,123.9 ±0.2% | 2,231.3 ±0.3% | 2,020.8 ±0.3% | −4.54% | −9.43% |
| gate/up | 1,536 | 3,678.1 ±0.2% | 3,792.1 ±0.3% | 3,670.2 ±0.7% | 3,662.1 ±1.3% | +3.10% | not used above 512 |
| down | 1,536 | 4,357.3 ±0.4% | 3,933.4 ±0.5% | 4,357.7 ±0.4% | 4,344.0 ±1.1% | −9.73% | not used above 512 |

Per chunk (48 layers), in ms:

| Tokens | pristine | #30373 | kept | kept + compact |
| ---: | ---: | ---: | ---: | ---: |
| 32 | 117.1 | 120.1 | 117.1 | 116.1 |
| 512 | 294.9 | 298.9 | 295.5 | 283.8 |
| 1,536 | 562.2 | 552.8 | 561.5 | 560.1 |

## Experts in use

At 512 tokens, with the same arithmetic at every count. Per chunk (48 layers), in ms:

| Experts in use | pristine | #30373 | kept | kept + compact |
| ---: | ---: | ---: | ---: | ---: |
| 10 | 134.6 | 134.9 | 135.0 | 119.8 |
| 32 | 132.7 | 134.6 | 133.0 | 119.6 |
| 64 | 146.0 | 145.4 | 146.4 | 130.2 |
| 128 | 171.8 | 174.2 | 172.1 | 159.3 |
| 256 | 193.0 | 196.3 | 193.5 | 182.6 |
| 512 | 271.7 | 277.0 | 272.7 | 262.3 |

- Run-to-run ranges were at most 0.8% per operation for pristine, #30373 and kept, and 1.5–4.1% for kept + compact.
- Line fits give 1.90 µs per expert for gate/up and 1.94 µs for down on the pristine source. #30373 gives 1.96 and 2.03 µs, kept 1.91 and 1.95 µs, kept + compact 1.97 and 2.04 µs. The rise is not straight (fit residuals up to 4.2–5.6%): 32 experts cost the same as 10, and the step from 256 to 512 is the largest.
- #30373 is faster for down at every count (−11.7% at 10 experts, −4.5% at 512) and slower for gate/up at every count (+7.9% at 10, +5.6% at 512). Why gate/up is slower was not measured.
- One expert's slice of one matrix is 450 KiB (Q2_0 stores 64 weights in 18 bytes). Reading it in 1.90–2.04 µs would take 226–243 GB/s. Memory bandwidth was not measured, so this pass cannot say the per-expert cost is all weight reading. Each expert in use also adds one partly filled 32-token tile of work: an expert with 10 tokens fills 10 of the tile's 32 rows.

## What this means for N01

- N00b found a fixed cost of 89.4 ms per chunk in the routed experts and asked whether it is weight reading. A weight-reading cost would grow with the number of experts in use, not with tokens. This sweep finds such a cost: about 137 ms per 512-token chunk when the work is spread over all 512 experts.
- Both #30373 and the compact tiles only skip experts with no tokens. They leave this per-expert cost unchanged, as the equal slopes show.
- Porting #30373 would cost a three-file merge with the kept patch. At the default 512-token chunks it is slower on our shapes; at 1,536 it saves 1.7% of the matrix time. The kept engine's own compact path is faster at 512 and still gave no full-model gain.

## Limitations

- Routes are synthetic. N00b measured the model's whole experts segment at 248.6 ms per 512-token chunk, which includes the shared expert's activation and down matrix. That is less than either synthetic sum with all experts in use (271.7–298.9 ms). The synthetic routes therefore do not match the model's, and the model's per-chunk expert counts were not recorded.
- Each operation was timed alone, repeated on the same weights. In the model, other work runs between expert matrices.
- Only 32, 512 and 1,536 tokens were timed with random routes, and only 512 in the sweep.

## Next

- N01 is closed without a port. Revisit #30373 if upstream changes its gate/up path, or if the model ever needs its duplicate-id fix. Our router picks 10 distinct experts per token, so the fix does not apply today.
- The per-expert cost is the larger item. A change that reads fewer expert weights per chunk would target it. No such change is queued.
- Next in the queue: split the router's 42.4 ms fixed cost per chunk.

## Reproduce

From `macos/lab`, with no model server running. The scratch copies live outside the repository; any empty folder works.

```sh
N=/tmp/n01
for t in base pr kept; do mkdir -p $N/$t; git -C vendor/llama.cpp archive HEAD | tar -x -C $N/$t; done
gh pr diff 30373 --repo ggml-org/llama.cpp > $N/pr30373.diff
git -C $N/pr init -q && git -C $N/pr apply $N/pr30373.diff
git -C $N/kept init -q && git -C $N/kept apply "$PWD/patches/mtp-m5-small-stack.patch"
```

Add the cases to `tests/test-backend-ops.cpp` in all three copies. Put the struct before `// FP4 W4A8 path on the MoE path`:

```cpp
// N01: ids drawn from the first `live` experts only, ten distinct per token and spread evenly, so the expert
// weights read scale with `live` while the arithmetic stays the same.
struct test_mul_mat_id_live : public test_mul_mat_id {
    const int live;

    test_mul_mat_id_live(int live, bool b, int64_t m, int64_t n, int64_t k)
        : test_mul_mat_id(GGML_TYPE_Q2_0, GGML_TYPE_F32, 512, 10, b, m, n, k), live(live) {
        GGML_ASSERT(live >= 10 && live <= 512);
    }

    std::string vars() override {
        return test_mul_mat_id::vars() + ",live=" + std::to_string(live);
    }

    void set_ids(ggml_context * ctx) {
        for (ggml_tensor * t = ggml_get_first_tensor(ctx); t != NULL; t = ggml_get_next_tensor(ctx, t)) {
            if (t->type != GGML_TYPE_I32 || ggml_is_view_op(t->op)) {
                continue;
            }
            for (int64_t r = 0; r < ggml_nrows(t); r++) {
                std::vector<int32_t> data(t->ne[0]);
                for (int i = 0; i < t->ne[0]; i++) {
                    data[i] = i < 10 ? (int32_t) ((r*10 + i) % live) : i % 512;
                }
                ggml_backend_tensor_set(t, data.data(), r * t->nb[1], t->ne[0] * sizeof(int32_t));
            }
        }
    }

    void initialize_tensors(ggml_context * ctx) override {
        test_mul_mat_id::initialize_tensors(ctx);
        set_ids(ctx);
    }

    void reinit_perf_iter(ggml_context * ctx) override {
        set_ids(ctx);
    }
};
```

Insert these lines at the start of both `make_test_cases_eval()` and `make_test_cases_perf()`, after the `test_cases` vector is declared. The sweep loop goes into the perf list as shown; the eval list uses `{10, 64}` instead:

```cpp
    for (int n : {32, 512, 1536}) {
        test_cases.emplace_back(new test_mul_mat_id(GGML_TYPE_Q2_0, GGML_TYPE_F32, 512, 10, true, 640, n, 2560));
        test_cases.emplace_back(new test_mul_mat_id(GGML_TYPE_Q2_0, GGML_TYPE_F32, 512, 10, false, 2560, n, 640));
    }
    for (int live : {10, 32, 64, 128, 256, 512}) {
        test_cases.emplace_back(new test_mul_mat_id_live(live, true, 640, 512, 2560));
        test_cases.emplace_back(new test_mul_mat_id_live(live, false, 2560, 512, 640));
    }
```

Build and run. Use bash so that `$K` splits into separate variables:

```sh
for t in base pr kept; do
  .venv/bin/cmake -S $N/$t -B $N/$t/build -DCMAKE_BUILD_TYPE=Release -DGGML_METAL=ON -DGGML_METAL_EMBED_LIBRARY=ON \
    -DLLAMA_BUILD_TESTS=ON -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_TOOLS=OFF -DLLAMA_BUILD_SERVER=OFF -DLLAMA_OPENSSL=OFF
  .venv/bin/cmake --build $N/$t/build --target test-backend-ops -j 4
done
K="GGML_M5_LAB_CONV_DIRECT=1 GGML_M5_LAB_REDUCE10=1"
$N/base/build/bin/test-backend-ops test -b MTL0 -o MUL_MAT_ID -p 'type_a=q2_0.*n_mats=512'
env $K GGML_M5_LAB_COMPACT_TILES=1 $N/kept/build/bin/test-backend-ops perf -b MTL0 -o MUL_MAT_ID -p 'live=' --output sql
```

The SQL output keeps `time_us`; the CSV output leaves it out. The raw runs, logs and the scripts that ran the order above and computed these tables stay ignored under `bench/features/20261014-n01-sizing/`.
