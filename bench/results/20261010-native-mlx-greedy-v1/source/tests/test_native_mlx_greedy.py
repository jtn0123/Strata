import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import native_mlx_greedy as screen


class NativeMLXGreedyTests(unittest.TestCase):
    def fixture(self):
        plan = dict(output_limit=3)
        expected = dict(input_ids=[10, 11], output_ids=[21, 22, 23])
        response = dict(generated_token_ids=[21, 22, 23], final=dict(stop=True, stop_type='limit',
            tokens_predicted=3, timings=dict(predicted_n=3, prompt_n=2),
            generation_settings=dict(temperature=0, seed=1234, ignore_eos=False, samplers=['temperature'])))
        return response, expected, plan

    def test_exact_output_does_not_claim_state_numerical_or_adoption(self):
        result = screen.evaluate(*self.fixture())
        self.assertTrue(result['exact_output'])
        self.assertFalse(result['tensor_state_equivalence'])
        self.assertFalse(result['numerical_equivalence'])
        self.assertFalse(result['adoption'])

    def test_divergence_and_changed_finish_are_retained(self):
        response, expected, plan = self.fixture()
        response['generated_token_ids'][1] = 42
        result = screen.evaluate(response, expected, plan)
        self.assertFalse(result['exact_output'])
        self.assertEqual((result['first_mismatch_zero_based'], result['expected_token'], result['actual_token']), (1, 22, 42))
        response, expected, plan = self.fixture()
        response['final']['stop_type'] = 'eos'
        self.assertFalse(screen.evaluate(response, expected, plan)['exact_output'])

    def test_invalid_native_counts_sampling_or_helpers_fail(self):
        response, expected, plan = self.fixture()
        for field, value in [('prompt_n', 1), ('predicted_n', 2), ('draft_n', 1)]:
            bad = copy.deepcopy(response)
            bad['final']['timings'][field] = value
            with self.assertRaises(ValueError): screen.evaluate(bad, expected, plan)
        bad = copy.deepcopy(response)
        bad['final']['generation_settings']['samplers'] = ['top_k', 'temperature']
        with self.assertRaises(ValueError): screen.evaluate(bad, expected, plan)

    def test_default_never_loads_a_model_and_config_keeps_native_guards(self):
        with patch.object(screen, 'run') as run, patch.object(screen, 'freeze') as freeze:
            screen.main([])
        run.assert_not_called()
        freeze.assert_not_called()
        plan = json.loads(screen.CONFIG.read_text())
        self.assertEqual(plan['admission_gib'], 34)
        self.assertEqual(plan['availability_floor_gib'], 1)
        self.assertEqual(plan['swap_growth_allowed_bytes'], 0)
        self.assertFalse(plan['payload']['ignore_eos'])


if __name__ == '__main__': unittest.main()
