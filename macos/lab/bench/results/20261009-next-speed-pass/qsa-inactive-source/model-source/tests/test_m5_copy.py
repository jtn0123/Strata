import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark_m5_copy import parse


class CopyEvidenceTests(unittest.TestCase):
    def perf_lines(self):
        lines = []
        graph = 0
        for rows in (1,4,5):
            for layout in ('contiguous','strided'):
                for sample in range(-3,40):
                    graph += 1
                    call = {'width':786432,'rows':rows,'layout':layout,'copy_bytes':786432*rows*4,
                            'sample':sample,'phase':'warmup' if sample<0 else 'measure'}
                    b = {'context':'target','graph':graph,'cb':0,'original_nodes':3,'op_counts':{'CPY':1,'VIEW':2},
                         'valid':True,'completed':True,'gpu_start_s':float(graph),'gpu_end_s':graph+0.001,'gpu_ms':1.0}
                    lines.extend([('M5_COPY_CALL',call),('M5_PROFILE',b),('M5_COPY_RETURN',{**call,'wall_us':1100})])
                lines.append(('M5_COPY_PASS',{'rows':rows,'layout':layout}))
        lines.append(('M5_COPY_DONE',{'mode':'perf','passed':6}))
        return lines

    def text(self, lines): return '\n'.join(marker+' '+json.dumps(value) for marker,value in lines)

    def test_complete_copy_timing_and_correctness_evidence(self):
        result = parse(self.text(self.perf_lines()),'perf')
        self.assertEqual(result['cases_passed'],6)
        self.assertEqual(len(result['summary']),6)
        self.assertTrue(all(r['samples']==40 and abs(r['gpu_us']-1000)<0.01 for r in result['summary']))

    def test_rejects_missing_copy_completion_samples_and_gpu_coverage(self):
        lines = self.perf_lines()
        for mutation in ('completion','copy-pass','sample','gpu-buffer','extra-operation','timestamp','call-return','graph'):
            changed = copy.deepcopy(lines)
            if mutation=='completion': changed.pop()
            elif mutation=='copy-pass': changed = [r for i,r in enumerate(changed) if i!=129]
            elif mutation=='sample': changed[9][1]['sample']=99
            elif mutation=='gpu-buffer': changed.pop(1)
            elif mutation=='extra-operation': changed[1][1]['op_counts']['ADD']=1
            elif mutation=='timestamp': changed[1][1]['gpu_end_s']=0
            elif mutation=='call-return': changed[2][1]['rows']=99
            elif mutation=='graph': changed[1][1]['graph']=99
            with self.subTest(mutation=mutation),self.assertRaises(ValueError): parse(self.text(changed),'perf')


if __name__ == '__main__': unittest.main()
