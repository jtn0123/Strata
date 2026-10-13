import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark_parent_metal import MAX_OUTPUT, compare, main, parse_done, quality, verified_pack, release_owned_expert_cache


class ParentMetalTests(unittest.TestCase):
    def test_full_native_counters_are_validated(self):
        row = parse_done('DONE 2 3000 6000.0 40.0 stop 0 0 0 0 0 0 0 0.0 3000 0', [9, 248046], 3000)
        self.assertEqual(row['generation_tok_s'], 50)
        self.assertEqual(row['prompt_tok_s'], 500)
        for line in (
            'DONE 2 3000 6000.0 40.0 length 0 0 0 0 0 0 0 0.0 3000 0',
            'DONE 3 3000 6000.0 40.0 stop 0 0 0 0 0 0 0 0.0 3000 0',
            'DONE 2 3000 6000.0 40.0 stop 0 0 1 0 0 0 0 0.0 2999 0',
            'DONE 2 3000 6000.0 nan stop 0 0 0 0 0 0 0 0.0 3000 0',
            'DONE 2 3000 6000.0 40.0 stop 1 0 0 0 0 0 0 0.0 3000 0',
            'DONE 2 3000 6000.0 0.0 stop 0 0 0 0 0 0 0 0.0 3000 0',
            'DONE 2 3000 6000.0 40.0 stop'):
            with self.assertRaises(ValueError): parse_done(line, [9, 248046], 3000)

    def test_file_and_retrieval_checks_do_not_accept_plausible_wrong_output(self):
        file = dict(kind='editing', expected='TIMEOUT = 20\n')
        self.assertTrue(quality(file, 'TIMEOUT = 20\n')['passed'])
        self.assertFalse(quality(file, 'TIMEOUT = 12\n')['passed'])
        self.assertFalse(quality(file, '```python\nTIMEOUT = 20\n```')['passed'])
        facts = dict(kind='retrieval', expected_json={'owner': 'Grove', 'retry_limit': 2})
        self.assertTrue(quality(facts, '{"retry_limit":2,"owner":"Grove"}')['passed'])
        self.assertFalse(quality(facts, '{"retry_limit":3,"owner":"Grove"}')['passed'])
        self.assertFalse(quality(facts, 'Grove has two retries.')['passed'])

    def test_syntax_check_is_labelled_and_does_not_execute_generated_code(self):
        row = quality(dict(kind='code'), 'def compare_reports(before, after):\n    raise RuntimeError("not executed")')
        self.assertTrue(row['passed'])
        self.assertIn('not functional equivalence', row['scope'])
        self.assertFalse(quality(dict(kind='code'), '```python\nx = 1\n```')['passed'])

    def test_different_outputs_are_reported_not_called_exact_keepers(self):
        cases = [dict(name='prose', kind='prose', prompt_sha256='same')]
        arms = []
        for i, role in enumerate(('current', 'parent', 'parent', 'current')):
            rows = [dict(name='prose', repeat=r, prompt_sha256='same', quality={'passed': True},
                         generation_tok_s=60 if role == 'current' else 40,
                         prompt_tok_s=400, ttft_s=0.3, wall_s=5,
                         generated_token_ids=[i, r], output_tokens=300) for r in range(2)]
            arms.append(dict(role=role, status='passed', cases=rows))
        result = compare(arms, cases)
        self.assertFalse(result['keeper_enabled'])
        self.assertFalse(result['rows'][0]['exact_output_parity'])
        self.assertTrue(result['whole_model_outputs_may_differ'])
        for change in ('partial', 'prompt', 'repeat'):
            bad = copy.deepcopy(arms)
            if change == 'partial': bad[1]['status'] = 'failed'
            elif change == 'prompt': bad[1]['cases'][0]['prompt_sha256'] = 'other'
            else: bad[1]['cases'].pop()
            with self.assertRaises(ValueError): compare(bad, cases)

    def test_default_plan_never_prepares_or_loads_a_model(self):
        with tempfile.TemporaryDirectory() as d, patch('sys.argv', ['trial', '--output', d]), \
                patch('benchmark_parent_metal.prepare_cases', side_effect=AssertionError('No model metadata')), \
                patch('benchmark_parent_metal.launch', side_effect=AssertionError('No model load')):
            main()

    def test_larger_arena_override_is_rejected_before_native_execution(self):
        with patch('sys.argv', ['trial', '--output', '/unused', '--arena-gb', '27', '--run']), \
                patch('benchmark_parent_metal.launch', side_effect=AssertionError('No model load')):
            with self.assertRaises(SystemExit): main()

    def test_pack_hash_reuse_is_invalidated_when_bytes_change(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); folder = root / 'pack'; folder.mkdir()
            payload = folder / 'dense.bin'; payload.write_bytes(b'old')
            receipt = root / 'receipt.json'
            original = verified_pack(folder, receipt)
            with patch('benchmark_parent_metal.sha256', side_effect=AssertionError('No repeated payload scan')):
                self.assertEqual(verified_pack(folder, receipt), original)
            payload.write_bytes(b'new data')
            self.assertNotEqual(verified_pack(folder, receipt), original)

    def test_cache_cleanup_refuses_before_touching_files_with_an_active_engine(self):
        with patch('benchmark_parent_metal.no_engines', side_effect=RuntimeError('Active engine')), \
                patch.object(Path, 'read_text', side_effect=AssertionError('No file access')):
            with self.assertRaisesRegex(RuntimeError, 'Active engine'): release_owned_expert_cache()


if __name__ == '__main__': unittest.main()
