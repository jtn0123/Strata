#!/usr/bin/env python3
"""Project isolated matrix latencies onto saved generation inventories; never runs a model."""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path

from benchmark_m5_ops import expected_shape, FAMILIES
from engines import sha256


def project(operations, trace):
    if operations["status"] != "passed" or trace["status"] != "passed":
        raise ValueError("Only completed diagnostic records can be projected")
    if (len(trace["requests"]) != len(trace["diagnostics"]["requests"]) or
        not trace["requests"] or trace["requests"][0].get("warmup") is not True or
        any(r.get("warmup") is not False for r in trace["requests"][1:])):
        raise ValueError("Request inventories or excluded warmup differ")
    timings = {}
    for row in operations["summary"]:
        if row["cache"] != "pressure-128MiB":
            continue
        key = (row["family"], row["rows"], row["routing"])
        value = row["gpu_median_ms"]
        if key in timings or not math.isfinite(value) or value <= 0:
            raise ValueError("Missing, duplicate or invalid operation latency")
        timings[key] = value
    output = []
    # The first request is the excluded warmup. Prompt inventories are never used.
    for original, request in zip(trace["requests"][1:], trace["diagnostics"]["requests"][1:]):
        generation = request["phases"]["generation"]
        costs = {mode: defaultdict(float) for mode in ("shared", "independent")}
        counts = defaultdict(int)
        unmeasured = defaultdict(int)
        for shape in generation["matrix_shapes"]:
            if shape["backend"] != "MTL0" or shape["op"] not in ("MUL_MAT", "MUL_MAT_ID"):
                continue
            family = next((f for f in FAMILIES if
                shape["src0"] == expected_shape(f, 1)["src0"] and
                shape["type"] == expected_shape(f, 1)["type"] and
                shape["op"] == ("MUL_MAT" if f == "head" else "MUL_MAT_ID")), None)
            role = shape["role"]
            count = shape["original_node_appearances"]
            if not isinstance(count, int) or count < 1:
                raise ValueError("Invalid original matrix-node count")
            if family is None:
                unmeasured[role] += count
                continue
            if role not in ("target", "helper") or (family != "head" and role != "target"):
                raise ValueError("Operation family belongs to a different role")
            rows = shape["src1"][1 if family == "head" else 2]
            expected = expected_shape(family, rows)
            if any(shape[k] != expected[k] for k in ("src0", "src1", "dst", "type")):
                raise ValueError("Recorded matrix geometry differs from the measured operation")
            counts[role + "/" + family + "/rows" + str(rows)] += count
            for mode in costs:
                route = "none" if family == "head" else "independent" if rows == 1 else mode
                if (family, rows, route) not in timings:
                    raise ValueError("A generation shape has no measured latency")
                costs[mode][role + "/" + family] += count * timings[(family, rows, route)]
        if any(not any(k.startswith("target/" + f + "/") for k in counts) for f in FAMILIES):
            raise ValueError("Generation inventory lacks a required main-model family")
        scenarios = []
        for mode, values in costs.items():
            totals = {role: sum(v for k, v in values.items() if k.startswith(role + "/")) for role in ("target", "helper")}
            scenarios.append({"synthetic_routing": mode, "projected_family_ms": dict(values),
                "projected_role_ms": totals, "ratio_to_recorded_role_gpu_interval_percent": {
                    role: 100 * total / generation[role + "_gpu_buffer_union_ms"] for role, total in totals.items()}})
        output.append({"depth": trace["depth"], "input_tokens": original["prompt_tokens"],
            "task": request["task"], "original_node_counts": dict(counts),
            "unmeasured_gpu_matrix_node_appearances": dict(unmeasured),
            "recorded_target_gpu_buffer_ms": generation["target_gpu_buffer_union_ms"],
            "recorded_helper_gpu_buffer_ms": generation["helper_gpu_buffer_union_ms"], "scenarios": scenarios})
    if len(output) != len(trace["requests"]) - 1 or not output:
        raise ValueError("Trace request inventories are incomplete")
    return output


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--operations", type=Path, required=True)
    ap.add_argument("--trace", type=Path, nargs="+", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    operations = json.loads(args.operations.read_text())
    record = {"schema": 1, "kind": "m5-matrix-cost-projection", "sources": [
        {"path": str(p), "sha256": sha256(p)} for p in (args.operations, *args.trace)],
        "requests": [r for p in args.trace for r in project(operations, json.loads(p.read_text()))],
        "no_performance_gain_claim": True,
        "limits": "Synthetic routing and cache pressure, initialized synthetic weights, original pre-fusion node counts and isolated synchronization. These are scenario estimates, not bounds on actual routing cost, measured in-model per-kernel costs, active GPU utilization, SSD wait or a TPS prediction. Unmeasured matrices, attention/state operations and scheduling remain outside this model."}
    args.output.write_text(json.dumps(record, indent=2) + "\n")
    print(f"Saved {args.output}; offline projection only")


if __name__ == "__main__":
    main()
