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

    def test_ignored_termination_escalates_to_kill(self):
        import subprocess
        with tempfile.TemporaryDirectory() as folder:
            monitor, child = self.monitor(folder)
            child.poll.return_value = None
            child.wait.side_effect = [subprocess.TimeoutExpired("owned", 2), 0]
            monitor.stop_owned_child()
            child.terminate.assert_called_once()
            child.kill.assert_called_once()


if __name__ == "__main__": unittest.main()
