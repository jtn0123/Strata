#!/usr/bin/env python3
"""Change helper depth or CPU workers with unchanged, repeated controls."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import threading

import psutil

from benchmark import run
from benchmark_shared import settings as shared_settings
from benchmark_vocab import change, metrics
from check_memory import assert_no_model_server, print_snapshot, snapshot
from engines import verify_engine
from lab import ROOT


def settings(axis, value, label, base_depth=2, base_threads=8, repeats=2):
    args = shared_settings("shared-mixed", label, repeats=repeats)
    args.comparison_profile = str(value)
    args.draft = value if axis == "depth" else base_depth
    args.draft_threads = value if axis == "threads" else base_threads
    return args


def compare(records, order, axis, base_depth=2, base_threads=8, repeats=2):
    if len(records) != len(order) or any(r["status"] != "passed" for r in records):
        raise ValueError("Every planned run and its answer checks must pass")
    for record, value in zip(records, order):
        expected = vars(settings(axis, value, record["settings"]["label"], base_depth, base_threads, repeats))
        if record["settings"] != expected:
            raise ValueError("A setting outside the tuning axis changed")
        if any(record[k] != records[0][k] for k in
               ("model", "runtime", "draft_model", "selected_engine", "actual_sources")):
            raise ValueError("Model, helper, source or binary changed")
        if record.get("memory", {}).get("guard") or not all(c["passed"] for c in record["checks"]):
            raise ValueError("Memory or answer checks failed")
    profiles = tuple(dict.fromkeys(order))
    baseline = str(base_depth if axis == "depth" else base_threads)
    rows = []
    keys = sorted({(c["workload"], c["prompt_tokens"]) for c in records[0]["cases"]})
    for cached, workloads in ((False, keys), (True, [("cached-ledger", n) for n in (512, 2048)])):
        for name, length in workloads:
            groups = {}
            for value in profiles:
                cases = [c for r in records if r["settings"]["comparison_profile"] == str(value)
                         for c in r["cached_cases" if cached else "cases"]]
                groups[str(value)] = [c for c in cases if not c["warmup"] and c["history_budget"] == length] if cached else [
                    c for c in cases if (c["workload"], c["prompt_tokens"]) == (name, length)]
            if any(len(cases) != repeats * order.count(int(p)) for p, cases in groups.items()):
                raise ValueError("Missing measured cases")
            hashes = {p: sorted(c["prompt_sha256"] for c in cases) for p, cases in groups.items()}
            if any(hashes[p] != hashes[baseline] for p in groups):
                raise ValueError("Prompt tokens differ between profiles")
            if not cached and any(c["output_tokens"] != records[0]["settings"]["predict"]
                                  for cases in groups.values() for c in cases):
                raise ValueError("Fixed output counts differ")
            rates = {p: metrics(cases, cached) for p, cases in groups.items()}
            baseline_passes = [r for r in records if r["settings"]["comparison_profile"] == baseline]
            per_pass = []
            for record in baseline_passes:
                cases = [c for c in record["cached_cases"] if not c["warmup"] and c["history_budget"] == length] if cached else [
                    c for c in record["cases"] if (c["workload"], c["prompt_tokens"]) == (name, length)]
                per_pass.append(metrics(cases, cached))
            rows.append({"workload": name, "input_budget": length, "cached": cached,
                         "profiles": rates, "vs_control": {p: change(rates[baseline], rate)
                                                           for p, rate in rates.items()},
                         "control_passes": per_pass})
    return rows


def render(record):
    profiles = tuple(dict.fromkeys(record["order"]))
    lines = ["# Helper tuning: " + record["axis"], "", "Status: " + record["status"], "",
             "Full Flash-Next Q2_0, packed shared Q3 helper, mixed placement, 4K context, "
             "batch/ubatch 512, F16 cache, target CPU threads 8, temperature 0.6. "
             "Only the named helper setting changes. No kernel, vocabulary or GPU-limit change.", "",
             f"Control: depth {record['base_depth']}, helper threads {record['base_threads']}. "
             f"Order: {record['order']}. Each pass excludes one warmup and measures {record['repeats']} repeats. "
             "Fresh replies use 128 output tokens; cached replies and answer checks stop normally. "
             "Previous suites are not pooled into these percentages.", ""]
    for key, title in (("generation_tok_s", "Output tokens/second"), ("wall_s", "Complete reply, seconds"),
                       ("ttft_s", "First token, seconds"), ("prompt_tok_s", "Input tokens/second"),
                       ("draft_acceptance_percent", "Draft acceptance, percent")):
        lines += [title, "", "| Workload / input | " + " | ".join(str(p) for p in profiles) + " |",
                  "| --- | " + " | ".join("---:" for _ in profiles) + " |"]
        for row in record.get("summary", []):
            values = [row["profiles"][str(p)][key] for p in profiles]
            lines.append(f"| {row['workload']} / {row['input_budget']} | " + " | ".join(
                f"{v:.3f}" if v is not None else "n/a" for v in values) + " |")
        lines += [""]
    lines += ["Changes from this suite's control", "",
              "| Workload / input | Setting | Output gain | Total reply quicker | First token quicker |",
              "| --- | ---: | ---: | ---: | ---: |"]
    for row in record.get("summary", []):
        for value in profiles:
            if value == record["control"]:
                continue
            delta = row["vs_control"][str(value)]
            lines.append(f"| {row['workload']} / {row['input_budget']} | {value} | "
                         f"{delta['generation_increase_percent']:+.2f}% | "
                         f"{delta['total_time_reduction_percent']:+.2f}% | "
                         f"{delta['ttft_reduction_percent']:+.2f}% |")
    lines += ["", "Raw runs", ""]
    for run_info in record["runs"]:
        lines.append(f"- [{run_info['value']} / {run_info['run_id']}](../{run_info['run_id']}/result.json): "
                     f"{run_info['status']}, new swap {run_info['memory'].get('swap_growth_bytes', 0)/1024**3:.3f} GiB")
    if record.get("error"):
        lines += ["", record["error"]]
    return "\n".join(lines) + "\n"


def watch_resources(path, done):
    processes = {}
    with path.open("w") as stream:
        while not done.is_set():
            groups = {}
            for proc in psutil.process_iter(["name", "memory_info"]):
                try:
                    tracked = processes.setdefault(proc.pid, proc)
                    if proc.info["memory_info"] is None: continue
                    name = proc.info["name"] or "unknown"
                    group = groups.setdefault(name, {"name": name, "cpu_percent": 0, "rss_bytes": 0})
                    group["cpu_percent"] += tracked.cpu_percent()
                    group["rss_bytes"] += proc.info["memory_info"].rss
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    continue
            stream.write(json.dumps({"utc": datetime.now(timezone.utc).isoformat(),
                "available_bytes": psutil.virtual_memory().available, "swap_used_bytes": psutil.swap_memory().used,
                "cpu_groups": sorted(groups.values(), key=lambda g: g["cpu_percent"], reverse=True)[:8]}) + "\n")
            stream.flush()
            done.wait(2)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--axis", choices=["depth", "threads"], default="depth")
    ap.add_argument("--values", type=int, nargs="+")
    ap.add_argument("--base-depth", type=int, default=2)
    ap.add_argument("--base-threads", type=int, default=8)
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args(argv)
    control = args.base_depth if args.axis == "depth" else args.base_threads
    values = args.values if args.values is not None else ([1, 3, 4] if args.axis == "depth" else [6, 12])
    if args.repeats < 1 or not values or len(set(values)) != len(values) or control in values or min(values) < 1:
        ap.error("Use positive, distinct candidate settings, excluding the control, and at least one repeat")
    if not 1 <= args.base_depth <= 4 or not 1 <= args.base_threads <= 18 or max(values) > (4 if args.axis == "depth" else 18):
        ap.error("This Mac experiment supports depths 1-4 and helper thread counts 1-18")
    half = (control, *values)
    order = half + tuple(reversed(half))
    print_snapshot(snapshot())
    print(f"Plan: {args.axis} {order}", flush=True)
    if not args.run:
        print("Preparation only. Add --run to benchmark.")
        return
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        verify_engine("mtp-shared")
        assert_no_model_server()
        folder = ROOT / "bench/results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-tuning-{args.axis}")
        folder.mkdir()
        record = {"schema": 1, "kind": "helper-tuning", "axis": args.axis, "status": "running",
                  "order": order, "control": control, "base_depth": args.base_depth,
                  "base_threads": args.base_threads, "repeats": args.repeats, "runs": [], "preflight": snapshot()}
        done = threading.Event()
        watcher = threading.Thread(target=watch_resources, args=(folder / "resources.jsonl", done), daemon=True)
        watcher.start()
        records = []
        try:
            for index, value in enumerate(order, 1):
                assert_no_model_server()
                result = run(settings(args.axis, value, f"tuning-{args.axis}-{index}-{value}",
                                      args.base_depth, args.base_threads, args.repeats))
                records.append(result)
                record["runs"].append({"run_id": result["run_id"], "value": value,
                                      "status": result["status"], "memory": result.get("memory", {})})
                (folder / "comparison.json").write_text(json.dumps(record, indent=2) + "\n")
                if result["status"] != "passed":
                    raise RuntimeError("Answer checks failed; tuning stopped")
                log = (ROOT / "bench/results" / result["run_id"] / "server.log").read_text()
                if "borrowing target embeddings/output; draft KV remains separate" not in log:
                    raise RuntimeError("Shared helper did not activate")
            record["summary"] = compare(records, order, args.axis, args.base_depth, args.base_threads, args.repeats)
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
