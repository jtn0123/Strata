#!/usr/bin/env python3
"""Plan the Q2 comparison; model loading requires an explicit --run."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import statistics

from benchmark import run
from check_memory import assert_no_model_server, print_snapshot, snapshot
from engines import verify_engine
from lab import ROOT

ORDER = ("baseline", "q2-masked", "q2-masked", "baseline")


def settings(engine, label, predict=512, repeats=3):
    return argparse.Namespace(model="flash", label=label, engine=engine, context=4096,
        batch=512, ubatch=512, cache_type="f16", spec="none", draft=3, draft_placement="gpu",
        draft_model="mtp", threads=8, temperature=0.6, extended_checks=True, repeats=repeats,
        warmups=1, predict=predict, prompts=[512, 2048])


def compare(records):
    if len(records) != len(ORDER) or any(record["status"] != "passed" for record in records):
        raise ValueError("Comparison requires four completed runs with passing answer checks")
    if [record["settings"]["engine"] for record in records] != list(ORDER):
        raise ValueError("Comparison must preserve baseline/candidate/candidate/baseline order")
    reference = {k: v for k, v in records[0]["settings"].items() if k not in ("label", "engine")}
    for record in records:
        if any(record.get(key) != records[0].get(key) for key in ("model", "runtime")):
            raise ValueError("Model identity or pinned runtime changed between runs")
        if {k: v for k, v in record["settings"].items() if k not in ("label", "engine")} != reference:
            raise ValueError("Benchmark settings differ between engines")
        if record.get("memory", {}).get("guard"):
            raise ValueError("A run stopped on memory pressure; its speed cannot be adopted")
    summaries = []
    for length in reference["prompts"]:
        cases = {engine: [case for record in records if record["settings"]["engine"] == engine
                          for case in record["cases"] if case["prompt_tokens"] == length] for engine in set(ORDER)}
        expected_count = 2 * reference["repeats"]
        if any(len(items) != expected_count for items in cases.values()):
            raise ValueError("Missing measured cases")
        if len({case["prompt_sha256"] for items in cases.values() for case in items}) != 1:
            raise ValueError("Prompt tokens differ between runs")
        if any(case["output_tokens"] != reference["predict"] for items in cases.values() for case in items):
            raise ValueError("Output lengths differ between runs")
        metrics = {engine: {name: statistics.median(case[name] for case in items)
                            for name in ("generation_tok_s", "prompt_tok_s", "ttft_s", "wall_s")}
                   for engine, items in cases.items()}
        before, after = metrics["baseline"], metrics["q2-masked"]
        summaries.append({"prompt_tokens": length, "baseline": before, "q2-masked": after,
            "generation_increase_percent": 100 * (after["generation_tok_s"] / before["generation_tok_s"] - 1),
            "prompt_increase_percent": 100 * (after["prompt_tok_s"] / before["prompt_tok_s"] - 1),
            "ttft_reduction_percent": 100 * (1 - after["ttft_s"] / before["ttft_s"]),
            "total_time_reduction_percent": 100 * (1 - after["wall_s"] / before["wall_s"])})
    return summaries


def render_report(record):
    lines = ["# Q2 Metal comparison", "", f"Status: {record['status']}", "",
             "Same full model, 4K context, batch/ubatch 512, F16 cache, temperature 0.6, prediction off. "
             f"Order: baseline, candidate, candidate, baseline. Each prompt has one excluded warmup and {record['repeats']} measured replies of {record['predict']} tokens. "
             "Fresh prompts disable prompt reuse. OS file cache is uncontrolled. Percentages compare this fresh baseline, not historical runs.", "",
             "| Input tokens | Baseline output TPS | Candidate output TPS | Output change | Baseline input TPS | Candidate input TPS |",
             "| ---: | ---: | ---: | ---: | ---: | ---: |"]
    for item in record.get("summary", []):
        lines.append(f"| {item['prompt_tokens']} | {item['baseline']['generation_tok_s']:.2f} | "
                     f"{item['q2-masked']['generation_tok_s']:.2f} | {item['generation_increase_percent']:+.2f}% | "
                     f"{item['baseline']['prompt_tok_s']:.2f} | {item['q2-masked']['prompt_tok_s']:.2f} |")
    lines += ["", "| Input tokens | Baseline first token (s) | Candidate first token (s) | Less waiting | Baseline reply (s) | Candidate reply (s) | Reply time reduction |",
              "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for item in record.get("summary", []):
        before, after = item["baseline"], item["q2-masked"]
        lines.append(f"| {item['prompt_tokens']} | {before['ttft_s']:.3f} | {after['ttft_s']:.3f} | "
                     f"{item['ttft_reduction_percent']:+.2f}% | {before['wall_s']:.3f} | {after['wall_s']:.3f} | "
                     f"{item['total_time_reduction_percent']:+.2f}% |")
    lines += ["", "Raw runs contain prompt throughput, exact source/patch/binary hashes, normal-EOS answer checks, memory/swap samples and server logs.", ""]
    for item in record.get("runs", []):
        lines.append(f"- [{item['engine']} / {item['run_id']}](../{item['run_id']}/result.json): "
                     f"{item['status']}; swap growth {item['memory'].get('swap_growth_bytes', 0)/1024**3:.3f} GiB")
    if record.get("error"):
        lines += ["", record["error"]]
    return "\n".join(lines) + "\n"


def execute_plan(args):
    engines = {engine: verify_engine(engine) for engine in set(ORDER)}
    proofs = sorted((ROOT / "bench/features").glob("*-q2-metal/checks.json"))
    proof = next((path for path in reversed(proofs) if
                  (saved := json.loads(path.read_text())).get("status") == "passed" and
                  saved["engine"] == engines["q2-masked"]), None)
    if proof is None:
        raise RuntimeError("Run scripts/verify_q2.py for this exact candidate build before benchmarking")
    assert_no_model_server()
    folder = ROOT / "bench/results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-q2-comparison")
    folder.mkdir()
    record = {"schema": 1, "kind": "q2-metal", "status": "running", "runs": [],
              "order": ORDER, "predict": args.predict, "repeats": args.repeats, "preflight": snapshot(),
              "correctness_record": str(proof.relative_to(ROOT))}
    records = []
    try:
        for index, engine in enumerate(ORDER, 1):
            assert_no_model_server()
            result = run(settings(engine, f"q2-{index}-{engine}", args.predict, args.repeats))
            records.append(result)
            record["runs"].append({"run_id": result["run_id"], "engine": engine,
                                   "status": result["status"], "memory": result.get("memory", {})})
            (folder / "comparison.json").write_text(json.dumps(record, indent=2) + "\n")
            if result["status"] != "passed":
                raise RuntimeError("Answer checks failed; comparison stopped")
        record["summary"] = compare(records)
        record["status"] = "passed"
    except BaseException as error:
        record["status"] = "failed"
        record["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        (folder / "comparison.json").write_text(json.dumps(record, indent=2) + "\n")
        (folder / "COMPARISON.md").write_text(render_report(record))
        print(f"Saved comparison: {folder}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true", help="Start model loading and benchmarks after the RAM check")
    ap.add_argument("--predict", type=int, default=512)
    ap.add_argument("--repeats", type=int, default=3)
    args = ap.parse_args(argv)
    if not 1 <= args.predict <= 1024 or args.repeats < 1:
        ap.error("Use 1-1024 output tokens and at least one measured repeat")
    print_snapshot(snapshot())
    print(f"Plan: {' / '.join(ORDER)}; full Flash-Next Q2_0; {args.predict} output tokens; {args.repeats} repeats per prompt.")
    if not args.run:
        print("ON HOLD. No model loading or benchmarks. After approval, rerun with --run.")
        return
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        execute_plan(args)


if __name__ == "__main__":
    main()
