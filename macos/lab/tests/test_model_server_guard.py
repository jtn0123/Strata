"""Admission rejects both supported native engines without stopping anything."""
from pathlib import Path
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


if __name__ == '__main__': unittest.main()
