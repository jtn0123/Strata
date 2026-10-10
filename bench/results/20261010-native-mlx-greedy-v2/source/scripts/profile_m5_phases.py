#!/usr/bin/env python3
"""Separate request phases, model roles and matrix shapes; diagnostics require --run."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
import socket
import subprocess
import threading

import psutil
from benchmark import Monitor, host_snapshot, wait_ready
from benchmark_tuning import watch_resources
from check_memory import assert_no_model_server, snapshot
from engines import verify_engine
from lab import ROOT, request, server_command
from metal_environment import configure
from profile_m5 import parse as parse_buffers
from verify_m5 import check as check_math


def union_ms(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    return 1000 * sum(end - start for start, end in merged)


def parse(text, expected_requests=None):
    markers = {name: [] for name in ("M5_PHASE", "M5_REQUEST_END", "M5_SHAPES", "M5_HELPER", "M5_PROFILE")}
    for line in text.splitlines():
        for marker in markers:
            if marker + " " in line:
                markers[marker].append(json.loads(line.split(marker + " ", 1)[1]))
                break
    validated = parse_buffers(text)
    events = sorted(markers["M5_PHASE"], key=lambda e: e["cpu_us"])
    if not events or {e["slot"] for e in events} != {0} or any(e["phase"] not in ("prompt", "generation") for e in events):
        raise ValueError("Phase tracing requires one active slot and known phases")
    tasks = list(dict.fromkeys(e["task"] for e in events))
    if expected_requests is not None and len(tasks) != expected_requests:
        raise ValueError("Request count differs from the diagnostic plan")
    ends = markers["M5_REQUEST_END"]
    if len(ends) != len(tasks) or {e["task"] for e in ends} != set(tasks) or any(e["slot"] != 0 for e in ends):
        raise ValueError("Every request needs exactly one completion marker")
    shape_calls = {s["call"]: s for s in markers["M5_SHAPES"]}
    if len(shape_calls) != len(markers["M5_SHAPES"]):
        raise ValueError("Duplicate shape-call identifiers")
    seen = set()
    for b in markers["M5_PROFILE"]:
        key = (b["context"], b["graph"], b["cb"])
        if key in seen:
            raise ValueError("Duplicate GPU command-buffer record")
        seen.add(key)
        if b["call"] and (b["call"] not in shape_calls or any(b[k] != shape_calls[b["call"]][k] for k in ("role", "tokens"))):
            raise ValueError("GPU buffer and shape metadata disagree")
    output = []
    previous_end = None
    for task in tasks:
        phases = [e for e in events if e["task"] == task]
        start = phases[0]["cpu_us"]
        end = next(e["cpu_us"] for e in ends if e["task"] == task)
        if start >= end or any(e["cpu_us"] >= end for e in phases) or (previous_end is not None and start < previous_end):
            raise ValueError("Requests overlap or phase markers exceed their request")
        previous_end = end
        if phases[0]["phase"] != "prompt" or not any(e["phase"] == "generation" for e in phases):
            raise ValueError("Both prompt and generation phases are required")
        generation = next(e["cpu_us"] for e in phases if e["phase"] == "generation")
        if any(e["phase"] == "prompt" and e["cpu_us"] >= generation for e in phases):
            raise ValueError("Phase order changed within a request")
        phases_out = {}
        for phase, low, high in (("prompt", start, generation), ("generation", generation, end)):
            calls = {k: s for k, s in shape_calls.items() if low <= s["cpu_us"] < high}
            buffers = [b for b in validated["command_buffers"] if b["call"] in calls]
            submitted = [b for b in validated["command_buffers"] if low <= b["submit_cpu_us"] < high]
            if not buffers or len(buffers) != len(submitted) or any(not low <= b["submit_cpu_us"] < high for b in buffers):
                raise ValueError("Missing phase GPU work or submission outside its phase")
            by_role = {role: [b for b in buffers if b["role"] == role] for role in ("target", "helper")}
            if any(s["role"] not in by_role for s in calls.values()):
                raise ValueError("Unknown model role")
            gpu = lambda bs: union_ms([(b["gpu_start_s"], b["gpu_end_s"]) for b in bs])
            helpers = [h for h in markers["M5_HELPER"] if low <= h["cpu_start_us"] < high]
            if any(h["cpu_end_us"] < h["cpu_start_us"] or h["cpu_end_us"] > high for h in helpers):
                raise ValueError("Helper interval crosses its phase boundary")
            helper_ops = Counter()
            for h in helpers:
                helper_ops[h["operation"]] += (h["cpu_end_us"] - h["cpu_start_us"]) / 1000
            shapes = Counter()
            for s in calls.values():
                for shape in s["shapes"]:
                    if shape["count"] < 1 or any(len(shape[k]) != 4 or any(n < 1 for n in shape[k]) for k in ("src0", "src1", "dst")):
                        raise ValueError("Invalid matrix shape/count")
                    key = json.dumps({"role": s["role"], **{k: v for k, v in shape.items() if k != "count"}}, sort_keys=True)
                    shapes[key] += shape["count"]
            target, helper, total = gpu(by_role["target"]), gpu(by_role["helper"]), gpu(buffers)
            phases_out[phase] = {
                "raw_gpu_buffers": sum(low <= b["submit_cpu_us"] < high for b in validated["raw_command_buffers"]),
                "untimed_metadata_buffers": sum(low <= b["submit_cpu_us"] < high for b in validated["untimed_completed_buffers"]),
                "server_phase_wall_ms": (high - low) / 1000,
                "all_gpu_buffer_union_ms": total,
                "target_gpu_buffer_union_ms": target,
                "helper_gpu_buffer_union_ms": helper,
                "target_helper_overlap_ms": max(0, target + helper - total),
                "helper_wall_union_ms": union_ms([(h["cpu_start_us"] / 1e6, h["cpu_end_us"] / 1e6) for h in helpers]),
                "helper_operation_wall_ms": dict(helper_ops),
                "gpu_buffers": len(buffers), "llama_graph_calls": len(calls),
                "empty_original_matrix_nodes": sum(s.get("empty_matrix_nodes", 0) for s in calls.values()),
                "role_token_batches": {role: dict(Counter(s["tokens"] for s in calls.values() if s["role"] == role)) for role in by_role},
                "matrix_shapes": [{**json.loads(k), "original_node_appearances": v} for k, v in sorted(shapes.items())],
            }
        output.append({"task": task, "phases": phases_out})
    return {"requests": output, "raw_gpu_buffers": len(validated["raw_command_buffers"]),
            "timed_gpu_buffers": len(validated["command_buffers"]),
            "untimed_completed_buffers": len(validated["untimed_completed_buffers"]),
            "startup_shape_calls": sum(not any(e["cpu_us"] <= s["cpu_us"] < next(x["cpu_us"] for x in ends if x["task"] == e["task"]) for e in events) for s in shape_calls.values()),
            "note": "Command-buffer elapsed intervals are not active kernel time or accelerator occupancy. Phase membership uses native monotonic submission times and graph-call identifiers, not callback order or batch size. Shape counts describe original graph-node appearances before fusion. Helper wall time includes CPU work, GPU work and synchronization; it overlaps GPU intervals and must not be added to them. No CPU-only or SSD-wait duration is inferred from the gaps."}


def run_pass(depth, engine, enabled, math_proof):
    pin = verify_engine(engine)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = ROOT / "bench/features" / f"{stamp}-m5-phases-{depth}-{'trace' if enabled else 'control'}"
    folder.mkdir()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    command = server_command("flash", port, 4096, 512, 512, "draft-mtp", depth,
                             draft_placement="mixed", draft_model="mtp_shared_packed_q3", engine=engine,
                             draft_threads=8, draft_p_min=0.0)
    env, flags = configure(os.environ, engine, "on", profile=enabled)
    record = {"schema": 1, "kind": "m5-request-phase-diagnostics", "status": "running", "depth": depth,
              "engine": pin, "command": command, "metal_environment": flags, "math_check": math_proof,
              "host_before": host_snapshot(), "requests": [], "timings_excluded_from_speed_results": True}
    process = monitor = None
    done = threading.Event()
    watcher = threading.Thread(target=watch_resources, args=(folder / "resources.jsonl", done), daemon=True)
    watcher.start()
    try:
        assert_no_model_server()
        with (folder / "native.log").open("w") as log:
            launch_baseline = Monitor.baseline()
            process = subprocess.Popen(command, stdout=log, stderr=log, env=env)
            monitor = Monitor(process, folder / "memory.jsonl", 128 * 1024**2, 512 * 1024**2, baseline=launch_baseline)
            monitor.thread.start()
            base = f"http://127.0.0.1:{port}"
            record["ready_s"] = wait_ready(process, base)
            filler = "Explain how to compare AI inference speed and memory usage in plain language. " * 1000
            rendered = request(base, "/apply-template", {"messages": [{"role": "user", "content": filler}],
                "chat_template_kwargs": {"enable_thinking": False}})["prompt"]
            tokens = request(base, "/tokenize", {"content": rendered, "add_special": False, "parse_special": True})["tokens"]
            for length, predict, warmup in ((512, 16, True), (512, 128, False), (2048, 128, False)):
                prompt = tokens[:length - 48] + tokens[-48:]
                before = psutil.disk_io_counters()
                response = request(base, "/completion", {"prompt": prompt, "n_predict": predict, "ignore_eos": True,
                    "temperature": 0, "seed": 1234, "cache_prompt": False, "return_tokens": True})
                after = psutil.disk_io_counters()
                if response["timings"]["prompt_n"] != length or response["timings"]["predicted_n"] != predict or len(response["tokens"]) != predict:
                    raise RuntimeError("Diagnostic token counts differ from the plan")
                record["requests"].append({"prompt_tokens": length, "output_tokens": predict, "warmup": warmup,
                    "prompt_sha256": hashlib.sha256(json.dumps(prompt).encode()).hexdigest(), "response": response,
                    "system_disk_read_bytes": after.read_bytes - before.read_bytes if before and after else None,
                    "system_disk_write_bytes": after.write_bytes - before.write_bytes if before and after else None})
                print(f"depth={depth} {'trace' if enabled else 'control'} input={length} output={predict} done", flush=True)
        record["status"] = "completed"
    except BaseException as error:
        record.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if monitor:
            record["memory"] = monitor.finish()
        done.set()
        watcher.join(timeout=5)
        assert_no_model_server()
        record["servers_stopped"] = True
        try:
            if record["status"] == "completed":
                if enabled:
                    record["diagnostics"] = parse((folder / "native.log").read_text(), expected_requests=len(record["requests"]))
                if record["memory"].get("guard") or record["memory"]["swap_growth_bytes"] or verify_engine(engine) != pin:
                    raise RuntimeError("Diagnostic memory or source checks failed")
                record["status"] = "passed"
        except BaseException as error:
            record.update(status="failed", error=f"{type(error).__name__}: {error}")
        (folder / "profile.json").write_text(json.dumps(record, indent=2) + "\n")
        print(f"Saved {folder}", flush=True)
    if record["status"] != "passed":
        raise RuntimeError(record.get("error", "Phase diagnostics failed"))
    return str((folder / "profile.json").relative_to(ROOT))


def execute(depths):
    assert_no_model_server()
    pins = {name: verify_engine(name) for name in ("m5-lab", "m5-trace")}
    proofs = {name: check_math(name, "on") for name in pins}
    record = {"schema": 1, "kind": "m5-phase-profile-batch", "status": "running", "math_checks": proofs,
              "timings_excluded_from_speed_results": True, "passes": [], "preflight": snapshot()}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "bench/features" / f"{stamp}-m5-phase-profile-batch.json"
    try:
        for depth in depths:
            control = run_pass(depth, "m5-lab", False, proofs["m5-lab"])
            trace = run_pass(depth, "m5-trace", True, proofs["m5-trace"])
            a, b = [json.loads((ROOT / p).read_text()) for p in (control, trace)]
            pairs = zip(a["requests"], b["requests"])
            parity = [all(x[k] == y[k] for k in ("prompt_sha256", "prompt_tokens", "output_tokens", "warmup")) and
                      all(x["response"][k] == y["response"][k] for k in ("content", "tokens")) for x, y in pairs]
            record["passes"].append({"depth": depth, "control": control, "trace": trace,
                                      "paired_outputs": len(parity), "paired_outputs_match": all(parity)})
            if len(parity) != 3 or not all(parity):
                raise RuntimeError("Diagnostic output differs from the untouched control")
        if any(verify_engine(name) != pin for name, pin in pins.items()):
            raise RuntimeError("Engine changed during diagnostics")
        record["status"] = "passed"
    except BaseException as error:
        record.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        record["postflight"] = snapshot()
        output.write_text(json.dumps(record, indent=2) + "\n")
        print(f"Saved {output}", flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--depths", type=int, nargs="+", default=[3, 4])
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args(argv)
    if not args.depths or len(set(args.depths)) != len(args.depths) or any(not 1 <= d <= 6 for d in args.depths):
        ap.error("Use distinct depths 1-6")
    print(f"Phase diagnostic plan: depths {args.depths}; untouched control then labeled trace; 512/2048 input, 128 output.")
    if not args.run:
        print("Plan only. No GPU work or model load. Add --run to execute.")
        return
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        execute(args.depths)


if __name__ == "__main__":
    main()
