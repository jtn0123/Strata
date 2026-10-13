import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from capture_lookup_long import assess, signature, validate_response, workloads
from test_m5_native_capture import lookup_fixture, text_for


class LongLookupTests(unittest.TestCase):
    def test_synthetic_english_inventory_is_bounded_and_distinct(self):
        cases = workloads()
        self.assertEqual(len(cases), 2)
        self.assertEqual(len({c['content'] for c in cases}), 2)
        for case in cases:
            self.assertEqual(case['content'].count('Record '), 36)
            self.assertLess(len(case['content']), 20000)
            self.assertTrue(case['content'].isascii())
        self.assertIn('Record 1:', cases[0]['content'])
        self.assertIn('Record 72:', cases[1]['content'])

    def test_capped_or_reused_incomplete_output_cannot_be_scored(self):
        response = dict(text='Keep a record.', generated_token_ids=[1, 2],
                        final=dict(stop=True, stop_type='eos', timings=dict(predicted_n=2, prompt_n=3000)))
        validate_response(response, 3000)
        for mutate in ('stop_type', 'count', 'prompt', 'empty'):
            bad = copy.deepcopy(response)
            if mutate == 'stop_type': bad['final']['stop_type'] = 'limit'
            elif mutate == 'count': bad['final']['timings']['predicted_n'] = 3
            elif mutate == 'prompt': bad['final']['timings']['prompt_n'] = 4
            else: bad['text'] = ''
            with self.assertRaises(ValueError): validate_response(bad, 3000)

    def test_phase_accounting_keeps_cache_unknown_and_never_claims_ssd_wait(self):
        mapping, op, req = lookup_fixture()
        req.update(repeat=0, response={'ttft_s': 0.0004})
        result = assess(text_for(mapping, [op]), [req])
        row = result['requests'][0]
        self.assertEqual(row['lookup_before_first_text_us'], 10)
        self.assertEqual(row['lookup_before_first_text_percent'], 2.5)
        self.assertEqual(row['upper_bound_percent'], 1)
        self.assertTrue(row['first_exposure'])
        self.assertIn('unknown', result['cache_state'])
        self.assertFalse(result['speed_gain_measured'])
        self.assertFalse(result['measured_SSD_wait'])
        self.assertTrue(result['prefetch_worth_investigating'])

    def test_phase_crossing_is_reported_not_silently_assigned(self):
        mapping, op, req = lookup_fixture()
        req.update(repeat=1, response={'ttft_s': 0.000105})
        row = assess(text_for(mapping, [op]), [req])['requests'][0]
        self.assertEqual(row['lookup_before_first_text_us'], 0)
        self.assertEqual(row['operations_crossing_first_text'], 1)
        self.assertFalse(row['first_exposure'])
        req['response']['ttft_s'] = 0.002
        with self.assertRaises(ValueError): assess(text_for(mapping, [op]), [req])

    def test_parity_requires_every_prompt_repeat_text_and_token(self):
        base = dict(requests=[dict(workload='a', repeat=0, prompt_sha256='hash', prompt_tokens=3000,
                                   response=dict(text='record', generated_token_ids=[1, 2]))])
        self.assertEqual(signature(base), signature(copy.deepcopy(base)))
        for key, value in (('repeat', 1), ('prompt_tokens', 2999), ('prompt_sha256', 'other')):
            bad = copy.deepcopy(base)
            bad['requests'][0][key] = value
            self.assertNotEqual(signature(base), signature(bad))
        bad = copy.deepcopy(base)
        bad['requests'][0]['response']['generated_token_ids'] = [1, 3]
        self.assertNotEqual(signature(base), signature(bad))


if __name__ == '__main__':
    unittest.main()
