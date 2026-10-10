"""Mapped spans and repeated reservations must not become a false RAM-fit claim."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from memory_budget import allocations,report,MIB


class BudgetTests(unittest.TestCase):
    def test_separate_attention_and_indexer_caches_are_not_overwritten(self):
        text='''load_tensors: loading model tensors
llama_kv_cache: MTL0 KV buffer size = 96.00 MiB
llama_memory_hybrid_idx: creating indexer KV cache, size = 4096 cells
llama_kv_cache: MTL0 KV buffer size = 24.00 MiB
load_tensors: loading model tensors
llama_kv_cache: MTL0 KV buffer size = 8.00 MiB
llama_memory_hybrid_idx: creating indexer KV cache, size = 4096 cells
llama_kv_cache: MTL0 KV buffer size = 2.00 MiB
sched_reserve: MTL0 compute buffer size = 148.11 MiB
sched_reserve: MTL0 compute buffer size = 148.11 MiB
'''
        result=allocations(text)
        caches=[e for e in result['entries'] if e['kind']=='KV']
        self.assertEqual(len(caches),4)
        self.assertEqual(sum(e['bytes'] for e in caches),130*MIB)
        self.assertEqual(result['known_private_buffer_bytes'],130*MIB+round(148.11*MIB))

    def test_roles_mapping_exclusion_and_latest_reserve(self):
        text='''load_tensors: loading model tensors
load_tensors: MTL0_Mapped model buffer size = 35870.28 MiB
load_tensors: CPU_Mapped model buffer size = 27465.95 MiB
llama_kv_cache: MTL0 KV buffer size = 96.00 MiB
sched_reserve: MTL0 compute buffer size = 185.61 MiB
load_tensors: loading model tensors
load_tensors: MTL0_Mapped model buffer size = 45.64 MiB
load_tensors: CPU_REPACK model buffer size = 450.00 MiB
sched_reserve: MTL0 compute buffer size = 100.00 MiB
sched_reserve: MTL0 compute buffer size = 148.11 MiB
'''
        result=allocations(text)
        self.assertEqual(len(result['lazy_file_mappings']),1)
        self.assertEqual(result['missing_roles'],[])
        helper=[e for e in result['entries'] if e['role']=='helper' and e['kind']=='compute']
        self.assertEqual(len(helper),1)
        self.assertEqual(helper[0]['bytes'],round(148.11*MIB))
        self.assertEqual(result['known_private_buffer_bytes'],round(96*MIB)+round(185.61*MIB)+round(148.11*MIB))

    def test_unknown_fit_is_explicit_and_table_is_not_counted_as_resident_weights(self):
        inventory={'shards':[{'tensors':[{'name':'weight','size_bytes':100},{'name':'per_layer_token_embd.weight','size_bytes':1000}]}]}
        registry={'mtp_shared_packed_q3':{'files':[{'size_bytes':20}]}}
        result=report(inventory,registry)
        self.assertEqual(result['target_unique_tensor_bytes'],100)
        self.assertEqual(result['lazy_lookup_file_bytes'],1000)
        self.assertEqual(result['admission_decision'],'not-an-admission-controller')
        self.assertIsNone(result['observed_allocations'])
