"""Reproduce caller-close-at-EOS and keep native completion counters truthful."""
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from native_backend import NativeEngine


class Connection:
    def __init__(self, final=True, delay=0.03):
        self.final = final
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
            yield b'data: ' + json.dumps(dict(tokens=[], stop=True, timings=dict(
                prompt_ms=12, predicted_ms=25, predicted_n=2, predicted_per_second=80,
                prompt_per_second=250, cache_n=4, draft_n=3, draft_n_accepted=2))).encode() + b'\n'


class NativeFinalMetricsTests(unittest.TestCase):
    def engine(self):
        engine = NativeEngine('http://127.0.0.1:1', dict(default_generation_settings=dict(n_ctx=4096),
                             build_info='fixture', model_path='synthetic-model'), 'flash')
        engine.stop_ids = {99}
        return engine

    def test_caller_close_at_stop_token_retains_final_native_counters(self):
        engine = self.engine(); connection = Connection()
        with patch('native_backend.http.client.HTTPConnection', return_value=connection):
            stream = engine.generate([10, 11], 32, {}, threading.Event())
            self.assertEqual(next(stream), 1)
            self.assertEqual(next(stream), 99)
            stream.close()  # The pinned Service breaks and closes at this exact point.
        self.assertEqual(engine.last.get('native_timings', {}).get('predicted_per_second'), 80)
        self.assertEqual(engine.last.get('reused'), 4)
        self.assertEqual(len(connection.calls), 1)

    def test_cancel_skips_final_drain_and_does_not_reuse_old_metrics(self):
        engine = self.engine(); engine.last = dict(native_timings=dict(predicted_per_second=999))
        connection = Connection(final=False, delay=5); cancel = threading.Event()
        with patch('native_backend.http.client.HTTPConnection', return_value=connection):
            stream = engine.generate([10], 32, {}, cancel)
            self.assertEqual(next(stream), 1)
            cancel.set(); started = time.monotonic(); stream.close()
        self.assertLess(time.monotonic() - started, 0.25)
        self.assertNotIn('native_timings', engine.last)

    def test_cancel_before_start_clears_previous_request_counters(self):
        engine = self.engine(); engine.last = dict(native_timings=dict(predicted_per_second=999))
        cancel = threading.Event(); cancel.set()
        with patch('native_backend.http.client.HTTPConnection') as connection:
            self.assertEqual(list(engine.generate([10], 32, {}, cancel)), [])
        connection.assert_not_called()
        self.assertEqual(engine.last, {})

    def test_eof_without_final_keeps_telemetry_unreported(self):
        engine = self.engine(); connection = Connection(final=False, delay=0)
        with patch('native_backend.http.client.HTTPConnection', return_value=connection):
            stream = engine.generate([10], 32, {}, threading.Event())
            self.assertEqual(next(stream), 1); self.assertEqual(next(stream), 99); stream.close()
        self.assertNotIn('native_timings', engine.last)

    def test_queued_full_record_does_not_label_cancelled_partial_output_native(self):
        engine = self.engine(); connection = Connection(delay=0); cancel = threading.Event()
        with patch('native_backend.http.client.HTTPConnection', return_value=connection):
            stream = engine.generate([10], 32, {}, cancel)
            self.assertEqual(next(stream), 1); cancel.set(); stream.close()
        self.assertEqual(engine.last['generated'], 1)
        self.assertNotIn('native_timings', engine.last)

    def test_non_stop_caller_close_does_not_drain_or_claim_full_request(self):
        engine = self.engine(); connection = Connection(delay=0)
        with patch('native_backend.http.client.HTTPConnection', return_value=connection):
            stream = engine.generate([10], 32, {}, threading.Event())
            self.assertEqual(next(stream), 1); stream.close()
        self.assertEqual(engine.last['generated'], 1)
        self.assertNotIn('native_timings', engine.last)

    def test_unresponsive_final_record_has_a_bounded_drain(self):
        engine = self.engine(); connection = Connection(final=False, delay=5)
        with patch('native_backend.http.client.HTTPConnection', return_value=connection):
            stream = engine.generate([10], 32, {}, threading.Event())
            self.assertEqual(next(stream), 1); self.assertEqual(next(stream), 99)
            started = time.monotonic(); stream.close()
        self.assertLess(time.monotonic() - started, 1)
        self.assertNotIn('native_timings', engine.last)

    def test_cancel_during_eos_drain_stops_waiting(self):
        engine = self.engine(); connection = Connection(final=False, delay=5); cancel = threading.Event()
        with patch('native_backend.http.client.HTTPConnection', return_value=connection):
            stream = engine.generate([10], 32, {}, cancel)
            self.assertEqual(next(stream), 1); self.assertEqual(next(stream), 99)
            timer = threading.Timer(0.02, cancel.set); timer.start()
            started = time.monotonic(); stream.close(); timer.join()
        self.assertLess(time.monotonic() - started, 0.25)
        self.assertNotIn('native_timings', engine.last)
