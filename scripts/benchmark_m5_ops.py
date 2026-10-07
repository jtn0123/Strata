#!/usr/bin/env python3
"""Measure exact generation matrix shapes without editing the engine or model."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import threading
import time

from benchmark import Monitor, host_snapshot
from benchmark_tuning import watch_resources
from check_memory import assert_no_model_server, snapshot
from engines import ENGINES, sha256, verify_engine
from lab import ROOT
from metal_environment import configure
from profile_m5 import parse as parse_buffers

FAMILIES = ("expert-down", "expert-up", "head")
SOURCE = ROOT / "native/m5_operation_probe.cpp"
WORK = ROOT / "bench/runtime/m5-ops"
BINARY = WORK / "probe"
RECEIPT = WORK / "build.json"


def build():
    pin = verify_engine("m5-lab")
    native = ROOT / pin["directory"]
    includes = ("include", "ggml/include", "common", "vendor")
    defines = ("GGML_BACKEND_SHARED", "GGML_SHARED", "GGML_USE_BLAS", "GGML_USE_CPU", "GGML_USE_METAL", "LLAMA_SHARED", "LLAMA_SUBPROCESS")
    libs = [native / "build/bin" / name for name in ("libllama-common.0.6.0.dylib", "libllama.0.6.0.dylib",
        "libggml.0.26.0.dylib", "libggml-cpu.0.26.0.dylib", "libggml-blas.0.26.0.dylib",
        "libggml-metal.0.26.0.dylib", "libggml-base.0.26.0.dylib")]
    libs.append(native / "build/common/libllama-common-base.a")
    command = ["/usr/bin/c++", "-O3", "-DNDEBUG", "-std=gnu++17", "-arch", "arm64",
        *["-D" + d for d in defines], *["-I" + str(native / p) for p in includes],
        '-DM5_NATIVE_TEST_SOURCE="' + str(native / "tests/test-backend-ops.cpp") + '"',
        str(SOURCE), "-o", str(BINARY), "-Wl,-rpath," + str(native / "build/bin"), *map(str, libs)]
    WORK.mkdir(parents=True, exist_ok=True)
    with (WORK / "build.log").open("w") as log:
        subprocess.run(command, stdout=log, stderr=log, check=True)
    subprocess.run([BINARY, "--self-test"], check=True)
    record = {"schema": 1, "engine": pin, "source_sha256": sha256(SOURCE),
        "native_tester_sha256": sha256(native / "tests/test-backend-ops.cpp"),
        "common_archive_sha256": sha256(libs[-1]), "binary_sha256": sha256(BINARY), "command": command,
        "scope": "New diagnostic executable links the existing pinned libraries. No engine, shader or model changes."}
    RECEIPT.write_text(json.dumps(record, indent=2) + "\n")
    return record


def verify():
    r = json.loads(RECEIPT.read_text())
    native = ROOT / r["engine"]["directory"]
    if (verify_engine("m5-lab") != r["engine"] or sha256(SOURCE) != r["source_sha256"] or
        sha256(BINARY) != r["binary_sha256"] or
        sha256(native / "tests/test-backend-ops.cpp") != r["native_tester_sha256"] or
        sha256(native / "build/common/libllama-common-base.a") != r["common_archive_sha256"]):
        raise RuntimeError("Diagnostic build provenance changed")
    return r


def records(text, marker):
    return [json.loads(line.split(marker + " ", 1)[1]) for line in text.splitlines() if marker + " " in line]


def expected_shape(family, rows):
    if family == "head":
        return {"type": "q5_K", "src0": [2560, 248320, 1, 1], "src1": [2560, rows, 1, 1], "dst": [248320, rows, 1, 1]}
    k, m, broadcast = (640, 2560, 10) if family == "expert-down" else (2560, 640, 1)
    return {"type": "q2_0", "src0": [k, m, 512, 1], "src1": [k, broadcast, rows, 1], "dst": [m, 10, rows, 1], "ids_row_stride_bytes": 2048}


def parse(text, family, rows, samples):
    calls, done = records(text, "M5_OP_CALL"), records(text, "M5_OP_DONE")
    if len(done) != 1 or done[0]["family"] != family or done[0]["samples"] != samples:
        raise ValueError("Missing or inconsistent completion")
    mapping = {c["graph"]: c for c in calls}
    if len(mapping) != len(calls) or sorted(mapping) != list(range(1, done[0]["graphs"] + 1)):
        raise ValueError("Missing or duplicate graph calls")
    buffers = parse_buffers(text)["command_buffers"]
    contexts = {b["context"] for b in buffers}
    if len(contexts) != 1:
        raise ValueError("One Metal context required for isolated operation attribution")
    by_graph = defaultdict(list)
    for b in buffers:
        if b["graph"] not in mapping:
            raise ValueError("GPU completion has no operation label")
        by_graph[b["graph"]].append(b)
    if set(by_graph) != set(mapping) or any(len(bs) != 1 for bs in by_graph.values()):
        raise ValueError("Each single-operation graph needs one completed buffer")
    groups = defaultdict(list)
    for graph, c in mapping.items():
        b = by_graph[graph][0]
        expected_op = "SQR" if c["phase"] == "cache-pressure" else "MUL_MAT" if family == "head" else "MUL_MAT_ID"
        operations = dict(b["op_counts"])
        views = operations.pop("VIEW", 0)
        if (c["family"] != family or views not in (0, 1) or operations != {expected_op: 1}
            or b["original_nodes"] != sum(b["op_counts"].values())):
            raise ValueError("The timed graph contains different or additional operations")
        if c["phase"] not in ("measure", "warmup", "cache-pressure"):
            raise ValueError("Unknown operation phase")
        if c["phase"] in ("measure", "warmup") and c["cache"] == "pressure-128MiB":
            previous = mapping.get(graph-1, {})
            if previous.get("phase") != "cache-pressure" or previous.get("rows") != c["rows"]:
                raise ValueError("Cache-pressure scenario was not preceded by its scratch operation")
        if c["phase"] == "measure":
            if c["rows"] not in rows or c["cache"] not in ("unflushed", "pressure-128MiB"):
                raise ValueError("Unexpected shape/cache scenario")
            groups[(c["rows"], c["routing"], c["cache"])].append({**c, "gpu_ms": b["gpu_ms"]})
    expected = {(n, route, cache) for n in rows
        for route in (["none"] if family == "head" else ["independent"] if n == 1 else ["independent", "shared"])
        for cache in ("unflushed", "pressure-128MiB")}
    if set(groups) != expected:
        raise ValueError("Not all planned operation scenarios completed")
    for n, route, cache in expected:
        warm = [c["sample"] for c in calls if c["phase"] == "warmup" and
                (c["rows"], c["routing"], c["cache"]) == (n, route, cache)]
        if sorted(warm) != [-3, -2, -1]:
            raise ValueError("Each scenario requires three excluded warm samples")
    shapes = records(text, "M5_OP_SHAPE")
    shape_keys = {(s["rows"], s["routing"]) for s in shapes}
    if len(shape_keys) != len(shapes) or shape_keys != {(n, route) for n, route, _ in expected}:
        raise ValueError("Actual shape inventory does not match the plan")
    for s in shapes:
        if s["family"] != family or any(s.get(k) != v for k, v in expected_shape(family, s["rows"]).items()):
            raise ValueError("Actual matrix geometry or routing stride differs")
    summaries = []
    for key in sorted(groups):
        data = sorted(groups[key], key=lambda c: c["sample"])
        if [c["sample"] for c in data] != list(range(samples)):
            raise ValueError("Missing or duplicate measured samples")
        n, route, cache = key
        for c in data:
            unique = c["unique_experts"]
            if ((family == "head" and unique != 0) or (family != "head" and not 10 <= unique <= 10*n) or
                (route == "shared" and unique != 10)):
                raise ValueError("Routing sample does not match its scenario")
        times = [c["gpu_ms"] for c in data]
        summaries.append({"family": family, "rows": n, "routing": route, "cache": cache, "samples": samples,
            "gpu_median_ms": statistics.median(times), "gpu_mean_ms": statistics.mean(times),
            "gpu_p10_ms": sorted(times)[int((samples-1)*0.1)], "gpu_p90_ms": sorted(times)[int((samples-1)*0.9)],
            "unique_experts_mean": statistics.mean(c["unique_experts"] for c in data)})
    compiled = re.findall(r"compiling pipeline: base = '([^']+)', name = '([^']+)'", text)
    if not compiled or not any("mul_" in base for base, _ in compiled):
        raise ValueError("Missing actual pipeline compilation evidence")
    return {"summary": summaries, "graphs": done[0]["graphs"], "weight_bytes": done[0]["weight_bytes"], "shapes": shapes,
        "pipeline_compilations": [{"base": base, "name": name} for base, name in compiled],
        "note": "One matrix operation per timed command buffer. Isolated elapsed GPU latency, not active utilization or model TPS. Cache pressure is an explicit 128 MiB SQR input, not a guaranteed cold cache. Routing is synthetic, not measured model routing."}


def child(folder, name, parts, profiling):
    env, flags = configure(os.environ, "m5-lab", "on", profile=profiling)
    command = [str(BINARY), *map(str, parts)]
    path = folder / (name + ".log")
    process = monitor = None
    with path.open("w") as log:
        process = subprocess.Popen(command, stdout=log, stderr=log, env=env)
        monitor = Monitor(process, folder / (name + "-memory.jsonl"), 128*1024**2, 1024**3)
        monitor.thread.start()
        try:
            process.wait(timeout=900)
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
            memory = monitor.finish()
    result = {"command": command, "metal_environment": flags, "exit_code": process.returncode,
        "memory": memory, "log": path.name}
    if process.returncode or memory.get("guard") or memory.get("swap_growth_bytes", 0):
        raise RuntimeError(f"Diagnostic process or memory check failed: {name}; see {path}")
    if "has tensor            = true" not in path.read_text():
        raise RuntimeError("Tensor API activation not verified")
    return result


def aggregate(passes):
    groups = defaultdict(list)
    for p in passes:
        for row in p["diagnostics"]["summary"]:
            groups[(row["family"], row["rows"], row["routing"], row["cache"])].append(row)
    if any(len(values) != len(passes)//len(FAMILIES) for values in groups.values()):
        raise ValueError("Every shape needs the same number of complete passes")
    return [{"family": k[0], "rows": k[1], "routing": k[2], "cache": k[3],
        "gpu_median_ms": statistics.median(v["gpu_median_ms"] for v in values),
        "pass_medians_ms": [v["gpu_median_ms"] for v in values],
        "pass_spread_percent": (max(v["gpu_median_ms"] for v in values) / min(v["gpu_median_ms"] for v in values)-1)*100,
        "unique_experts_mean": statistics.mean(v["unique_experts_mean"] for v in values)}
        for k, values in sorted(groups.items())]


def execute(rows, samples, passes, checks_only=False):
    assert_no_model_server()
    pins = {name: verify_engine(name) for name in ENGINES}
    receipt = verify()
    folder = ROOT / "bench/features" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-m5-operations")
    folder.mkdir()
    record = {"schema": 1, "kind": "m5-isolated-operation-latency", "status": "running", "build": receipt,
        "rows": rows, "samples": samples, "passes_per_family": 0 if checks_only else passes, "checks_only": checks_only,
        "runner_sha256": sha256(Path(__file__)), "preflight": snapshot(),
        "host": host_snapshot(), "checks": [], "passes": [], "models_loaded": False,
        "no_inference_gain_claim": True, "unchanged_engines": list(pins)}
    done = threading.Event()
    watcher = threading.Thread(target=watch_resources, args=(folder / "resources.jsonl", done), daemon=True)
    watcher.start()
    def save(): (folder / "operations.json").write_text(json.dumps(record, indent=2) + "\n")
    try:
        for family in FAMILIES:
            for n in sorted(rows):
                for route in (["independent", "shared"] if family != "head" and n > 1 else ["independent"]):
                    name = f"check-{family}-{n}-{route}"
                    check = child(folder, name, ["test", family, n, 1, route], False)
                    results = records((folder / check["log"]).read_text(), "M5_OP_CHECK")
                    if results != [{"family": family, "rows": n, "routing": route, "passed": True}]:
                        raise RuntimeError("Correctness result missing or mismatched")
                    record["checks"].append(check); save()
                    print(f"CPU-reference PASS {family} rows={n} {route}", flush=True)
        for p in range(0 if checks_only else passes):
            order = FAMILIES if p % 2 == 0 else tuple(reversed(FAMILIES))
            for family in order:
                ordered_rows = rows if p % 2 == 0 else list(reversed(rows))
                name = f"perf-{p+1}-{family}"
                result = child(folder, name, ["perf", family, ",".join(map(str, ordered_rows)), samples, "independent"], True)
                result["diagnostics"] = parse((folder / result["log"]).read_text(), family, rows, samples)
                record["passes"].append(result); save()
                print(f"GPU latency PASS {family}, pass {p+1}/{passes}", flush=True)
        record["summary"] = aggregate(record["passes"]) if record["passes"] else []
        if verify() != receipt or any(verify_engine(name) != pin for name, pin in pins.items()):
            raise RuntimeError("An existing engine or diagnostic binary changed")
        record["status"] = "passed"
    except BaseException as error:
        record.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        done.set(); watcher.join(timeout=5)
        record["postflight"] = snapshot()
        assert_no_model_server(); save()
        print(f"Saved {folder / 'operations.json'}", flush=True)
    return folder


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--checks-only", action="store_true", help="With --run, check all selected shapes without latency measurements")
    ap.add_argument("--rows", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    ap.add_argument("--samples", type=int, default=40)
    ap.add_argument("--passes", type=int, default=3)
    args = ap.parse_args(argv)
    if args.checks_only and not args.run:
        ap.error("--checks-only requires --run")
    if (not args.rows or len(set(args.rows)) != len(args.rows) or any(not 1 <= n <= 5 for n in args.rows)
        or not 10 <= args.samples <= 200 or not 2 <= args.passes <= 4):
        ap.error("Use unique rows1-5,10-200 samples and2-4 passes")
    print(f"Operation plan: {FAMILIES}; rows {args.rows}; " +
          ("CPU-reference GPU checks only." if args.checks_only else f"{args.passes} passes, {args.samples} samples/scenario."))
    if not args.build and not args.run:
        print("Plan only. --build compiles diagnostics; --run performs GPU/CPU checks and latency measurements.")
        return
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.build: build()
        if args.run: execute(args.rows, args.samples, args.passes, args.checks_only)


if __name__ == "__main__":
    main()
