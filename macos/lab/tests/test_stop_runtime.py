"""Stop every maintained supervisor while retaining ownership checks."""
import json
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import stop


class StopRuntimeTests(unittest.TestCase):
    def fixture(self, root, script='scripts/runtime_profiles.py', created=42, cwd=None):
        path = root / 'bench/runtime/active.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(dict(pid=123, create_time=42)))
        process = Mock()
        process.create_time.return_value = created
        process.cmdline.return_value = ['python', script, '--profile', 'balanced']
        process.cwd.return_value = str(root) if cwd is None else cwd
        return process

    def test_generic_and_profile_supervisors_stop_in_relative_and_absolute_forms(self):
        for name in ('run.py', 'runtime_profiles.py'):
            for absolute in (False, True):
                with self.subTest(name=name, absolute=absolute), tempfile.TemporaryDirectory() as folder:
                    root = Path(folder)
                    script = str(root / 'scripts' / name) if absolute else 'scripts/' + name
                    process = self.fixture(root, script)
                    with patch.object(stop, 'ROOT', root), patch.object(stop.psutil, 'Process', return_value=process):
                        stop.main()
                    process.send_signal.assert_called_once_with(signal.SIGTERM)
                    process.wait.assert_called_once_with(timeout=25)

    def test_replaced_pid_foreign_script_and_foreign_workspace_are_never_signalled(self):
        for changes in (dict(created=43), dict(script='other.py'), dict(cwd='/foreign')):
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                process = self.fixture(root, **changes)
                with patch.object(stop, 'ROOT', root), patch.object(stop.psutil, 'Process', return_value=process):
                    with self.assertRaises(RuntimeError): stop.main()
                process.send_signal.assert_not_called()


if __name__ == '__main__': unittest.main()
