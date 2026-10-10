import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from benchmark_m5_gdn import inventory,fixture_inventory,buffer_inventory,evidence_elements,parse,read_buffers,trace_record,summarize_perf,ROOT


def fixture(tuning='gdn-row1'):
    lines=[];total=0
    for c in inventory('check'):
        shapes=[s for _,s in fixture_inventory(c)]
        wanted=[a for a in range(c['T']+1) if a==0 or c['T']-a<c['K']] if c['label']=='target' else []
        missing=[a for a in range(1,c['T']+1) if c['T']-a>=c['K']] if c['label']=='target' else []
        count=evidence_elements(c);total+=count
        r={**c,'samples':1,'distinct_state_buffers':1,'elements':count,
           'attention_values_checked':sum(s['S']*s['H']*s['T']*s['B'] for s in shapes),
           'state_values_checked':sum(s['S']**2*s['H']*s['B']*min(s['T'],s['K']) for s in shapes),
           'continuation_pairs':len(wanted),'rollback_prefixes':wanted,'unavailable_prefixes':missing,
           'scheduler_splits':1,'all_nodes_metal':True,'inputs_preserved':True,'unwritten_slots_preserved':True,
           'attention_nmse':1e-14,'state_nmse':1e-14,'max_absolute_error':1e-7,'wall_us_per_graph_sync':200.0}
        r.update(warmup_minimum_ms=0,warmup_elapsed_ms=0,warmup_graphs=0,wall_samples_us_per_graph_sync=[200.0])
        r['geometry']=dict(padded_cache=True,qkv_view_offsets_bytes=[12,16,20],
                           cache_view_offset_bytes=44,cache_slot_stride_floats=c['S']**2*c['H']*c['B']+37)
        lines.append('M5_GDN_CASE '+json.dumps(r));lines.append('M5_GDN_SHAPE '+json.dumps(trace_record(c,tuning)))
    lines.append('M5_GDN_DONE '+json.dumps(dict(mode='check',cases=32,elements=total,sync_included=True,
                   callbacks_used=False,evidence_format='sha256-buffer-manifest-v1')))
    return '\n'.join(lines)


class GDNEvidenceTests(unittest.TestCase):
    def test_missing_rollback_sentinel_accuracy_or_fusion_evidence_fails(self):
        text=fixture();self.assertEqual(len(parse(text,'check','gdn-row1')),32)
        for bad in (text.replace('"unwritten_slots_preserved": true','"unwritten_slots_preserved": false'),
                    text.replace('"rollback_prefixes": [0, 1]','"rollback_prefixes": [0]'),
                    text.replace('"state_nmse": 1e-14','"state_nmse": NaN'),
                    text.replace('"all_nodes_metal": true','"all_nodes_metal": false'),
                    text.replace('"wall_samples_us_per_graph_sync": [200.0]','"wall_samples_us_per_graph_sync": []'),
                    text.replace('M5_GDN_SHAPE','MISSING'),text.replace('"variant_rows": 1','"variant_rows": 2')):
            with self.assertRaises(ValueError):parse(bad,'check','gdn-row1')

    def test_digest_manifest_covers_exact_buffers_including_padding(self):
        rows=[{**b,'sha256':'a'*64} for c in inventory('check') for b in buffer_inventory(c)]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'outputs.jsonl'
            write=lambda records:path.write_text('\n'.join(json.dumps(r) for r in records)+'\n')
            write(rows);self.assertEqual(len(read_buffers(directory,'check')),960)
            for changed in (rows[:-1],[rows[0]]+rows[1:-1]+[rows[0]],
                            [{**rows[0],'bytes':rows[0]['bytes']-4}]+rows[1:],
                            [{**rows[0],'sha256':'garbage'}]+rows[1:]):
                write(changed)
                with self.assertRaises(ValueError):read_buffers(directory,'check')

    def test_identical_kernel_negative_control_blocks_false_promotion(self):
        paths={name:ROOT/'bench/features'/name for name in ('before','after','row4a','row4b','row1a','row1b','row2a','row2b')}
        def record(path):
            name=Path(path).name
            tuning='conv-direct' if name in ('before','after') else 'gdn-'+name[:4]
            latency=100 if tuning=='conv-direct' else 70 if tuning=='gdn-row4' else 75
            return dict(mode='perf',metal_environment=dict(tuning=tuning),
                        cases=[dict(wall_us_per_graph_sync=latency) for _ in inventory('perf')])
        candidates={t:[paths[n] for n in names] for t,names in (
                    ('gdn-row4',('row4a','row4b')),('gdn-row1',('row1a','row1b')),('gdn-row2',('row2a','row2b')))}
        with patch('benchmark_m5_gdn.read_record',side_effect=record):
            result=summarize_perf(paths['before'],paths['after'],candidates)
        self.assertFalse(any(c['qualifies_for_model_trial'] for c in result['cases']))


if __name__=='__main__':unittest.main()
