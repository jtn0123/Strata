"""Read geometry is bounded and file probes cannot silently accept changed bytes."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import profile_lookup_io as lookup


class LookupTests(unittest.TestCase):
    def tensor(self): return {'name':'per_layer_token_embd.weight','quant':'IQ4_NL','shape':[160,1000],'size_bytes':90000,'offset':192}

    def test_offsets_stay_in_shard_include_full_rows_and_respect_bound(self):
        tensor=self.tensor()
        samples=lookup.spans(tensor,90192)
        self.assertEqual(samples,lookup.spans(tensor,90192))
        self.assertLessEqual(sum(s['length'] for s in samples)*3,lookup.MAX_READ_BYTES)
        for s in samples:
            row=192+s['row']*90
            self.assertLessEqual(s['offset'],row)
            self.assertGreaterEqual(s['offset']+s['length'],row+90)
            self.assertLessEqual(s['offset']+s['length'],90192)
        for mutate in (lambda t:t.update(offset=200),lambda t:t.update(size_bytes=90001),lambda t:t.update(quant='F16')):
            bad=copy.deepcopy(tensor);mutate(bad)
            with self.assertRaises(ValueError):lookup.spans(bad,90192)
        with self.assertRaises(ValueError):lookup.spans(tensor,90192,129)

    def test_short_read_fails_and_retains_failure_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'lookup.gguf';source.write_bytes(b'x'*90192)
            record=lookup.plan({'shards':[{'path':source.name,'expected_file_bytes':90192,'tensors':[self.tensor()]}]},1)
            with patch.object(lookup.os,'pread',return_value=b''),self.assertRaisesRegex(RuntimeError,'Short lookup'):
                lookup.execute(record,source,root/'result')
            self.assertEqual(record['status'],'failed')
            self.assertTrue((root/'result/probe.json').exists())

    def test_default_plan_never_opens_the_payload(self):
        with patch.object(lookup,'execute') as execute:lookup.main([])
        execute.assert_not_called()
