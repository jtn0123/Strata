#!/usr/bin/env python3
"""Refresh today's unchanged writing preset; no candidate or gain is implied."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import threading

from benchmark import run
from benchmark_m5 import settings
from benchmark_tuning import watch_resources
from benchmark_vocab import metrics
from check_memory import assert_no_model_server, snapshot
from engines import verify_engine
from lab import ROOT

SPEC = {"engine": "mtp-mma", "axis": "engine", "depth": 3}


def acceptance_errors(result, args, pin):
    reasons = []
    if result["status"] != "passed": reasons.append("Benchmark checks did not pass")
    if result["settings"] != vars(args): reasons.append("Settings differ from the writing control")
    if result["selected_engine"] != pin: reasons.append("Engine provenance changed")
    if result["memory"].get("guard"): reasons.append("Memory guard stopped this launch")
    if result["memory"]["swap_growth_bytes"]:
        reasons.append(f"New swap grew {result['memory']['swap_growth_bytes']} bytes; clean baseline requires zero")
    return reasons


def execute():
    assert_no_model_server()
    pin = verify_engine("mtp-mma")
    folder = ROOT / "bench/features" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-m5-decision-baseline")
    folder.mkdir()
    record = {"schema": 1, "kind": "m5-current-writing-baseline", "status": "running", "preflight": snapshot(),
        "engine": pin, "runs": [], "run_acceptance": [], "no_candidate": True, "no_performance_gain_claim": True}
    done = threading.Event()
    watcher = threading.Thread(target=watch_resources, args=(folder / "resources.jsonl", done), daemon=True)
    watcher.start()
    def save(): (folder / "baseline.json").write_text(json.dumps(record, indent=2) + "\n")
    try:
        for index in (1, 2):
            args = settings(SPEC, "mtp-mma", f"m5-decision-baseline-{index}", 2)
            result = run(args)
            errors = acceptance_errors(result, args, pin)
            record["runs"].append(result)
            record["run_acceptance"].append({"run_id": result["run_id"], "accepted": not errors, "reasons": errors}); save()
            if errors:
                raise RuntimeError("; ".join(errors))
        first, second = record["runs"]
        for key in ("model", "runtime", "draft_model", "actual_sources"):
            if first[key] != second[key]: raise RuntimeError("Baseline sources changed")
        summary = []
        for name, length in sorted({(c["workload"], c["prompt_tokens"]) for c in first["cases"]}):
            selected = [[c for c in r["cases"] if (c["workload"], c["prompt_tokens"]) == (name, length)] for r in record["runs"]]
            if any(len(c) != 2 for c in selected) or sorted(c["prompt_sha256"] for c in selected[0]) != sorted(c["prompt_sha256"] for c in selected[1]):
                raise RuntimeError("Baseline sample or prompt mismatch")
            summary.append({"workload": name, "input_tokens": length, "samples": 4,
                "metrics": metrics(selected[0]+selected[1], False), "pass_metrics": [metrics(c, False) for c in selected]})
        record["summary"] = summary
        if verify_engine("mtp-mma") != pin: raise RuntimeError("Writing engine changed")
        record["status"] = "passed"
    except BaseException as error:
        record.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        done.set(); watcher.join(timeout=5)
        record["postflight"] = snapshot()
        assert_no_model_server(); save()
        print(f"Saved {folder / 'baseline.json'}", flush=True)
    return folder


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args(argv)
    print("Baseline plan: unchanged writing preset, depth3,8 helper workers, confidence0,Tensor API on; two launches, two measured repeats each,128 output tokens.")
    if not args.run:
        print("Plan only. --run loads the full model. No candidate, new default or performance gain is implied.")
        return
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        execute()


if __name__ == "__main__":
    main()
