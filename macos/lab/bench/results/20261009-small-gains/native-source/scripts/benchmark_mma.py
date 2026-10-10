#!/usr/bin/env python3
"""Compare the few-row GPU patch with fresh controls at the measured helper depths."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import threading

from benchmark import run
from benchmark_tuning import settings as tuning_settings, watch_resources
from benchmark_vocab import change, metrics
from check_memory import assert_no_model_server, print_snapshot, snapshot
from engines import verify_engine
from lab import ROOT

ENGINES = {"control": "mtp-shared", "candidate": "mtp-mma"}


def settings(profile, depth, label, repeats=2):
    args = tuning_settings("depth", depth, label, repeats=repeats)
    args.engine = ENGINES[profile]
    args.comparison_profile = profile
    return args


def plan(depths):
    return [(depth, profile) for depth in depths for profile in ("control", "candidate", "candidate", "control")]


def compare(records, order, repeats=2):
    if len(records) != len(order) or any(r["status"] != "passed" for r in records):
        raise ValueError("Every planned run must pass")
    pins = {}
    for record, (depth, profile) in zip(records, order):
        expected = vars(settings(profile, depth, record["settings"]["label"], repeats))
        if record["settings"] != expected:
            raise ValueError("A setting outside the kernel experiment changed")
        if any(record[k] != records[0][k] for k in ("model", "runtime", "draft_model", "actual_sources")):
            raise ValueError("Model, helper or baseline sources changed")
        engine = record["selected_engine"]
        if engine.get("engine") != ENGINES[profile]:
            raise ValueError("Incorrect engine was used")
        if profile in pins and engine != pins[profile]:
            raise ValueError("Source or binary changed between passes")
        pins[profile] = engine
        if record.get("memory", {}).get("guard") or not record["checks"] or not all(c["passed"] for c in record["checks"]):
            raise ValueError("Memory or answer checks failed")
    rows = []
    keys = sorted({(c["workload"], c["prompt_tokens"]) for c in records[0]["cases"]})
    for depth in dict.fromkeys(d for d, _ in order):
        subset = [r for r in records if r["settings"]["draft"] == depth]
        if any({(c["workload"], c["prompt_tokens"]) for c in r["cases"]} != set(keys) for r in subset):
            raise ValueError("Workload coverage changed")
        for cached, workloads in ((False, keys), (True, [("cached-ledger", n) for n in (512, 2048)])):
            for name, length in workloads:
                def select(record):
                    return [c for c in record["cached_cases"] if not c["warmup"] and c["history_budget"] == length] if cached else [
                        c for c in record["cases"] if (c["workload"], c["prompt_tokens"]) == (name, length)]
                groups = {p: [c for r in subset if r["settings"]["comparison_profile"] == p for c in select(r)] for p in ENGINES}
                if any(len(cases) != repeats * 2 for cases in groups.values()):
                    raise ValueError("Missing measured cases")
                if sorted(c["prompt_sha256"] for c in groups["control"]) != sorted(c["prompt_sha256"] for c in groups["candidate"]):
                    raise ValueError("Prompt tokens differ")
                if not cached and any(c["output_tokens"] != records[0]["settings"]["predict"] for cases in groups.values() for c in cases):
                    raise ValueError("Fixed output counts differ")
                rates = {p: metrics(cases, cached) for p, cases in groups.items()}
                passes = [metrics(select(r), cached) for r in subset if r["settings"]["comparison_profile"] == "control"]
                rows.append({"depth": depth, "workload": name, "input_budget": length, "cached": cached,
                             "profiles": rates, "candidate_vs_control": change(rates["control"], rates["candidate"]),
                             "control_passes": passes, "control_drift": change(*passes)})
    return rows


def render(record):
    lines = ["# Few-row Metal comparison", "", "Status: " + record["status"], "",
             "Full Flash-Next Q2_0, unchanged packed shared Q3 helper, mixed placement, 4K context, "
             "batch/ubatch 512, F16 cache, eight target and helper workers, temperature 0.6. "
             "Only the dense few-row Metal dispatch/kernel patch differs between paired engines.", "",
             f"Order: {record['order']}. Each pass excludes one warmup and measures {record['repeats']} repeats. "
             "Fresh replies use 128 tokens; cached replies stop normally. Percentages use fresh, matching-depth controls.", "",
             "| Depth | Workload / input | Control TPS | Patch TPS | Output gain | Total reply quicker | First token quicker | Control TPS drift |",
             "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for row in record.get("summary", []):
        a, b = (row["profiles"][p] for p in ENGINES)
        d = row["candidate_vs_control"]
        lines.append(f"| {row['depth']} | {row['workload']} / {row['input_budget']} | {a['generation_tok_s']:.3f} | "
                     f"{b['generation_tok_s']:.3f} | {d['generation_increase_percent']:+.2f}% | "
                     f"{d['total_time_reduction_percent']:+.2f}% | {d['ttft_reduction_percent']:+.2f}% | "
                     f"{row['control_drift']['generation_increase_percent']:+.2f}% |")
    for metric in ("wall_s", "ttft_s", "prompt_tok_s", "draft_acceptance_percent"):
        lines += ["", metric, "", "| Depth | Workload / input | Control | Patch |", "| ---: | --- | ---: | ---: |"]
        for row in record.get("summary", []):
            values = [row["profiles"][p][metric] for p in ENGINES]
            lines.append(f"| {row['depth']} | {row['workload']} / {row['input_budget']} | " + " | ".join(
                "n/a" if v is None else f"{v:.4f}" for v in values) + " |")
    lines += ["", "Raw runs", ""]
    for run_info in record["runs"]:
        lines.append(f"- [{run_info['depth']} / {run_info['profile']} / {run_info['run_id']}](../{run_info['run_id']}/result.json): "
                     f"{run_info['status']}, new swap {run_info['memory'].get('swap_growth_bytes', 0)/1024**3:.3f} GiB")
    if record.get("error"):
        lines += ["", record["error"]]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--depths", type=int, nargs="+", default=[1, 3, 4])
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args(argv)
    if args.repeats < 1 or not args.depths or len(set(args.depths)) != len(args.depths) or min(args.depths) < 1 or max(args.depths) > 4:
        ap.error("Use distinct depths 1-4 and at least one measured repeat")
    order = plan(args.depths)
    print_snapshot(snapshot())
    print(f"Plan: {order}", flush=True)
    if not args.run:
        print("Preparation only. Add --run to benchmark.")
        return
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        pins = {p: verify_engine(engine) for p, engine in ENGINES.items()}
        assert_no_model_server()
        folder = ROOT / "bench/results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-mma-comparison")
        folder.mkdir()
        record = {"schema": 1, "kind": "metal-few-row-comparison", "status": "running", "order": order,
                  "repeats": args.repeats, "engines": pins, "runs": [], "preflight": snapshot()}
        done = threading.Event()
        watcher = threading.Thread(target=watch_resources, args=(folder / "resources.jsonl", done), daemon=True)
        watcher.start()
        records = []
        try:
            for index, (depth, profile) in enumerate(order, 1):
                assert_no_model_server()
                result = run(settings(profile, depth, f"mma-{index}-{depth}-{profile}", args.repeats))
                records.append(result)
                record["runs"].append({"run_id": result["run_id"], "depth": depth, "profile": profile,
                                      "status": result["status"], "memory": result.get("memory", {})})
                (folder / "comparison.json").write_text(json.dumps(record, indent=2) + "\n")
                if result["status"] != "passed" or result["selected_engine"] != pins[profile]:
                    raise RuntimeError("Answer checks failed or the engine changed; comparison stopped")
                log = (ROOT / "bench/results" / result["run_id"] / "server.log").read_text()
                if "borrowing target embeddings/output; draft KV remains separate" not in log:
                    raise RuntimeError("Shared helper did not activate")
            record["summary"] = compare(records, order, args.repeats)
            record["status"] = "passed"
        except BaseException as error:
            record.update(status="failed", error=f"{type(error).__name__}: {error}")
            raise
        finally:
            done.set()
            watcher.join(timeout=5)
            record["postflight"] = snapshot()
            (folder / "comparison.json").write_text(json.dumps(record, indent=2) + "\n")
            (folder / "COMPARISON.md").write_text(render(record))
            print(f"Saved {folder}", flush=True)


if __name__ == "__main__":
    main()
