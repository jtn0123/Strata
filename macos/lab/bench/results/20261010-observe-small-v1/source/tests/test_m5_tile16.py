"""Tile16 protocol rejects incomplete activation, parity and drift evidence."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import benchmark_m5_tile16 as probe
from metal_environment import configure
import test_m5_compact as fixtures


class Tile16Gates(unittest.TestCase):
    def fixture(self, rows=512, layout='plain'):
        expected, row, done = fixtures.CompactEvidenceGates().fixture(layout=layout, rows=rows)
        row['scope'] = done['scope'] = 'tile16'
        row['counter_semantics'] = probe.SEMANTICS
        return expected, row, done

    def parse(self, expected, row, done):
        text = 'M5_TILE16_CASE ' + json.dumps(row) + '\nM5_TILE16_DONE ' + json.dumps(done)
        with patch.object(probe.oracle, 'inventory', return_value=[expected]):
            return probe.parse(text, 'perf', 'tile16')

    def test_new_counter_identity_and_complete_activation_required(self):
        expected, row, done = self.fixture()
        self.assertEqual(self.parse(expected, row, done), [row])
        for changes in (dict(count_delta=0), dict(counter_available=False),
                        dict(counter_semantics=probe.oracle.COUNTER_SEMANTICS), dict(scope='compact')):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.parse(expected, dict(row, **changes), done)
        with self.assertRaises(ValueError):
            self.parse(expected, row, dict(done, cases=2))

    def test_fallback_must_encode_zero_candidate_matrices(self):
        for rows, layout in ((31, 'plain'), (513, 'plain'), (512, 'unsupported-shape')):
            expected, row, done = self.fixture(rows, layout)
            self.assertEqual(row['count_delta'], 0)
            self.parse(expected, row, done)
            with self.assertRaises(ValueError): self.parse(expected, dict(row, count_delta=1), done)

    def groups(self, candidate=49.6, extra=None):
        rows = [self.fixture(n)[1] for n in (508, 512)]
        if extra is not None: rows.append(self.fixture(32)[1])
        groups = []
        for value in (50.0, candidate, candidate + .01, 50.05):
            group = copy.deepcopy(rows)
            for row in group: row['median_ns'] = value * 1e6
            if extra is not None and len(groups) in (1, 2): group[-1]['median_ns'] = extra * 1e6
            groups.append(group)
        return groups

    def test_sub_one_percent_gain_can_qualify_above_drift(self):
        result = probe.summarize(self.groups())
        self.assertTrue(result['qualifies_for_model_trial'])
        self.assertLess(result['rows'][0]['time_reduction_percent'], 1)
        self.assertFalse(result['adoption'])
        self.assertIsNone(result['model_TPS'])
        self.assertFalse(probe.summarize(self.groups(candidate=50.0))['qualifies_for_model_trial'])

    def test_regression_elsewhere_or_changed_complete_bytes_blocks(self):
        self.assertFalse(probe.summarize(self.groups(extra=50.8))['qualifies_for_model_trial'])
        groups = self.groups(); groups[1][0]['output_sha256'] = 'c' * 64
        with self.assertRaises(ValueError): probe.summarize(groups)
        with self.assertRaises(ValueError): probe.summarize(groups[:3])

    def test_default_never_builds_or_executes(self):
        with patch.object(probe, 'build') as build, patch.object(probe, 'freeze') as freeze, \
                patch.object(probe, 'execute') as execute:
            probe.main([])
            build.assert_not_called(); freeze.assert_not_called(); execute.assert_not_called()

    def test_control_and_candidate_keep_p07_and_remove_other_flags(self):
        inherited = dict(GGML_M5_LAB_TOP10='1', GGML_M5_LAB_COMPACT_TILES='1', GGML_M5_LAB_TILE16='1')
        for tuning, enabled in (('prompt-tile32', False), ('prompt-tile16', True)):
            env, _ = configure(inherited, 'm5-tile16', 'on', tuning)
            self.assertEqual(env['GGML_M5_LAB_REDUCE10'], '1')
            self.assertEqual('GGML_M5_LAB_TILE16' in env, enabled)
            self.assertNotIn('GGML_M5_LAB_TOP10', env)
            self.assertNotIn('GGML_M5_LAB_COMPACT_TILES', env)
        with self.assertRaises(ValueError): configure({}, 'm5-small-stack', 'on', 'prompt-tile16')


if __name__ == '__main__': unittest.main()
