import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark_prompt_chunks import PROFILES, REPEATS, cases, chunk_receipt, compare, main, quality


def bracket():
    arms = []
    for role in ('control', 'candidate', 'candidate', 'control'):
        rows = []
        for case in cases():
            for repeat in range(REPEATS):
                fast = role == 'candidate'
                rows.append(dict(name=case['name'], repeat=repeat, prompt_sha256='prompt', prompt_tokens=2200,
                    response=dict(text='same', generated_token_ids=[1, 2]), quality_passed=True,
                    generation_tok_s=60, prompt_tok_s=600 if fast else 500,
                    ttft_s=3 if fast else 4, wall_s=4 if fast else 5))
        arms.append(dict(status='passed', role=role, cases=rows))
    return arms


class PromptChunkTests(unittest.TestCase):
    def test_inventory_and_bounded_profiles(self):
        self.assertEqual(len(cases()), 4)
        self.assertEqual(len({c['name'] for c in cases()}), 4)
        self.assertEqual(PROFILES, {'512': (512, 512), '1024': (1024, 1024),
                                    '1536': (1536, 1536), '256': (512, 256)})
        for b, ub in PROFILES.values(): self.assertLessEqual(ub, b)
        editing = cases('code-edit')
        self.assertEqual(len(editing), 6)
        files = [c['fixture'] for c in editing if c['kind'] == 'editing']
        self.assertEqual({f['language'] for f in files}, {'python', 'javascript', 'json'})
        self.assertTrue(all(f['cohort'] == 'confirm' for f in files))
        with self.assertRaises(ValueError): cases('unqualified')

    def test_factual_retrieval_allows_team_label_but_rejects_wrong_facts(self):
        case = cases()[0]
        for owner in ('Grove', 'team Grove'):
            self.assertTrue(quality(case, f'{{"owner":"{owner}","timeout_seconds":38,"retry_limit":2}}'))
        self.assertFalse(quality(case, '{"owner":"Grove","timeout_seconds":39,"retry_limit":2}'))
        self.assertFalse(quality(case, '[]'))

    def test_only_complete_healthy_bracket_is_scored(self):
        arms = bracket()
        self.assertEqual(len(compare(arms)['rows']), 8)
        for mutate in ('partial', 'failed', 'duplicate', 'extra'):
            bad = copy.deepcopy(arms)
            if mutate == 'partial': bad.pop()
            elif mutate == 'failed': bad[1]['status'] = 'failed'
            elif mutate == 'duplicate': bad[1]['cases'][-1] = bad[1]['cases'][0]
            else: bad[1]['cases'].append(bad[1]['cases'][0])
            with self.assertRaises(ValueError): compare(bad)

    def test_output_change_or_quality_failure_blocks_gain(self):
        arms = bracket()
        self.assertTrue(all(r['eligible_prompt_scope'] for r in compare(arms)['rows']))
        for mutate in ('token', 'text', 'prompt', 'quality'):
            bad = copy.deepcopy(arms)
            row = bad[1]['cases'][0]
            if mutate == 'token': row['response']['generated_token_ids'] = [1, 3]
            elif mutate == 'text': row['response']['text'] = 'different'
            elif mutate == 'prompt': row['prompt_sha256'] = 'changed'
            else: row['quality_passed'] = False
            self.assertFalse(any(r['eligible_prompt_scope'] for r in compare(bad)['rows']))

    def test_first_exposure_and_replay_are_separate(self):
        arms = bracket()
        for arm in arms:
            for row in arm['cases']:
                if row['repeat'] == 0: row['ttft_s'] *= 10
        rows = compare(arms)['rows']
        self.assertEqual(rows[0]['control']['ttft_s'], 40)
        self.assertEqual(rows[1]['control']['ttft_s'], 4)
        self.assertFalse(compare(arms)['default_changed'])

    def test_default_only_prints_plan_without_file_or_engine_activity(self):
        with patch.object(sys, 'argv', ['trial', '--candidate', '1536', '--output', '/unused']), \
                patch('benchmark_prompt_chunks.assert_no_model_server', side_effect=AssertionError), \
                patch('benchmark_prompt_chunks.require_pass', side_effect=AssertionError), \
                patch('benchmark_prompt_chunks.verify_models', side_effect=AssertionError), \
                patch.object(Path, 'mkdir', side_effect=AssertionError):
            main()

    def test_native_target_and_helper_must_really_use_requested_chunks(self):
        def text(batches, ubatches):
            return '\n'.join(f'0.123 I llama_context: {key} = {n}' for key, values in
                (('n_batch', batches), ('n_ubatch', ubatches)) for n in values)
        self.assertEqual(chunk_receipt(text([1536, 1536], [1536, 1536]), '1536')['n_ubatch'], [1536, 1536])
        for b, ub in (([512, 1536], [512, 1536]), ([1536], [1536]),
                      ([1536, 1536], [512, 512]), ([1536, 1536, 1536], [1536, 1536])):
            with self.assertRaises(ValueError): chunk_receipt(text(b, ub), '1536')


if __name__ == '__main__': unittest.main()
