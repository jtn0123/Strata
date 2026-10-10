"""Reject incomplete monitoring evidence and overlapping-time speed claims."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_m5_phase_profile as phase_fixture
import baseline_m5_observe as baseline
import observe_metrics as metrics


class ObserveTests(unittest.TestCase):
    def records(self):
        d=phase_fixture.PhaseTests().records()
        for b in d['M5_PROFILE']:
            start=b['submit_cpu_us']/1e6+8
            duration=b['gpu_ms']/1000
            b.update(gpu_start_s=start,gpu_end_s=start+duration)
        # GPU mach timestamps are 8 seconds ahead of the CPU monotonic clock.
        d['M5_CPU_CALL']=[]
        for shape in d['M5_SHAPES']:
            low=shape['cpu_us']-100
            d['M5_CPU_CALL'].append(dict(call=shape['call'],role=shape['role'],tokens=shape['tokens'],seqs=1,
                outputs=1,reason='topology',begin_us=low,end_us=shape['cpu_us'],
                clock_low_us=low-2,clock_high_us=low,mach_us=low-1+8e6,
                spans=[dict(stage=name,begin_us=low+i*10,end_us=low+(i+1)*10)
                       for i,name in enumerate(('memory_apply','reset','build','allocate','inputs'))]))
        d['M5_ACCEPT']=[dict(seq=0,accepted_drafts=2,cpu_us=2300000)]
        d['M5_CHECKPOINT']=[dict(task=7,slot=0,operation='create',begin_us=1200000,end_us=1300000,bytes=112)]
        return d

    def render(self,d):return phase_fixture.PhaseTests().render(d)

    def test_calibrated_cpu_stages_and_other_metrics(self):
        r=metrics.parse(self.render(self.records()),1)
        self.assertEqual(r['clock']['mach_minus_ggml_us'],8e6)
        self.assertEqual(r['clock']['spread_us'],0)
        p=r['requests'][0]['phases']
        self.assertAlmostEqual(p['generation']['planning_wall_union_ms'],0.06)
        self.assertEqual(p['prompt']['checkpoint_payload_bytes'],112)
        self.assertEqual(p['generation']['accepted_draft_histogram'],{2:1})
        self.assertEqual(p['generation']['graph_calls']['helper'],{'topology':1})

    def test_overlapping_intervals_are_not_added(self):
        self.assertAlmostEqual(metrics.outside_ms([(1,3),(2,4)],[(2,3)]),2000)
        self.assertAlmostEqual(metrics.outside_ms([(1,2)],[(0,3)]),0)

    def test_corrupted_or_missing_cpu_evidence_is_rejected(self):
        changes=[lambda d:d['M5_CPU_CALL'].pop(),
                 lambda d:d['M5_CPU_CALL'].append(copy.deepcopy(d['M5_CPU_CALL'][0])),
                 lambda d:d['M5_CPU_CALL'][0].update(mach_us=float('nan')),
                 lambda d:d['M5_CPU_CALL'][0].update(mach_us=9e6),
                 lambda d:d['M5_CPU_CALL'][0].update(reason='reuse'),
                 lambda d:d['M5_CPU_CALL'][0]['spans'].pop(),
                 lambda d:d['M5_CPU_CALL'][0]['spans'][1].update(begin_us=0),
                 lambda d:d['M5_CPU_CALL'][0].update(role='helper'),
                 lambda d:d['M5_CPU_CALL'][0].update(clock_low_us=0),
                 lambda d:d['M5_CHECKPOINT'][0].update(end_us=3000000)]
        for change in changes:
            d=self.records();change(d)
            with self.subTest(change=change),self.assertRaises(ValueError):metrics.parse(self.render(d),1)

    def test_allocation_reservations_retain_duplicate_cache_rows(self):
        r=metrics.allocation_entries('load_tensors: loading model tensors\nx Metal KV buffer size = 96.00 MiB\nx Metal KV buffer size = 24.00 MiB\nx Metal compute buffer size = 2.00 MiB\nx Metal compute buffer size = 3.00 MiB')
        self.assertEqual(len(r['entries']),4)
        self.assertIsNone(r['unique_physical_total_bytes'])

    def test_plan_has_no_execution(self):
        with patch.object(baseline,'freeze') as f,patch.object(baseline,'run') as r:
            baseline.main([]);f.assert_not_called();r.assert_not_called()

    def test_baseline_requires_four_exact_launches(self):
        def record():
            return dict(status='passed',cases=[dict(workload=w,repeat=i,warmup=i<0,input_ids=[1],
                response=dict(generated_token_ids=[2],text='x',ttft_s=1,wall_s=2,
                              final=dict(stop_type='limit',timings=dict(predicted_per_second=10,prompt_per_second=20))))
                for w in ('code','prose') for i in (-1,0,1,2)])
        data=[record() for _ in range(4)]
        self.assertEqual(baseline.summarize(data)[0]['baseline']['tps'],10)
        data[2]['cases'][1]['response']['generated_token_ids']=[3]
        with self.assertRaises(ValueError):baseline.summarize(data)

    def test_run_refuses_attempted_campaign(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'result.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'already attempted'):baseline.run(p)


if __name__=='__main__':unittest.main()
