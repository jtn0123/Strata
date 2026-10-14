"""Native transport faults must reach the retained API's structured error paths."""
from io import BytesIO
import importlib
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'vendor/Strata-macOS'))
from native_backend import NativeEngine, NativeTemplate, NativeTokenizer, create_backend, native_request
import native_backend
from performance_metrics import tracked_service
from serve.server import EngineDied, Service, make_handler


# A complete final record for prompt [10] and the two emitted tokens [1, 99].
COUNTS = dict(prompt_n=1, cache_n=0, predicted_n=2)


class Tokenizer:
    def encode(self, *args, **kwargs): return [99]
    def decode(self, ids, **kwargs): return 'hello'


class Connection:
    def __init__(self, *, status=200, lines=(), request_error=None, reader_error=None):
        self.status, self.lines = status, lines
        self.request_error, self.reader_error = request_error, reader_error
        self.sock, self.closed = self, False
    def request(self, *args, **kwargs):
        if self.request_error: raise self.request_error
    def getresponse(self):
        if self.reader_error: raise self.reader_error
        return self
    def read(self): return b'fixture native unavailable'
    def __iter__(self): return iter(self.lines)
    def shutdown(self, how): self.closed = True
    def close(self): self.closed = True


class NativeErrorTests(unittest.TestCase):
    def engine(self):
        engine = NativeEngine('http://127.0.0.1:1', dict(default_generation_settings=dict(n_ctx=4096),
            build_info='fixture', model_path='fixture'), 'small', stop_ids={99})
        engine.last = dict(native_timings=dict(predicted_per_second=999), reused=999)
        return engine

    def test_missing_native_hostname_fails_before_creating_transport(self):
        engine = self.engine()
        engine.base = 'not-a-native-url'
        response = engine.generate([10], 10, {}, threading.Event())
        with patch('native_backend.http.client.HTTPConnection') as connection:
            with self.assertRaisesRegex(EngineDied, 'no hostname'):
                list(response)
        connection.assert_not_called()

    def test_native_faults_mark_history_error_without_old_or_native_counters(self):
        faults = [Connection(status=503), Connection(), Connection(lines=[b'data: invalid-json\n']),
                  Connection(request_error=ConnectionRefusedError('fixture refused')),
                  Connection(reader_error=ConnectionResetError('fixture reset')),
                  Connection(lines=[b'data: {"error":{"message":"fixture failed"}}\n'])]
        for connection in faults:
            with self.subTest(connection=connection):
                engine = self.engine(); service = Service(engine, Tokenizer(), None)
                with patch('native_backend.http.client.HTTPConnection', return_value=connection):
                    response = service.run([10], False, [], 10, {}, threading.Event())
                    with self.assertRaises(EngineDied):
                        list(response)
                self.assertEqual(service.history[-1]['finish'], 'error')
                self.assertNotIn('native_timings', engine.last)
                self.assertNotIn('reused', engine.last)
                self.assertIsNone(service.history[-1]['decode_tok_s'])
                self.assertTrue(connection.closed)

    def test_openai_and_anthropic_emit_errors_in_both_response_modes(self):
        for endpoint in ('/v1/chat/completions', '/v1/messages'):
            for streaming in (False, True):
                with self.subTest(endpoint=endpoint, streaming=streaming):
                    engine = self.engine(); service = Service(engine, Tokenizer(), None)
                    service.prepare = lambda *args: ([10], False, 10)
                    handler = object.__new__(make_handler(service))
                    payload = json.dumps(dict(messages=[dict(role='user', content='fixture')],
                                              stream=streaming, max_tokens=10)).encode()
                    handler.path, handler.headers = endpoint, {'Content-Length': str(len(payload))}
                    handler.rfile, handler.wfile = BytesIO(payload), BytesIO()
                    replies = []
                    handler._json = lambda code, body: replies.append((code, body))
                    handler._sse = lambda: replies.append((200, 'stream'))
                    with patch('native_backend.http.client.HTTPConnection', return_value=Connection(status=503)):
                        handler.do_POST()
                    self.assertEqual(service.history[-1]['finish'], 'error')
                    if streaming:
                        body = handler.wfile.getvalue()
                        self.assertIn(b'"error"', body)
                        self.assertIn(b'fixture native unavailable', body)
                        if endpoint.endswith('completions'): self.assertIn(b'[DONE]', body)
                        else: self.assertIn(b'event: error', body)
                    else:
                        self.assertEqual(replies[0][0], 503)
                        self.assertIn('fixture native unavailable', replies[0][1]['error']['message'])

    def test_template_and_tokenizer_transport_errors_use_the_same_api_boundary(self):
        tokenizer = NativeTokenizer('local')
        calls = (lambda: tokenizer.encode('fixture'), lambda: tokenizer.decode([1]),
                 lambda: NativeTemplate('local').render([dict(role='user', content='fixture')]))
        with patch('native_backend.request', side_effect=ConnectionResetError('fixture reset')):
            for call in calls:
                with self.assertRaisesRegex(EngineDied, 'fixture reset'): call()

    def test_downstream_detokenize_failure_has_no_native_or_synthetic_rate(self):
        packet = lambda row: b'data: ' + json.dumps(row).encode() + b'\n'
        connection = Connection(lines=[packet(dict(tokens=[1])), packet(dict(tokens=[99])),
            packet(dict(stop=True, timings=dict(prompt_ms=12, predicted_ms=25, predicted_per_second=80, **COUNTS)))])
        engine = self.engine()
        service = tracked_service(Service, type(None))(engine, Tokenizer(), None)
        service.tok = NativeTokenizer('fixture')
        with patch('native_backend.http.client.HTTPConnection', return_value=connection), \
                patch('native_backend.request', side_effect=ConnectionResetError('detokenize failed')):
            response = service.run([10], False, [], 10, {}, threading.Event())
            with self.assertRaisesRegex(EngineDied, 'detokenize failed'):
                list(response)
        row = service.history[-1]
        self.assertEqual(row['finish'], 'error')
        self.assertEqual(row['output_tokens'], 1)
        self.assertIsNone(row['decode_ms'])
        self.assertIsNone(row['decode_tok_s'])
        self.assertIsNone(row['generation_tps'])
        self.assertEqual(row['generation_source'], 'unreported')
        self.assertNotIn('native_timings', engine.last)

    def test_normal_eos_in_an_unrelated_exception_handler_retains_native_timings(self):
        packet = lambda row: b'data: ' + json.dumps(row).encode() + b'\n'
        connection = Connection(lines=[packet(dict(tokens=[1])), packet(dict(tokens=[99])),
            packet(dict(stop=True, timings=dict(prompt_ms=12, predicted_ms=25, predicted_per_second=80, **COUNTS)))])
        engine = self.engine(); service = Service(engine, Tokenizer(), None)
        try:
            raise ValueError('previous unrelated operation')
        except ValueError:
            with patch('native_backend.http.client.HTTPConnection', return_value=connection):
                list(service.run([10], False, [], 10, {}, threading.Event()))
        self.assertEqual(service.history[-1]['finish'], 'stop')
        self.assertEqual(engine.last['native_timings']['predicted_per_second'], 80)

    def test_impossible_final_counters_leave_monitor_without_native_rate(self):
        packet = lambda row: b'data: ' + json.dumps(row).encode() + b'\n'
        connection = Connection(lines=[packet(dict(tokens=[1])), packet(dict(tokens=[99])),
            packet(dict(stop=True, timings=dict(prompt_ms=-5, predicted_ms=25, predicted_per_second=400000,
                                                prompt_n=20, cache_n=100, predicted_n=800)))])
        engine = self.engine()
        service = tracked_service(Service, type(None))(engine, Tokenizer(), None)
        with patch('native_backend.http.client.HTTPConnection', return_value=connection):
            list(service.run([10], False, [], 10, {}, threading.Event()))
        row = service.history[-1]
        self.assertEqual((row['finish'], row['output_tokens']), ('stop', 2))
        self.assertIsNone(row['reused'])
        self.assertNotEqual(row['generation_source'], 'native')
        self.assertNotEqual(row['generation_tps'], 400000)
        self.assertNotIn('native_timings', engine.last)
        self.assertIn('Native output count differs', engine.last['native_timing_error'])

    def test_native_error_and_malformed_schemas_reach_supported_error_boundary(self):
        tokenizer = NativeTokenizer('fixture')
        calls = [('tokenize', lambda: tokenizer.encode('fixture'), [{'tokens': [True]}, {'tokens': [-1]}]),
                 ('detokenize', lambda: tokenizer.decode([1]), [{'content': 7}]),
                 ('apply-template', lambda: NativeTemplate('fixture').render([]), [{'prompt': None}]),
                 ('props', lambda: create_backend(dict(native_url='http://127.0.0.1:1', model_name='small')),
                  [dict(default_generation_settings=dict(n_ctx=True), build_info='fixture', model_path='fixture')])]
        for endpoint, call, invalid in calls:
            for response in [{'error': {'message': 'native error fixture'}}, {}, [], *invalid]:
                with self.subTest(endpoint=endpoint, response=response), \
                        patch('native_backend.request', return_value=response):
                    with self.assertRaises(EngineDied): call()

    def test_invalid_stream_packets_end_the_request_without_a_native_rate(self):
        packet = lambda row: b'data: ' + json.dumps(row).encode() + b'\n'
        final = packet(dict(stop=True, timings=dict(predicted_per_second=80, prompt_ms=12, predicted_ms=25, **COUNTS)))
        for row in ([], 5, dict(tokens=[True, -4]), dict(tokens=[-4]), dict(tokens=[1.0]), dict(tokens='1'),
                    dict(tokens=None), dict(tokens=[1], stop='yes')):
            with self.subTest(row=row):
                connection = Connection(lines=[packet(row), packet(dict(tokens=[1, 99])), final])
                engine = self.engine(); service = Service(engine, Tokenizer(), None)
                with patch('native_backend.http.client.HTTPConnection', return_value=connection):
                    with self.assertRaisesRegex(EngineDied, 'completion'):
                        list(service.run([10], False, [], 10, {}, threading.Event()))
                self.assertEqual(service.history[-1]['finish'], 'error')
                self.assertIsNone(service.history[-1]['decode_tok_s'])
                self.assertNotIn('native_timings', engine.last)
                self.assertTrue(connection.closed)
        grouped = Connection(lines=[packet(dict(tokens=[1, 99], stop=False)), final])
        engine = self.engine(); service = Service(engine, Tokenizer(), None)
        with patch('native_backend.http.client.HTTPConnection', return_value=grouped):
            list(service.run([10], False, [], 10, {}, threading.Event()))
        self.assertEqual((service.history[-1]['finish'], engine.last['generated']), ('stop', 2))
        self.assertEqual(engine.last['native_timings']['predicted_per_second'], 80)

    def test_nonfinite_sampling_never_reaches_the_native_server(self):
        connection = Connection()
        sent = []
        connection.request = lambda *args, **kwargs: sent.append(kwargs)
        engine = self.engine(); service = Service(engine, Tokenizer(), None)
        with patch('native_backend.http.client.HTTPConnection', return_value=connection):
            with self.assertRaisesRegex(EngineDied, 'JSON compliant'):
                list(service.run([10], False, [], 10, dict(temperature=float('nan')), threading.Event()))
        self.assertEqual(sent, [])

    def test_valid_empty_text_and_token_responses_are_preserved(self):
        responses = {'/tokenize': {'tokens': []}, '/detokenize': {'content': ''},
                     '/apply-template': {'prompt': ''}, '/props': dict(default_generation_settings=dict(n_ctx=4096),
                         build_info='fixture', model_path='fixture')}
        for endpoint, response in responses.items():
            with self.subTest(endpoint=endpoint), patch('native_backend.request', return_value=response):
                self.assertEqual(native_request('fixture', endpoint), response)

    def test_standalone_error_resolves_vendored_exception_identity(self):
        # The pinned shell can add the resolved target of a vendor symlink too.
        search = [path for path in sys.path if not (Path(path or '.') / 'serve/server.py').is_file()]
        original = ConnectionResetError('standalone transport failed')
        with patch.dict(sys.modules), patch.object(sys, 'path', search), \
                patch('native_backend.request', side_effect=original):
            for name in list(sys.modules):
                if name == 'serve' or name.startswith('serve.'): del sys.modules[name]
            tokenizer = NativeTokenizer('fixture')
            with self.assertRaises(RuntimeError) as caught:
                tokenizer.encode('fixture')
            self.assertIn('standalone transport failed', str(caught.exception))
            self.assertIs(caught.exception.__cause__, original)
            exception_type = importlib.import_module('serve.server').EngineDied
            self.assertIsInstance(caught.exception, exception_type)

    def test_partial_failure_is_not_timed_as_completed_and_next_request_recovers(self):
        packet = lambda row: b'data: ' + json.dumps(row).encode() + b'\n'
        failed = Connection(lines=[packet(dict(tokens=[1])), packet(dict(error='fixture failed'))])
        completed = Connection(lines=[packet(dict(tokens=[1])), packet(dict(tokens=[99])),
            packet(dict(stop=True, timings=dict(predicted_per_second=80, prompt_ms=12, predicted_ms=25, **COUNTS)))])
        engine = self.engine(); service = Service(engine, Tokenizer(), None)
        with patch('native_backend.http.client.HTTPConnection', side_effect=[failed, completed]):
            response = service.run([10], False, [], 10, {}, threading.Event())
            with self.assertRaises(EngineDied):
                list(response)
            self.assertEqual(service.history[-1]['finish'], 'error')
            self.assertEqual(service.history[-1]['output_tokens'], 1)
            self.assertIsNone(service.history[-1]['decode_tok_s'])
            self.assertNotIn('native_timings', engine.last)
            list(service.run([10], False, [], 10, {}, threading.Event()))
        self.assertEqual(service.history[-1]['finish'], 'stop')
        self.assertEqual(engine.last['native_timings']['predicted_per_second'], 80)

    def test_cancellation_during_transport_fault_stays_cancelled(self):
        cancel = threading.Event(); connection = Connection()
        def reset():
            cancel.set()
            raise ConnectionResetError('cancelled fixture')
        connection.getresponse = reset
        engine = self.engine(); service = Service(engine, Tokenizer(), None)
        with patch('native_backend.http.client.HTTPConnection', return_value=connection):
            list(service.run([10], False, [], 10, {}, cancel))
        self.assertEqual(service.history[-1]['finish'], 'cancel')
        self.assertNotIn('native_timings', engine.last)
        self.assertTrue(connection.closed)


if __name__ == '__main__': unittest.main()
