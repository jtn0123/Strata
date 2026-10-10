"""Small gains need repeatable launch direction and metric-specific evidence."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from benchmark_m5_small_gains import launch_row, scope_decision, feature_receipts, specification
from benchmark_m5 import settings
from metal_environment import configure


class SmallGainTests(unittest.TestCase):
    def values(self):
        a=dict(generation_tok_s=50,prompt_tok_s=500,ttft_s=1,wall_s=6)
        b=dict(generation_tok_s=50.25,prompt_tok_s=502.5,ttft_s=.995,wall_s=5.97)
        return [a,b,copy.deepcopy(b),copy.deepcopy(a)]

    def test_half_percent_is_eligible_with_repeatable_direction(self):
        row=launch_row(self.values())
        rows=[dict(row,workload=name,cached=False) for name in ('code','prose')]
        self.assertTrue(scope_decision(rows)['eligible_for_confirmation'])
        self.assertIn('generation',scope_decision(rows)['common_metric_scopes'])

    def test_passing_average_cannot_hide_one_losing_candidate(self):
        values=self.values();values[1]['generation_tok_s']=49;values[2]['generation_tok_s']=52
        self.assertGreater(launch_row(values)['vs_control']['generation_increase_percent'],0)
        self.assertFalse(launch_row(values)['qualifying_metrics']['generation_increase_percent'])

    def test_control_drift_defeats_small_gain(self):
        values=self.values();values[3]['generation_tok_s']=50.2
        self.assertFalse(launch_row(values)['qualifying_metrics']['generation_increase_percent'])

    def test_material_ttft_loss_blocks_other_wins(self):
        values=self.values();values[1]['ttft_s']=values[2]['ttft_s']=1.02
        row=launch_row(values);rows=[dict(row,workload=name,cached=False) for name in ('code','prose')]
        self.assertFalse(scope_decision(rows)['eligible_for_confirmation'])

    def test_prompt_gain_needs_reply_and_cannot_become_generation(self):
        values=self.values()
        for value in values:value['generation_tok_s']=50
        row=launch_row(values);decision=scope_decision([dict(row,workload=name,cached=False) for name in ('code','prose')])
        self.assertIn('prompt-latency',decision['common_metric_scopes'])
        self.assertNotIn('generation',decision['common_metric_scopes'])
        for value in values:value['wall_s']=6
        row=launch_row(values)
        self.assertFalse(scope_decision([dict(row,workload=name,cached=False) for name in ('code','prose')])['eligible_for_confirmation'])

    def test_inactive_marker_and_memory_fail_closed(self):
        marker='M5_REDUCE10_DISPATCH '+json.dumps(dict(rows=4,channels=2560,experts=10,stage='encoded'))
        self.assertTrue(feature_receipts(marker,['reduce'])['reduce']['encoded'])
        with self.assertRaises(ValueError):feature_receipts(marker,[])
        with self.assertRaises(ValueError):feature_receipts('', ['reduce'])
        row=launch_row(self.values())
        self.assertFalse(scope_decision([dict(row,workload=name,cached=False) for name in ('code','prose')],False)['eligible_for_confirmation'])

    def test_zero_swap_and_original_control_in_each_cohort(self):
        for cohort in ('short','long'):
            spec=specification('small-reduce',cohort,'fixture')
            a,b=settings(spec,'conv-direct','fixture',3),settings(spec,'small-reduce','fixture',3)
            self.assertEqual((a.engine,b.engine),('m5-copy','m5-small-stack'))
            self.assertEqual((a.swap_guard_bytes,b.swap_guard_bytes),(0,0))
            self.assertEqual((a.prompts,b.prompts),([],[]))
            with self.assertRaises(ValueError):configure({},'m5-copy','on','small-reduce')


if __name__=='__main__':unittest.main()
