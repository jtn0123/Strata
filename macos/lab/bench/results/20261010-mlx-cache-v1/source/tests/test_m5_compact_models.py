"""Model acceptance rejects inactive dispatch and gains explained by control drift."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark_m5_compact_models import dispatch, latency_decision
from benchmark_m5 import settings


class CompactModelGates(unittest.TestCase):
    def test_encoding_marker_and_original_control_are_required(self):
        marker = dict(rows=508, k=2560, m=640, experts=512, selected=10, stage='encoded')
        text = 'M5_COMPACT_INPUT ' + json.dumps(marker)
        self.assertTrue(dispatch(text, True)['actual_eligible_encoding'])
        self.assertFalse(dispatch('', False)['actual_eligible_encoding'])
        for invalid in ('', text + '\n' + text):
            with self.assertRaises(ValueError):
                dispatch(invalid, True)
        with self.assertRaises(ValueError):
            dispatch(text, False)
        for key, value in (('rows', 513), ('rows', True), ('k', 640), ('selected', 9), ('stage', 'prepared')):
            with self.subTest(key=key), self.assertRaises(ValueError):
                dispatch('M5_COMPACT_INPUT ' + json.dumps(dict(marker, **{key: value})), True)
        spec = dict(id='compact-tiles', engine='m5-compact', depth=3, axis='m5_tuning',
                    control='conv-direct', candidates=['compact-tiles'], predict=256,
                    engine_for_value={'conv-direct': 'm5-copy', 'compact-tiles': 'm5-compact'},
                    workloads_file='config/m5_compact_workloads.json', prompts=[])
        control = settings(spec, 'conv-direct', 'fixture', 3)
        candidate = settings(spec, 'compact-tiles', 'fixture', 3)
        self.assertEqual((control.engine, candidate.engine), ('m5-copy', 'm5-compact'))
        self.assertEqual((control.swap_guard_bytes, candidate.swap_guard_bytes), (0, 0))
        self.assertEqual(control.real_workload_sha256, candidate.real_workload_sha256)
        self.assertEqual(control.prompts, [])

    def test_latency_gain_requires_both_tasks_above_their_own_drift(self):
        rows = [dict(cached=False, workload=name,
                     vs_control={'compact-tiles': dict(ttft_reduction_percent=5.0,
                                                      total_time_reduction_percent=0.5,
                                                      generation_increase_percent=0.0)},
                     control_drift=dict(ttft_reduction_percent=1.0,
                                        total_time_reduction_percent=0.1,
                                        generation_increase_percent=0.2)) for name in ('code', 'prose')]
        self.assertTrue(latency_decision(rows)['measured_prompt_latency_candidate'])
        for metric, value in (('ttft_reduction_percent', 0.9), ('ttft_reduction_percent', 2.0),
                              ('total_time_reduction_percent', 0.1), ('generation_increase_percent', -1.0)):
            broken = copy.deepcopy(rows)
            broken[1]['vs_control']['compact-tiles'][metric] = value
            self.assertFalse(latency_decision(broken)['measured_prompt_latency_candidate'])
        with self.assertRaises(ValueError):
            latency_decision(rows[:1])


if __name__ == '__main__':
    unittest.main()
