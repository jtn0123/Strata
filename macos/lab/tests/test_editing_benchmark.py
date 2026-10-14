"""Reject false editing wins and unsafe speculative allocation settings."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark_editing import compare, fixtures, prompt, trial_command, validate_response


class EditingBenchmarkTests(unittest.TestCase):
    def test_activation_uses_real_counters_not_unavailable_debug_messages(self):
        from benchmark_editing import drafting_receipts
        text = ("spec: adding speculative implementation 'ngram-mod'\n"
                "spec: statistics        ngram-mod: #calls(b,g,a) = 18 784 727, "
                "#gen drafts = 727, #acc drafts = 723, #gen tokens = 2178, #acc tokens = 2150\n")
        self.assertEqual(drafting_receipts(text, 'code-edit')['ngram-mod']['accepted_tokens'], 2150)
        with self.assertRaises(ValueError): drafting_receipts(text, 'prompt-local')
        with self.assertRaises(ValueError): drafting_receipts(text.replace('2150', '2200'), 'code-edit')
        with self.assertRaises(ValueError): drafting_receipts(text.replace('2178', '2182'), 'code-edit')

    def response(self):
        case = fixtures()[0]
        return dict(text=case['source'].replace(case['old'], case['new']), generated_token_ids=[1, 2, 3],
                    ttft_s=0.8, wall_s=5, final=dict(stop=True, stop_type='eos', timings=dict(
                        predicted_per_second=60, prompt_per_second=500, predicted_n=3, draft_n=3, draft_n_accepted=2,
                        prompt_ms=6, predicted_ms=33)))

    def arms(self):
        memory = dict(monitor_healthy=True, child_exited=True, normal_pressure_required=True,
                      normal_pressure_observed=True, pressure_live_samples=1, guard=None,
                      swap_growth_bytes=0, peak_rss_bytes=1000)
        arms = []
        for role in ('control', 'candidate', 'candidate', 'control'):
            cases = []
            files = fixtures()[:3] + [dict(name='prose-control', language='prose')]
            for file in files:
                for repeat in range(4):
                    response = self.response()
                    if file['language'] != 'prose':
                        response['text'] = file['source'].replace(file['old'], file['new'])
                    case = validate_response(response, file if file['language'] != 'prose' else None)
                    case.update(name=file['name'], language=file['language'], repeat=repeat, prompt_sha256='same')
                    if role == 'candidate':
                        case['generation_tok_s'] *= 1.005
                        case['wall_s'] /= 1.005
                    cases.append(case)
            arms.append(dict(role=role, status='passed', cohort='screen', cases=cases, memory=copy.deepcopy(memory)))
        return arms

    def test_heldout_files_are_complete_unique_changes(self):
        cases = fixtures()
        self.assertEqual(len(cases), 6)
        self.assertEqual({c['language'] for c in cases}, {'python', 'javascript', 'json'})
        self.assertTrue(all('entire updated file' in prompt(c) for c in cases))

    def test_prompt_local_bounds_both_allocations_and_keeps_fallback(self):
        command = trial_command(['server', '--spec-type', 'draft-mtp', '--spec-draft-n-max', '3'], 'prompt-map')
        self.assertEqual(command[command.index('--spec-type')+1], 'ngram-map-k,ngram-mod,draft-mtp')
        self.assertEqual(command[command.index('--spec-ngram-map-k-size-n')+1], '12')
        self.assertEqual(command[command.index('--spec-ngram-map-k-size-m')+1], '3')
        self.assertEqual(command[command.index('--spec-ngram-mod-n-max')+1], '3')
        with self.assertRaises(ValueError):
            trial_command(['server', '--spec-type', 'draft-mtp', '--spec-draft-n-max', '5'], 'prompt-map')

    def test_known_inactive_simple_matcher_is_rejected_before_launch(self):
        with self.assertRaisesRegex(ValueError, 'cannot draft'):
            trial_command(['server', '--spec-type', 'draft-mtp', '--spec-draft-n-max', '3'], 'prompt-local')

    def test_active_primary_may_leave_fallback_unused(self):
        from benchmark_editing import drafting_receipts
        text = ("adding speculative implementation 'ngram-mod'\n"
                "adding speculative implementation 'ngram-map-k'\n"
                "statistics ngram-mod: #gen drafts = 0, #acc drafts = 0, #gen tokens = 0, #acc tokens = 0\n"
                "statistics ngram-map-k: #gen drafts = 4, #acc drafts = 4, #gen tokens = 12, #acc tokens = 12\n")
        self.assertEqual(drafting_receipts(text, 'prompt-map')['ngram-map-k']['accepted_tokens'], 12)
        with self.assertRaises(ValueError): drafting_receipts(text.replace('ngram-map-k: #gen drafts = 4', 'ngram-map-k: #gen drafts = 0'), 'prompt-map')

    def test_capped_or_partial_edit_is_ineligible(self):
        response = self.response(); response['final']['stop_type'] = 'limit'
        with self.assertRaises(ValueError): validate_response(response, fixtures()[0])
        response = self.response(); response['text'] = response['text'][:120]
        with self.assertRaises(ValueError): validate_response(response, fixtures()[0])

    def test_wrong_or_impossible_output_counter_is_ineligible(self):
        case = fixtures()[0]
        for count in (-5, True, 1, 4):
            response = self.response(); response['final']['timings']['predicted_n'] = count
            with self.subTest(count=count), self.assertRaises(ValueError):
                validate_response(response, case)

    def test_tiny_repeatable_gain_can_qualify(self):
        self.assertEqual(compare(self.arms())['eligible_languages'], ['javascript', 'json', 'python'])

    def test_partial_launch_or_swap_cannot_qualify(self):
        arms = self.arms()
        with self.assertRaises(ValueError): compare(arms[:3])
        arms[1]['memory']['swap_growth_bytes'] = 1
        with self.assertRaises(ValueError): compare(arms)

    def test_changed_tokens_cannot_qualify_even_with_same_text(self):
        arms = self.arms(); arms[1]['cases'][0]['response']['generated_token_ids'] = [1, 2, 4]
        with self.assertRaises(ValueError): compare(arms)

    def test_missing_warmed_repeat_cannot_qualify(self):
        arms = self.arms()
        for arm in arms: arm['cases'] = [c for c in arm['cases'] if c['repeat'] != 3]
        with self.assertRaises(ValueError): compare(arms)

    def test_missing_whole_language_cannot_qualify(self):
        arms = self.arms()
        for arm in arms: arm['cases'] = [c for c in arm['cases'] if c['language'] != 'json']
        with self.assertRaises(ValueError): compare(arms)

    def test_large_first_token_cost_blocks_editing_claim(self):
        arms = self.arms()
        for arm in arms[1:3]:
            for case in arm['cases']: case['ttft_s'] += 0.101
        self.assertEqual(compare(arms)['eligible_languages'], [])

    def test_one_losing_candidate_is_not_saved_by_average(self):
        arms = self.arms()
        for case in arms[1]['cases']: case['wall_s'] = 5.1
        for case in arms[2]['cases']: case['wall_s'] = 4.8
        self.assertEqual(compare(arms)['eligible_languages'], [])

    def test_control_drift_blocks_small_gain(self):
        arms = self.arms()
        for case in arms[3]['cases']:
            case['wall_s'] = 4.98
            case['generation_tok_s'] = 60.24
        self.assertEqual(compare(arms)['eligible_languages'], [])
