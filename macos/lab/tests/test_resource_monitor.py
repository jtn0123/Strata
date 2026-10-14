"""Exercise launch/exit pressure and failed telemetry without loading a model."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark import Monitor


class MonitorTests(unittest.TestCase):
    def monitor(self, folder):
        child = Mock(pid=123)
        child.poll.return_value = 0
        baseline = {"swap_used_bytes": 0, "available_bytes": 8*1024**3}
        return Monitor(child, Path(folder)/"memory.jsonl", 128*1024**2,
                       baseline=baseline), child

    def test_swap_during_startup_counts_against_prelaunch_baseline(self):
        with tempfile.TemporaryDirectory() as folder:
            monitor, child = self.monitor(folder)
            child.poll.return_value = None
            with patch("benchmark.psutil.virtual_memory", return_value=SimpleNamespace(available=4*1024**3)), \
                 patch("benchmark.psutil.swap_memory", return_value=SimpleNamespace(used=200*1024**2)), \
                 patch("benchmark.psutil.disk_io_counters", return_value=None), \
                 patch("benchmark.psutil.Process") as proc:
                proc.return_value.memory_info.return_value = SimpleNamespace(rss=1024, vms=2048)
                monitor.run()
            child.terminate.assert_called_once()
            self.assertGreater(monitor.peak_swap, monitor.initial_swap)

    def test_sampling_failure_is_fatal_and_stops_only_owned_child(self):
        with tempfile.TemporaryDirectory() as folder:
            monitor, child = self.monitor(folder)
            child.poll.return_value = None
            with patch("benchmark.psutil.Process") as proc, \
                 patch("benchmark.psutil.virtual_memory", side_effect=RuntimeError("telemetry failed")):
                proc.return_value.memory_info.return_value = SimpleNamespace(rss=1, vms=1)
                monitor.run()
            self.assertIn("telemetry failed", monitor.guard)
            child.terminate.assert_called_once()

    def test_persistent_telemetry_failure_still_returns_failed_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            monitor, child = self.monitor(folder)
            with patch("benchmark.psutil.Process") as proc, \
                 patch("benchmark.psutil.virtual_memory", side_effect=RuntimeError("telemetry unavailable")):
                proc.return_value.memory_info.return_value = SimpleNamespace(rss=1, vms=1)
                monitor.run()
                result = monitor.finish()
            self.assertFalse(result["monitor_healthy"])
            self.assertEqual(result["samples"], 0)
            self.assertIn("telemetry unavailable", result["monitor_error"])
            self.assertIsNone(result["system_disk_read_bytes"])

    def test_finish_includes_teardown_swap(self):
        with tempfile.TemporaryDirectory() as folder:
            monitor, child = self.monitor(folder)
            with patch("benchmark.psutil.virtual_memory", return_value=SimpleNamespace(available=4*1024**3)), \
                 patch("benchmark.psutil.swap_memory", return_value=SimpleNamespace(used=60*1024**2)), \
                 patch("benchmark.psutil.disk_io_counters", return_value=None):
                result = monitor.finish()
            self.assertEqual(result["swap_growth_bytes"], 60*1024**2)
            self.assertFalse(result["monitor_healthy"])
            self.assertIn("No live", result["guard"])

    def test_teardown_swap_above_budget_fails_after_healthy_live_sample(self):
        for limit, final_swap in ((0, 1), (128*1024**2, 200*1024**2)):
            with self.subTest(limit=limit), tempfile.TemporaryDirectory() as folder:
                monitor, child = self.monitor(folder)
                monitor.swap_guard_bytes = limit
                with patch("benchmark.psutil.virtual_memory", return_value=SimpleNamespace(available=4*1024**3)), \
                     patch("benchmark.psutil.swap_memory", return_value=SimpleNamespace(used=0)), \
                     patch("benchmark.psutil.disk_io_counters", return_value=None):
                    monitor.sample(SimpleNamespace(rss=1, vms=1))
                    with patch("benchmark.psutil.swap_memory", return_value=SimpleNamespace(used=final_swap)):
                        result = monitor.finish()
                self.assertTrue(result["monitor_healthy"])
                self.assertEqual(result["swap_growth_bytes"], final_swap)
                self.assertIn("swap grew", result["guard"])
                child.terminate.assert_not_called()

    def test_ignored_termination_escalates_to_kill(self):
        import subprocess
        with tempfile.TemporaryDirectory() as folder:
            monitor, child = self.monitor(folder)
            child.poll.return_value = None
            child.wait.side_effect = [subprocess.TimeoutExpired("owned", 2), 0]
            monitor.stop_owned_child()
            child.terminate.assert_called_once()
            child.kill.assert_called_once()


class NormalPressureTests(unittest.TestCase):
    def setup_monitor(self, folder):
        child = Mock(pid=123)
        child.poll.return_value = None
        monitor = Monitor(child, Path(folder)/'memory.jsonl', 0, 1024**3,
                          baseline={'swap_used_bytes': 0, 'available_bytes': 8*1024**3},
                          require_normal_pressure=True)
        return monitor, child

    def telemetry(self):
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch('benchmark.psutil.virtual_memory', return_value=SimpleNamespace(available=4*1024**3)))
        stack.enter_context(patch('benchmark.psutil.swap_memory', return_value=SimpleNamespace(used=0)))
        stack.enter_context(patch('benchmark.psutil.disk_io_counters', return_value=None))
        proc = stack.enter_context(patch('benchmark.psutil.Process'))
        proc.return_value.memory_info.return_value = SimpleNamespace(rss=1, vms=1)
        return stack

    def test_pressure_rise_stops_child_even_without_swap_or_low_memory(self):
        with tempfile.TemporaryDirectory() as folder, self.telemetry():
            monitor, child = self.setup_monitor(folder)
            with patch.object(Monitor, 'read_pressure_level', side_effect=[1, 2]):
                monitor.run()
            child.terminate.assert_called_once()
            self.assertIn('pressure', monitor.guard)
            self.assertEqual(monitor.peak_swap, 0)
            self.assertGreater(monitor.minimum_available, 1024**3)

    def test_pressure_read_failure_stops_owned_child(self):
        with tempfile.TemporaryDirectory() as folder, self.telemetry():
            monitor, child = self.setup_monitor(folder)
            with patch.object(Monitor, 'read_pressure_level', side_effect=RuntimeError('pressure unavailable')):
                monitor.run()
            child.terminate.assert_called_once()
            self.assertIn('pressure unavailable', monitor.monitor_error)

    def test_teardown_pressure_is_included(self):
        with tempfile.TemporaryDirectory() as folder, self.telemetry():
            monitor, child = self.setup_monitor(folder)
            with patch.object(Monitor, 'read_pressure_level', return_value=1):
                monitor.sample(SimpleNamespace(rss=1, vms=1))
            child.poll.return_value = 0
            with patch.object(Monitor, 'read_pressure_level', return_value=4):
                receipt = monitor.finish()
            self.assertEqual(receipt['peak_pressure_level'], 4)
            self.assertFalse(receipt['normal_pressure_observed'])
            self.assertIn('pressure', receipt['guard'])

    def test_normal_live_and_teardown_pressure_are_recorded(self):
        with tempfile.TemporaryDirectory() as folder, self.telemetry():
            monitor, child = self.setup_monitor(folder)
            with patch.object(Monitor, 'read_pressure_level', return_value=1):
                monitor.sample(SimpleNamespace(rss=1, vms=1))
                child.poll.return_value = 0
                receipt = monitor.finish()
            self.assertTrue(receipt['monitor_healthy'])
            self.assertTrue(receipt['normal_pressure_observed'])
            self.assertEqual(receipt['pressure_live_samples'], 1)
            self.assertEqual(receipt['pressure_samples'], 2)

    def test_missing_live_pressure_coverage_cannot_pass(self):
        with tempfile.TemporaryDirectory() as folder, self.telemetry():
            monitor, child = self.setup_monitor(folder)
            child.poll.return_value = 0
            with patch.object(Monitor, 'read_pressure_level', return_value=1):
                receipt = monitor.finish()
            self.assertFalse(receipt['monitor_healthy'])
            self.assertFalse(receipt['normal_pressure_observed'])

    def test_pressure_read_uses_a_bounded_command_and_rejects_bad_values(self):
        with patch('benchmark.subprocess.check_output', return_value='1\n') as call:
            self.assertEqual(Monitor.read_pressure_level(), 1)
            self.assertEqual(call.call_args.kwargs['timeout'], 2)
        for value in ('garbage', '0', '3', '-1'):
            with patch('benchmark.subprocess.check_output', return_value=value), self.assertRaises(ValueError):
                Monitor.read_pressure_level()


if __name__ == "__main__": unittest.main()
