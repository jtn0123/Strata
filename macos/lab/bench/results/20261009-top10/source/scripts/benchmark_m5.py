#!/usr/bin/env python3
"""Plan single-variable M5 experiments with fresh controls; inference requires --run."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import threading

from benchmark import run
from benchmark_shared import settings as shared_settings
from benchmark_tuning import watch_resources
from benchmark_vocab import change, metrics
from check_memory import assert_no_model_server, snapshot
from engines import verify_engine
from lab import ROOT
from metal_environment import configure
from verify_m5 import check as check_math


def experiments():
    completed = json.loads((ROOT / "config/m5_test_plan.json").read_text())["experiments"]
    pending = json.loads((ROOT / "config/m5_pending_speed_plan.json").read_text())["experiments"]
    return completed + pending


def plan(spec):
    half = [spec["control"], *spec["candidates"]]
    return half + half[::-1]


def settings(spec, value, label, repeats=2):
    args = shared_settings("shared-mixed", label, repeats=repeats)
    args.engine = spec["engine"]
    args.draft = spec["depth"]
    args.draft_threads = 8
    args.draft_p_min = 0.0
    args.tensor_api = "on"
    args.m5_tuning = "stock"
    args.swap_guard_bytes = 0 if spec["engine"] == "m5-top10" else 128 * 1024**2
    args.minimum_available_bytes = 1024**3
    args.require_quiet_host = True
    args.comparison_profile = str(value)
    args.predict = spec.get("predict", 128)
    if spec["axis"] not in ("engine", "draft", "draft_threads", "draft_p_min", "tensor_api", "m5_tuning"):
        raise ValueError("Unknown experiment axis")
    setattr(args, spec["axis"], value)
    if 'engine_for_value' in spec:
        if spec['axis'] != 'm5_tuning' or set(spec['engine_for_value']) != set(plan(spec)):
            raise ValueError('Explicit engine mapping must match every tuning profile')
        args.engine = spec['engine_for_value'][value]
    configure({}, args.engine, args.tensor_api, args.m5_tuning)
    return args


def compare(records, spec, repeats=2):
    order = plan(spec)
    if len(records) != len(order) or not records or any(r["status"] != "passed" for r in records):
        raise ValueError("Every planned pass must complete successfully")
    pins = {}
    keys = {(c["workload"], c["prompt_tokens"]) for c in records[0]["cases"]}
    if not keys:
        raise ValueError("No measured fresh workloads")
    for record, value in zip(records, order):
        expected = settings(spec, value, record["settings"]["label"], repeats)
        if record["settings"] != vars(expected):
            raise ValueError("A setting outside the experiment axis changed")
        if any(record[k] != records[0][k] for k in ("model", "runtime", "draft_model", "actual_sources")):
            raise ValueError("Model, helper or baseline sources changed")
        engine = record["selected_engine"]
        if engine.get("engine") != expected.engine:
            raise ValueError("Wrong engine selected")
        if expected.engine in pins and pins[expected.engine] != engine:
            raise ValueError("Engine source or binary changed")
        pins[expected.engine] = engine
        _, environment = configure({}, expected.engine, expected.tensor_api, expected.m5_tuning)
        if record.get("metal_environment") != environment:
            raise ValueError("Incorrect or unrecorded Metal environment")
        memory = record.get("memory", {})
        if ("swap_growth_bytes" not in memory or memory.get("guard") or memory["swap_growth_bytes"]
            or not memory.get("monitor_healthy") or not memory.get("child_exited")
            or not record["checks"] or not all(c["passed"] for c in record["checks"])):
            raise ValueError("Answer or memory checks failed")
        if {(c["workload"], c["prompt_tokens"]) for c in record["cases"]} != keys:
            raise ValueError("Fresh workload coverage changed")
        if {c["history_budget"] for c in record["cached_cases"] if not c["warmup"]} != {512, 2048}:
            raise ValueError("Cached workload coverage changed")
    values = list(dict.fromkeys(map(str, order)))
    control = str(spec["control"])
    rows = []
    for cached, workloads in ((False, sorted(keys)), (True, [("cached-ledger", n) for n in (512, 2048)])):
        for name, length in workloads:
            def select(record):
                return [c for c in record["cached_cases"] if not c["warmup"] and c["history_budget"] == length] if cached else [
                    c for c in record["cases"] if (c["workload"], c["prompt_tokens"]) == (name, length)]
            groups = {p: [c for r in records if r["settings"]["comparison_profile"] == p for c in select(r)] for p in values}
            if any(len(cases) != repeats * 2 for cases in groups.values()):
                raise ValueError("Missing measured cases")
            hashes = {p: sorted(c["prompt_sha256"] for c in cases) for p, cases in groups.items()}
            if any(hashes[p] != hashes[control] for p in values):
                raise ValueError("Prompt tokens differ")
            if not cached and any(c["output_tokens"] != records[0]["settings"]["predict"] for cases in groups.values() for c in cases):
                raise ValueError("Fixed output counts differ")
            rates = {p: metrics(cases, cached) for p, cases in groups.items()}
            controls = [metrics(select(r), cached) for r in records if r["settings"]["comparison_profile"] == control]
            rows.append({"workload": name, "input_budget": length, "cached": cached, "profiles": rates,
                         "vs_control": {p: change(rates[control], rates[p]) for p in values},
                         "control_passes": controls, "control_drift": change(*controls)})
    return rows


def render(record):
    lines = ["# M5 experiment: " + record["experiment"]["id"], "", "Status: " + record["status"], "",
             "Only the configured axis changes. Fresh controls bracket candidates; historical suites are not pooled.",
             f"{record['experiment'].get('predict', 128)} output tokens for fresh workloads; short cached replies stop normally. Tensor API mode is an API-path comparison, not an accelerator-utilization counter.", "",
             "| Workload / input | Setting | TPS | Output gain | Reply quicker | First token quicker | Control drift |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for row in record.get("summary", []):
        for value, rate in row["profiles"].items():
            delta = row["vs_control"][value]
            lines.append(f"| {row['workload']} / {row['input_budget']} | {value} | {rate['generation_tok_s']:.3f} | "
                         f"{delta['generation_increase_percent']:+.2f}% | {delta['total_time_reduction_percent']:+.2f}% | "
                         f"{delta['ttft_reduction_percent']:+.2f}% | {row['control_drift']['generation_increase_percent']:+.2f}% |")
    lines += ["", "Raw runs", ""]
    for item in record["runs"]:
        lines.append(f"- [{item['value']} / {item['run_id']}](../{item['run_id']}/result.json)")
    if record.get("error"):
        lines += ["", record["error"]]
    return "\n".join(lines) + "\n"


def execute(spec, repeats, resume=None, before_pass=None, after_pass=None):
    assert_no_model_server()
    folder = resume.parent if resume else ROOT / "bench/results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-m5-" + spec["id"])
    if not resume: folder.mkdir()
    record = json.loads(resume.read_text()) if resume else {"schema": 1, "kind": "m5-single-axis-comparison", "experiment": spec, "order": plan(spec),
              "status": "running", "repeats": repeats, "runs": [], "math_checks": [], "preflight": snapshot()}
    if record['experiment'] != spec or record['repeats'] != repeats or record['order'] != plan(spec):
        raise ValueError('Resume experiment/settings differ')
    records, pins = [], {}
    if resume:
        for entry, value in zip(record['runs'], plan(spec)):
            result = json.loads((ROOT/'bench/results'/entry['run_id']/'result.json').read_text())
            expected = settings(spec,value,result['settings']['label'],repeats)
            if (entry['value'] != value or result['status'] != 'passed' or result['settings'] != vars(expected)
                    or result['selected_engine'] != verify_engine(expected.engine) or result['memory']['swap_growth_bytes']):
                raise ValueError('Resume requires unchanged completed prefix runs')
            records.append(result)
        record['resumed_utc'] = datetime.now(timezone.utc).isoformat()
        record['previous_error'] = record.pop('error', None)
        record['status'] = 'running'
    done = threading.Event()
    watcher = threading.Thread(target=watch_resources, args=(folder / "resources.jsonl", done), daemon=True)
    watcher.start()
    try:
        combos = {(a.engine, a.tensor_api, a.m5_tuning) for a in
                  (settings(spec, v, "preflight", repeats) for v in plan(spec))}
        for engine, tensor, tuning in sorted(combos):
            pin = verify_engine(engine)
            if engine in pins and pins[engine] != pin:
                raise RuntimeError("Engine changed between prerequisite checks")
            pins[engine] = pin
            record["math_checks"].append(check_math(engine, tensor, tuning))
        for index, value in enumerate(plan(spec), 1):
            if index <= len(records): continue
            assert_no_model_server()
            if before_pass:
                record.setdefault('headroom_waits',[]).append(before_pass())
            args = settings(spec, value, f"m5-{spec['id']}-{index}-{value}", repeats)
            result = run(args)
            records.append(result)
            record["runs"].append({"value": value, "run_id": result["run_id"], "status": result["status"]})
            (folder / "comparison.json").write_text(json.dumps(record, indent=2) + "\n")
            if result["status"] != "passed" or result["selected_engine"] != pins[args.engine] or result.get("memory", {}).get("swap_growth_bytes", 0):
                raise RuntimeError("Answer, source or no-new-swap check failed; experiment stopped")
            if after_pass:
                after_pass(result, value)
            if "borrowing target embeddings/output; draft KV remains separate" not in (ROOT / "bench/results" / result["run_id"] / "server.log").read_text():
                raise RuntimeError("Shared helper did not activate")
        record["summary"] = compare(records, spec, repeats)
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
    return folder


def main(argv=None):
    specs = experiments()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--experiment", choices=[s["id"] for s in specs], nargs="+")
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args(argv)
    if args.repeats < 1 or (args.experiment and len(set(args.experiment)) != len(args.experiment)):
        ap.error("Use at least one repeat and distinct experiment names")
    selected = [s for s in specs if args.experiment is None or s["id"] in args.experiment]
    for spec in selected:
        print(f"{spec['id']}: {spec['axis']} {plan(spec)}")
    if not args.run:
        print("Preparation only. No GPU test or model load. Add --run after the user's testing go-ahead and a quiet-host preflight.")
        return
    if args.experiment is None:
        ap.error("Select --experiment explicitly for a testing run")
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for spec in selected:
            execute(spec, args.repeats)


if __name__ == "__main__":
    main()
