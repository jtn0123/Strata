"""Prevent unqualified lookup combinations and launches under memory pressure."""
from argparse import Namespace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run
import runtime_memory
from runtime_profiles import lookup_command


class RuntimeProfileTests(unittest.TestCase):
    def args(self, **changes):
        values = dict(lookup_profile='code-edit', model='flash', engine='m5-small-stack',
                      m5_tuning='small-reduce', tensor_api='on', context=4096, ubatch=512,
                      cache_type='f16', spec='draft-mtp', draft_model='mtp_shared_packed_q3',
                      draft=3, draft_placement='mixed', draft_threads=8, draft_p_min=0.0)
        return Namespace(**dict(values, **changes))

    def test_lookup_retains_mtp_fallback_and_bounded_verification(self):
        command = ['--spec-type', 'draft-mtp']
        actual = lookup_command(command, self.args())
        self.assertEqual(command, ['--spec-type', 'draft-mtp'])
        self.assertEqual(actual[1], 'ngram-mod,draft-mtp')
        self.assertEqual(actual[actual.index('--spec-ngram-mod-n-max') + 1], '3')

    def test_unqualified_lookup_combinations_fail_before_engine_or_launch(self):
        for changes in (dict(model='small'), dict(draft=6), dict(engine='mtp-mma'),
                        dict(m5_tuning='small-reduce-top10'), dict(cache_type='q8_0')):
            with self.subTest(changes=changes), patch.object(run, 'verify_engine') as engine, \
                    patch.object(run.subprocess, 'Popen') as launch:
                with self.assertRaises(ValueError): run.execute(self.args(**changes))
                engine.assert_not_called(); launch.assert_not_called()

    def test_normal_profile_does_not_enable_lookup(self):
        command = ['--spec-type', 'draft-mtp']
        self.assertEqual(lookup_command(command, self.args(lookup_profile='off')), command)

    def test_low_headroom_refused(self):
        with patch.object(runtime_memory.Monitor, 'baseline', return_value=dict(available_bytes=33*1024**3)), \
                patch.object(runtime_memory.Monitor, 'read_pressure_level', return_value=1):
            with self.assertRaisesRegex(RuntimeError, 'No model loaded'): runtime_memory.admit_model('flash')

    def test_warning_pressure_refused_despite_available_ram(self):
        with patch.object(runtime_memory.Monitor, 'baseline', return_value=dict(available_bytes=40*1024**3)), \
                patch.object(runtime_memory.Monitor, 'read_pressure_level', return_value=2):
            with self.assertRaisesRegex(RuntimeError, 'No model loaded'): runtime_memory.admit_model('flash')

    def test_app_monitor_uses_continuous_pressure_and_zero_swap_guard(self):
        baseline = dict(available_bytes=40*1024**3, swap_used_bytes=0)
        with patch.object(runtime_memory.Monitor, 'baseline', return_value=baseline), \
                patch.object(runtime_memory.Monitor, 'read_pressure_level', return_value=1):
            policy = runtime_memory.admit_model('flash')
        with patch.object(runtime_memory, 'Monitor') as monitor:
            runtime_memory.app_monitor('owned-child', 'memory.jsonl', policy)
            monitor.assert_called_once_with('owned-child', 'memory.jsonl', 0, 1024**3,
                                            baseline=baseline, require_normal_pressure=True)


if __name__ == '__main__': unittest.main()
