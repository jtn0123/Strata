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

    def test_bootstrap_installs_locked_quality_tools_before_native_builds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory); uv = root / 'uv'; uv.touch()
            commands = []
            with patch.object(provision, 'ROOT', root), patch.object(provision, 'preflight', return_value={
                    'build_flags': [], 'llama_cpp': {}, 'strata_macos': {}}), \
                    patch.object(provision, 'source_check'), \
                    patch.object(provision.shutil, 'which', return_value=str(uv)), \
                    patch.object(provision, 'run', side_effect=lambda command: commands.append(list(map(str, command)))), \
                    patch.object(provision, 'write_receipt'), patch.object(provision, 'verify_engine'):
                provision.main([])
            installs = [command for command in commands if command[1:3] == ['pip', 'install']]
            quality = next((command for command in installs if 'requirements-quality.lock' in command), None)
            self.assertIsNotNone(quality, 'The mandatory offline coverage tests need their pinned tools')
            self.assertIn('--require-hashes', quality)
            self.assertEqual(quality[quality.index('--only-binary') + 1], ':all:')
            self.assertEqual(quality[quality.index('--python') + 1], '.venv/bin/python')
            self.assertLess(commands.index(quality), next(index for index, command in enumerate(commands) if '-S' in command))

    def test_failed_quality_install_stops_before_build_or_receipt_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory); uv = root / 'uv'; uv.touch()
            commands = []
            def install(command):
                commands.append(list(map(str, command)))
                if 'requirements-quality.lock' in command:
                    raise RuntimeError('quality wheel verification failed')
            with patch.object(provision, 'ROOT', root), patch.object(provision, 'preflight', return_value={
                    'build_flags': [], 'llama_cpp': {}, 'strata_macos': {}}), \
                    patch.object(provision, 'source_check'), \
                    patch.object(provision.shutil, 'which', return_value=str(uv)), \
                    patch.object(provision, 'run', side_effect=install), \
                    patch.object(provision, 'write_receipt') as receipt, patch.object(provision, 'verify_engine') as verify:
                with self.assertRaisesRegex(RuntimeError, 'quality wheel verification failed'):
                    provision.main([])
            self.assertFalse(any('-S' in command or '--build' in command for command in commands))
            receipt.assert_not_called(); verify.assert_not_called()
