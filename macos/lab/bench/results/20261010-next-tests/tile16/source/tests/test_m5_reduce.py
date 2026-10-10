import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from benchmark_m5_reduce import parse
from benchmark_m5_next import output_signatures


class ReductionEvidenceTests(unittest.TestCase):
    def fixture(self):
        cases=[{'width':2560,'rows':r,'experts':10,'layout':'plain','elements':2560*r,
                'samples':100,'wall_us':30,'input_preserved':True} for r in (1,3,4,5)]
        return cases

    def text(self,cases,done=True):
        text='\n'.join('M5_REDUCE_CASE '+json.dumps(c) for c in cases)
        if done: text+='\nM5_REDUCE_DONE '+json.dumps({'mode':'perf','cases':4})
        return text

    def test_complete_exact_shape_timing(self):
        self.assertEqual(len(parse(self.text(self.fixture()),'perf')),4)

    def test_incomplete_wrong_shape_or_duplicate_timing_is_rejected(self):
        cases=self.fixture()
        with self.assertRaises(ValueError): parse(self.text(cases,False),'perf')
        for key,value in [('rows',6),('width',2559),('samples',99),('input_preserved',False)]:
            changed=copy.deepcopy(cases);changed[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError): parse(self.text(changed),'perf')
        changed=copy.deepcopy(cases);changed[1]=changed[0]
        with self.assertRaises(ValueError): parse(self.text(changed),'perf')

    def test_token_comparison_rejects_empty_and_duplicate_cases(self):
        with self.assertRaises(ValueError): output_signatures({'cases':[],'cached_cases':[]})
        c={'workload':'code','prompt_sha256':'a','repeat':1,'response':{'generated_token_ids':[1,2],'text':'ok'}}
        self.assertEqual(len(output_signatures({'cases':[c],'cached_cases':[]})),1)
        with self.assertRaises(ValueError): output_signatures({'cases':[c,c],'cached_cases':[]})


if __name__=='__main__': unittest.main()
