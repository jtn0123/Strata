"""Held input-cache screen requires real activation, complete cases and clean resources."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import benchmark_input_cache as b


class InputBenchmarkGates(unittest.TestCase):
    def records(self):
        records=[]
        for index, enabled in enumerate(b.ORDER):
            cases=[]
            for task in b.TASKS:
                for mode in b.MODES:
                    for n in range(4):
                        hit=int(enabled and mode=='identical' and n>0)
                        cases.append(dict(task=task, mode=mode, repeat=n, warmup=n==0,
                            text_sha256='a'*64, input_tokens=[1,2], tokens=[3,4],
                            events=[dict(text='answer')], done=dict(finish='length'),
                            generation_tok_s=50, prompt_tok_s=500,
                            ttft_s=(.48 if enabled and mode=='identical' else .5) + index*.00001,
                            wall_s=(5.98 if enabled and mode=='identical' else 6) + index*.00001,
                            cache_accounted_bytes=1024, encode_stats=dict(hits=hit,requests=1-hit,errors=0)))
            records.append(dict(status='passed',enabled=enabled,engine=dict(pin='native'),models=dict(pin='model'),
                memory=dict(swap_growth_bytes=0,guard=None,monitor_healthy=True,child_exited=True),cases=cases))
        return records

    def test_small_gain_licenses_confirmation_only(self):
        result=b.summarize(self.records())
        self.assertTrue(result['eligible_for_confirmation'])
        self.assertFalse(result['adoption'])
        self.assertEqual(result['attributed_native_TPS_gain'],0)

    def test_resource_provenance_and_complete_parity_rejections(self):
        for change in ('swap','monitor','missing-model','missing-memory','output','input','duplicate'):
            records=self.records(); row=records[1]
            if change=='swap': row['memory']['swap_growth_bytes']=1
            if change=='monitor': row['memory']['monitor_healthy']=False
            if change=='missing-model': del row['models']
            if change=='missing-memory': del row['memory']
            if change=='output': row['cases'][0]['tokens']=[99]
            if change=='input': row['cases'][0]['input_tokens']=[99]
            if change=='duplicate': row['cases'][0]=copy.deepcopy(row['cases'][1])
            with self.subTest(change=change),self.assertRaises(ValueError):b.summarize(records)

    def test_real_hits_and_miss_modes_cannot_be_assumed(self):
        for mode in b.MODES:
            records=self.records()
            row=next(c for c in records[1]['cases'] if c['mode']==mode and c['repeat']==1)
            row['encode_stats']['hits']=1-row['encode_stats']['hits']
            with self.subTest(mode=mode),self.assertRaises(ValueError):b.summarize(records)

    def test_cold_or_unique_regression_blocks_good_repeated_case(self):
        records=self.records()
        for index in (1,2):
            for row in records[index]['cases']:
                if row['mode']=='unique':row['wall_s']=6.2
        self.assertFalse(b.summarize(records)['eligible_for_confirmation'])

    def test_default_does_not_load_or_freeze(self):
        with patch.object(b,'freeze') as freeze,patch.object(b,'execute') as execute:
            b.main([]);freeze.assert_not_called();execute.assert_not_called()


if __name__=='__main__':unittest.main()
