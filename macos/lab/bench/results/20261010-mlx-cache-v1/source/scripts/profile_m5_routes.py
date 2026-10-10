#!/usr/bin/env python3
"""Prepare expert-reuse and split-operation diagnostics without changing existing engines."""
import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import socket
import statistics
import subprocess
import threading
import psutil

from benchmark import Monitor, host_snapshot, wait_ready
from benchmark_tuning import watch_resources
from check_memory import assert_no_model_server, snapshot
from engines import ENGINES, engine_binary, sha256, verify_engine
from lab import ROOT, request, server_command
from metal_environment import configure
from profile_m5 import parse as parse_buffers
from profile_m5_phases import parse as parse_phases, union_ms
from model_provenance import verify_models, assert_unchanged

SOURCE = ROOT / "native/m5_eval_server.cpp"
WORK = ROOT / "bench/runtime/m5-eval"
BINARY = WORK / "llama-server-m5-eval"
RECEIPT = WORK / "build.json"
METADATA = {"NONE", "VIEW", "RESHAPE", "PERMUTE", "TRANSPOSE"}


def build():
    required = {"baseline", "mtp-mma", "m5-trace"}
    pins = {n: verify_engine(n) for n in ENGINES if n in required or engine_binary(n).is_file()}
    native = ROOT / pins["m5-trace"]["directory"]
    cmake = native / "build/tools/server"
    flags = (cmake / "CMakeFiles/llama-server.dir/flags.make").read_text().splitlines()
    includes = shlex.split(next(s.split(" = ", 1)[1] for s in flags if s.startswith("CXX_INCLUDES = ")))
    defines = shlex.split(next(s.split(" = ", 1)[1] for s in flags if s.startswith("CXX_DEFINES = ")))
    link = shlex.split((cmake / "CMakeFiles/llama-server.dir/link.txt").read_text())
    libs = [(cmake / s).resolve() for s in link if s.endswith((".dylib", ".a"))]
    frameworks = [item for i, s in enumerate(link) if s == "-framework" for item in link[i:i+2]]
    command = ["/usr/bin/c++", "-O3", "-DNDEBUG", "-std=gnu++17", "-arch", "arm64", *defines, *includes,
        str(SOURCE), "-o", str(BINARY), "-Wl,-rpath," + str(native / "build/bin"), *map(str, libs), *frameworks]
    WORK.mkdir(parents=True, exist_ok=True)
    with (WORK / "build.log").open("w") as log:
        subprocess.run(command, stdout=log, stderr=log, check=True)
    with (WORK / "self-test.log").open("w") as log:
        subprocess.run([BINARY, "--self-test"], stdout=log, stderr=log, check=True)
        for case in ("cap", "overlap", "completion", "failed", "extraction"):
            result = subprocess.run([BINARY, "--self-test-failure", case], capture_output=True, text=True, timeout=10)
            log.write(f"Fatal-stop fixture {case}: exit {result.returncode}\n" + result.stdout + result.stderr)
            if result.returncode != 86 or '"fatal":true' not in result.stderr:
                raise RuntimeError(f"CPU-only fatal-stop fixture failed: {case}")
    if any(verify_engine(n) != p for n, p in pins.items()): raise RuntimeError("Existing engine changed during diagnostic build")
    record = {"schema": 1, "engine": pins["m5-trace"], "source_sha256": sha256(SOURCE), "binary_sha256": sha256(BINARY),
        "archives": {str(p.relative_to(ROOT)): sha256(p) for p in libs if p.suffix == ".a"}, "command": command,
        "dynamic_libraries": {str(p): sha256(p) for p in libs if p.suffix == ".dylib"},
        "build_toolchain": {"compiler": subprocess.check_output(["/usr/bin/c++","--version"],text=True).strip(),
                            "sdk": subprocess.check_output(["xcrun","--show-sdk-version"],text=True).strip()},
        "scope": "Diagnostic entry point around existing server libraries. Reads routing IDs or deliberately splits scheduled nodes with an evaluation callback. No vendor, shader, model, launcher or memory-limit changes."}
    RECEIPT.write_text(json.dumps(record, indent=2) + "\n")
    print("Diagnostic build and CPU-only strided-routing self-test passed", flush=True)
    return record


def verify():
    r = json.loads(RECEIPT.read_text())
    if (verify_engine("m5-trace") != r["engine"] or sha256(SOURCE) != r["source_sha256"] or
        sha256(BINARY) != r["binary_sha256"] or any(sha256(ROOT / p) != h for p, h in r["archives"].items()) or
        not r.get("dynamic_libraries") or any(sha256(Path(p)) != h for p,h in r["dynamic_libraries"].items())):
        raise RuntimeError("Diagnostic build provenance changed")
    return r


def markers(text, name):
    return [json.loads(s.split(name + " ", 1)[1]) for s in text.splitlines() if name + " " in s]


def reuse(ids):
    sets = [set(row) for row in ids]
    if not 1 <= len(sets) <= 6 or any(len(row) != 10 or len(s) != 10 or any(type(i) is not int or not 0 <= i < 512 for i in row) for row, s in zip(ids, sets)):
        raise ValueError("Expert routing IDs, rows or uniqueness are invalid")
    counts = Counter(i for row in ids for i in row)
    assignments = 10 * len(ids)
    return {"unique_experts": len(counts), "assignments": assignments,
        "assignments_per_active_expert": assignments / len(counts),
        "reused_assignment_percent": 100 * (assignments-len(counts)) / assignments,
        "assignments_in_experts_with_two_or_more_tokens_percent": 100 * sum(c for c in counts.values() if c >= 2) / assignments,
        "expert_token_count_histogram": dict(sorted(Counter(counts.values()).items())),
        "adjacent_shared_experts": [len(a & b) for a, b in zip(sets, sets[1:])]}


def parse(text, mode):
    config = markers(text, "M5_EVAL_CONFIG")
    if len(config) != 1 or config[0]["mode"] != mode or markers(text, "M5_EVAL_ERROR"):
        raise ValueError("Diagnostic mode or callback error")
    begins, ends, routes = [markers(text, m) for m in ("M5_EVAL_BEGIN", "M5_EVAL_END", "M5_ROUTE")]
    end_by = {r["serial"]: r for r in ends}
    if len(end_by) != len(ends) or sorted(end_by) != list(range(1, len(begins)+1)) or [b["serial"] for b in begins] != list(range(1, len(begins)+1)):
        raise ValueError("Missing, duplicated or reordered callback intervals")
    intervals = []
    previous = 0
    for begin in begins:
        end = end_by[begin["serial"]]["cpu_us"]
        if not previous <= begin["cpu_us"] < end: raise ValueError("Callback intervals overlap or have invalid time")
        intervals.append({**begin, "end_cpu_us": end}); previous = end
    empty_by_serial = defaultdict(Counter)
    for e in markers(text,"M5_EVAL_EMPTY"):
        serial, dims = e["serial"], e["dst"]
        if (type(serial) is not int or not 1 <= serial <= len(intervals) or len(dims) != 4 or
            any(type(n) is not int or n < 0 for n in dims) or 0 not in dims or e["op"] in METADATA or
            not (intervals[serial-2]["end_cpu_us"] if serial > 1 else 0) <= e["cpu_us"] <= intervals[serial-1]["cpu_us"]):
            raise ValueError("Invalid empty-compute geometry or scheduling boundary")
        empty_by_serial[serial][e["op"]] += 1
    route_serials = set()
    for r in routes:
        if type(r["serial"]) is not int or not 1 <= r["serial"] <= len(begins) or r["serial"] in route_serials:
            raise ValueError("Routing event has no unique callback interval")
        route_serials.add(r["serial"])
        b = intervals[r["serial"]-1]
        layer = r["layer"]
        if (type(layer) is not int or not 0 <= layer <= 48 or r["role"] != ("helper" if layer == 48 else "target") or
            b["name"] != f"ffn_moe_topk-{layer}" or not b["cpu_us"] <= r["cpu_us"] <= b["end_cpu_us"] or
            r["row_stride_bytes"] != 2048 or b["dst"] != [10, r["rows"], 1, 1] or len(r["ids"]) != r["rows"]):
            raise ValueError("Routing role, geometry, stride or interval differs")
        r["reuse"] = reuse(r["ids"])
    expected_routes = {b["serial"] for b in begins if b["name"].startswith("ffn_moe_topk-") and b["dst"][1] <= 6}
    if route_serials != expected_routes: raise ValueError("Missing expert ID capture")
    if mode == "control" and begins: raise ValueError("Control unexpectedly installs a callback")
    buffers = parse_buffers(text)
    phase_events, request_ends = markers(text, "M5_PHASE"), markers(text, "M5_REQUEST_END")
    tasks = list(dict.fromkeys(e["task"] for e in phase_events))
    requests = []
    for task in tasks:
        phases = [p for p in phase_events if p["task"] == task]
        finished = [e["cpu_us"] for e in request_ends if e["task"] == task]
        generation = [p["cpu_us"] for p in phases if p["phase"] == "generation"]
        if not phases or phases[0]["phase"] != "prompt" or not generation or len(finished) != 1 or generation[0] >= finished[0]:
            raise ValueError("Missing request phases or completion")
        low, high = generation[0], finished[0]
        selected = [r for r in routes if low <= r["cpu_us"] < high]
        groups = defaultdict(list)
        for r in selected: groups[(r["role"], r["rows"])].append(r)
        summary = [{"role": role, "rows": rows, "layer_batches": len(values),
            "unique_experts_median": statistics.median(r["reuse"]["unique_experts"] for r in values),
            "assignments_per_active_expert_median": statistics.median(r["reuse"]["assignments_per_active_expert"] for r in values),
            "reused_assignment_percent_mean": statistics.mean(r["reuse"]["reused_assignment_percent"] for r in values),
            "assignments_in_reused_experts_percent_mean": statistics.mean(r["reuse"]["assignments_in_experts_with_two_or_more_tokens_percent"] for r in values),
            "layer_coverage": sorted({r["layer"] for r in values})} for (role, rows), values in sorted(groups.items())]
        measured_buffers = [b for b in buffers["command_buffers"] if low <= b["submit_cpu_us"] < high]
        timed = [b for b in intervals if low <= b["cpu_us"] < high]
        attributed = []
        assigned = set()
        if mode == "split":
            # CPU monotonic boundaries attribute buffers by submission, independent of completion-log order.
            starts = [segment["cpu_us"] for segment in timed]
            by_segment = defaultdict(list)
            for b in measured_buffers:
                index = bisect_right(starts,b["submit_cpu_us"])-1
                if index >= 0 and b["submit_cpu_us"] < timed[index]["end_cpu_us"]:
                    by_segment[timed[index]["serial"]].append(b)
            for segment in timed:
                matches = by_segment[segment["serial"]]
                counts = Counter(op for b in matches for op, n in b["op_counts"].items() if op not in METADATA for _ in range(n))
                expected = Counter({segment["op"]:1}) + empty_by_serial[segment["serial"]]
                if matches and (counts and counts != expected):
                    raise ValueError("A split GPU interval contains another computational operation")
                keys = {(b["context"], b["graph"], b["cb"]) for b in matches}
                if keys & assigned: raise ValueError("GPU buffer assigned to multiple operation intervals")
                assigned.update(keys)
                if matches:
                    roles = {b["role"] for b in matches}
                    if len(roles) != 1: raise ValueError("Split interval crosses model roles")
                    attributed.append({"serial": segment["serial"], "role": next(iter(roles)), "name": segment["name"],
                        "empty_original_ops": dict(empty_by_serial[segment["serial"]]),
                        "op": segment["op"], "src0_type": segment.get("src0_type"), "src0": segment.get("src0"),
                        "dst": segment["dst"], "gpu_ms": union_ms([(b["gpu_start_s"], b["gpu_end_s"]) for b in matches]),
                        "gpu_buffers": len(matches)})
            uncovered = [b for b in measured_buffers if (b["context"], b["graph"], b["cb"]) not in assigned]
            if any(any(op not in METADATA for op in b["op_counts"]) for b in uncovered):
                raise ValueError("Computational GPU buffer lacks a callback interval")
        costs = defaultdict(list)
        for a in attributed:
            family = "expert-matrix" if a["op"] == "MUL_MAT_ID" else "vocabulary" if a["op"] == "MUL_MAT" and a["src0"] == [2560,248320,1,1] else "other-matrix" if a["op"] == "MUL_MAT" else "attention/state" if a["op"] in ("FLASH_ATTN_EXT", "SSM_CONV", "SSM_SCAN", "GATED_DELTA_NET", "GATED_LINEAR_ATTN", "RWKV_WKV6", "RWKV_WKV7") else "other-ops"
            costs[(a["role"], family, a["op"])].append(a["gpu_ms"])
        requests.append({"task": task, "expert_reuse": summary,
            "raw_generation_gpu_buffers": sum(low <= b["submit_cpu_us"] < high for b in buffers["raw_command_buffers"]),
            "untimed_metadata_buffers": sum(low <= b["submit_cpu_us"] < high for b in buffers["untimed_completed_buffers"]),
            "split_costs": [{"role": role, "family": family, "op": op, "segments": len(values),
                "gpu_elapsed_sum_ms": sum(values), "gpu_elapsed_median_ms": statistics.median(values)} for (role,family,op),values in sorted(costs.items())],
            "split_attributed_buffers": len(assigned), "generation_gpu_buffers": len(measured_buffers), "segments": attributed})
    return {"requests": requests, "routing_events": routes, "callback_intervals": len(intervals),
        "limits": "Evaluation callbacks synchronize and split scheduled graphs. Split costs include command-buffer overhead and remove fusion across boundaries; they do not measure uninstrumented per-kernel cost, active utilization or TPS. Expert reuse is token assignments within each verification/layer batch, not across layers, requests or devices."}


def preflight(small=False, quiet=True):
    assert_no_model_server()
    info = snapshot()
    policy = json.loads((ROOT/"config/m5_future_plan.json").read_text())["comparison"]
    required = 4*1024**3 if small else policy["minimum_available_before_full_model_bytes"]
    info["required_available_bytes"] = required
    if info["memory"]["available"] < required:
        raise RuntimeError("Not enough available RAM for this diagnostic; no model was loaded")
    info["pressure_level"] = int(subprocess.check_output(["sysctl","-n","kern.memorystatus_vm_pressure_level"],text=True))
    if info["pressure_level"] != 1: raise RuntimeError("Memory pressure is not normal; no model was loaded")
    samples = [psutil.cpu_percent(interval=1) for _ in range(3)] if quiet and not small else [psutil.cpu_percent(interval=0.25)]
    info["host_cpu_percent_samples"] = samples
    info["quiet_host_required"] = quiet and not small
    if info["quiet_host_required"] and (max(samples) > 25 or statistics.mean(samples) > 15):
        raise RuntimeError(f"Host still busy ({samples} percent CPU); diagnostic deferred without stopping other work")
    return info


def run_pass(folder, depth, mode, small=False, output_budget=None):
    folder.mkdir()
    record = {"schema": 1, "kind": "m5-expert-reuse-and-split-diagnostic", "status": "running", "depth": depth,
        "mode": mode, "small_smoke": small, "requests": [], "cleanup_errors": [],
        "timings_excluded_from_speed_results": True}
    process = monitor = None
    done = threading.Event()
    watcher = threading.Thread(target=watch_resources, args=(folder / "resources.jsonl", done), daemon=True)
    def save(): (folder / "capture.json").write_text(json.dumps(record, indent=2)+"\n")
    save()
    try:
        record["preparation_preflight"] = preflight(small, quiet=False)
        pin = verify_engine("m5-trace"); receipt = verify()
        model_proof = verify_models(["small"] if small else ["flash","mtp_shared_packed_q3"])
        record.update(engine=pin, build=receipt, model_verification=model_proof, host_before=host_snapshot())
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
        command = server_command("small" if small else "flash", port, 2048 if small else 4096,
            512, 512, "none" if small else "draft-mtp", depth,
            draft_placement="mixed", draft_model="mtp_shared_packed_q3", engine="m5-trace",
            draft_threads=None if small else 8, draft_p_min=None if small else 0.0)
        if mode != "control": command[0] = str(BINARY)
        env, flags = configure(os.environ, "m5-trace", "on", profile=True)
        env["GGML_M5_LAB_EVAL_MODE"] = mode
        record.update(command=command, metal_environment=flags, diagnostic_mode_variable=mode)
        watcher.start()
        with (folder / "native.log").open("w") as log:
            record["launch_preflight"] = preflight(small)
            assert_unchanged(model_proof)
            launch_baseline = Monitor.baseline()
            save()
            process = subprocess.Popen(command, stdout=log, stderr=log, env=env)
            monitor = Monitor(process, folder / "memory.jsonl", 128*1024**2, 1024**3, baseline=launch_baseline)
            monitor.thread.start()
            base = f"http://127.0.0.1:{port}"
            record["ready_s"] = wait_ready(process, base)
            filler = "Explain how to compare AI inference speed and memory usage in plain language. " * 1000
            rendered = request(base, "/apply-template", {"messages": [{"role":"user","content":filler}],
                "chat_template_kwargs":{"enable_thinking":False}})["prompt"]
            tokens = request(base, "/tokenize", {"content":rendered,"add_special":False,"parse_special":True})["tokens"]
            output = output_budget if output_budget is not None else 16 if small or mode == "split" else 128
            lengths = [128, 256] if small else [512, 2048]
            for length, predict, warmup in ((lengths[0], 4 if small else 8, True),
                                           (lengths[0],output,False),(lengths[1],output,False)):
                prompt = tokens[:length-48]+tokens[-48:]
                response = request(base, "/completion", {"prompt":prompt,"n_predict":predict,"ignore_eos":True,
                    "temperature":0,"seed":1234,"cache_prompt":False,"return_tokens":True})
                if (response["timings"]["prompt_n"] != length or response["timings"]["predicted_n"] != predict or
                    len(response["tokens"]) != predict): raise RuntimeError("Diagnostic token counts differ")
                record["requests"].append({"prompt_tokens":length,"output_tokens":predict,"warmup":warmup,
                    "prompt_sha256":hashlib.sha256(json.dumps(prompt).encode()).hexdigest(),"response":response}); save()
                print(f"{mode}: depth{depth}, input{length}, output{predict} complete",flush=True)
        record["status"] = "completed"
    except BaseException as error:
        record.update(status="failed",error=f"{type(error).__name__}: {error}")
        raise
    finally:
        try:
            if process and process.poll() is None:
                process.terminate()
                try: process.wait(timeout=2)
                except subprocess.TimeoutExpired: process.kill();process.wait(timeout=2)
        except BaseException as error: record["cleanup_errors"].append(f"Child cleanup: {error}")
        try:
            if monitor: record["memory"] = monitor.finish()
        except BaseException as error: record["cleanup_errors"].append(f"Monitor cleanup: {error}")
        try:
            if process:
                record["child_exit_code"] = process.poll()
                record["child_exit_verified"] = record["child_exit_code"] is not None
                if not record["child_exit_verified"]:
                    record["cleanup_errors"].append("Owned child still running after cleanup")
        except BaseException as error: record["cleanup_errors"].append(f"Child exit verification: {error}")
        done.set()
        if watcher.ident is not None: watcher.join(timeout=5)
        try:
            assert_no_model_server(); record["servers_stopped"] = True
        except BaseException as error: record["cleanup_errors"].append(f"Stop verification: {error}")
        try:
            if record["cleanup_errors"]: raise RuntimeError("; ".join(record["cleanup_errors"]))
            if (folder/"native.log").exists():
                native_errors = markers((folder/"native.log").read_text(), "M5_EVAL_ERROR")
                if native_errors:
                    record["native_errors"] = native_errors
                    raise RuntimeError(f"Native diagnostic stopped: {native_errors}")
            if record["status"] == "completed":
                text = (folder / "native.log").read_text()
                record["phases"] = parse_phases(text, expected_requests=len(record["requests"]))
                if mode != "control": record["diagnostics"] = parse(text, mode)
                if (record["memory"].get("guard") or not record["memory"]["monitor_healthy"] or record["memory"]["swap_growth_bytes"] or
                    verify_engine("m5-trace") != pin or verify() != receipt):
                    raise RuntimeError("Diagnostic memory or provenance checks failed")
                assert_unchanged(model_proof)
                if not small and mode != "control":
                    for req in record["diagnostics"]["requests"][1:]:
                        main = [r for r in req["expert_reuse"] if r["role"] == "target"]
                        if not main or set(l for r in main for l in r["layer_coverage"]) != set(range(48)):
                            raise RuntimeError("Generation did not capture all 48 expert layers")
                        helper = [r for r in req["expert_reuse"] if r["role"] == "helper"]
                        if not helper or set(l for r in helper for l in r["layer_coverage"]) != {48}:
                            raise RuntimeError("Generation did not capture the verified helper layer48")
                record["status"] = "passed"
        except BaseException as error:
            record["status"] = "failed"
            record.setdefault("error",f"{type(error).__name__}: {error}")
        save(); print(f"Saved {folder / 'capture.json'}",flush=True)
    if record["status"] != "passed": raise RuntimeError(record.get("error","Capture failed"))
    return record


def execute(mode, depths, small=False):
    assert_no_model_server()
    before = preflight(small,quiet=False)
    pins = {n:verify_engine(n) for n in ENGINES}
    receipt = verify()
    folder = ROOT / "bench/features" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-m5-"+mode+"-batch")
    folder.mkdir()
    batch = {"schema":1,"status":"running","mode":mode,"small_smoke":small,"preflight":before,
        "build":receipt,"passes":[],"timings_excluded_from_speed_results":True}
    try:
        output = 16 if small or mode == "split" else 128
        for depth in depths:
            a = run_pass(folder / f"depth{depth}-control",depth,"control",small,output)
            b = run_pass(folder / f"depth{depth}-{mode}",depth,mode,small,output)
            assert_unchanged(a["model_verification"])
            if len(a["requests"]) != len(b["requests"]): raise RuntimeError("Request coverage differs")
            parity = [all(x[k] == y[k] for k in ("prompt_tokens","output_tokens","warmup","prompt_sha256")) and
                all(x["response"][k] == y["response"][k] for k in ("content","tokens")) for x,y in zip(a["requests"],b["requests"])]
            batch["passes"].append({"depth":depth,"control":f"depth{depth}-control/capture.json",
                "capture":f"depth{depth}-{mode}/capture.json","paired_outputs":len(parity),"paired_outputs_match":all(parity)})
            if not all(parity): raise RuntimeError("Instrumented greedy output differs from unchanged control")
        if any(verify_engine(n) != pin for n,pin in pins.items()): raise RuntimeError("An existing engine changed")
        batch["status"] = "passed"
    except BaseException as error:
        batch.update(status="failed",error=f"{type(error).__name__}: {error}"); raise
    finally:
        batch["postflight"] = snapshot()
        (folder / "batch.json").write_text(json.dumps(batch,indent=2)+"\n")
        print(f"Saved {folder / 'batch.json'}",flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--mode", choices=["routes","split"], default="routes")
    ap.add_argument("--depths",type=int,nargs="+",default=[3,4])
    ap.add_argument("--small-smoke",action="store_true",help="With --run, use the small model to test plumbing, not Flash expert reuse")
    args = ap.parse_args(argv)
    if not args.depths or len(set(args.depths)) != len(args.depths) or any(d not in (3,4) for d in args.depths):
        ap.error("Use distinct depths3/4")
    print("Plan: matched control, real expert ID capture at depths3/4, and bounded split-operation diagnostics. Default does not load a model.")
    if args.build or args.run:
        with (ROOT / "bench/.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.build: build()
            if args.run: execute(args.mode,args.depths,args.small_smoke)


if __name__ == "__main__":
    main()
