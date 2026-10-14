"""Malformed raw timing evidence must never become a performance percentage."""
import copy
import io
import json
import math
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark_metrics import METRICS, change, completion_counts, metrics
import benchmark_metrics
import benchmark
import benchmark_cache
import test_benchmark_receipts as receipt_fixtures


class MetricTests(unittest.TestCase):
    def test_evidence_preparation_stays_outside_cached_measurement_window(self):
        clock = {'now': 0}
        dumps = json.dumps
        def slow_evidence(value, *args, **kwargs):
            clock['now'] += 5
            return dumps(value, *args, **kwargs)
        class Engine:
            prompt_cache = False
            stop_ids = {99}
            last = {'native_timings': dict(predicted_n=2, prompt_n=3, cache_n=0,
                    predicted_per_second=50, prompt_per_second=500)}
            def generate(self, *args):
                for token in (7, 99):
                    clock['now'] += .1
                    yield token
        with patch.object(benchmark_cache.json, 'dumps', side_effect=slow_evidence), \
                patch.object(benchmark_cache.time, 'monotonic', side_effect=lambda: clock['now']):
            result = benchmark_cache.measure(Engine(), SimpleNamespace(decode=lambda ids: 'READY'), [1, 2, 3])
        self.assertAlmostEqual(result['ttft_s'], .1)
        self.assertAlmostEqual(result['wall_s'], .2)

    def test_rejected_response_keeps_original_error_and_json_safe_raw_evidence(self):
        error = ValueError('invalid native rate')
        raw = {'token_ids': [7, 9], 'text': 'NaN stays literal text',
               'native_timings': {'predicted_per_second': float('nan'), 'other': float('inf')}}
        benchmark_metrics.attach_response_failure(error, raw)
        response = error.benchmark_response
        self.assertEqual(str(error), 'invalid native rate')
        self.assertEqual(response['status'], 'rejected')
        self.assertEqual(response['error'], 'ValueError: invalid native rate')
        self.assertEqual(response['token_ids'], [7, 9])
        self.assertEqual(response['text'], raw['text'])
        self.assertEqual(response['native_timings'], {'predicted_per_second': 'NaN', 'other': 'Infinity'})
        self.assertNotIn('status', raw)
        self.assertTrue(math.isnan(raw['native_timings']['predicted_per_second']))
        json.dumps(response, allow_nan=False)

    def test_invalid_stream_counts_preserve_response_in_failed_campaign(self):
        helper = receipt_fixtures.BenchmarkReceiptTests()
        events = [dict(tokens=[7, 9], content='captured reply'), dict(stop=True,
                  timings=dict(prompt_n=64, predicted_n=999, predicted_per_second=50, prompt_per_second=500))]
        def response(*a, **kw):
            return io.BytesIO(b''.join(b'data: ' + json.dumps(event).encode() + b'\n' for event in events))
        def request(base, path, payload=None, **kw):
            if path == '/apply-template': return {'prompt': 'fixture'}
            if path == '/tokenize': return {'tokens': list(range(1000))}
            return {}
        with tempfile.TemporaryDirectory() as directory:
            root = helper.root(directory)
            with helper.patches(benchmark, root) as stack:
                for name, value in {'request': request, 'experiment_environment': lambda *a: ({}, {}),
                                    'configure': lambda *a: ({}, {})}.items():
                    stack.enter_context(patch.object(benchmark, name, value))
                stack.enter_context(patch.object(benchmark.urllib.request, 'urlopen', side_effect=response))
                stack.enter_context(patch.object(benchmark.psutil, 'swap_memory', return_value=SimpleNamespace(used=0)))
                args = helper.args()
                with self.assertRaisesRegex(ValueError, 'Native output count differs'):
                    benchmark.run(args)
            record = helper.receipt(root)
            self.assertEqual(record['status'], 'failed')
            self.assertEqual(record['cases'], [])
            self.assertEqual(record.get('summary', []), [])
            rejected = record['rejected_cases'][0]['response']
            self.assertEqual(rejected['generated_token_ids'], [7, 9])
            self.assertEqual(rejected['text'], 'captured reply')
            self.assertEqual(rejected['final']['timings']['predicted_n'], 999)
            self.assertEqual(len(rejected['prompt_token_ids']), 64)
            self.assertEqual(rejected['status'], 'rejected')
            json.dumps(record, allow_nan=False)

    def test_interrupted_stream_keeps_partial_evidence_and_same_exception(self):
        error = ConnectionResetError('fixture connection reset')
        class Response(io.BytesIO):
            def __iter__(self):
                yield b'data: {"tokens":[7],"content":"partial reply"}\n'
                raise error
        with patch.object(benchmark.urllib.request, 'urlopen', return_value=Response()):
            with self.assertRaises(ConnectionResetError) as caught:
                benchmark.stream_completion('http://unused', {'prompt': [1, 2, 3], 'n_predict': 96})
        self.assertIs(caught.exception, error)
        rejected = error.benchmark_response
        self.assertEqual(rejected['generated_token_ids'], [7])
        self.assertEqual(rejected['text'], 'partial reply')
        self.assertEqual(rejected['prompt_token_ids'], [1, 2, 3])
        self.assertIsNone(rejected['final'])

    def test_rejected_completed_stream_keeps_rate_count_and_missing_field_evidence(self):
        helper = receipt_fixtures.BenchmarkReceiptTests()
        def request(base, path, payload=None, **kw):
            if path == '/apply-template': return {'prompt': 'fixture'}
            if path == '/tokenize': return {'tokens': list(range(1000))}
            return {}
        for failure in ('nonfinite-rate', 'short-output', 'missing-rate'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                timings = dict(prompt_n=64, predicted_n=2, predicted_per_second=50, prompt_per_second=500)
                if failure == 'nonfinite-rate': timings['predicted_per_second'] = float('nan')
                if failure == 'missing-rate': timings.pop('predicted_per_second')
                raw = dict(ttft_s=.1, wall_s=.3, text='completed reply', generated_token_ids=[7, 9],
                           final=dict(stop=True, timings=timings))
                args = helper.args()
                if failure == 'short-output': args.predict = 3
                root = helper.root(directory)
                with helper.patches(benchmark, root) as stack:
                    for name, value in {'request': request, 'stream_completion': lambda *a: raw,
                                        'experiment_environment': lambda *a: ({}, {}),
                                        'configure': lambda *a: ({}, {})}.items():
                        stack.enter_context(patch.object(benchmark, name, value))
                    stack.enter_context(patch.object(benchmark.psutil, 'swap_memory', return_value=SimpleNamespace(used=0)))
                    with self.assertRaises((ValueError, RuntimeError, KeyError)):
                        benchmark.run(args)
                record = helper.receipt(root)
                self.assertEqual(record['status'], 'failed')
                self.assertEqual(record['cases'], [])
                rejected = record['rejected_cases'][0]['response']
                self.assertEqual(rejected['response']['text'], 'completed reply')
                self.assertEqual(rejected['response']['generated_token_ids'], [7, 9])
                if failure == 'nonfinite-rate': self.assertEqual(rejected['generation_tok_s'], 'NaN')
                json.dumps(record, allow_nan=False)

    def test_complete_native_counters_match_actual_tokens_and_input(self):
        good = dict(predicted_n=2, prompt_n=3, cache_n=2)
        self.assertEqual(completion_counts(good, [7, 9], 5, cached=True, max_new=2), 2)
        for mutation in ({"predicted_n": -1}, {"predicted_n": 3}, {"predicted_n": True},
                         {"prompt_n": 2}, {"cache_n": -1}, {"cache_n": 2.5}):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                completion_counts(dict(good, **mutation), [7, 9], 5, cached=True)
        with self.assertRaises(ValueError): completion_counts(good, [7, 9], 5, cached=False)
        with self.assertRaises(ValueError): completion_counts(good, [7, 9], max_new=1)
        with self.assertRaises(ValueError): completion_counts(good, [7, True])

    def case(self):
        return {"workload": "code", "prompt_tokens": 48, "repeat": 2,
                "generation_tok_s": 50, "prompt_tok_s": 500, "ttft_s": 0.2, "wall_s": 2.76,
                "response": {"final": {"timings": {"draft_n": 100, "draft_n_accepted": 80}}}}

    def test_rejects_one_invalid_sample_before_median_can_hide_it(self):
        for key in METRICS:
            for invalid in (float("nan"), float("inf"), float("-inf"), 0, -1, True):
                with self.subTest(key=key, invalid=invalid):
                    bad = self.case(); bad[key] = invalid
                    with self.assertRaisesRegex(ValueError, f"code/48/repeat=2/{key}"):
                        metrics([self.case(), bad, self.case()])

    def test_rejects_cached_native_rates_and_bad_percentage_operands(self):
        case = {"workload": "cached-ledger", "history_budget": 512, "repeat": 1,
                "ttft_s": 0.2, "wall_s": 0.7,
                "native_timings": {"predicted_per_second": float("nan"), "prompt_per_second": 500}}
        with self.assertRaisesRegex(ValueError, "cached-ledger/512"):
            metrics([case], cached=True)
        control = {k: self.case()[k] for k in METRICS}
        for key in METRICS:
            for operand in ("before", "after"):
                bad = copy.deepcopy(control); bad[key] = 0
                with self.assertRaises(ValueError):
                    change(bad, control) if operand == "before" else change(control, bad)

    def test_acceptance_counters_validate_without_inventing_missing_acceptance(self):
        for values in ({"draft_n": -1}, {"draft_n": 3.5}, {"draft_n": True},
                       {"draft_n": 2, "draft_n_accepted": 3}, {"draft_n_accepted": 1}):
            case = self.case(); case["response"]["final"]["timings"] = values
            with self.assertRaises(ValueError): metrics([case])
        case = self.case(); case["response"]["final"]["timings"] = {}
        self.assertIsNone(metrics([case])["draft_acceptance_percent"])
        self.assertEqual(metrics([self.case()])["draft_acceptance_percent"], 80)
        with self.assertRaises(ValueError): metrics([])

    def test_valid_gain_remains_based_on_fresh_control(self):
        control = metrics([self.case()])
        candidate = dict(control, generation_tok_s=60, wall_s=2, ttft_s=0.1)
        delta = change(control, candidate)
        self.assertAlmostEqual(delta["generation_increase_percent"], 20)
        self.assertAlmostEqual(delta["ttft_reduction_percent"], 50)

    def test_finite_operands_cannot_publish_an_overflowed_percentage(self):
        control = metrics([self.case()])
        candidate = dict(control, generation_tok_s=1e308)
        control["generation_tok_s"] = 1e-308
        with self.assertRaisesRegex(ValueError, "percentage is nonfinite"):
            change(control, candidate)
