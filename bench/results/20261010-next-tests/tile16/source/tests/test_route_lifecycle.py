"""Refuse unsafe later launches and preserve failures; all processes are mocked."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import profile_m5_routes as routes


class LifecycleTests(unittest.TestCase):
    def test_full_model_low_headroom_refuses_before_quiet_host_sampling(self):
        with patch.object(routes,"assert_no_model_server"), \
             patch.object(routes,"snapshot",return_value={"memory":{"available":33*1024**3}}), \
             patch.object(routes.subprocess,"check_output") as pressure, \
             patch.object(routes.psutil,"cpu_percent") as cpu:
            with self.assertRaisesRegex(RuntimeError,"Not enough available RAM"):
                routes.preflight(False)
            pressure.assert_not_called();cpu.assert_not_called()

    def test_full_model_busy_host_refuses_without_stopping_other_work(self):
        with patch.object(routes,"assert_no_model_server"), \
             patch.object(routes,"snapshot",return_value={"memory":{"available":38*1024**3}}), \
             patch.object(routes.subprocess,"check_output",return_value="1\n"), \
             patch.object(routes.psutil,"cpu_percent",side_effect=[2,40,2]) as cpu, \
             patch.object(routes.subprocess,"Popen") as launch:
            with self.assertRaisesRegex(RuntimeError,"Host still busy"):
                routes.preflight(False)
            self.assertEqual(cpu.call_count,3)
            launch.assert_not_called()

    def test_each_launch_rechecks_headroom_before_popen(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(routes,"verify_engine",return_value={}), \
             patch.object(routes,"verify",return_value={}), \
             patch.object(routes,"verify_models",return_value={},create=True), \
             patch.object(routes,"assert_unchanged",create=True), \
             patch.object(routes,"server_command",return_value=["never-run"]), \
             patch.object(routes.socket,"socket"), \
             patch.object(routes,"host_snapshot",return_value={}), \
             patch.object(routes,"watch_resources"), \
             patch.object(routes,"preflight",side_effect=[{},RuntimeError("Not enough available RAM")],create=True) as gate, \
             patch.object(routes.subprocess,"Popen") as launch, \
             patch.object(routes,"wait_ready",side_effect=AssertionError("Launch gate was skipped")):
            with self.assertRaisesRegex(RuntimeError,"Not enough available RAM"):
                routes.run_pass(Path(directory)/"later-pass",3,"control",True)
            launch.assert_not_called();self.assertEqual(gate.call_count,2)
            import json
            record=json.loads((Path(directory)/"later-pass/capture.json").read_text())
            self.assertEqual(record["status"],"failed")

    def test_early_model_verification_failure_still_writes_failed_capture(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(routes,"verify_engine",return_value={}), \
             patch.object(routes,"verify",return_value={}), \
             patch.object(routes,"verify_models",side_effect=RuntimeError("Model SHA256 differs"),create=True), \
             patch.object(routes,"host_snapshot",return_value={}), \
             patch.object(routes,"preflight",return_value={},create=True), \
             patch.object(routes,"server_command",side_effect=AssertionError("Verification was skipped")), \
             patch.object(routes.subprocess,"Popen") as launch:
            with self.assertRaisesRegex(RuntimeError,"Model SHA256 differs"):
                routes.run_pass(Path(directory)/"bad-model",3,"control",True)
            launch.assert_not_called()
            import json
            record=json.loads((Path(directory)/"bad-model/capture.json").read_text())
            self.assertIn("SHA256 differs",record["error"])

    def test_load_and_cleanup_failures_preserve_original_error_and_child_state(self):
        child = Mock(pid=123)
        child.poll.return_value = None
        child.terminate.side_effect = PermissionError("Cannot stop owned child")
        monitor = Mock()
        monitor.finish.side_effect = RuntimeError("Monitor cleanup unavailable")
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(routes,"verify_engine",return_value={}), \
             patch.object(routes,"verify",return_value={}), \
             patch.object(routes,"verify_models",return_value={}), \
             patch.object(routes,"assert_unchanged"), \
             patch.object(routes,"host_snapshot",return_value={}), \
             patch.object(routes,"preflight",return_value={}), \
             patch.object(routes,"configure",return_value=({},{})), \
             patch.object(routes,"server_command",return_value=["never-run"]), \
             patch.object(routes.socket,"socket"), \
             patch.object(routes,"watch_resources"), \
             patch.object(routes.subprocess,"Popen",return_value=child), \
             patch.object(routes,"Monitor",return_value=monitor), \
             patch.object(routes,"wait_ready",side_effect=RuntimeError("Original load failure")), \
             patch.object(routes,"assert_no_model_server",side_effect=RuntimeError("Unrelated server still running")):
            with self.assertRaisesRegex(RuntimeError,"Original load failure"):
                routes.run_pass(Path(directory)/"failed-load",3,"control",True)
            import json
            record=json.loads((Path(directory)/"failed-load/capture.json").read_text())
            self.assertEqual(record["status"],"failed")
            self.assertIn("Original load failure",record["error"])
            self.assertTrue(any("Cannot stop owned child" in e for e in record["cleanup_errors"]))
            self.assertTrue(any("Monitor cleanup unavailable" in e for e in record["cleanup_errors"]))
            self.assertTrue(any("Unrelated server" in e for e in record["cleanup_errors"]))
            self.assertIsNone(record["child_exit_code"])
            self.assertFalse(record["child_exit_verified"])


if __name__ == "__main__":unittest.main()
