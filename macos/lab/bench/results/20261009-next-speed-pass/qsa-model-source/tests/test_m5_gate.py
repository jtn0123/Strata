import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from benchmark_m5_gate import inventory,output_elements,parse,POSITIVE


def evidence(mode='check',enabled=True):
    lines=[]
    for rows,route,layout,index in inventory(mode):
        copies=8 if mode=='perf' or layout=='chain' else 1;samples=60 if mode=='perf' else 1
        c=dict(rows=rows,route=route,layout=layout,route_index=index,samples=samples,
               triplets_per_graph=copies,input_ids_preserved=True,output_elements=output_elements(rows,layout,copies),
               distinct_experts=[10]*copies,cpu_nmse=1e-14,max_absolute_error=1e-7,max_scaled_error=1e-7,
               wall_us_per_triplet=300.0,wall_samples_us_per_triplet=[300.0]*samples,
               eligible=rows in (4,5) and layout in POSITIVE,scheduler=True,cpu_compute_nodes=0,graph_buffer_bytes=100000)
        lines.append('M5_GATE_CASE '+json.dumps(c))
        if enabled and mode=='check' and c['eligible']:
            lines.extend('M5_GATE_ROUTE '+json.dumps(dict(phase='dispatch',k=2560,m=640,rows=rows,tile=8,nodes=3)) for _ in range(5*copies))
    lines.append('M5_GATE_DONE '+json.dumps(dict(mode=mode,cases=len(inventory(mode)),weights_preserved=True,
                    allocated_weight_bytes=2124195840,scheduler=True,cpu_compute_nodes=0)))
    return '\n'.join(lines)


class GateEvidenceTests(unittest.TestCase):
    def test_fusion_and_fallback_dispatch_counts_required(self):
        text=evidence();self.assertEqual(len(parse(text,'check','gate-up8')),58)
        with self.assertRaises(ValueError):parse(evidence(enabled=False),'check','gate-up8')
        with self.assertRaises(ValueError):parse(text,'check','conv-direct')
        extra='\nM5_GATE_ROUTE '+json.dumps(dict(phase='dispatch',k=2560,m=640,rows=3,tile=8,nodes=3))
        with self.assertRaises(ValueError):parse(text+extra,'check','gate-up8')

    def test_cpu_fallback_nonfinite_results_and_incomplete_samples_fail(self):
        text=evidence()
        for bad in (text.replace('"cpu_compute_nodes": 0','"cpu_compute_nodes": 1'),
                    text.replace('"max_scaled_error": 1e-07','"max_scaled_error": NaN'),
                    text.replace('"weights_preserved": true','"weights_preserved": false'),
                    text.replace('"input_ids_preserved": true','"input_ids_preserved": false'),
                    text.replace('"wall_samples_us_per_triplet": [300.0]','"wall_samples_us_per_triplet": []')):
            with self.assertRaises(ValueError):parse(bad,'check','gate-up8')

    def test_timing_prohibits_diagnostics(self):
        text=evidence('perf');self.assertEqual(len(parse(text,'perf','gate-up8')),6)
        extra='\nM5_GATE_ROUTE '+json.dumps(dict(phase='structural',k=2560,m=640,rows=4,tile=8))
        with self.assertRaises(ValueError):parse(text+extra,'perf','gate-up8')


if __name__=='__main__':unittest.main()
