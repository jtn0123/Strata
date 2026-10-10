#!/usr/bin/env python3
"""Compare selected prediction runs and preserve the percentage calculations."""
import argparse
from datetime import datetime, timezone
import json
import statistics

from lab import ROOT


def load_record(run_id, name="result.json"):
    return json.loads((ROOT / "bench/results" / run_id / name).read_text())


def compare(base, candidate, cached=False):
    assert base["status"] == candidate["status"] == "passed"
    assert base["model"] == candidate["model"] and base["runtime"] == candidate["runtime"]
    assert base["settings"].get("temperature", 0) == candidate["settings"].get("temperature", 0)
    for key in ["context", "batch", "ubatch", "cache_type", "threads", "predict"]:
        assert base["settings"].get(key) == candidate["settings"].get(key), key
    key = "history_budget" if cached else "prompt_tokens"
    rows = []
    for size in sorted({c[key] for c in base["cases"]}):
        selected = []
        for record in [base, candidate]:
            selected.append([c for c in record["cases"] if c[key] == size and
                (not cached or (c["cache"] and not c["warmup"]))])
        a, b = selected
        assert a and b
        assert {(c["repeat"], c["prompt_sha256"]) for c in a} == {(c["repeat"], c["prompt_sha256"]) for c in b}
        def metrics(cases):
            return {"generation_tok_s": statistics.median(c["native_timings"]["predicted_per_second"] if cached else c["generation_tok_s"] for c in cases),
                    "ttft_s": statistics.median(c["ttft_s"] for c in cases),
                    "wall_s": statistics.median(c["wall_s"] for c in cases)}
        x, y = metrics(a), metrics(b)
        rows.append({"size": size, "baseline": x, "prediction": y,
            "generation_gain_percent": 100 * (y["generation_tok_s"] / x["generation_tok_s"] - 1),
            "ttft_change_percent": 100 * (y["ttft_s"] / x["ttft_s"] - 1),
            "total_time_change_percent": 100 * (y["wall_s"] / x["wall_s"] - 1)})
    return {"baseline_run": base["run_id"], "prediction_run": candidate["run_id"], "rows": rows,
            "baseline_swap_growth_bytes": base["memory"]["swap_growth_bytes"],
            "prediction_swap_growth_bytes": candidate["memory"]["swap_growth_bytes"]}


def main():
    ap = argparse.ArgumentParser()
    for name in ["baseline_greedy", "candidate_greedy", "baseline_sampled", "candidate_sampled", "baseline_cache", "candidate_cache"]:
        ap.add_argument("--" + name.replace("_", "-"), required=True)
    args = ap.parse_args()
    record = {"schema": 1, "kind": "prediction-comparison", "inputs": vars(args),
              "decision": "Keep prediction optional. The normal profile retains caching and no MTP: the fixed-length writing gain disappears at temperature 0.6 and fresh-prompt startup becomes slower. Cached ledger replies finish 4-10% sooner, a limited workload benefit.",
              "comparisons": {"greedy": compare(load_record(args.baseline_greedy), load_record(args.candidate_greedy)),
                "sampled": compare(load_record(args.baseline_sampled), load_record(args.candidate_sampled)),
                "cached_sampled": compare(load_record(args.baseline_cache, "comparison.json"), load_record(args.candidate_cache, "comparison.json"), True)}}
    output = ROOT / "bench/results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-prediction-summary.json")
    output.write_text(json.dumps(record, indent=2) + "\n")
    lines = ["# Optimization 2: smaller prediction helper", "", record["decision"], "",
             "The main model, native runtime, context and processing batch stay the same. Selected helper: locally generated Q3_K_S pure, two draft tokens, output projection on GPU and its body on CPU. It is 1.798 GB, versus 2.786 GB for the original self-contained Q4 helper (35.5% smaller). Norms/router precision and shape-compatible fallback quantization are preserved. Derived SHA256 and preparation receipts are in config/models.json.", "",
             "| Workload | Size | Baseline output tok/s | Prediction output tok/s | Writing change | First-token delay change | Total time change |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for kind, comparison in record["comparisons"].items():
        for row in comparison["rows"]:
            a, b = row["baseline"], row["prediction"]
            lines.append(f"| {kind} | {row['size']} | {a['generation_tok_s']:.2f} | {b['generation_tok_s']:.2f} | {row['generation_gain_percent']:+.1f}% | {row['ttft_change_percent']:+.1f}% | {row['total_time_change_percent']:+.1f}% |")
    lines += ["", "Positive writing change is faster. Positive delay/time change is slower. Percentages use candidate / matched baseline - 1. Synthetic writing runs produce 128 fixed tokens with EOS ignored; cached follow-ups use real ledger answers and normal EOS. Cache comparisons use only cache-on measured cases and exclude warm-ups. Exact prompt hashes, sampling, native logs and memory records are preserved.", "",
              "No additional swap growth occurred in the selected helper runs. Existing system swap remained; this is not a claim of zero total swap. These are limited local benchmarks with uncontrolled OS file cache and background applications.", "",
              "## Evidence", ""]
    for kind, comparison in record["comparisons"].items():
        name = "comparison.json" if kind == "cached_sampled" else "result.json"
        lines.append(f"- {kind}: [baseline](results/{comparison['baseline_run']}/{name}), [prediction](results/{comparison['prediction_run']}/{name}).")
    lines += [f"- [Machine-readable percentage calculations](results/{output.name}).", "",
              "## Other attempts", "",
              "- A 1.491 GB Q2_K helper with all-GPU placement exceeded the Metal working set on its first request. Its split placement ran without new swap, but its writing gain was only about 1-6% and prompt startup was slower.",
              "- A 1.110 GB Q2_0 helper ran initially with less than 2% draft acceptance, wrote at only 12-16 tokens/s, then failed with a Metal out-of-memory error. It is rejected. Partial failed-run speeds are not adopted benchmark results.",
              "- The Q3 CPU-only helper also ran without new swap, but was slower than the selected split placement.", "",
              "All attempts remain in the main scoreboard. The selected greedy and temperature-0.6 native runs each passed 18 focused answer checks. These check arithmetic, structured extraction, label changes and a small Python function; they are not a broad model-quality evaluation. Greedy output differs from the baseline after token 92 on the synthetic 512-token prompt, as in the original MTP experiment; 2048-token greedy output matches. Do not claim general bit-for-bit equivalence.", ""]
    (ROOT / "bench/PREDICTION.md").write_text("\n".join(lines))
    print(output)
    print(ROOT / "bench/PREDICTION.md")


if __name__ == "__main__":
    main()
