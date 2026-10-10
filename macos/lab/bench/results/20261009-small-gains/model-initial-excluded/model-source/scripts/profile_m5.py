#!/usr/bin/env python3
"""Plan GPU command-buffer and helper diagnostics; --run is required to load a model."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
import re
import socket
import subprocess

from benchmark import Monitor, wait_ready
from check_memory import assert_no_model_server
from engines import verify_engine
from lab import ROOT, request, server_command
from metal_environment import configure
from verify_m5 import check as check_math

METADATA_OPS = {"NONE", "VIEW", "RESHAPE", "PERMUTE", "TRANSPOSE"}

def parse(text):
    records = [json.loads(line.split("M5_PROFILE ", 1)[1]) for line in text.splitlines() if "M5_PROFILE " in line]
    untimed = [b for b in records if not b["valid"] and b.get("completed") and b["gpu_start_s"] == b["gpu_end_s"] == 0]
    if any("op_counts" not in b for b in untimed):
        raise ValueError("Untimed GPU buffer has no operation coverage evidence")
    if any(any(op not in METADATA_OPS and n > 0 for op, n in b["op_counts"].items()) for b in untimed):
        raise ValueError("Untimed computational GPU buffer: cost coverage is incomplete")
    buffers = [b for b in records if b not in untimed]
    if not buffers or any(not b["valid"] or b.get("completed", True) is not True or b["gpu_end_s"] <= b["gpu_start_s"] or
                          not all(math.isfinite(b[k]) for k in ("gpu_start_s", "gpu_end_s", "gpu_ms")) or
                          abs(b["gpu_ms"] - (b["gpu_end_s"] - b["gpu_start_s"])*1000) > 0.01 for b in buffers):
        raise ValueError("Missing or invalid GPU timestamp records")
    contexts = {}
    for buffer in buffers:
        item = contexts.setdefault(buffer["context"], {"buffers": 0, "elapsed_gpu_ms": 0, "original_graph_nodes": Counter()})
        item["buffers"] += 1
        item["elapsed_gpu_ms"] += buffer["gpu_ms"]
        item["original_graph_nodes"].update(buffer["op_counts"])
    intervals = sorted((b["gpu_start_s"], b["gpu_end_s"]) for b in buffers)
    merged = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    occupied = sum(end - start for start, end in merged)
    span = merged[-1][1] - merged[0][0]
    stats = re.findall(r"statistics\s+draft-mtp:.*dur\(b,g,a\) =\s*([\d.]+),\s*([\d.]+),\s*([\d.]+) ms", text)
    return {"command_buffers": buffers, "untimed_completed_buffers": untimed, "raw_command_buffers": records, "contexts": contexts,
            "command_buffer_interval_union_s": occupied, "first_to_last_buffer_span_s": span,
            "gaps_outside_recorded_buffers_s": max(0, span - occupied),
            "last_cumulative_helper_wall_ms": dict(zip(("begin", "draft", "accept"), map(float, stats[-1]))) if stats else None,
            "note": "Command-buffer elapsed intervals, not per-kernel compute time or AI-accelerator utilization. Graph node counts precede fusion. Gaps can contain CPU work, scheduling or unrecorded GPU activity. Helper wall time includes GPU/CPU synchronization and every diagnostic request, including warmup; do not add it to overlapping GPU intervals."}


def profile(depth, tensor_api, math_proof):
    engine = verify_engine("m5-lab")
    folder = ROOT / "bench/features" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-m5-profile-{depth}-{tensor_api}")
    folder.mkdir()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    command = server_command("flash", port, 4096, 512, 512, "draft-mtp", depth,
                             draft_placement="mixed", draft_model="mtp_shared_packed_q3",
                             engine="m5-lab", draft_threads=8, draft_p_min=0.0)
    env, flags = configure(os.environ, "m5-lab", tensor_api, profile=True)
    record = {"schema": 1, "kind": "m5-timing-diagnostics", "status": "running", "engine": engine,
              "command": command, "metal_environment": flags, "math_check": math_proof, "requests": [],
              "timings_excluded_from_speed_results": True}
    process, monitor = None, None
    log_path = folder / "native.log"
    try:
        assert_no_model_server()
        with log_path.open("w") as log:
            launch_baseline = Monitor.baseline()
            process = subprocess.Popen(command, stdout=log, stderr=log, env=env)
            monitor = Monitor(process, folder / "memory.jsonl", 128 * 1024**2, 512 * 1024**2, baseline=launch_baseline)
            monitor.thread.start()
            base = f"http://127.0.0.1:{port}"
            wait_ready(process, base)
            filler = "Explain how to compare AI inference speed and memory usage in plain language. " * 1000
            rendered = request(base, "/apply-template", {"messages": [{"role": "user", "content": filler}],
                "chat_template_kwargs": {"enable_thinking": False}})["prompt"]
            tokens = request(base, "/tokenize", {"content": rendered, "add_special": False, "parse_special": True})["tokens"]
            for length, predict, warmup in ((512, 16, True), (512, 32, False), (2048, 32, False)):
                prompt = tokens[:length - 48] + tokens[-48:]
                response = request(base, "/completion", {"prompt": prompt, "n_predict": predict, "ignore_eos": True,
                    "temperature": 0, "seed": 1234, "cache_prompt": False, "return_tokens": True})
                if response["timings"]["prompt_n"] != length or response["timings"]["predicted_n"] != predict:
                    raise RuntimeError("Diagnostic token counts differ from the plan")
                record["requests"].append({"prompt_tokens": length, "output_tokens": predict, "warmup": warmup,
                    "prompt_sha256": hashlib.sha256(json.dumps(prompt).encode()).hexdigest(), "response": response})
        record["status"] = "completed"
    except BaseException as error:
        record.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if monitor:
            record["memory"] = monitor.finish()
        record["servers_stopped"] = True
        try:
            if record["status"] == "completed":
                record["diagnostics"] = parse(log_path.read_text())
                if record["memory"].get("guard") or record["memory"].get("swap_growth_bytes", 0) or verify_engine("m5-lab") != engine:
                    raise RuntimeError("Diagnostic memory or source checks failed")
                record["status"] = "passed"
        except BaseException as error:
            record.update(status="failed", error=f"{type(error).__name__}: {error}")
        (folder / "profile.json").write_text(json.dumps(record, indent=2) + "\n")
        print(f"Saved {folder}", flush=True)
    if record["status"] != "passed":
        raise RuntimeError(record.get("error", "M5 diagnostics failed"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--depths", type=int, nargs="+", default=[3, 4])
    ap.add_argument("--tensor-api", choices=["on", "off"], default="on")
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args(argv)
    if len(set(args.depths)) != len(args.depths) or any(not 1 <= d <= 6 for d in args.depths):
        ap.error("Use distinct depths 1-6")
    print(f"Diagnostic plan: depths {args.depths}, Tensor API {args.tensor_api}, 512/2048 input tokens, 32 output tokens.")
    if not args.run:
        print("Preparation only. No model load. Add --run after the testing go-ahead.")
        return
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert_no_model_server()
        proof = check_math("m5-lab", args.tensor_api)
        for depth in args.depths:
            profile(depth, args.tensor_api, proof)


if __name__ == "__main__":
    main()
