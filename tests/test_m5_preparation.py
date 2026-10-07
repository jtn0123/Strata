"""Protect paused preparation, controlled experiments and diagnostic interpretation."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import benchmark_m5
from benchmark import Monitor
from lab import server_command
from metal_environment import configure
import prepare_m5
import profile_m5
import verify_m5


class M5Tests(unittest.TestCase):
    def records(self, name="tensor-writing"):
        spec = next(s for s in benchmark_m5.experiments() if s["id"] == name)
        records = []
        for index, value in enumerate(benchmark_m5.plan(spec)):
            args = benchmark_m5.settings(spec, value, str(index), repeats=1)
            rate = 40 if value == spec["control"] else 50
            cases = [{"workload": "synthetic", "prompt_tokens": n, "prompt_sha256": str(n),
                      "output_tokens": 128, "generation_tok_s": rate, "prompt_tok_s": 600,
                      "ttft_s": 1, "wall_s": 128 / rate + 1,
                      "response": {"final": {"timings": {}}}} for n in (512, 2048)]
            cached = [{"history_budget": n, "warmup": False, "prompt_sha256": str(n),
                       "ttft_s": 0.25, "wall_s": 0.25 + 24 / rate,
                       "native_timings": {"predicted_per_second": rate, "prompt_per_second": 600}}
                      for n in (512, 2048)]
            records.append({"settings": vars(args), "status": "passed", "cases": cases, "cached_cases": cached,
                            "checks": [{"passed": True}], "memory": {"guard": None, "swap_growth_bytes": 0},
                            "selected_engine": {"engine": args.engine, "binary": args.engine},
                            "metal_environment": configure({}, args.engine, args.tensor_api, args.m5_tuning)[1],
                            **{k: {"same": True} for k in ("model", "runtime", "draft_model", "actual_sources")}})
        return records, spec

    def test_all_entry_points_are_paused_by_default(self):
        with patch.object(benchmark_m5, "execute") as execute, patch.object(benchmark_m5, "check_math") as math:
            benchmark_m5.main([])
            execute.assert_not_called()
            math.assert_not_called()
        with patch.object(verify_m5, "check") as math:
            verify_m5.main([])
            math.assert_not_called()
        with patch.object(profile_m5, "profile") as profile, patch.object(profile_m5, "check_math") as math:
            profile_m5.main([])
            profile.assert_not_called()
            math.assert_not_called()

    def test_run_requires_an_explicit_experiment(self):
        with patch.object(benchmark_m5, "execute") as execute, self.assertRaises(SystemExit):
            benchmark_m5.main(["--run"])
        execute.assert_not_called()

    def test_percentages_use_fresh_controls_for_every_axis(self):
        for spec in benchmark_m5.experiments():
            records, spec = self.records(spec["id"])
            for row in benchmark_m5.compare(records, spec, repeats=1):
                for candidate in spec["candidates"]:
                    self.assertAlmostEqual(row["vs_control"][str(candidate)]["generation_increase_percent"], 25)
                self.assertEqual(row["control_drift"]["generation_increase_percent"], 0)

    def test_comparisons_reject_drift_and_missing_evidence(self):
        original, spec = self.records()
        mutations = (
            lambda r: r[1]["settings"].update(draft=6),
            lambda r: r[1]["settings"].update(draft_p_min=0.2),
            lambda r: r[1]["selected_engine"].update(binary="changed"),
            lambda r: r[1]["model"].update(same=False),
            lambda r: r[1]["metal_environment"].update(tensor_api="on"),
            lambda r: r[1]["metal_environment"].update(profile=True),
            lambda r: r[1]["memory"].update(swap_growth_bytes=1),
            lambda r: r[1]["memory"].pop("swap_growth_bytes"),
            lambda r: r[1]["checks"].clear(),
            lambda r: r[1]["checks"][0].update(passed=False),
            lambda r: r[1]["cases"][0].update(prompt_sha256="different"),
            lambda r: r[1]["cases"][0].update(output_tokens=64),
            lambda r: r[1]["cases"].pop(),
            lambda r: r[1]["cached_cases"].pop(),
        )
        for mutation in mutations:
            records = copy.deepcopy(original)
            mutation(records)
            with self.assertRaises(ValueError):
                benchmark_m5.compare(records, spec, repeats=1)

    def test_inherited_debug_and_tuning_flags_cannot_pollute_a_run(self):
        inherited = {"PATH": "/safe", "GGML_METAL_TENSOR_DISABLE": "1", "GGML_METAL_GRAPH_DEBUG": "2",
                     "GGML_METAL_GRAPH_OPTIMIZE_DISABLE": "1", "GGML_M5_LAB_PROFILE": "1", "METAL_CAPTURE_ENABLED": "1"}
        env, record = configure(inherited, "mtp-mma", "on")
        self.assertEqual(env, {"PATH": "/safe", "GGML_METAL_TENSOR_ENABLE": "1"})
        self.assertFalse(record["profile"])
        env, record = configure(inherited, "m5-lab", "off", "nt2")
        self.assertEqual(record["variables"], {"GGML_METAL_TENSOR_DISABLE": "1", "GGML_M5_LAB_NT_MAX": "2"})

    def test_tuning_requires_the_isolated_engine(self):
        for kwargs in ({"tuning": "nt2"}, {"profile": True}):
            with self.assertRaises(ValueError):
                configure({}, "mtp-mma", **kwargs)

    def test_confidence_is_a_separate_validated_native_option(self):
        with patch("lab.model_path", return_value=Path("unused.gguf")):
            command = server_command("flash", engine="mtp-mma", spec="draft-mtp", draft=6,
                draft_placement="mixed", draft_model="mtp_shared_packed_q3", draft_threads=8, draft_p_min=0.4)
            self.assertEqual(command[command.index("--spec-draft-p-min") + 1], "0.4")
            self.assertEqual(command[command.index("--spec-draft-n-max") + 1], "6")
            for value in (-0.1, 1.1, float("nan"), float("inf")):
                with self.assertRaises(ValueError):
                    server_command("flash", spec="draft-mtp", draft_p_min=value)
            with self.assertRaises(ValueError):
                server_command("flash", draft_p_min=0.2)

    def test_gpu_intervals_are_merged_without_double_counting(self):
        entries = [{"context": "target", "graph": i, "cb": 0, "valid": True,
                    "gpu_start_s": start, "gpu_end_s": end, "gpu_ms": (end-start)*1000,
                    "op_counts": {"MUL_MAT": 2}} for i, (start, end) in enumerate(((1, 2), (1.5, 2.5), (3, 4)))]
        text = "\n".join("M5_PROFILE " + json.dumps(e) for e in entries)
        text += "\nstatistics        draft-mtp: #calls(b,g,a) = 1 2 3, dur(b,g,a) = 0.1, 125.5, 0.3 ms\n"
        result = profile_m5.parse(text)
        self.assertEqual(result["command_buffer_interval_union_s"], 2.5)
        self.assertEqual(result["gaps_outside_recorded_buffers_s"], 0.5)
        self.assertEqual(result["contexts"]["target"]["original_graph_nodes"]["MUL_MAT"], 6)
        self.assertEqual(result["last_cumulative_helper_wall_ms"]["draft"], 125.5)
        empty = {"valid": False, "completed": True, "gpu_start_s": 0, "gpu_end_s": 0, "gpu_ms": 0}
        with_empty = profile_m5.parse(text + "\nM5_PROFILE " + json.dumps(empty))
        self.assertEqual(len(with_empty["untimed_completed_buffers"]), 1)
        self.assertEqual(with_empty["command_buffer_interval_union_s"], 2.5)
        entries[0]["valid"] = False
        with self.assertRaises(ValueError):
            profile_m5.parse("M5_PROFILE " + json.dumps(entries[0]))
        with self.assertRaises(ValueError):
            profile_m5.parse("no timestamp evidence")
        entries[0].update(valid=True, gpu_start_s=float("nan"))
        with self.assertRaises(ValueError):
            profile_m5.parse("M5_PROFILE " + json.dumps(entries[0]))

    def test_tighter_swap_guard_stops_the_native_process(self):
        vm = SimpleNamespace(total=48*1024**3, available=4*1024**3)
        native = Mock(pid=999)
        with tempfile.TemporaryDirectory() as directory, \
             patch("benchmark.psutil.virtual_memory", return_value=vm), \
             patch("benchmark.psutil.swap_memory", side_effect=[SimpleNamespace(used=0), SimpleNamespace(used=200*1024**2)]), \
             patch("benchmark.psutil.disk_io_counters", return_value=None), \
             patch("benchmark.psutil.Process") as proc:
            proc.return_value.memory_info.return_value = SimpleNamespace(rss=1024, vms=2048)
            monitor = Monitor(native, Path(directory)/"memory.jsonl", swap_guard_bytes=128*1024**2)
            monitor.run()
            native.terminate.assert_called_once()
            self.assertIn("128 MiB", monitor.guard)

    def test_compressed_weight_inventory_uses_saved_headers(self):
        result = prepare_m5.inventory()
        self.assertIn("Q2_0", result["formats"])
        self.assertGreater(result["formats"]["Q2_0"]["bytes"], 0)


if __name__ == "__main__":
    unittest.main()
