"""Setup must refuse source/Python drift before installing or rebuilding anything."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import provision


class ProvisionTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory)
        (root / 'config').mkdir()
        (root / '.venv/bin').mkdir(parents=True)
        (root / '.venv/bin/python').touch()
        for name in ('llama.cpp', 'Strata-macOS'): (root / 'vendor' / name).mkdir(parents=True)
        (root / 'config/runtime.json').write_text(json.dumps({'build_flags': [],
            'llama_cpp': {'revision': 'pin', 'repository': 'unused'},
            'strata_macos': {'revision': 'pin', 'repository': 'unused'}}))
        return root

    def output(self, command, **kwargs):
        return '3.12' if '-c' in command else ('pin' if command[-1] == 'HEAD' else '')

    def test_dirty_source_and_wrong_python_refuse_before_mutations(self):
        for reason in ('dirty', 'python'):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as directory:
                root = self.fixture(directory)
                def output(command, **kwargs):
                    if reason == 'dirty' and '--porcelain' in command: return ' M hacked.cpp'
                    if reason == 'python' and '-c' in command: return '3.13'
                    return self.output(command)
                with patch.object(provision, 'ROOT', root), patch.object(provision.platform, 'system', return_value='Darwin'), \
                     patch.object(provision.platform, 'machine', return_value='arm64'), \
                     patch.object(provision.subprocess, 'check_output', side_effect=output), patch.object(provision, 'run') as run:
                    with self.assertRaises(RuntimeError): provision.main([])
                    run.assert_not_called()

    def test_success_writes_then_verifies_baseline_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory); uv = root / 'uv'; uv.touch()
            events = []
            with patch.object(provision, 'ROOT', root), patch.object(provision.platform, 'system', return_value='Darwin'), \
                 patch.object(provision.platform, 'machine', return_value='arm64'), \
                 patch.object(provision.subprocess, 'check_output', side_effect=self.output), \
                 patch.object(provision.shutil, 'which', return_value=str(uv)), \
                 patch.object(provision, 'run', side_effect=lambda command: events.append(('command', command))), \
                 patch.object(provision, 'write_receipt', side_effect=lambda name: events.append(('receipt', name))), \
                 patch.object(provision, 'verify_engine', side_effect=lambda name: events.append(('verify', name))):
                provision.main(['--jobs', '1', '--local-http-only'])
            self.assertEqual(events[-2:], [('receipt', 'baseline'), ('verify', 'baseline')])
            self.assertTrue(any('-DLLAMA_OPENSSL=OFF' in c for kind,c in events if kind == 'command'))

    def test_check_only_requires_receipt_and_never_builds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            with patch.object(provision, 'ROOT', root), patch.object(provision.platform, 'system', return_value='Darwin'), \
                 patch.object(provision.platform, 'machine', return_value='arm64'), \
                 patch.object(provision.subprocess, 'check_output', side_effect=self.output), \
                 patch.object(provision, 'verify_engine', side_effect=FileNotFoundError('missing receipt')), patch.object(provision, 'run') as run:
                with self.assertRaises(FileNotFoundError): provision.main(['--check-only'])
                run.assert_not_called()
