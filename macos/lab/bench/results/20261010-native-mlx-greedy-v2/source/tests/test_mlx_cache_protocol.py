"""Reject misleading cache results before any model execution."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import benchmark_mlx_cache as runner
import mlx_cache_protocol as protocol


class MLXCacheProtocolTests(unittest.TestCase):
    def fixture(self, budget=6):
        plan = json.loads(runner.CONFIG.read_text())
        inputs = {'code': {'tokens': [1, 2]}, 'prose': {'tokens': [3, 4]}}
        rows = []
        for spec in protocol.schedule(plan):
            rows.append(dict(**spec, input_ids=inputs[spec['workload']]['tokens'], output_ids=[50] * 128,
                             output_tokens=128, finish_reason='length', decode_tokens=127,
                             ttft_s=1.0, decode_s=2.0, reply_s=3.0, decode_tok_s=63.5,
                             conversation_was_reset=True, expert_cache_retained_on_reset=True,
                             decoded_state_tokens=129, pending_token=50, decode_steps=127,
                             drafted=0, lookup_steps=0, expert_cache_held_bytes=1_000_000_000))
        output = dict(phase='complete', status='passed', dtype='float32', adoption=False,
                      expert_budget_bytes=budget*1_000_000_000, cases=rows)
        return plan, inputs, output

    def test_complete_inventory_and_scope_required(self):
        plan, inputs, output = self.fixture()
        self.assertEqual(len(protocol.validate_launch(output, plan, inputs, 6)), 8)
        for mutate in (lambda x: x['cases'].pop(), lambda x: x['cases'].reverse(),
                       lambda x: x.update(dtype='float16'), lambda x: x.update(expert_budget_bytes=12_000_000_000),
                       lambda x: x['cases'][2].update(warmup=True)):
            bad = copy.deepcopy(output); mutate(bad)
            with self.assertRaises(ValueError): protocol.validate_launch(bad, plan, inputs, 6)

    def test_false_metrics_state_and_finish_are_rejected(self):
        plan, inputs, output = self.fixture()
        for changes in (dict(decode_tokens=128), dict(decode_tok_s=99), dict(reply_s=1),
                        dict(ttft_s=float('nan')), dict(finish_reason='stop'),
                        dict(pending_token=51), dict(decoded_state_tokens=130), dict(decode_steps=128),
                        dict(conversation_was_reset=False), dict(expert_cache_retained_on_reset=False),
                        dict(expert_cache_held_bytes=6_000_000_001), dict(drafted=1)):
            bad = copy.deepcopy(output); bad['cases'][2].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                protocol.validate_launch(bad, plan, inputs, 6)

    def groups(self, gain=0.8):
        plan, _, output = self.fixture()
        groups = [copy.deepcopy(output['cases']) for _ in range(4)]
        for index, group in enumerate(groups):
            speed = (1, 1 + gain/100, 1 + gain/100, 1.0001)[index]
            for row in group:
                row['decode_s'] = 2 / speed
                row['decode_tok_s'] = 127 / row['decode_s']
                row['reply_s'] = row['ttft_s'] + row['decode_s']
        return plan, groups

    def test_valid_sub_one_percent_gain_can_qualify(self):
        plan, groups = self.groups()
        result = protocol.summarize(groups, plan)
        self.assertTrue(result['qualifies_for_native_followup'])
        self.assertLess(result['workloads'][0]['metrics']['decode_tok_s']['improvement_percent'], 1)
        self.assertFalse(result['adoption'])
        self.assertIsNone(result['added_P07_TPS'])
        _, noisy = self.groups(gain=0.01)
        self.assertFalse(protocol.summarize(noisy, plan)['qualifies_for_native_followup'])

    def test_slow_response_or_a_changed_final_token_blocks(self):
        plan, groups = self.groups()
        for row in groups[1]: row['ttft_s'] = 2; row['reply_s'] = row['decode_s'] + 2
        self.assertFalse(protocol.summarize(groups, plan)['qualifies_for_native_followup'])
        plan, groups = self.groups()
        groups[1][-1]['output_ids'][-1] = 51
        with self.assertRaisesRegex(ValueError, 'mismatch'): protocol.summarize(groups, plan)
        with self.assertRaises(ValueError): protocol.summarize(groups[:3], plan)

    def test_missing_repetition_or_changed_warmup_output_blocks(self):
        plan, groups = self.groups()
        groups[-1].pop()
        with self.assertRaises(ValueError): protocol.summarize(groups, plan)
        plan, groups = self.groups()
        groups[2][0]['output_ids'][0] = 51
        with self.assertRaises(ValueError): protocol.summarize(groups, plan)

    def test_pressure_failure_stops_only_owned_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            child = Mock(); child.poll.return_value = None
            state = dict(samples=0, error=None)
            with patch.object(runner.subprocess, 'check_output', return_value='2'):
                runner.watch_pressure(child, Path(tmp)/'pressure.jsonl', threading.Event(), state)
            child.terminate.assert_called_once()
            self.assertIn('Memory pressure', state['error'])

    def test_default_does_not_freeze_or_run(self):
        with patch.object(runner, 'freeze') as freeze, patch.object(runner, 'run') as run:
            runner.main([])
        freeze.assert_not_called(); run.assert_not_called()


if __name__ == '__main__': unittest.main()
