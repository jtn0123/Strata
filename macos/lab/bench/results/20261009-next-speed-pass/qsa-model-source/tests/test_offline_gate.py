"""The preparation gate must reject unclassified tests, stale evidence and native calls."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import validate_offline as gate


class OfflineGateTests(unittest.TestCase):
    def test_unclassified_test_blocks_the_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'config').mkdir(); (root / 'tests').mkdir()
            (root / 'tests/test_new.py').write_text('')
            (root / 'config/offline_tests.json').write_text(json.dumps({'included': [], 'excluded': {}}))
            with self.assertRaisesRegex(RuntimeError, 'Unclassified'): gate.inventory(root)

    def test_native_network_and_remote_git_are_denied(self):
        for command in (['llama-server', '--version'], ['cmake', '--build', '.'], ['git', 'fetch', 'origin'], 'git status'):
            with self.assertRaises(RuntimeError): gate.git_fixture_only(command)
        with self.assertRaises(RuntimeError): gate.deny()

    def test_changed_source_invalidates_a_passed_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for path in ('config', 'tests', 'scripts', 'bench/features'): (root / path).mkdir(parents=True, exist_ok=True)
            (root / 'config/offline_tests.json').write_text(json.dumps({'included': [], 'excluded': {}}))
            source = root / 'scripts/fixture.py'; source.write_text('before')
            receipt = root / 'bench/features/offline-validation.json'
            receipt.write_text(json.dumps({'status': 'passed', 'sources': gate.fingerprint(root)}))
            gate.require_pass(root)
            source.write_text('after')
            with self.assertRaisesRegex(RuntimeError, 'stale'): gate.require_pass(root)
