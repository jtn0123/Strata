import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from benchmark_m5_hc import parse


def fixture(mode):
    rows=[]
    for k,m in ((10240,320),(320,10240)):
        for r in (1,2,3,4,5,8):
            for layout in (('plain','residual','exposed','strided','cancel','wide') if mode=='check' else ('plain','residual')):
                copies=1 if mode=='check' else 20
                c=dict(k=k,m=m,rows=r,layout=layout,samples=1 if mode=='check' else 60,copies_per_graph=copies,
                       cpu_nmse=1e-14,max_absolute_error=0.000001,wall_us_per_op=12.0,input_preserved=True,
                       elements=m*r,distinct_weight_bytes=k*m*2*copies)
                rows.append('M5_HC_CASE '+json.dumps(c))
    rows.append('M5_HC_DONE '+json.dumps(dict(mode=mode,cases=len(rows))))
    return '\n'.join(rows)


class HCEvidenceTests(unittest.TestCase):
    def test_route_proof_and_fallbacks_are_required(self):
        text=fixture('check')
        self.assertEqual(len(parse(text,'check','conv-direct','on')),72)
        with self.assertRaises(ValueError): parse(text,'check','hc-down-ks4','on')
        routes='\n'.join(f'M5_HC_ROUTE k=10240 m=320 rows={r} add={add} split=4'
                         for r in (4,5) for add,n in ((0,20),(1,5)) for _ in range(n))
        self.assertEqual(len(parse(text+'\n'+routes,'check','hc-down-ks4','on')),72)
        with self.assertRaises(ValueError): parse(text+'\n'+routes,'check','hc-down-ks4','off')

    def test_incomplete_or_inaccurate_evidence_is_rejected(self):
        text=fixture('check')
        for changed in (text.replace('M5_HC_DONE','MISSING'),text.replace('1e-14','NaN'),
                        text.replace('1e-14','0.001'),text.replace('"input_preserved": true','"input_preserved": false'),
                        text.replace('"copies_per_graph": 1','"copies_per_graph": 20')):
            with self.assertRaises(ValueError): parse(changed,'check','conv-direct','on')

    def test_perf_uses_distinct_weights_and_excludes_diagnostics(self):
        text=fixture('perf')
        self.assertEqual(len(parse(text,'perf','hc-up','on')),24)
        for changed in (text+'\nM5_HC_ROUTE k=320 m=10240 rows=4 add=0 split=1',
                        text.replace('"samples": 60','"samples": 1'),text.replace('131072000','6553600')):
            with self.assertRaises(ValueError): parse(changed,'perf','hc-up','on')


if __name__=='__main__': unittest.main()
