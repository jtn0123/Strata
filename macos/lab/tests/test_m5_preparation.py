"""Protect paused preparation, controlled experiments and diagnostic interpretation."""
from contextlib import ExitStack
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from unittest.mock import Mock

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import benchmark_m5
from benchmark import Monitor
from lab import server_command
from metal_environment import configure
import prepare_m5
import profile_m5
import verify_m5
import verify_q2


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
                            "checks": [{"passed": True}], "memory": {"guard": None, "swap_growth_bytes": 0, "monitor_healthy": True, "child_exited": True},
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
            lambda r: r[1]["memory"].update(monitor_healthy=False),
            lambda r: r[1]["memory"].update(child_exited=False),
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
                     "GGML_METAL_GRAPH_OPTIMIZE_DISABLE": "1", "GGML_M5_LAB_PROFILE": "1", "METAL_CAPTURE_ENABLED": "1",
                     "GGML_SCHED_DEBUG": "2", "GGML_SCHED_DEBUG_REALLOC": "1"}
        env, record = configure(inherited, "mtp-mma", "on")
        self.assertEqual(env, {"PATH": "/safe", "GGML_METAL_TENSOR_ENABLE": "1"})
        self.assertFalse(record["profile"])
        env, record = configure(inherited, "m5-lab", "off", "nt2")
        self.assertEqual(record["variables"], {"GGML_METAL_TENSOR_DISABLE": "1", "GGML_M5_LAB_NT_MAX": "2"})

    def test_tuning_requires_the_isolated_engine(self):
        for kwargs in ({"tuning": "nt2"}, {"profile": True}):
            with self.assertRaises(ValueError):
                configure({}, "mtp-mma", **kwargs)

    def test_setting_errors_precede_engine_errors_and_environment_reads(self):
        class UnreadableEnvironment(dict):
            def items(self): raise AssertionError("Invalid settings must not read the environment")
        inherited = UnreadableEnvironment()
        cases = (
            ("baseline", "unknown", "head4", "Unknown Metal experiment setting"),
            ("baseline", "auto", "unknown", "Unknown Metal experiment setting"),
            ("baseline", "auto", "head4", "GPU tuning and timing diagnostics require an isolated M5 engine"),
            ("m5-lab", "auto", "copy-v4", "Copy kernels require the isolated m5-copy engine"),
            ("m5-copy", "auto", "head4", "Vocabulary head tiling requires the isolated m5-head engine"),
        )
        for engine, api, tuning, message in cases:
            with self.subTest(engine=engine, api=api, tuning=tuning):
                with self.assertRaisesRegex(ValueError, message):
                    configure(inherited, engine, api, tuning)

    def test_copy_modes_require_the_copy_engine_and_strip_inherited_trace(self):
        for mode, width in (("copy-scalar", "1"), ("copy-v4", "4"), ("copy-v8", "8")):
            for engine in ("baseline", "mtp-mma", "m5-lab", "m5-trace", "m5-correctness"):
                with self.assertRaises(ValueError):
                    configure({}, engine, tuning=mode)
            env, record = configure({"GGML_M5_LAB_COPY_TRACE": "1", "GGML_M5_LAB_COPY_WIDTH": "8"}, "m5-copy", "on", mode)
            self.assertNotIn("GGML_M5_LAB_COPY_TRACE", env)
            self.assertEqual(record["variables"]["GGML_M5_LAB_COPY_WIDTH"], width)
        for engine in ("baseline", "m5-lab", "m5-correctness"):
            with self.assertRaises(ValueError): configure({}, engine, tuning="conv-direct")
        self.assertEqual(configure({}, "m5-copy", tuning="conv-direct")[1]["variables"], {"GGML_M5_LAB_CONV_DIRECT":"1"})

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

    def test_helper_keyword_defaults_and_unknown_keys_preserve_binding(self):
        positional = ("small", 8123, 4096, 512, 128, "none", 3, "f16", 8, "gpu", "mtp", "baseline")
        with patch("lab.model_path", return_value=Path("unused.gguf")) as model, \
                patch("engines.engine_binary", return_value=Path("unused-engine")) as engine:
            implicit = server_command(*positional)
            explicit = server_command(*positional, draft_threads=None, draft_p_min=None)
            self.assertEqual(implicit, explicit)
            self.assertEqual(implicit[implicit.index("--port") + 1], "8123")
            engine.reset_mock(); model.reset_mock()
            unsupported = {"unsupported_helper": 1, "draft_p_min": -1}
            call = lambda: server_command(*positional, **unsupported)
            with self.assertRaisesRegex(TypeError, "unexpected keyword argument 'unsupported_helper'"):
                call()
            engine.assert_not_called(); model.assert_not_called()

    def test_draft_caps_require_the_isolated_engine_and_do_not_leak(self):
        inherited = {"GGML_M5_LAB_DRAFT_CAP": "1", "GGML_M5_LAB_DRAFT_TRACE": "1",
                     "GGML_M5_LAB_DRAFT_SCHEDULE": "1", "GGML_M5_LAB_DRAFT_EARLY_STOP": "1"}
        env, flags = configure(inherited, "m5-copy", "on", "conv-direct")
        self.assertFalse(any("DRAFT_" in key for key in env))
        for profile, cap in (("draftcap-tail", None), ("draftcap2", "2"), ("draftcap3", "3")):
            env, flags = configure(inherited, "m5-draftcap", "on", profile)
            self.assertEqual(env.get("GGML_M5_LAB_DRAFT_EARLY_STOP"), "1")
            self.assertEqual(env.get("GGML_M5_LAB_DRAFT_CAP"), cap)
            self.assertEqual(env.get("GGML_M5_LAB_CONV_DIRECT"), "1")
            self.assertNotIn("GGML_M5_LAB_DRAFT_TRACE", env)
            self.assertNotIn("GGML_M5_LAB_DRAFT_SCHEDULE", env)
            with self.assertRaises(ValueError):
                configure({}, "m5-copy", "on", profile)

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
        empty = {"valid": False, "completed": True, "gpu_start_s": 0, "gpu_end_s": 0, "gpu_ms": 0, "op_counts": {}}
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
        native.poll.return_value = None
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


class TinyCheck:
    """Owned test-backend-ops stand-in: writes its log, then exits after `live` running polls."""
    pid = 4242

    def __init__(self, live, log, text):
        self.live, self.returncode, self.calls = live, None, []
        log.write(text)

    def poll(self):
        if self.returncode is None and self.live <= 0:
            self.returncode = 0
        self.live -= 1
        return self.returncode

    def terminate(self):
        self.calls.append("terminate")
        self.returncode = -15

    def kill(self):
        self.calls.append("kill")
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


class SyntheticCheckResourceTests(unittest.TestCase):
    """Shared verify_q2.check_case: live and post-exit swap/pressure evidence decide acceptance."""

    def patched(self, stack, live, swaps, rss=64 * 1024**2, pressure=1, memory=None, sleep=None,
                text="1/1 tests passed\n"):
        children = []

        def start(command, stdout, stderr, env):
            children.append(TinyCheck(live, stdout, text))
            return children[-1]

        swap = Mock(side_effect=[SimpleNamespace(used=value) for value in swaps])
        stack.enter_context(patch("verify_q2.subprocess.Popen", side_effect=start))
        stack.enter_context(patch("verify_q2.psutil.swap_memory", swap))
        proc = stack.enter_context(patch("verify_q2.psutil.Process"))
        proc.return_value.memory_info.side_effect = memory
        proc.return_value.memory_info.return_value = SimpleNamespace(rss=rss)
        stack.enter_context(patch.object(verify_q2.Monitor, "read_pressure_level", side_effect=[pressure]))
        stack.enter_context(patch("verify_q2.time.sleep", side_effect=sleep))
        return children, swap

    def run_check(self, live, swaps, **options):
        folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        with ExitStack() as stack:
            children, swap = self.patched(stack, live, swaps, **options)
            result = verify_q2.check_case(Path("test-backend-ops"), folder, "math", "type_a=q2_0,")
        published = json.loads((folder / "math.json").read_text())
        self.assertEqual(published, json.loads(json.dumps(result)))
        return result, children[0], swap

    def test_normal_tiny_check_passes_with_live_and_final_samples(self):
        result, child, swap = self.run_check(2, [0, 0, 0, 0])
        self.assertTrue(result["passed"])
        self.assertEqual((result["live_samples"], result["guard"], result["system_swap_growth_bytes"]), (2, None, 0))
        self.assertEqual(result["final_observation"], {"swap_used_bytes": 0, "pressure_level": 1})
        self.assertEqual((child.calls, swap.call_count), ([], 4))

    def test_swap_growth_after_the_last_live_sample_fails(self):
        result, _, swap = self.run_check(1, [0, 0, 1024**3])
        self.assertFalse(result["passed"])
        self.assertEqual(result["system_swap_growth_bytes"], 1024**3)
        self.assertEqual(result["guard"], verify_q2.LIMIT_GUARD)
        self.assertEqual(result["final_observation"]["swap_used_bytes"], 1024**3)
        self.assertEqual(swap.call_count, 3)

    def test_exit_before_the_first_poll_still_takes_the_final_sample(self):
        result, child, swap = self.run_check(0, [0, 512 * 1024**2])
        self.assertEqual((result["live_samples"], swap.call_count, child.calls), (0, 2, []))
        self.assertEqual(result["final_observation"], {"swap_used_bytes": 512 * 1024**2, "pressure_level": 1})
        self.assertEqual(result["system_swap_growth_bytes"], 512 * 1024**2)
        self.assertFalse(result["passed"])
        result, _, _ = self.run_check(0, [0, 0])
        self.assertFalse(result["passed"])
        self.assertIn("No live child sample", result["guard"])

    def test_monitor_read_failure_rejects_with_evidence(self):
        result, child, _ = self.run_check(5, [0, 0], memory=psutil.AccessDenied(4242))
        self.assertFalse(result["passed"])
        self.assertIn("Monitoring failed: AccessDenied", result["guard"])
        self.assertEqual((child.calls, result["exit_code"]), (["terminate"], -15))
        self.assertEqual(result["final_observation"], {"swap_used_bytes": 0, "pressure_level": 1})
        result, _, _ = self.run_check(1, [0, 0, 0], pressure=subprocess.CalledProcessError(1, ["sysctl"]))
        self.assertFalse(result["passed"])
        self.assertTrue(result["monitor_error"].startswith("Final observation failed: CalledProcessError"))
        self.assertEqual(result["final_observation"], {"swap_used_bytes": 0})
        result, _, _ = self.run_check(1, [0, 0, 0], pressure=2)
        self.assertFalse(result["passed"])
        self.assertIn("pressure level 2", result["guard"])

    def test_live_guard_stops_the_child_and_returns_rejected_evidence(self):
        result, child, _ = self.run_check(5, [0, 0, 0], rss=2 * 1024**3)
        self.assertFalse(result["passed"])
        self.assertEqual((result["guard"], result["peak_rss_bytes"]), (verify_q2.LIMIT_GUARD, 2 * 1024**3))
        self.assertEqual(child.calls, ["terminate"])

    def test_child_exiting_during_a_sample_keeps_earlier_live_evidence(self):
        memory = [SimpleNamespace(rss=64 * 1024**2), psutil.NoSuchProcess(4242)]
        result, child, swap = self.run_check(2, [0, 0, 0], memory=memory)
        self.assertTrue(result["passed"])
        self.assertEqual((result["live_samples"], result["monitor_error"], child.calls), (1, None, []))
        self.assertEqual(swap.call_count, 3)

    def test_child_ignoring_terminate_is_killed_and_reaped(self):
        child = Mock(returncode=None)
        child.poll.return_value = None
        child.wait.side_effect = [subprocess.TimeoutExpired("test-backend-ops", 10), -9, -9]
        self.assertEqual(verify_q2.reap(child), -9)
        self.assertEqual([call[0] for call in child.method_calls], ["poll", "terminate", "wait", "kill", "wait", "wait"])

    def test_interrupted_check_publishes_evidence_and_reaps(self):
        folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        with ExitStack() as stack, self.assertRaises(KeyboardInterrupt):
            children, _ = self.patched(stack, 5, [0, 0, 0], sleep=KeyboardInterrupt)
            verify_q2.check_case(Path("test-backend-ops"), folder, "math", "type_a=q2_0,")
        published = json.loads((folder / "math.json").read_text())
        self.assertEqual((published["passed"], published["exit_code"], children[0].calls), (False, -15, ["terminate"]))
        self.assertEqual(published["final_observation"], {"swap_used_bytes": 0, "pressure_level": 1})

    def m5_check(self, swaps):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (root / "bench/features").mkdir(parents=True)
        error = None
        with ExitStack() as stack:
            self.patched(stack, 1, swaps, text="has tensor            = true\n1/1 tests passed\n")
            stack.enter_context(patch.multiple(verify_m5, ROOT=root, sha256=Mock(return_value="tester"),
                                               verify_engine=Mock(return_value={"directory": "engine"})))
            try:
                verify_m5.check("m5-lab", "on")
            except RuntimeError as caught:
                error = caught
        return error, json.loads(next((root / "bench/features").glob("*/checks.json")).read_text())

    def test_m5_zero_swap_gate_sees_growth_after_exit(self):
        error, receipt = self.m5_check([0, 0, 0])
        self.assertIsNone(error)
        self.assertEqual(receipt["status"], "passed")
        # 1 MiB is under the shared 256 MiB guard, but the M5 gate requires zero new swap.
        error, receipt = self.m5_check([0, 0, 1024**2])
        self.assertIn("memory check failed", str(error))
        self.assertEqual(receipt["status"], "failed")
        self.assertTrue(receipt["check"]["passed"])
        self.assertEqual(receipt["check"]["system_swap_growth_bytes"], 1024**2)


if __name__ == "__main__":
    unittest.main()
