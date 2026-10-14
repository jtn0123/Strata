"""Telemetry truth, bounded guard reads, provenance labels and privacy filtering."""
from collections import deque
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import performance_metrics as perf


class PerformanceTests(unittest.TestCase):
    def test_native_timing_scope_and_acceptance(self):
        row = dict(finish='stop', time=100, decode_tok_s=55)
        last = dict(native_timings=dict(predicted_per_second=60, prompt_per_second=220, draft_n=5, draft_n_accepted=3))
        with patch.object(perf.time, 'time', return_value=100.5):
            result = perf.measured_history(row, dict(started=100, first_token=100.125), last, 'model')
        self.assertEqual(result['server_first_token_ms'], 125)
        self.assertEqual(result['server_duration_ms'], 500)
        self.assertEqual(result['generation_tps'], 60)
        self.assertEqual(result['generation_source'], 'native')
        self.assertEqual(result['draft_acceptance_percent'], 60)
        self.assertEqual(row, dict(finish='stop', time=100, decode_tok_s=55))

    def test_unknowns_are_not_zeros_or_invalid_percentages(self):
        for accepted, proposed in ((7, 5), (0, 0), (None, 5)):
            result = perf.measured_history(dict(finish='cancel'), {}, dict(native_timings=dict(draft_n=proposed, draft_n_accepted=accepted)), 'mock')
            self.assertIsNone(result['server_first_token_ms'])
            self.assertIsNone(result['generation_tps'])
            self.assertIsNone(result['draft_acceptance_percent'])
            self.assertEqual(result['measurement_kind'], 'mock')

    def test_nonfinite_negative_and_boolean_values_rejected(self):
        for value in (True, '60', float('nan'), float('inf'), -1):
            self.assertIsNone(perf.number(value))
        self.assertEqual(perf.number(0), 0)

    def test_bounded_guard_uses_last_complete_fresh_sample(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root/'run/memory.jsonl'; path.parent.mkdir()
            path.write_text('x'*20000+'\n'+json.dumps(dict(rss_bytes=123, pressure_level=1))+'\n{"incomplete":')
            self.assertEqual(perf.guard_sample(path, runtime_root=root)['rss_bytes'], 123)
            self.assertIsNone(perf.guard_sample(path, now=path.stat().st_mtime+4, runtime_root=root))

    def test_guard_path_cannot_read_models_or_foreign_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); runtime=root/'runtime'; runtime.mkdir()
            foreign=root/'models/memory.jsonl'; foreign.parent.mkdir(); foreign.write_text('{"rss_bytes":999}\n')
            self.assertIsNone(perf.guard_sample(foreign, runtime_root=runtime))
            link=runtime/'memory.jsonl'; link.symlink_to(foreign)
            self.assertIsNone(perf.guard_sample(link, runtime_root=runtime))

    def test_resources_reuse_guard_and_keep_system_swap_separate(self):
        with patch.object(perf.psutil, 'virtual_memory', return_value=SimpleNamespace(available=100,total=256)), \
             patch.object(perf.psutil, 'swap_memory', return_value=SimpleNamespace(used=50)), \
             patch.object(perf, 'guard_sample', return_value=dict(rss_bytes=12,pressure_level=2)):
            result=perf.resources(dict(initial_swap_bytes=40))
        self.assertEqual(result['swap_used_bytes'],50)
        self.assertEqual(result['new_swap_bytes'],10)
        self.assertEqual(result['pressure_level'],2)

    def test_service_retains_existing_metrics_and_filters_private_config(self):
        class Mock: pass
        class Original:
            def __init__(self):
                self.engine=Mock(); self.engine.last={}
                self.status={}; self.history=deque(maxlen=30)
            def metrics(self): return dict(requests=list(self.history),original='unchanged')
        Service=perf.tracked_service(Original,Mock,dict(model='small',engine='baseline',batch=1536,ubatch=1536,
            api_key='synthetic-secret',model_path='private-path'))
        service=Service();service.history.append(dict(finish='stop'))
        with patch.object(perf,'resources',return_value={}): result=service.metrics()
        self.assertEqual(result['original'],'unchanged')
        self.assertEqual(service.history.maxlen,30)
        self.assertEqual(result['performance']['measurement_kind'],'mock')
        self.assertEqual(result['performance']['settings'],dict(model='small',engine='baseline',batch=1536,ubatch=1536))
        self.assertNotIn('synthetic-secret',json.dumps(result))
        self.assertNotIn('private-path',json.dumps(result))


if __name__ == '__main__': unittest.main()
