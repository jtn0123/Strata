import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import benchmark_m5_route_map as probe

class RouteMapEvidenceGates(unittest.TestCase):
    def fixture(self):
        expected=dict(rows=512,route='uniform',id_stride_bytes=2048,layout='plain',
                      precision='default',terminal_only=False,round=0)
        row=dict(expected,mode='perf',scope='reuse',eligible=True,executions=10,
                 triplets_per_graph=2,count_delta=20,counter_available=True,
                 inputs_preserved=True,ids_preserved=True,all_nodes_metal=True,
                 scheduler_splits=1,cpu_compute_nodes=0,evaluation_callbacks=False,
                 outputs=[dict(finite=True)],allocation_estimate_bytes=1024,
                 ns_samples=[50000000.0]*7,median_ns=50000000.0,
                 warmup_ns=500000000,pipeline_primed=True,
                 block_iterations=[10]*7,block_ns=[500000000]*7)
        done=dict(mode='perf',scope='reuse',cases=1,models_loaded=False,
                  weights_preserved=True,route_source='synthetic')
        return expected,row,done

    def parse(self,expected,row,done):
        text='M5_ROUTE_MAP_CASE '+json.dumps(row)+'\nM5_ROUTE_MAP_DONE '+json.dumps(done)
        with patch.object(probe,'inventory',return_value=[expected]):
            return probe.parse(text,'perf','reuse')

    def test_partial_activation_is_rejected(self):
        expected,row,done=self.fixture()
        self.assertEqual(len(self.parse(expected,row,done)),1)
        for delta in (0,1,19,21,True):
            with self.assertRaises(ValueError):self.parse(expected,dict(row,count_delta=delta),done)
        expected=dict(expected,rows=513);row=dict(row,rows=513,eligible=False,count_delta=0)
        self.assertEqual(len(self.parse(expected,row,done)),1)
        with self.assertRaises(ValueError):self.parse(expected,dict(row,count_delta=20),done)

    def test_timing_must_match_duration_and_iterations(self):
        expected,row,done=self.fixture()
        broken=dict(row,ns_samples=[40000000.0]*7,median_ns=40000000.0)
        with self.assertRaises(ValueError):self.parse(expected,broken,done)
        with self.assertRaises(ValueError):self.parse(expected,dict(row,block_ns=[500000000]*6),done)

if __name__=='__main__':unittest.main()
