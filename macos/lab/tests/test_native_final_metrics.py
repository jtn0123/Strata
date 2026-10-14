"""Reproduce caller-close-at-EOS and keep native completion counters truthful."""
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from native_backend import NativeEngine

PROMPT = [10, 11, 12, 13, 14]
# A complete final record for PROMPT (four cached, one read) and the two emitted tokens [1, 99].
TIMINGS = dict(prompt_ms=12, predicted_ms=25, predicted_n=2, predicted_per_second=80,
               prompt_per_second=250, prompt_n=1, cache_n=4, draft_n=3, draft_n_accepted=2)


class Connection:
    def __init__(self, final=True, delay=0.03, timings=TIMINGS):
        self.final = final
        self.timings = timings
        self.delay = delay
        self.release = threading.Event()
        self.closed = False
        self.sock = self
        self.calls = []

    def request(self, *args, **kwargs): self.calls.append((args, kwargs))
    def shutdown(self, how): self.closed = True; self.release.set()
    def close(self): self.shutdown(None)
    def getresponse(self): return self
    status = 200

    def __iter__(self):
        for token in (1, 99):
            yield b'data: ' + json.dumps(dict(tokens=[token], stop=False)).encode() + b'\n'
        self.release.wait(self.delay)
        if not self.closed and self.final:
            yield b'data: ' + json.dumps(dict(tokens=[], stop=True, timings=self.timings)).encode() + b'\n'


class NativeFinalMetricsTests(unittest.TestCase):
    def engine(self):
        engine = NativeEngine('http://127.0.0.1:1', dict(default_generation_settings=dict(n_ctx=4096),
                             build_info='fixture', model_path='synthetic-model'), 'flash')
        engine.stop_ids = {99}
        return engine

    def test_caller_close_at_stop_token_retains_final_native_counters(self):
        engine = self.engine(); connection = Connection()
        with patch('native_backend.http.client.HTTPConnection', return_value=connection):
            stream = engine.generate(PROMPT, 32, {}, threading.Event())
            self.assertEqual(next(stream), 1)
            self.assertEqual(next(stream), 99)
            stream.close()  # The pinned Service breaks and closes at this exact point.
        self.assertEqual(engine.last.get('native_timings', {}).get('predicted_per_second'), 80)
        self.assertEqual(engine.last.get('reused'), 4)
        self.assertEqual(len(connection.calls), 1)

    def test_grouped_final_tokens_preserve_sampling_payload_and_native_metrics(self):
        class GroupedConnection(Connection):
            def __iter__(self):
                yield b': keepalive\n'
                yield b'data: ' + json.dumps(dict(tokens=[1, 2], stop=True, timings=dict(
                    prompt_ms=12, predicted_ms=25, predicted_n=2, prompt_n=2, cache_n=0))).encode() + b'\n'
        connection = GroupedConnection()
        engine = self.engine()
        engine.prompt_cache = False
        sampling = dict(temperature=0, repetition_penalty=1.2, top_p=0, top_k=0,
                        min_p=0, frequency_penalty=0, presence_penalty=0, seed=0,
                        unsupported='fixture')
        with patch('native_backend.http.client.HTTPConnection', return_value=connection):
            self.assertEqual(list(engine.generate([10, 11], 32, sampling, threading.Event())), [1, 2])
        args, kwargs = connection.calls[0]
        self.assertEqual(args, ('POST', '/completion'))
        self.assertEqual(json.loads(kwargs['body']), dict(prompt=[10, 11], n_predict=32,
            stream=True, return_tokens=True, cache_prompt=False, temperature=0, repeat_penalty=1.2,
            top_p=0, top_k=0, min_p=0, frequency_penalty=0, presence_penalty=0, seed=0))
        self.assertEqual(engine.last, dict(generated=2, prompt_tokens=2, prompt_ms=12, decode_ms=25, reused=0,
            native_timings=dict(prompt_ms=12, predicted_ms=25, predicted_n=2, prompt_n=2, cache_n=0)))
        self.assertTrue(connection.closed)

    def run_final(self, timings, max_new=32, prompt_cache=True):
        engine = self.engine(); engine.prompt_cache = prompt_cache
        with patch('native_backend.http.client.HTTPConnection', return_value=Connection(timings=timings)):
            stream = engine.generate(PROMPT, max_new, {}, threading.Event())
            self.assertEqual([next(stream), next(stream)], [1, 99])
            stream.close()
        return engine.last

    def test_impossible_final_counters_and_times_are_not_native_facts(self):
        broken = {
            'more output than emitted': dict(predicted_n=800),
            'less output than emitted': dict(predicted_n=1),
            'prompt larger than requested': dict(prompt_n=20, cache_n=100),
            'prompt only partly read': dict(prompt_n=0),
            'boolean counter': dict(predicted_n=True),
            'fractional counter': dict(prompt_n=1.0),
            'negative prompt time': dict(prompt_ms=-5),
            'nonfinite decode time': dict(predicted_ms=float('inf')),
            'nonfinite rate': dict(predicted_per_second=float('nan')),
            'text rate': dict(prompt_per_second='fast'),
            'accepted drafts exceed proposals': dict(draft_n_accepted=4),
            'missing output count': dict(predicted_n=None),
            'missing decode time': dict(predicted_ms=None),
        }
        for name, change in broken.items():
            with self.subTest(name):
                timings = {key: value for key, value in dict(TIMINGS, **change).items() if value is not None}
                last = self.run_final(timings)
                self.assertNotIn('native_timings', last)
                self.assertNotIn('reused', last)
                self.assertEqual((last['generated'], last['prompt_tokens']), (2, len(PROMPT)))
                self.assertIn('Error', last['native_timing_error'])
                self.assertEqual(json.dumps(last['rejected_native_timings']), json.dumps(timings))
        for name, last in {'output above the requested cap': self.run_final(TIMINGS, max_new=1),
                           'cache reuse with the prompt cache off': self.run_final(TIMINGS, prompt_cache=False)}.items():
            with self.subTest(name):
                self.assertNotIn('native_timings', last)
                self.assertIn('ValueError', last['native_timing_error'])

    def test_complete_final_counters_remain_native_facts(self):
        for name, timings, options in [
                ('without drafts or rates', {key: TIMINGS[key] for key in
                    ('prompt_ms', 'predicted_ms', 'predicted_n', 'prompt_n', 'cache_n')}, {}),
                ('one token per second step', dict(TIMINGS, predicted_ms=0, predicted_per_second=0), {}),
                ('uncached prompt', dict(TIMINGS, prompt_n=5, cache_n=0), dict(prompt_cache=False)),
                ('unlimited cap', TIMINGS, dict(max_new=-1))]:
            with self.subTest(name):
                last = self.run_final(timings, **options)
                self.assertEqual(last['native_timings'], timings)
                self.assertNotIn('native_timing_error', last)
                self.assertNotIn('rejected_native_timings', last)

    def test_quiet_transport_heartbeat_and_deadline_keep_owned_cleanup(self):
        class QuietConnection(Connection):
            def __iter__(self):
                self.release.wait(5)
                return iter(())
        for expired in (False, True):
            with self.subTest(expired=expired):
                engine = self.engine()
                connection = QuietConnection()
                cancel = threading.Event()
                clock = iter((1.0, 602.0 if expired else 2.0, 3.0))
                with patch('native_backend.http.client.HTTPConnection', return_value=connection), \
                        patch('native_backend.time.monotonic', side_effect=lambda: next(clock)):
                    stream = engine.generate(PROMPT, 32, {}, cancel)
                    if expired:
                        with self.assertRaisesRegex(RuntimeError, 'exceeded 600 seconds'):
                            next(stream)
                        self.assertNotIn('decode_ms', engine.last)
                    else:
                        self.assertIsNone(next(stream))
                        cancel.set()
                        stream.close()
                    self.assertEqual(engine.last['generated'], 0)
                    self.assertNotIn('native_timings', engine.last)
                    self.assertTrue(connection.closed)

    def test_cancel_skips_final_drain_and_does_not_reuse_old_metrics(self):
        engine = self.engine(); engine.last = dict(native_timings=dict(predicted_per_second=999))
        connection = Connection(final=False, delay=5); cancel = threading.Event()
        with patch('native_backend.http.client.HTTPConnection', return_value=connection):
            stream = engine.generate(PROMPT, 32, {}, cancel)
            self.assertEqual(next(stream), 1)
            cancel.set(); started = time.monotonic(); stream.close()
        self.assertLess(time.monotonic() - started, 0.25)
        self.assertNotIn('native_timings', engine.last)

    def test_cancel_before_start_clears_previous_request_counters(self):
        engine = self.engine(); engine.last = dict(native_timings=dict(predicted_per_second=999))
        cancel = threading.Event(); cancel.set()
        with patch('native_backend.http.client.HTTPConnection') as connection:
            self.assertEqual(list(engine.generate(PROMPT, 32, {}, cancel)), [])
        connection.assert_not_called()
        self.assertEqual(engine.last, {})

    def test_eof_without_final_keeps_telemetry_unreported(self):
        engine = self.engine(); connection = Connection(final=False, delay=0)
        with patch('native_backend.http.client.HTTPConnection', return_value=connection):
            stream = engine.generate(PROMPT, 32, {}, threading.Event())
            self.assertEqual(next(stream), 1); self.assertEqual(next(stream), 99); stream.close()
        self.assertNotIn('native_timings', engine.last)

    def test_queued_full_record_does_not_label_cancelled_partial_output_native(self):
        engine = self.engine(); connection = Connection(delay=0); cancel = threading.Event()
        with patch('native_backend.http.client.HTTPConnection', return_value=connection):
            stream = engine.generate(PROMPT, 32, {}, cancel)
            self.assertEqual(next(stream), 1); cancel.set(); stream.close()
        self.assertEqual(engine.last['generated'], 1)
        self.assertNotIn('native_timings', engine.last)

    def test_non_stop_caller_close_does_not_drain_or_claim_full_request(self):
        engine = self.engine(); connection = Connection(delay=0)
        with patch('native_backend.http.client.HTTPConnection', return_value=connection):
            stream = engine.generate(PROMPT, 32, {}, threading.Event())
            self.assertEqual(next(stream), 1); stream.close()
        self.assertEqual(engine.last['generated'], 1)
        self.assertNotIn('native_timings', engine.last)

    def test_unresponsive_final_record_has_a_bounded_drain(self):
        engine = self.engine(); connection = Connection(final=False, delay=5)
        with patch('native_backend.http.client.HTTPConnection', return_value=connection):
            stream = engine.generate(PROMPT, 32, {}, threading.Event())
            self.assertEqual(next(stream), 1); self.assertEqual(next(stream), 99)
            started = time.monotonic(); stream.close()
        self.assertLess(time.monotonic() - started, 1)
        self.assertNotIn('native_timings', engine.last)

    def test_cancel_during_eos_drain_stops_waiting(self):
        engine = self.engine(); connection = Connection(final=False, delay=5); cancel = threading.Event()
        class FinalReady:
            def __init__(self):
                self.ready=threading.Event()
                self.waits=[]
            def is_set(self):return self.ready.is_set()
            def set(self):self.ready.set()
            def wait(self,timeout):
                self.waits.append(timeout)
                # Cancel during the actual drain wait, without depending on when
                # a Timer thread is scheduled on a shared CI runner.
                cancel.set()
                return False
        final_ready=FinalReady()
        events=iter((threading.Event(),final_ready))
        native_threading=SimpleNamespace(Event=lambda:next(events),Thread=threading.Thread)
        with patch('native_backend.http.client.HTTPConnection', return_value=connection), \
                patch('native_backend.threading',native_threading):
            stream = engine.generate(PROMPT, 32, {}, cancel)
            self.assertEqual(next(stream), 1); self.assertEqual(next(stream), 99)
            stream.close()
        self.assertTrue(cancel.is_set())
        self.assertEqual(len(final_ready.waits),1,'Cancellation must prevent further drain waits')
        self.assertLessEqual(final_ready.waits[0],0.05,'Cancellation polling must remain bounded')
        self.assertTrue(connection.closed)
        self.assertNotIn('native_timings', engine.last)
