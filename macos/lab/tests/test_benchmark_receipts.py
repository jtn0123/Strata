"""Load-free benchmark failure, model identity and cache activation receipts."""
from contextlib import ExitStack
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import benchmark
import benchmark_cache


class BenchmarkReceiptTests(unittest.TestCase):
    def root(self, folder):
        root = Path(folder)
        for relative in ('bench/results', 'config', 'scripts', 'models/small'):
            (root / relative).mkdir(parents=True)
        model = root / 'models/small/tiny.gguf'
        model.write_bytes(b'weights')
        (root / 'config/models.json').write_text(json.dumps({'small': {'files': [dict(
            path=model.name, size_bytes=7, sha256=hashlib.sha256(b'weights').hexdigest())]}}))
        (root / 'config/runtime.json').write_text(json.dumps({
            'llama_cpp': {'revision': 'fixture'}, 'strata_macos': {'revision': 'fixture'}}))
        for name in ('native_backend.py', 'benchmark_cache.py'):
            (root / 'scripts' / name).write_text('owned fixture')
        return root

    def args(self):
        return SimpleNamespace(model='small', label='receipt-fixture', engine='baseline',
            spec='none', draft=3, draft_placement='gpu', draft_model='mtp',
            temperature=0, repeats=1, histories=[512], context=4096, batch=512,
            ubatch=128, cache_type='f16', threads=8, predict=2, prompts=[64],
            warmups=0, extended_checks=False)

    def patches(self, module, root, memory=None):
        stack = ExitStack()
        monitor = SimpleNamespace(thread=SimpleNamespace(start=lambda: None), finish=lambda: memory or dict(
            guard=None, monitor_healthy=True, child_exited=True, swap_growth_bytes=0))
        factory = Mock(return_value=monitor)
        factory.baseline.return_value = {}
        for name, value in {
            'ROOT': root, 'verify_engine': lambda *a: {'engine': 'baseline'},
            'host_snapshot': lambda: {}, 'server_command': lambda *a, **k: ['owned-fixture'],
            'command_output': lambda command: 'fixture' if command[-1] == 'HEAD' else '',
            'wait_ready': lambda *a, **k: 0, 'Monitor': factory,
        }.items(): stack.enter_context(patch.object(module, name, value))
        sockets = stack.enter_context(patch.object(module.socket, 'socket'))
        sockets.return_value.__enter__.return_value.getsockname.return_value = ('127.0.0.1', 8123)
        child = SimpleNamespace(pid=123, poll=lambda: 0)
        stack.enter_context(patch.object(module.subprocess, 'Popen', return_value=child))
        return stack

    def receipt(self, root):
        return json.loads(next((root / 'bench/results').glob('*/*.json')).read_text())

    def test_model_corruption_is_rejected_before_either_documented_benchmark_launch(self):
        for module in (benchmark, benchmark_cache):
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory() as folder:
                root = self.root(folder)
                (root / 'models/small/tiny.gguf').write_bytes(b'changed')
                args = self.args()
                with self.patches(module, root), patch.object(module.subprocess, 'Popen') as spawn:
                    with self.assertRaisesRegex(RuntimeError, 'SHA256 differs'): module.run(args)
                spawn.assert_not_called()
                record = self.receipt(root)
                self.assertEqual(record['status'], 'failed')
                self.assertTrue(record['preparation_failed'])

    def test_failed_engine_verification_keeps_receipt_before_any_native_execution(self):
        for module in (benchmark, benchmark_cache):
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory() as folder:
                root = self.root(folder)
                args = self.args()
                with patch.object(module, 'ROOT', root), \
                     patch.object(module, 'verify_engine', side_effect=RuntimeError('Replaced native library')), \
                     patch.object(module.subprocess, 'Popen') as spawn:
                    with self.assertRaisesRegex(RuntimeError, 'Replaced native library'): module.run(args)
                spawn.assert_not_called()
                self.assertEqual(self.receipt(root)['status'], 'failed')

    def test_fresh_campaign_cannot_pass_teardown_swap_above_its_guard_budget(self):
        original_monitor = benchmark.Monitor
        with tempfile.TemporaryDirectory() as folder:
            root = self.root(folder); swap = {'used': 0}
            class FinalSwapMonitor(original_monitor):
                def finish(self):
                    self.thread.join(timeout=2)
                    swap['used'] = 3*1024**3
                    return super().finish()
            def request(base, path, payload=None, **kw):
                if path == '/apply-template': return {'prompt': 'fixture'}
                if path == '/tokenize': return {'tokens': list(range(1000))}
                if path == '/v1/chat/completions':
                    answer = '391' if 'multiplied' in payload['messages'][0]['content'] else 'violet-730'
                    return {'choices': [{'message': {'content': answer}}]}
                return {}
            response = dict(ttft_s=.1, wall_s=.3, text='fixture', generated_token_ids=[7, 9],
                final=dict(stop=True, timings=dict(prompt_n=64, predicted_n=2,
                                                  predicted_per_second=50, prompt_per_second=500)))
            with self.patches(benchmark, root) as stack:
                for name, value in {'Monitor': FinalSwapMonitor, 'request': request,
                                   'stream_completion': lambda *a, **k: response,
                                   'experiment_environment': lambda *a: ({}, {}),
                                   'configure': lambda *a: ({}, {})}.items():
                    stack.enter_context(patch.object(benchmark, name, value))
                stack.enter_context(patch.object(benchmark.urllib.request, 'urlopen', return_value=io.BytesIO(b'')))
                stack.enter_context(patch.object(benchmark.psutil, 'Process', return_value=SimpleNamespace(
                    memory_info=lambda: SimpleNamespace(rss=1, vms=1))))
                stack.enter_context(patch.object(benchmark.psutil, 'virtual_memory', return_value=SimpleNamespace(available=8*1024**3)))
                stack.enter_context(patch.object(benchmark.psutil, 'swap_memory', side_effect=lambda: SimpleNamespace(used=swap['used'])))
                stack.enter_context(patch.object(benchmark.psutil, 'disk_io_counters', return_value=None))
                record = benchmark.run(self.args())
            self.assertTrue(all(check['passed'] for check in record['checks']))
            self.assertTrue(record['memory']['monitor_healthy'])
            self.assertEqual(record['memory']['swap_growth_bytes'], 3*1024**3)
            self.assertEqual(record['status'], 'failed')

    def cache_campaign(self, root, *, hits=True, memory=None, real_engine=False, fault=None):
        active = {'messages': [], 'request': 0}
        class Tokenizer:
            def __init__(self, *a): pass
            def encode(self, messages, **kw): return [99] if isinstance(messages, str) else messages
            def decode(self, ids):
                if fault and active['request'] == fault['request']:
                    if fault.get('decode_error'): raise fault['decode_error']
                    return fault.get('text', 'rejected fixture')
                return text_for(active['messages'])
        class Template:
            def __init__(self, *a): pass
            def render(self, messages, **kw): return messages
        def text_for(messages):
            if len(messages) > 1:
                text = ('maple-99117' if 'maple-99117' in messages[0]['content'] else 'cedar') + ',violet,basil'
            elif 'fresh chat label' in messages[0]['content']:
                text = 'plum-70291' if 'plum-70291' in messages[0]['content'] else 'lime-81302'
            else: text = 'READY'
            return text
        def measure(engine, tokenizer, messages, *a):
            text = text_for(messages)
            reused = int(hits and engine.prompt_cache)
            return dict(ttft_s=.1, wall_s=.3, token_ids=[99], text=text, prompt_tokens=len(messages),
                prompt_sha256=hashlib.sha256(json.dumps(messages).encode()).hexdigest(), native_timings=dict(
                    predicted_n=1, predicted_per_second=50, prompt_per_second=500,
                    prompt_n=len(messages)-reused, cache_n=reused))
        class Connection:
            status = 200
            def __init__(self, *a, **kw): self.sock = self; self.payload = {}
            def request(self, method, path, body, **kw):
                self.payload = json.loads(body); active['messages'] = self.payload['prompt']
                active['request'] += 1
            def getresponse(self): return self
            def __iter__(self):
                reused = int(self.payload['cache_prompt'])
                defect = fault if fault and active['request'] == fault['request'] else {}
                timings = dict(predicted_n=2, predicted_per_second=50, predicted_ms=40, prompt_ms=10,
                    prompt_per_second=500, prompt_n=len(self.payload['prompt'])-reused, cache_n=reused)
                timings.update(defect.get('timings', {}))
                yield b'data: '+json.dumps(dict(tokens=defect.get('tokens', [7, 99]))).encode()+b'\n'
                if defect.get('error'): raise defect['error']
                for row in (dict(stop=True, timings=timings),):
                    yield b'data: '+json.dumps(row).encode()+b'\n'
            def shutdown(self, *a): pass
            def close(self): pass
        with self.patches(benchmark_cache, root, memory) as stack:
            for name, value in {
                'request': lambda *a, **k: dict(default_generation_settings=dict(n_ctx=4096),
                    build_info='fixture', model_path='fixture'),
                'NativeTokenizer': Tokenizer, 'NativeTemplate': Template,
                'build_workload': lambda *a: dict(messages=[dict(role='user', content='ledger cedar')],
                    question='labels', expected=['cedar', 'violet', 'basil'], records=3),
            }.items(): stack.enter_context(patch.object(benchmark_cache, name, value))
            if real_engine:
                stack.enter_context(patch('native_backend.http.client.HTTPConnection', Connection))
            else:
                stack.enter_context(patch.object(benchmark_cache, 'NativeEngine',
                    lambda base, props, model, flag, **kw: SimpleNamespace(prompt_cache=flag, stop_ids=kw['stop_ids'])))
                stack.enter_context(patch.object(benchmark_cache, 'measure', measure))
            stack.enter_context(patch.object(benchmark_cache.psutil, 'Process',
                return_value=SimpleNamespace(memory_info=lambda: SimpleNamespace(rss=10))))
            stack.enter_context(patch.object(benchmark_cache.psutil, 'swap_memory', return_value=SimpleNamespace(used=0)))
            benchmark_cache.run(self.args())

    def test_cache_campaign_requires_actual_prefix_reuse(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.root(folder)
            with self.assertRaisesRegex(AssertionError, 'did not reuse'): self.cache_campaign(root, hits=False)
            self.assertEqual(self.receipt(root)['status'], 'failed')

    def test_cache_campaign_rejects_late_guard_failure_after_correct_answers(self):
        for memory in (dict(guard='late guard', monitor_healthy=True, child_exited=True),
                       dict(guard=None, monitor_healthy=False, child_exited=True)):
            with self.subTest(memory=memory), tempfile.TemporaryDirectory() as folder:
                root = self.root(folder)
                with self.assertRaises(SystemExit): self.cache_campaign(root, memory=memory)
                record = self.receipt(root)
                self.assertTrue(all(c['passed'] for c in record['checks']))
                self.assertEqual(record['status'], 'failed')

    def test_cache_campaign_records_verified_inputs_when_all_gates_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.root(folder); self.cache_campaign(root)
            record = self.receipt(root)
            self.assertEqual(record['status'], 'passed')
            self.assertIn('small', record['model_provenance']['models'])
            self.assertEqual(record['selected_engine']['engine'], 'baseline')

    def test_cache_pairs_keep_excluded_warmup_and_alternating_order(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.root(folder)
            args = self.args(); args.repeats = 2
            with patch.object(self, 'args', return_value=args):
                self.cache_campaign(root)
            cases = self.receipt(root)['cases']
            self.assertEqual([(case['repeat'], case['cache'], case['warmup']) for case in cases],
                             [(0, False, True), (0, True, True), (1, True, False),
                              (1, False, False), (2, False, False), (2, True, False)])
            for left, right in zip(cases[::2], cases[1::2], strict=True):
                self.assertEqual(left['prompt_sha256'], right['prompt_sha256'])
                self.assertEqual(left['order'], [left['cache'], right['cache']])
                self.assertEqual(left['prime']['native_timings']['cache_n'], 0)
                self.assertEqual(right['prime']['native_timings']['cache_n'], 0)

    def test_real_engine_construction_and_measurement_recognize_the_tokenizers_eos(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.root(folder); self.cache_campaign(root, real_engine=True)
            record = self.receipt(root)
            self.assertEqual(record['status'], 'passed')
            self.assertTrue(all(c['token_ids'] == [7, 99] for c in record['cases']))
            self.assertTrue(all(c['native_timings']['cache_n'] > 0 for c in record['cases'] if c['cache']))

    def test_cache_measure_rejects_wrong_counts_capped_output_and_invalid_metrics(self):
        good = dict(predicted_n=2, prompt_n=3, cache_n=0,
                    predicted_per_second=50, prompt_per_second=500)
        class Engine:
            prompt_cache = False
            stop_ids = {99}
            def generate(self, *a): yield from self.tokens
        for timings, tokens in ((dict(good, predicted_n=999), [7, 99]),
                                (dict(good, prompt_n=2), [7, 99]),
                                (good, [7, 8]), (dict(good, predicted_per_second=float('nan')), [7, 99])):
            engine = Engine(); engine.tokens = tokens; engine.last = {'native_timings': timings}
            tokenizer = SimpleNamespace(decode=lambda ids: 'fixture')
            with self.subTest(timings=timings, tokens=tokens), self.assertRaises(ValueError):
                benchmark_cache.measure(engine, tokenizer, [1, 2, 3])

    def test_rejected_cache_phases_preserve_raw_response_and_prior_evidence(self):
        for request, stage, completed, cap in ((1, 'prime', 0, 16), (2, 'followup', 0, 96),
                                              (9, 'seed', 4, 32), (10, 'cache_on', 4, 96),
                                              (11, 'cache_off', 4, 96)):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as folder:
                root = self.root(folder)
                tokens = [7] * cap
                fault = dict(request=request, tokens=tokens, timings=dict(predicted_n=cap))
                with self.assertRaisesRegex(ValueError, 'normal-EOS'):
                    self.cache_campaign(root, real_engine=True, fault=fault)
                record = self.receipt(root)
                self.assertEqual(record['status'], 'failed')
                self.assertEqual(len(record['cases']), completed)
                rejected = record['rejected_cases'][0]
                self.assertEqual((rejected['status'], rejected['stage']), ('rejected', stage))
                response = rejected[stage]
                self.assertEqual(response['status'], 'rejected')
                self.assertEqual(response['token_ids'], tokens)
                self.assertEqual(response['text'], 'rejected fixture')
                self.assertEqual(response['native_timings']['predicted_n'], cap)
                self.assertEqual(response['max_new'], cap)
                self.assertEqual(response['prompt_sha256'], hashlib.sha256(
                    json.dumps(response['prompt_token_ids']).encode()).hexdigest())
                if stage == 'followup': self.assertEqual(rejected['prime']['token_ids'], [7, 99])
                if stage in ('cache_on', 'cache_off'): self.assertEqual(rejected['seed']['token_ids'], [7, 99])
                if stage == 'cache_off': self.assertEqual(rejected['cache_on']['token_ids'], [7, 99])

    def test_rejected_cache_counter_and_semantic_failures_remain_auditable(self):
        faults = (dict(request=1, text='WRONG', error_text='ledger instruction'),
                  dict(request=2, timings=dict(predicted_n=999), error_text='output count'),
                  dict(request=4, timings=dict(cache_n=0, prompt_n=3), error_text='did not reuse'))
        for fault in faults:
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as folder:
                root = self.root(folder)
                expected = AssertionError if fault['request'] in (1, 4) else ValueError
                with self.assertRaisesRegex(expected, fault['error_text']):
                    self.cache_campaign(root, real_engine=True, fault=fault)
                record = self.receipt(root)
                rejected = record['rejected_cases'][0]
                self.assertEqual(rejected['status'], 'rejected')
                response = rejected['prime'] if fault['request'] == 1 else rejected['followup']
                self.assertEqual(response['text'], fault.get('text', 'rejected fixture'))
                if fault['request'] == 2: self.assertEqual(response['native_timings']['predicted_n'], 999)
                if fault['request'] == 4: self.assertEqual(response['native_timings']['cache_n'], 0)

    def test_complete_wrong_answers_retain_legacy_pair_and_diagnostic_semantics(self):
        for request in (6, 10):
            with self.subTest(request=request), tempfile.TemporaryDirectory() as folder:
                root = self.root(folder)
                with self.assertRaises(SystemExit):
                    self.cache_campaign(root, real_engine=True, fault=dict(request=request, text='WRONG'))
                record = self.receipt(root)
                self.assertEqual(record['status'], 'correctness-failure')
                self.assertEqual(len(record['cases']), 4)
                self.assertEqual(record.get('rejected_cases', []), [])
                self.assertTrue(any(not check['passed'] for check in record['checks']))
                summary = record['summary'][0]
                self.assertEqual(summary['cache_on']['all_correct'], request != 6)
                self.assertEqual(summary['cache_on']['repeats'], 1)
                self.assertEqual(summary['cache_off']['repeats'], 1)

    def test_rejected_cache_nonfinite_metrics_have_strict_json_receipts(self):
        values = (('predicted_per_second', float('nan'), 'NaN'),
                  ('predicted_n', float('inf'), 'Infinity'),
                  ('predicted_n', float('-inf'), '-Infinity'),
                  ('predicted_n', [2], [2]), ('predicted_n', True, True))
        for key, invalid, preserved in values:
            with self.subTest(key=key, invalid=invalid), tempfile.TemporaryDirectory() as folder:
                root = self.root(folder)
                with self.assertRaises(ValueError):
                    self.cache_campaign(root, real_engine=True, fault=dict(request=2,
                        timings={key: invalid}))
                record = self.receipt(root)
                response = record['rejected_cases'][0]['followup']
                self.assertEqual(response['native_timings'][key], preserved)
                json.dumps(record, allow_nan=False)

    def test_cache_counter_failure_is_not_replaced_by_decode_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.root(folder)
            failure = ValueError('counter fixture')
            original = benchmark_cache.completion_counts
            calls = {'count': 0}
            def validate(*args, **kwargs):
                calls['count'] += 1
                if calls['count'] == 2: raise failure
                return original(*args, **kwargs)
            with patch.object(benchmark_cache, 'completion_counts', validate), \
                    self.assertRaisesRegex(ValueError, 'counter fixture') as caught:
                self.cache_campaign(root, real_engine=True, fault=dict(request=2,
                    decode_error=OSError('decode fixture')))
            self.assertIs(caught.exception, failure)
            response = self.receipt(root)['rejected_cases'][0]['followup']
            self.assertEqual(response['token_ids'], [7, 99])
            self.assertIn('decode fixture', response['text_error'])

    def test_partial_cache_transport_and_cancellation_preserve_original_failure(self):
        from native_backend import engine_failure
        for error, decode_error in ((OSError('transport fixture'), None),
                                    (OSError('transport fixture'), OSError('decode fixture')),
                                    (KeyboardInterrupt('cancel fixture'), None)):
            with self.subTest(error=error, decode_error=decode_error), tempfile.TemporaryDirectory() as folder:
                root = self.root(folder)
                expected = KeyboardInterrupt if isinstance(error, KeyboardInterrupt) else type(engine_failure('fixture'))
                with self.assertRaisesRegex(expected, 'cancel fixture|transport fixture') as caught:
                    self.cache_campaign(root, real_engine=True, fault=dict(request=2,
                        tokens=[7], error=error, decode_error=decode_error))
                if isinstance(error, KeyboardInterrupt): self.assertIs(caught.exception, error)
                record = self.receipt(root)
                rejected = record['rejected_cases'][0]
                response = rejected['followup']
                self.assertEqual(response['token_ids'], [7])
                self.assertIsNone(response['native_timings'])
                self.assertEqual(rejected['prime']['token_ids'], [7, 99])
                self.assertEqual(record.get('summary', []), [])
                if decode_error: self.assertIn('decode fixture', response['text_error'])

    def test_cache_cancellation_does_not_start_diagnostic_decode(self):
        for failure in (KeyboardInterrupt('cancel fixture'), SystemExit('stop fixture')):
            with self.subTest(failure=failure):
                class Engine:
                    prompt_cache = False
                    last = {}
                    def generate(self, *args):
                        yield 7
                        raise failure
                tokenizer = SimpleNamespace(decode=Mock(side_effect=AssertionError('No decode after cancellation')))
                with self.assertRaises(type(failure)) as caught:
                    benchmark_cache.measure(Engine(), tokenizer, [1, 2, 3])
                self.assertIs(caught.exception, failure)
                tokenizer.decode.assert_not_called()
                self.assertEqual(caught.exception.benchmark_response['token_ids'], [7])

    def test_failed_cache_native_diagnostic_decode_is_bounded(self):
        class Engine:
            prompt_cache = False
            stop_ids = {99}
            last = {'native_timings': dict(predicted_n=2, prompt_n=3, cache_n=0,
                predicted_per_second=50, prompt_per_second=500)}
            def generate(self, *args): yield from [7, 8]
        tokenizer = SimpleNamespace(base='http://unused', decode=Mock(side_effect=AssertionError('Use bounded decode')))
        with patch.object(benchmark_cache, 'request', return_value={'content': 'partial fixture'}) as request, \
                self.assertRaisesRegex(ValueError, 'normal-EOS') as caught:
            benchmark_cache.measure(Engine(), tokenizer, [1, 2, 3])
        request.assert_called_once_with('http://unused', '/detokenize', {'tokens': [7, 8]}, timeout=2)
        tokenizer.decode.assert_not_called()
        self.assertEqual(caught.exception.benchmark_response['text'], 'partial fixture')

    def test_rejected_cache_rows_cannot_enter_timing_aggregates(self):
        cases = [dict(history_budget=512, cache=flag, warmup=False, status='accepted',
            ttft_s=.1, wall_s=.3, native_timings=dict(predicted_per_second=50, cache_n=int(flag)),
            prompt_tokens=3, rss_after_bytes=10, correct=True) for flag in (False, True)]
        cases.append(dict(cases[1], status='rejected', wall_s=.0001, ttft_s=.0001,
                          native_timings=dict(predicted_per_second=100000, cache_n=2)))
        record = {'cases': cases}
        benchmark_cache._summarize_cache(self.args(), record)
        summary = record['summary'][0]
        self.assertEqual(summary['cache_on']['repeats'], 1)
        self.assertEqual(summary['cache_on']['median_generation_tok_s'], 50)
        self.assertEqual(summary['generation_increase_percent'], 0)


if __name__ == '__main__': unittest.main()
