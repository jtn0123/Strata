import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from capture_m5_native import parse_lookup,parse_native,normalized_command
from metal_environment import configure


def lookup_fixture():
    address=0x100000000+192
    mapping=dict(role='lookup',tensor='per_layer_token_embd.weight',shard=1,file_offset=192,
                 tensor_bytes=28800138240,row_bytes=90,mapping_base=hex(address-192),
                 tensor_address=hex(address),lazy=True)
    op=dict(pool='0xabc',ordinal=0,begin_us=200,end_us=210,envelope_us=10,worker_sum_us=16,
            threads=2,rows=3,unique_rows=2,logical_bytes=180,pages=2,page_bytes=32768,
            page_size=16384,metadata_rows=3,metadata_complete=True,tensor_address=hex(address),
            demand_samples=[dict(row=17,address=hex(address+17*90),tensor_offset=17*90)])
    req=dict(workload='prose',warmup=False,begin_us=100,end_us=1100)
    return mapping,op,req


def text_for(mapping,ops):
    return 'M5_LOOKUP_MAPPING '+json.dumps(mapping)+'\n'+'\n'.join('M5_LOOKUP_OP '+json.dumps(op) for op in ops)


class NativeCaptureTests(unittest.TestCase):
    def test_upper_bound_screen_never_claims_ssd_wait(self):
        m,o,r=lookup_fixture();result=parse_lookup(text_for(m,[o]),[r])
        self.assertFalse(result['measured_SSD_wait']);self.assertFalse(result['prefetch_worth_investigating'])
        self.assertEqual(result['requests'][0]['upper_bound_percent'],1)
        # Parallel worker time is not the wall envelope; overlapping separate pools can overcount.
        second={**o,'pool':'0xdef','begin_us':202,'end_us':217,'envelope_us':15,'worker_sum_us':20}
        result=parse_lookup(text_for(m,[o,second]),[r])
        self.assertEqual(result['requests'][0]['upper_bound_percent'],2.5)
        self.assertTrue(result['prefetch_worth_investigating'])

    def test_boundary_operations_cannot_create_false_small_cost(self):
        m,o,r=lookup_fixture()
        for begin,end in ((90,200),(900,1200),(90,1200)):
            crossing={**o,'pool':'0xdef','begin_us':begin,'end_us':end,'envelope_us':end-begin}
            with self.assertRaises(ValueError):parse_lookup(text_for(m,[o,crossing]),[r])
        for requests in ([{**r,'end_us':100}],[r,r],[{**r,'begin_us':True}]):
            with self.assertRaises(ValueError):parse_lookup(text_for(m,[o]),requests)

    def test_exact_file_row_and_worker_attribution_required(self):
        m,o,r=lookup_fixture()
        for change in ({'shard':999},{'lazy':False},{'tensor_address':'0x100000000'},
                       {'file_offset':193},{'row_bytes':89}):
            with self.assertRaises(ValueError):parse_lookup(text_for({**m,**change},[o]),[r])
        changes=({'metadata_complete':False},{'worker_sum_us':21},{'page_size':4096},
                 {'logical_bytes':181},{'ordinal':1},{'rows':True},
                 {'demand_samples':[dict(row=17,address=o['tensor_address'],tensor_offset=1530)]})
        for change in changes:
            with self.assertRaises(ValueError):parse_lookup(text_for(m,[{**o,**change}]),[r])
        with self.assertRaises(ValueError):parse_lookup(text_for(m,[o,o]),[r])

    def test_timing_controls_and_opt_in_modes_are_isolated(self):
        env,flags=configure({'GGML_M5_LAB_GATE_TRACE':'1'},'m5-gate-lanes','on','gate-up4')
        self.assertEqual(flags['variables'],{'GGML_M5_LAB_CONV_DIRECT':'1','GGML_M5_LAB_GATE_UP':'2','GGML_METAL_TENSOR_ENABLE':'1'})
        self.assertNotIn('GGML_M5_LAB_GATE_TRACE',env)
        for engine,tuning in (('m5-copy','gate-up8'),('m5-gate','gdn-row1'),('m5-gdn','gate-up4'),('m5-copy','encoders0'),('m5-copy','head2')):
            with self.assertRaises(ValueError):configure({},engine,'on',tuning)
        for mode in ('head2','head4'):
            env,flags=configure({'GGML_M5_LAB_HEAD_TRACE':'1','GGML_M5_LAB_HEAD_NR0':'4'},'m5-head','on',mode)
            self.assertEqual(env['GGML_M5_LAB_HEAD_NR0'],mode[-1])
            self.assertNotIn('GGML_M5_LAB_HEAD_TRACE',env)
        for mode in ('encoders0','encoders2'):
            env,flags=configure({'GGML_M5_LAB_N_CB':'2','GGML_METAL_FUSION_DEBUG':'1'},'m5-encoders','on',mode)
            self.assertEqual(env['GGML_M5_LAB_N_CB'],mode[-1])
            self.assertNotIn('GGML_METAL_FUSION_DEBUG',env)
        env,flags=configure({'GGML_M5_LAB_N_CB':'2','GGML_M5_LAB_GATE_TRACE':'1','GGML_M5_LAB_LOOKUP_TRACE':'1',
                             'GGML_M5_LAB_GDN_ROWS':'1'},'m5-gdn','on','conv-direct')
        self.assertEqual(flags['variables'],{'GGML_M5_LAB_CONV_DIRECT':'1','GGML_METAL_TENSOR_ENABLE':'1'})
        self.assertNotIn('GGML_M5_LAB_LOOKUP_TRACE',env)
        self.assertNotIn('GGML_M5_LAB_N_CB',env)
        with self.assertRaises(ValueError):parse_native('','gate','gate-up8',[])
        with self.assertRaises(ValueError):parse_native('','gdn','gdn-row1',[])

    def test_settings_comparison_allows_only_binary_and_port_changes(self):
        a=['engine-a','--port','123','-c','4096','--draft-max','3']
        b=['engine-b','--port','456','-c','4096','--draft-max','3']
        self.assertEqual(normalized_command(a),normalized_command(b))
        b[-1]='4';self.assertNotEqual(normalized_command(a),normalized_command(b))
        with self.assertRaises(ValueError):normalized_command(['engine','-c','4096'])


if __name__=='__main__':unittest.main()
