import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from benchmark_m5_qsa_models import dispatch
from benchmark_m5 import settings

class QsaModelGates(unittest.TestCase):
    def test_marker_requires_eligible_input(self):
        row=dict(pools=64,tokens=512,n_sel=256,stage='input-prepared')
        text='0.01.537.560 I M5_QSA_INPUT '+json.dumps(row)
        self.assertTrue(dispatch(text,True)['actual_input_prepared'])
        self.assertFalse(dispatch('',False)['actual_input_prepared'])
        for bad in ('',text+'\n'+text,'M5_QSA_INPUT '+json.dumps(dict(row,pools=576)),
                    'M5_QSA_INPUT '+json.dumps(dict(row,stage='graph-built')),
                    'M5_QSA_INPUT '+json.dumps(dict(row,n_sel=255)),
                    'M5_QSA_INPUT '+json.dumps(dict(row,tokens=True))):
            with self.assertRaises(ValueError):dispatch(bad,True)
        with self.assertRaises(ValueError):dispatch(text,False)

    def test_original_control_and_zero_swap_guard(self):
        spec=dict(engine='m5-qsa',depth=3,axis='m5_tuning',control='conv-direct',
                  candidates=['qsa-all-pools'],predict=256,
                  engine_for_value={'conv-direct':'m5-copy','qsa-all-pools':'m5-qsa'})
        a=settings(spec,'conv-direct','control',3)
        b=settings(spec,'qsa-all-pools','candidate',3)
        self.assertEqual((a.engine,b.engine),('m5-copy','m5-qsa'))
        self.assertEqual((a.swap_guard_bytes,b.swap_guard_bytes),(0,0))

if __name__=='__main__':unittest.main()
