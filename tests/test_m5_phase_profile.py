"""Reject ambiguous phase attribution and overlapping-time double counting."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import profile_m5_phases as trace


class PhaseTests(unittest.TestCase):
    def records(self):
        return {
            "M5_PHASE": [{"task": 7, "slot": 0, "phase": "prompt", "cpu_us": 1000000},
                         {"task": 7, "slot": 0, "phase": "generation", "cpu_us": 2000000}],
            "M5_REQUEST_END": [{"task": 7, "slot": 0, "cpu_us": 4000000}],
            "M5_SHAPES": [{"call": 1, "role": "target", "tokens": 512, "cpu_us": 1100000, "shapes": []},
                          {"call": 2, "role": "target", "tokens": 4, "cpu_us": 2100000, "shapes": [
                              {"op": "MUL_MAT_ID", "type": "q2_0", "backend": "Metal", "src0": [1536, 768, 512, 1],
                               "src1": [1536, 10, 4, 1], "dst": [768, 10, 4, 1], "count": 48}]},
                          {"call": 3, "role": "helper", "tokens": 1, "cpu_us": 2200000, "shapes": []}],
            "M5_HELPER": [{"operation": "draft", "cpu_start_us": 2100000, "cpu_end_us": 2600000}],
            "M5_PROFILE": [{"context": "target", "graph": 1, "cb": 0, "call": 1, "role": "target", "tokens": 512,
                            "submit_cpu_us": 1150000, "valid": True, "completed": True,
                            "gpu_start_s": 10, "gpu_end_s": 10.5, "gpu_ms": 500, "op_counts": {}},
                           {"context": "target", "graph": 2, "cb": 0, "call": 2, "role": "target", "tokens": 4,
                            "submit_cpu_us": 2150000, "valid": True, "completed": True,
                            "gpu_start_s": 11, "gpu_end_s": 12, "gpu_ms": 1000, "op_counts": {}},
                           {"context": "helper", "graph": 1, "cb": 0, "call": 3, "role": "helper", "tokens": 1,
                            "submit_cpu_us": 2250000, "valid": True, "completed": True,
                            "gpu_start_s": 11.5, "gpu_end_s": 12.5, "gpu_ms": 1000, "op_counts": {}}],
        }

    def render(self, records):
        # Completion callbacks can arrive out of submission order.
        return "\n".join(key + " " + json.dumps(item) for key, items in reversed(list(records.items())) for item in reversed(items))

    def test_roles_phases_and_overlap_are_separate(self):
        result = trace.parse(self.render(self.records()), expected_requests=1)
        p = result["requests"][0]["phases"]
        self.assertEqual(p["prompt"]["all_gpu_buffer_union_ms"], 500)
        self.assertEqual(p["generation"]["all_gpu_buffer_union_ms"], 1500)
        self.assertEqual(p["generation"]["target_gpu_buffer_union_ms"], 1000)
        self.assertEqual(p["generation"]["helper_gpu_buffer_union_ms"], 1000)
        self.assertEqual(p["generation"]["target_helper_overlap_ms"], 500)
        self.assertEqual(p["generation"]["helper_wall_union_ms"], 500)
        self.assertEqual(p["generation"]["server_phase_wall_ms"], 2000)
        self.assertEqual(p["generation"]["matrix_shapes"][0]["original_node_appearances"], 48)

    def test_bad_records_cannot_become_a_bottleneck_claim(self):
        changes = [
            lambda d: d["M5_REQUEST_END"].clear(),
            lambda d: d["M5_PHASE"][1].update(slot=1),
            lambda d: d["M5_PHASE"][1].update(phase="unknown"),
            lambda d: d["M5_SHAPES"][1].update(call=1),
            lambda d: d["M5_PROFILE"][1].update(role="helper"),
            lambda d: d["M5_PROFILE"][1].update(call=999),
            lambda d: d["M5_PROFILE"][1].update(call=0),
            lambda d: d["M5_PROFILE"].append(copy.deepcopy(d["M5_PROFILE"][0])),
            lambda d: d["M5_PROFILE"][1].update(gpu_ms=1001),
            lambda d: d["M5_PROFILE"][1].update(gpu_start_s=float("nan")),
            lambda d: d["M5_HELPER"][0].update(cpu_end_us=4100000),
        ]
        for change in changes:
            d = self.records()
            change(d)
            with self.subTest(change=change), self.assertRaises(ValueError):
                trace.parse(self.render(d), expected_requests=1)

    def test_inactive_graph_nodes_are_reported_separately(self):
        records = self.records()
        records["M5_SHAPES"][1]["empty_matrix_nodes"] = 7
        result = trace.parse(self.render(records), expected_requests=1)
        phase = result["requests"][0]["phases"]["generation"]
        self.assertEqual(phase["empty_original_matrix_nodes"], 7)
        self.assertEqual(phase["matrix_shapes"][0]["original_node_appearances"], 48)

    def test_plan_does_not_start_gpu_or_inference(self):
        with patch.object(trace, "execute") as run:
            trace.main([])
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
