#!/usr/bin/env python3
"""Prepare a matched 4K/8K capacity trial; only --run loads a model."""
import argparse
from datetime import datetime, timezone
import fcntl
import json

from benchmark import run
from benchmark_m5 import settings as base_settings
from benchmark_metrics import change, metrics
from context_fixture import SEEDS
from engines import verify_engine
from lab import ROOT
from model_provenance import assert_unchanged, verify_models

ORDER = (4096, 8192, 8192, 4096)
SPEC = {"engine": "mtp-mma", "axis": "engine", "depth": 3}


def settings(context, label, repeats=2):
    args = base_settings(SPEC, "mtp-mma", label, repeats)
    args.context = context
    args.comparison_profile = str(context)
    args.retrieval_budget = 6144 if context == 8192 else None
    return args


def compare(records, repeats=2):
    if len(records) != 4: raise ValueError("Four ABBA launches are required")
    for record, context in zip(records, ORDER):
        if record["status"] != "passed" or record["settings"] != vars(settings(context, record["settings"]["label"], repeats)):
            raise ValueError("Failed pass or a setting outside context capacity changed")
        if any(record[k] != records[0][k] for k in ("selected_engine", "actual_sources", "runtime", "model", "draft_model", "metal_environment")):
            raise ValueError("Engine, model, helper or environment differs")
        memory = record["memory"]
        if memory.get("swap_growth_bytes") != 0 or memory.get("guard") or not memory.get("monitor_healthy") or not memory.get("child_exited"):
            raise ValueError("Missing/failed memory or child-teardown evidence")
        if not record["checks"] or not all(c["passed"] for c in record["checks"]): raise ValueError("Quality checks failed")
        if context == 8192:
            retrieval = record.get("retrieval_cases", [])
            if len(retrieval) != len(SEEDS) or [c["seed"] for c in retrieval] != list(SEEDS) or any(not c["passed"] or c["prompt_tokens"] != 6144 for c in retrieval):
                raise ValueError("Missing 6144-token retrieval evidence")
    retrieval_hashes = [[c["prompt_sha256"] for c in r["retrieval_cases"]] for r in records if r["settings"]["context"] == 8192]
    if retrieval_hashes[0] != retrieval_hashes[1]: raise ValueError("Long-context fixture token IDs changed between passes")
    keys = {(c["workload"], c["prompt_tokens"]) for c in records[0]["cases"]}
    if not keys or any({(c["workload"], c["prompt_tokens"]) for c in r["cases"]} != keys for r in records):
        raise ValueError("Matched workload coverage differs")
    rows = []
    for cached, workloads in ((False, sorted(keys)), (True, [("cached-ledger", n) for n in (512, 2048)])):
        for name, length in workloads:
            def select(record):
                return [c for c in record["cached_cases"] if not c["warmup"] and c["history_budget"] == length] if cached else [c for c in record["cases"] if (c["workload"], c["prompt_tokens"]) == (name, length)]
            groups = {str(n): [c for r in records if r["settings"]["context"] == n for c in select(r)] for n in (4096,8192)}
            if any(len(c) != repeats*2 for c in groups.values()): raise ValueError("Missing measured samples")
            if sorted(c["prompt_sha256"] for c in groups["4096"]) != sorted(c["prompt_sha256"] for c in groups["8192"]): raise ValueError("Prompt tokens changed")
            if not cached and any(c["output_tokens"] != 128 for g in groups.values() for c in g): raise ValueError("Output counts changed")
            rates = {key:metrics(cases,cached) for key,cases in groups.items()}
            controls = [metrics(select(r),cached) for r in records if r["settings"]["context"] == 4096]
            rows.append({"workload":name,"input_budget":length,"cached":cached,"profiles":rates,
                         "vs_4k":change(rates["4096"],rates["8192"]),"control_drift":change(*controls)})
    return rows


def execute(repeats):
    pin = verify_engine("mtp-mma")
    models = verify_models(["flash", "mtp_shared_packed_q3"])
    folder = ROOT/"bench/results"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-context-8k")
    folder.mkdir()
    record = {"schema":1,"status":"running","order":ORDER,"runs":[],"model_provenance":models,
              "limits":"6144-token recall is capacity-only; never compared with 4K throughput. No cache-precision change."}
    def save(): (folder/"comparison.json").write_text(json.dumps(record,indent=2,allow_nan=False)+"\n")
    save()
    try:
        for index, context in enumerate(ORDER,1):
            assert_unchanged(models)
            if verify_engine("mtp-mma") != pin: raise RuntimeError("Context engine changed")
            result = run(settings(context,f"context-{index}-{context}",repeats))
            record["runs"].append(result); save()
            if result["status"] != "passed" or result["selected_engine"] != pin or result.get("memory",{}).get("swap_growth_bytes") != 0:
                raise RuntimeError("Context trial failed its control, memory or quality checks")
            from memory_budget import allocations
            result["allocation_budget"] = allocations((ROOT/"bench/results"/result["run_id"]/"server.log").read_text())
            save()
        assert_unchanged(models)
        if verify_engine("mtp-mma") != pin: raise RuntimeError("Context engine changed")
        record["summary"] = compare(record["runs"],repeats)
        record["status"] = "passed"
    except BaseException as error:
        record.update(status="failed",error=f"{type(error).__name__}: {error}")
        raise
    finally: save()


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run",action="store_true"); ap.add_argument("--repeats",type=int,default=2)
    args=ap.parse_args(argv)
    if args.repeats < 1: ap.error("Use at least one measured repeat")
    print("Plan: 4K / 8K / 8K / 4K; identical 512/2048-token speed inputs; three separate 6144-token retrieval fixtures at 8K. F16 cache unchanged.")
    if not args.run:
        print("Testing is on hold. No model, GPU test or benchmark started."); return
    with (ROOT/"bench/.lock").open("w") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        execute(args.repeats)


if __name__ == "__main__": main()
