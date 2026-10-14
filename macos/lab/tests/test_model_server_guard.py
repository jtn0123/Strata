"""Admission rejects both supported native engines without stopping anything."""
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import check_memory


class ModelServerGuardTests(unittest.TestCase):
    def test_llama_and_parent_strata_are_both_rejected(self):
        for name in ('llama-server', 'llama-server-debug', 'strata'):
            with self.subTest(name=name), patch.object(check_memory.psutil, 'process_iter', return_value=[
                    SimpleNamespace(pid=123, info={'name': name})]):
                with self.assertRaisesRegex(RuntimeError, '123'):
                    check_memory.assert_no_model_server()

    def test_unrelated_names_and_missing_names_are_allowed(self):
        with patch.object(check_memory.psutil, 'process_iter', return_value=[
                SimpleNamespace(pid=n, info={'name': name}) for n, name in enumerate((None, 'python', 'stratagem'))]):
            check_memory.assert_no_model_server()

    def test_snapshot_preserves_platform_fields_and_grouped_rss(self):
        memory=dict(total=16*check_memory.GIB, available=8*check_memory.GIB,
                    wired=check_memory.GIB, percent=50.0, extra_platform_counter=17)
        swap=dict(used=check_memory.GIB//2, free=check_memory.GIB, percent=33.3)
        processes=[SimpleNamespace(info={'name': name, 'memory_info': SimpleNamespace(rss=rss)})
                   for name, rss in (('python', 100), ('python', 200), (None, 250), ('other', 10))]
        processes.append(SimpleNamespace(info={'name': 'missing', 'memory_info': None}))
        with patch.object(check_memory.psutil, 'process_iter', return_value=processes), \
                patch.object(check_memory.psutil, 'virtual_memory', return_value=SimpleNamespace(_asdict=lambda: memory)), \
                patch.object(check_memory.psutil, 'swap_memory', return_value=SimpleNamespace(_asdict=lambda: swap)), \
                patch.object(check_memory.subprocess, 'check_output', return_value='normal fixture\n') as pressure:
            result=check_memory.snapshot()
        self.assertIs(result['memory'], memory)
        self.assertIs(result['swap'], swap)
        self.assertEqual(result['pressure'], 'normal fixture')
        self.assertEqual(result['largest_process_groups'], [
            {'name': 'python', 'rss_bytes': 300}, {'name': 'unknown', 'rss_bytes': 250},
            {'name': 'other', 'rss_bytes': 10}])
        pressure.assert_called_once_with(['memory_pressure', '-Q'], text=True)
        output=StringIO()
        with redirect_stdout(output):
            check_memory.print_snapshot(result)
        self.assertIn('RAM: 16.0 GiB total, 8.0 GiB available, 1.0 GiB wired.', output.getvalue())
        self.assertIn('Swap used: 0.50 GiB.', output.getvalue())
        self.assertIn(result['note'], output.getvalue())


if __name__ == '__main__': unittest.main()
