import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from verify_m5_sampling import parse


class SamplingEvidenceTests(unittest.TestCase):
    def test_native_failure_or_missing_completion_is_rejected(self):
        for text in ('', 'sampling view first-read test PASSED\nWarning: skipping test',
                     'sampling view first-read test PASSED\nGGML_ASSERT failure'):
            with self.assertRaises(ValueError): parse(text,'first_read')

    def test_all_cpu_and_grammar_cases_are_required(self):
        text='\n'.join(f'SAMPLING_COMMON_TOKEN {m} {i} 42' for m in range(6) for i in range(3))
        text+='\nsampling view common test PASSED\n'
        self.assertEqual(len(parse(text,'common')['tokens']),18)
        with self.assertRaises(ValueError): parse(text.replace('SAMPLING_COMMON_TOKEN 5 2 42',''),'common')

    def test_timing_rejects_wrong_samples_or_incomplete_pairs(self):
        text='\n'.join(f'SAMPLING_READ_COST {r} {v} 200000 0.02' for r in range(8) for v in (0,1))
        text+='\nsampling view read-cost test PASSED\n'
        self.assertEqual(len(parse(text,'read_cost')['costs']),16)
        for changed in (text.replace('200000','1'),text.replace('SAMPLING_READ_COST 7 1 200000 0.02','')):
            with self.assertRaises(ValueError): parse(changed,'read_cost')


class WinnerCeilingTests(unittest.TestCase):
    def bracket(self):
        rows = []
        for scope, value in zip(('control', 'head-floor', 'head-floor', 'control'), (2000, 1900, 1910, 2010)):
            case = dict(id='mixed', rows=1, k=2560, m=248320, input_sha256='a'*64,
                        weight_sha256='b'*64, output_sha256='c'*64, median_us=value)
            rows.append(dict(scope=scope, status='passed', mode='perf', cases=[case]))
        return rows

    def test_ideal_component_is_not_model_gain(self):
        from benchmark_m5_winner_ceiling import summarize
        result = summarize(self.bracket())
        self.assertFalse(result['tps_gain_measured'])
        self.assertFalse(result['winner_kernel_implemented'])
        self.assertAlmostEqual(result['cases'][0]['removable_consumer_us'], 100)

    def test_reject_changed_scores_and_failed_run(self):
        from benchmark_m5_winner_ceiling import summarize
        rows = self.bracket(); rows[2]['cases'][0]['output_sha256'] = 'd'*64
        with self.assertRaises(ValueError): summarize(rows)
        rows = self.bracket(); rows[2]['status'] = 'failed'
        with self.assertRaises(ValueError): summarize(rows)

    def test_reject_unbracketed_and_nonfinite_timings(self):
        from benchmark_m5_winner_ceiling import summarize
        rows = self.bracket(); rows[0]['scope'] = 'head-floor'
        with self.assertRaises(ValueError): summarize(rows)
        rows = self.bracket(); rows[1]['cases'][0]['median_us'] = float('nan')
        with self.assertRaises(ValueError): summarize(rows)


class Top10EvidenceTests(unittest.TestCase):
    def bracket(self):
        rows = WinnerCeilingTests().bracket()
        for row in rows:
            candidate = row['scope'] == 'head-floor'
            row['scope'] = 'candidate' if candidate else 'control'
            row['cases'][0]['consumers'] = [dict(ids=[1,2,3,4,5,6,7,8,9,10],
                values_sha256='e'*64, selector_status=1 if candidate else -1)]
        return rows

    def test_exact_component_is_not_tps_claim(self):
        from benchmark_m5_top10 import summarize
        result = summarize(self.bracket())
        self.assertFalse(result['tps_gain_measured'])
        self.assertTrue(result['qualifies_for_model_trial'])

    def test_reject_changed_candidates_or_inactive_path(self):
        from benchmark_m5_top10 import summarize
        rows = self.bracket(); rows[2]['cases'][0]['consumers'][0]['ids'][0] = 99
        with self.assertRaises(ValueError): summarize(rows)
        rows = self.bracket(); rows[2]['cases'][0]['consumers'][0]['selector_status'] = 0
        with self.assertRaises(ValueError): summarize(rows)

    def test_wrong_engine_cannot_enable_top10(self):
        from metal_environment import configure
        with self.assertRaises(ValueError): configure({}, 'm5-copy', 'on', 'top10')
        env, _ = configure({'GGML_M5_LAB_TOP10':'1'}, 'm5-top10', 'on', 'conv-direct')
        self.assertNotIn('GGML_M5_LAB_TOP10', env)

    def test_missing_fixture_completion_is_rejected(self):
        from benchmark_m5_top10 import parse
        with self.assertRaises(ValueError): parse('', 'candidate', 'check')


class Top10ModelGateTests(unittest.TestCase):
    def test_original_control_mapping_and_zero_swap_guard(self):
        from benchmark_m5 import settings
        spec = dict(engine='m5-top10', depth=3, axis='m5_tuning', control='conv-direct',
            candidates=['top10'], engine_for_value={'conv-direct':'m5-copy','top10':'m5-top10'})
        a = settings(spec,'conv-direct','test',3); b = settings(spec,'top10','test',3)
        self.assertEqual((a.engine,a.m5_tuning,a.swap_guard_bytes),('m5-copy','conv-direct',0))
        self.assertEqual((b.engine,b.m5_tuning,b.swap_guard_bytes),('m5-top10','top10',0))
        spec['engine_for_value'].pop('conv-direct')
        with self.assertRaises(ValueError): settings(spec,'conv-direct','test',3)

    def test_normal_dispatch_marker_required_only_on_candidate(self):
        from benchmark_m5_top10_models import dispatch
        text='M5_TOP10_DISPATCH {"ncols":248320,"rows":1,"k":10,"device":"M5 Pro","fallback":"ties-exceptional-subnormal"}'
        self.assertTrue(dispatch(text,True)['eligible_variant_entered'])
        self.assertFalse(dispatch('',False)['all_invocations_fast_proven'])
        for raw,candidate in (('',True),(text,False),(text+'\n'+text,True)):
            with self.assertRaises(ValueError): dispatch(raw,candidate)


class Top10StrictDecisionTests(unittest.TestCase):
    def test_tps_win_with_subthreshold_reply_gain_is_not_adopted(self):
        from benchmark_m5_top10_models import model_adoption
        rows=[]
        for workload in ('code','prose'):
            rows.append(dict(cached=False,workload=workload,vs_control={'top10':dict(
                generation_increase_percent=1.1,total_time_reduction_percent=0.96)},
                control_drift=dict(generation_increase_percent=0.2,total_time_reduction_percent=0.2)))
        decision=model_adoption(rows)
        self.assertFalse(decision['measured_speed_candidate'])
        self.assertNotIn('callbacks',decision['rule'])
        for row in rows: row['vs_control']['top10']['total_time_reduction_percent']=1.1
        self.assertTrue(model_adoption(rows)['measured_speed_candidate'])
        rows[1]['control_drift']['total_time_reduction_percent']=1.2
        self.assertFalse(model_adoption(rows)['measured_speed_candidate'])


if __name__=='__main__': unittest.main()
