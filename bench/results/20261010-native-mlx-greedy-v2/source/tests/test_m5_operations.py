"""Prevent misleading geometry, GPU attribution and synthetic benchmark results."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import benchmark_m5_ops as ops
import analyze_m5_operations as analysis
import benchmark_m5_decision_baseline as baseline


class OperationTests(unittest.TestCase):
    def fixture(self):
        family = "expert-down"
        d = {"M5_OP_SHAPE": [{"family": family, "rows": 1, "routing": "independent", **ops.expected_shape(family, 1)}],
             "M5_OP_CALL": [], "M5_PROFILE": [], "M5_OP_DONE": []}
        def add(c, operation):
            graph = len(d["M5_OP_CALL"]) + 1
            d["M5_OP_CALL"].append({"family": family, "graph": graph, "rows": 1, **c})
            counts = {operation: 1}
            if operation == "MUL_MAT_ID": counts["VIEW"] = 1
            d["M5_PROFILE"].append({"context": "ctx", "graph": graph, "cb": 2,
                "original_nodes": sum(counts.values()), "gpu_start_s": graph, "gpu_end_s": graph+0.0001,
                "gpu_ms": 0.1, "valid": True, "completed": True, "op_counts": counts})
        for cache in ("unflushed", "pressure-128MiB"):
            for sample in range(-3, 2):
                if cache != "unflushed": add({"phase": "cache-pressure"}, "SQR")
                add({"phase": "warmup" if sample < 0 else "measure", "sample": sample,
                     "routing": "independent", "cache": cache, "unique_experts": 10}, "MUL_MAT_ID")
        d["M5_OP_DONE"] = [{"family": family, "samples": 2, "graphs": len(d["M5_OP_CALL"]), "weight_bytes": 1}]
        return d

    def render(self, data):
        # Completion order must not determine sample attribution.
        return "\n".join(marker+" "+json.dumps(row) for marker, rows in data.items() for row in reversed(rows)) + \
            "\ncompiling pipeline: base = 'kernel_mul_mv_id_q2_0_f32', name = 'kernel_mul_mv_id_q2_0_f32_nsg=2'\n"

    def test_isolated_matrix_buffers_exclude_scratch_and_warmup(self):
        result = ops.parse(self.render(self.fixture()), "expert-down", [1], 2)
        self.assertEqual(len(result["summary"]), 2)
        self.assertEqual([s["gpu_median_ms"] for s in result["summary"]], [0.1, 0.1])
        self.assertEqual([s["samples"] for s in result["summary"]], [2, 2])

    def test_ambiguous_or_incomplete_measurements_are_rejected(self):
        changes = [
            lambda d: d["M5_OP_DONE"].clear(),
            lambda d: d["M5_OP_CALL"][0].update(graph=2),
            lambda d: d["M5_PROFILE"].pop(),
            lambda d: d["M5_PROFILE"].append(copy.deepcopy(d["M5_PROFILE"][0])),
            lambda d: d["M5_PROFILE"][0].update(context="other"),
            lambda d: d["M5_PROFILE"][0].update(op_counts={"MUL_MAT_ID": 1, "MUL_MAT": 1}),
            lambda d: d["M5_OP_SHAPE"][0].update(src1=[640, 1, 1, 1]),
            lambda d: d["M5_OP_SHAPE"][0].update(ids_row_stride_bytes=40),
            lambda d: d["M5_OP_CALL"][0].update(phase="measure"),
            lambda d: d["M5_OP_CALL"][5].update(phase="warmup", sample=-9, routing="independent", cache="unflushed"),
            lambda d: d["M5_OP_CALL"][-1].update(unique_experts=11),
        ]
        for change in changes:
            d = self.fixture(); change(d)
            with self.subTest(change=change), self.assertRaises(ValueError):
                ops.parse(self.render(d), "expert-down", [1], 2)

    def test_actual_expert_and_head_geometries_are_distinct(self):
        self.assertEqual(ops.expected_shape("expert-down", 4)["src1"], [640, 10, 4, 1])
        self.assertEqual(ops.expected_shape("expert-up", 5)["src1"], [2560, 1, 5, 1])
        self.assertEqual(ops.expected_shape("head", 1)["src0"], [2560, 248320, 1, 1])

    def test_plan_does_not_build_or_run_gpu(self):
        with patch.object(ops, "build") as build, patch.object(ops, "execute") as execute:
            ops.main([])
            build.assert_not_called(); execute.assert_not_called()
        with patch.object(baseline, "execute") as execute:
            baseline.main([])
            execute.assert_not_called()

    def projection_fixture(self):
        op_rows, shapes = [], []
        for family in ops.FAMILIES:
            routes = ("none",) if family == "head" else ("shared", "independent")
            for route in routes:
                op_rows.append({"family": family, "rows": 4, "routing": route,
                    "cache": "pressure-128MiB", "gpu_median_ms": 2 if family == "head" else 0.1 if route == "shared" else 0.2})
            geometry = ops.expected_shape(family, 4)
            geometry.pop("ids_row_stride_bytes", None)
            shapes.append({**geometry, "backend": "MTL0", "role": "target",
                "op": "MUL_MAT" if family == "head" else "MUL_MAT_ID",
                "original_node_appearances": 96 if family == "expert-up" else 48 if family == "expert-down" else 1})
        # A CPU matrix with the same geometry must not be attributed to Metal.
        shapes.append({**shapes[0], "backend": "CPU", "role": "helper", "original_node_appearances": 900})
        generation = {"matrix_shapes": shapes, "target_gpu_buffer_union_ms": 50, "helper_gpu_buffer_union_ms": 5}
        return ({"status": "passed", "summary": op_rows}, {"status": "passed", "depth": 3,
            "requests": [{"warmup": True}, {"prompt_tokens": 512, "warmup": False}],
            "diagnostics": {"requests": [{"task": 1, "phases": {"generation": generation}},
                {"task": 2, "phases": {"prompt": generation, "generation": generation}}]}})

    def test_projection_excludes_warmup_prompt_and_cpu_operations(self):
        operations, trace = self.projection_fixture()
        result = analysis.project(operations, trace)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["input_tokens"], 512)
        self.assertEqual(result[0]["original_node_counts"]["target/expert-up/rows4"], 96)
        shared, independent = result[0]["scenarios"]
        self.assertAlmostEqual(shared["projected_role_ms"]["target"], 16.4)
        self.assertAlmostEqual(independent["projected_role_ms"]["target"], 30.8)
        self.assertEqual(shared["projected_role_ms"]["helper"], 0)
        self.assertAlmostEqual(shared["ratio_to_recorded_role_gpu_interval_percent"]["target"], 32.8)

    def test_projection_rejects_missing_costs_and_different_geometry(self):
        operations, trace = self.projection_fixture()
        operations["summary"].pop()
        with self.assertRaises(ValueError): analysis.project(operations, trace)
        operations, trace = self.projection_fixture()
        trace["diagnostics"]["requests"][1]["phases"]["generation"]["matrix_shapes"][0]["src1"] = [640, 1, 4, 1]
        with self.assertRaises(ValueError): analysis.project(operations, trace)
        operations, trace = self.projection_fixture()
        trace["diagnostics"]["requests"].pop()
        with self.assertRaises(ValueError): analysis.project(operations, trace)

    def test_small_swap_growth_cannot_become_an_accepted_baseline(self):
        args = baseline.settings(baseline.SPEC, "mtp-mma", "control", 2)
        result = {"status": "passed", "settings": vars(args), "selected_engine": {"revision": "pinned"},
            "memory": {"guard": None, "swap_growth_bytes": 0}}
        self.assertEqual(baseline.acceptance_errors(result, args, {"revision": "pinned"}), [])
        result["memory"]["swap_growth_bytes"] = 63242240
        errors = baseline.acceptance_errors(result, args, {"revision": "pinned"})
        self.assertEqual(len(errors), 1)
        self.assertIn("63242240", errors[0])
        self.assertIn("requires zero", errors[0])


if __name__ == "__main__":
    unittest.main()
