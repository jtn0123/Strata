import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from benchmark_m5_group import inventory,parse,ggml_row_bytes
from metal_environment import configure


def fixture(mode,group=False):
    lines=[]
    for rows,route,layout,index in inventory(mode):
        copies=8 if mode=='perf' or layout=='chain' else 1
        case=dict(rows=rows,route=route,layout=layout,route_index=index,samples=60 if mode=='perf' else 1,
                  triplets_per_graph=copies,input_ids_preserved=True,elements=3840*10*rows*copies,
                  distinct_experts=[10]*copies,cpu_nmse=1e-14,max_absolute_error=1e-6,wall_us_per_triplet=300.0)
        lines.append('M5_GROUP_CASE '+json.dumps(case))
        if mode=='check' and group and rows in (4,5) and layout!='weights-strided':
            for k,m,n in ((2560,640,10*copies),(640,2560,5*copies)):
                lines.extend('M5_GROUP_ROUTE '+json.dumps(dict(k=k,m=m,rows=rows,assignments=10*rows,map_bytes=280*rows,map_reused=False)) for _ in range(n))
    size=6*512*ggml_row_bytes(2560)*640+2*512*ggml_row_bytes(2560)*641+512*ggml_row_bytes(640)*2561
    lines.append('M5_GROUP_DONE '+json.dumps(dict(mode=mode,cases=len(inventory(mode)),weights_preserved=True,allocated_weight_bytes=size)))
    return '\n'.join(lines)


class GroupEvidenceTests(unittest.TestCase):
    def test_candidate_activation_and_fallback_proof_required(self):
        self.assertEqual(len(parse(fixture('check',True),'check','expert-group')),42)
        with self.assertRaises(ValueError): parse(fixture('check'),'check','expert-group')
        with self.assertRaises(ValueError): parse(fixture('check',True),'check','conv-direct')

    def test_missing_chain_inaccurate_or_corrupted_evidence_rejected(self):
        text=fixture('check',True)
        for changed in (text.replace('M5_GROUP_DONE','MISSING'),text.replace('1e-14','NaN'),
                        text.replace('1e-14','0.01'),text.replace('"weights_preserved": true','"weights_preserved": false'),
                        text.replace('"layout": "chain"','"layout": "plain"'),
                        text.replace('"input_ids_preserved": true','"input_ids_preserved": false')):
            with self.assertRaises(ValueError): parse(changed,'check','expert-group')

    def test_perf_excludes_diagnostics_and_requires_full_workset(self):
        text=fixture('perf');self.assertEqual(len(parse(text,'perf','expert-group')),6)
        route='\nM5_GROUP_ROUTE '+json.dumps(dict(k=2560,m=640,rows=4,assignments=40,map_bytes=1120,map_reused=False))
        for changed in (text+route,text.replace('"samples": 60','"samples": 1'),
                        text.replace('2124195840','708198400'),text.replace('"triplets_per_graph": 8','"triplets_per_graph": 1')):
            with self.assertRaises(ValueError): parse(changed,'perf','expert-group')

    def test_mode_is_isolated_and_inherited_flags_removed(self):
        for engine in ('baseline','mtp-mma','m5-copy','m5-hc'):
            with self.assertRaises(ValueError): configure({},engine,'on','expert-group')
        env,flags=configure({'GGML_M5_LAB_GROUP_TRACE':'1','GGML_M5_LAB_EXPERT_GROUP':'1'},'m5-group','on','conv-direct')
        self.assertNotIn('GGML_M5_LAB_GROUP_TRACE',env);self.assertNotIn('GGML_M5_LAB_EXPERT_GROUP',env)
        self.assertEqual(flags['variables'],{'GGML_M5_LAB_CONV_DIRECT':'1','GGML_METAL_TENSOR_ENABLE':'1'})


if __name__=='__main__': unittest.main()
