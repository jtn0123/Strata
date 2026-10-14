"""N06 MTP state saves and restores per request, the comparison between modes and the state driver, without a model."""
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from engines import EXPERIMENTS
from metal_environment import configure
from mtpstate_ops import compare, parse, request_state
import profile_mtpstate as driver

RECEIPT = ['llama_context: n_batch = 512', 'llama_context: n_ubatch = 512'] * 2


def save(t_us, rows=508, size=4096):
    return dict(t_us=t_us, event='save', seq=0, rows=rows, bytes=size)


def restore(t_us, applied=False, valid=True, drift=0.5):
    return dict(t_us=t_us, event='restore', seq=0, bytes=4096, valid=valid, applied=applied, saved_rows=508,
                current_rows=3, pending_rel_diff=drift, pending_max_abs=2.0)


def line(event):
    return 'M5_MTPSTATE ' + json.dumps(event)


def state(restores=(), saves=1):
    return dict(saves=saves, save_bytes=4096 * saves,
                restores=[dict(valid=v, applied=a, pending_rel_diff=d, pending_max_abs=2.0) for v, a, d in restores])


def request(name, kind, accepted, drafted=60, content='a', restores=(), tok_s=50.0):
    return dict(name=name, kind=kind, prompt_n=4, cache_n=2000, predicted_n=100, tok_s=tok_s, drafted=drafted,
                accepted=accepted, content=content, state=state(restores))


def launch(mode, accepted, content='a', peak=40):
    """accepted: per conversation, accepted drafts for its first reply, regenerate, follow-up and edit."""
    applied = mode == 'restore'
    requests = [request('w', 'warmup', 0, drafted=0)]
    for name, counts in accepted.items():
        for kind, n in zip(('first', 'regenerate', 'follow-up', 'edit'), counts, strict=True):
            restored = () if kind == 'first' else ((True, applied, 0.25 if kind == 'edit' else 0.5),)
            requests.append(request(name, kind, n, content=content, restores=restored))
    return dict(mode=mode, requests=requests,
                memory=dict(peak_rss_bytes=peak, minimum_available_bytes=100 - peak, swap_growth_bytes=0))


class RequestStateTests(unittest.TestCase):
    def test_parse_reads_only_state_lines(self):
        event = save(5)
        self.assertEqual(parse(['noise', 'x ' + line(event), 'M5_MTPSTATES {}']), [event])

    def test_saves_and_restores_are_matched_to_the_request_window(self):
        events = [save(900), save(1000), restore(1100, applied=True), save(1200, size=100), restore(9000)]
        self.assertEqual(request_state(events, 1000, 5000), dict(
            saves=2, save_bytes=4196,
            restores=[dict(valid=True, applied=True, pending_rel_diff=0.5, pending_max_abs=2.0)]))


class ComparisonTests(unittest.TestCase):
    def test_repeatable_launches_regenerated_replies_and_paired_acceptance(self):
        launches = [launch('stale', dict(p=(50, 45, 40, 30), q=(20, 20, 10, 5))),
                    launch('restore', dict(p=(50, 50, 42, 30), q=(20, 20, 10, 6))),
                    launch('restore', dict(p=(50, 50, 42, 30), q=(20, 20, 10, 6))),
                    launch('stale', dict(p=(50, 45, 40, 30), q=(20, 21, 10, 5)), peak=42)]
        result = compare(launches)
        self.assertEqual(result['launches'], ['stale', 'restore', 'restore', 'stale'])
        self.assertEqual(result['repeatable'], {
            'stale': dict(launches=2, identical=False, differing=['q regenerate']),
            'restore': dict(launches=2, identical=True, differing=[])})
        self.assertEqual(result['regenerated']['restore'],
                         dict(pairs=4, identical_drafts=4, same_text=4, accepted_change=0))
        self.assertEqual(result['regenerated']['stale'],
                         dict(pairs=4, identical_drafts=1, same_text=4, accepted_change=-9))
        stale = result['acceptance']['stale']
        self.assertEqual((stale['all']['drafted'], stale['all']['accepted'], stale['regenerate']['requests']),
                         (960, 441, 4))
        self.assertAlmostEqual(stale['all']['rate'], 441 / 960)
        self.assertEqual(stale['first']['tok_s'], 50.0)
        self.assertEqual(result['restores']['restore'], dict(
            restores=12, by_kind={'first': 0, 'regenerate': 4, 'follow-up': 4, 'edit': 4}, applied=12, invalid=0,
            pending_rel_diff_median=0.5, pending_rel_diff_max=0.5, saves=18, save_bytes_max=4096))
        self.assertEqual(result['restores']['stale']['applied'], 0)
        paired = result['paired']
        self.assertEqual((paired['requests'], paired['accepted_stale'], paired['accepted_restore']), (8, 220.5, 228))
        self.assertAlmostEqual(paired['accepted_change_pct'], 7.5 / 220.5 * 100)
        self.assertEqual((paired['higher'], paired['lower']), (3, 1))
        self.assertEqual(paired['deltas'], {'p regenerate': 5, 'p follow-up': 2, 'q regenerate': -0.5, 'q edit': 1})
        self.assertTrue(result['parity']['identical'])
        self.assertEqual(result['memory']['stale'], dict(launches=2, peak_rss_bytes=42, minimum_available_bytes=58,
                                                         swap_growth_bytes=0))

    def test_one_launch_per_mode_and_different_text(self):
        launches = [launch('stale', dict(p=(1, 1, 1, 1))), launch('restore', dict(p=(1, 1, 1, 1)), content='b')]
        launches[0]['requests'][2]['state']['restores'][0]['valid'] = False
        launches[0]['requests'][2]['drafted'] = 0
        result = compare(launches)
        self.assertEqual(result['repeatable'], {})
        self.assertEqual(result['parity']['differing_cases'], ['p edit', 'p first', 'p follow-up', 'p regenerate'])
        self.assertEqual(result['restores']['stale']['invalid'], 1)
        self.assertEqual(result['acceptance']['stale']['regenerate']['rate'], None)
        self.assertEqual(compare([launch('stale', {})])['restores']['stale']['pending_rel_diff_median'], None)
        lone = dict(launch('stale', {}), requests=[request('p', 'first', 1)])
        self.assertEqual(compare([lone])['acceptance']['stale']['edit'],
                         dict(requests=0, drafted=0, accepted=0, rate=None, tok_s=None))

    def test_launches_of_other_modes_are_refused(self):
        with self.assertRaisesRegex(ValueError, 'Unknown MTP state launch mode madvise'):
            compare([launch('madvise', {})])


class DriverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_plan_rotates_the_modes(self):
        self.assertEqual(driver.launch_plan(), ['stale', 'restore', 'restore', 'stale'])

    def test_each_mode_sets_only_its_state_switch_and_the_trace(self):
        env, settings = driver.state_env('stale')
        self.assertNotIn('GGML_M5_LAB_MTP_STATE', env)
        self.assertEqual(settings['diagnostic_env'], {'GGML_M5_LAB_MTP_STATE_TRACE': '1'})
        env, _ = driver.state_env('restore')
        control, _ = configure({}, 'm5-small-stack', 'on', 'small-reduce')
        self.assertEqual({k: v for k, v in env.items() if k.startswith('GGML_')},
                         {**{k: v for k, v in control.items() if k.startswith('GGML_')},
                          'GGML_M5_LAB_MTP_STATE': 'restore', 'GGML_M5_LAB_MTP_STATE_TRACE': '1'})

    def test_command_is_the_kept_launch_on_the_verified_state_engine(self):
        with patch.object(driver, 'verify_engine') as verify, \
                patch.object(driver, 'kept_server', return_value=('server',)) as server:
            self.assertEqual(driver.state_command(7, '512', 'restore'), ['server'])
        verify.assert_called_once_with('m5-mtpstate')
        server.assert_called_once_with(7, 512, 512, 'm5-mtpstate')

    def test_chat_keeps_the_prompt_cache_and_records_the_window(self):
        response = {'choices': [{'message': {'content': 'c'}}],
                    'timings': dict(prompt_n=4, cache_n=2000, prompt_ms=10.0, predicted_n=3, predicted_per_second=50.0,
                                    draft_n=4, draft_n_accepted=2)}
        with patch.object(driver, 'request', return_value=response) as sent, \
                patch.object(driver, 'monotonic_us', side_effect=[5, 9]):
            row = driver.chat('b', {'name': 'p', 'kind': 'first'}, [{'role': 'user', 'content': 'u'}], 128)
        path, payload = sent.call_args.args[1:3]
        self.assertEqual((path, payload['max_tokens'], payload['cache_prompt'], payload['temperature']),
                         ('/v1/chat/completions', 128, True, 0))
        self.assertEqual(payload['chat_template_kwargs'], {'enable_thinking': False})
        self.assertEqual(row, dict(name='p', kind='first', begin_us=5, end_us=9, prompt_n=4, cache_n=2000,
                                   prompt_ms=10.0, predicted_n=3, tok_s=50.0, drafted=4, accepted=2, content='c'))
        del response['timings']['draft_n'], response['timings']['draft_n_accepted']
        with patch.object(driver, 'request', return_value=response):
            row = driver.chat('b', {}, [], 1)
        self.assertEqual((row['drafted'], row['accepted']), (0, 0))
        self.assertGreater(driver.monotonic_us(), 0)

    def test_each_case_is_one_conversation_of_four_requests(self):
        folder = self.folder / 'stale'
        folder.mkdir()
        result = dict(mode='stale', requests=[])
        sent = []

        def chat(base, row, messages, max_tokens):
            sent.append((row['kind'], messages, max_tokens))
            return dict(row, prompt_n=1, cache_n=0, predicted_n=1, tok_s=1.0, drafted=0, accepted=0,
                        content=f"reply {row['name']} {row['kind']}")

        cases = [dict(name='p', content='P'), dict(name='q', content='Q')]
        with patch.object(driver, 'chat', side_effect=chat), patch.object(driver, 'cases', return_value=cases), \
                redirect_stdout(io.StringIO()) as printed:
            driver.state_requests(folder, result, 'b')
        self.assertEqual([r['kind'] for r in result['requests']],
                         ['warmup'] + ['first', 'regenerate', 'follow-up', 'edit'] * 2)
        self.assertEqual(sent[0], ('warmup', [{'role': 'user', 'content': 'Q'}], 1))
        opening = [{'role': 'user', 'content': 'P'}]
        reply = {'role': 'assistant', 'content': 'reply p first'}
        self.assertEqual(sent[1:5], [('first', opening, 128), ('regenerate', opening, 128),
                                     ('follow-up', [*opening, reply, {'role': 'user', 'content': driver.FOLLOW_UP}], 128),
                                     ('edit', [*opening, reply, {'role': 'user', 'content': driver.EDIT}], 128)])
        self.assertIn('stale: p edit: 1 new and 0 cached tokens, 1 tokens at 1.00 tok/s, 0/0 drafts accepted',
                      printed.getvalue())
        self.assertEqual(json.loads((folder / 'result.json').read_text())['requests'][-1]['kind'], 'edit')

    def analyze(self, mode, lines):
        folder = Path(tempfile.mkdtemp(dir=self.folder))
        (folder / 'native.log').write_text('\n'.join(RECEIPT + lines))
        result = dict(mode=mode, profile='512', requests=[dict(begin_us=0, end_us=100)])
        driver.state_analyze(folder, result)
        return result

    def test_analysis_checks_the_marker_and_the_applied_restores(self):
        checkpoints = ['slot create_check: id  0 | task 3 | created context checkpoint 1 of 32 (pos_min = 1)',
                       'slot create_check: id  0 | task 3 | created context checkpoint 3 of 32 (pos_min = 9)']
        result = self.analyze('restore', ['lab: MTP checkpoint state restore, trace on', line(save(10)),
                                          line(restore(20, applied=True)), line(restore(30, valid=False)),
                                          *checkpoints])
        self.assertEqual(result['requests'][0]['state']['saves'], 1)
        self.assertEqual(len(result['requests'][0]['state']['restores']), 2)
        self.assertEqual(result['checkpoints_max'], 3)
        self.assertEqual(self.analyze('stale', ['lab: MTP checkpoint state stale, trace on',
                                                line(restore(20))])['checkpoints_max'], 0)
        with self.assertRaisesRegex(ValueError, 'Missing engine marker: lab: MTP checkpoint state restore'):
            self.analyze('restore', [])
        with self.assertRaisesRegex(ValueError, 'did not reach the engine'):
            self.analyze('restore', ['lab: MTP checkpoint state restore, trace on', line(restore(20))])
        with self.assertRaisesRegex(ValueError, 'no checkpoint was restored'):
            self.analyze('restore', ['lab: MTP checkpoint state restore, trace on', line(save(10))])

    def test_the_guarded_launch_uses_these_steps_for_both_modes(self):
        import profile_prompt_ops as guarded
        for mode in driver.launch_plan():
            self.assertIs(guarded.steps(mode), driver.STEPS)

    def test_main_prints_the_plan_and_runs_each_launch_under_the_lock(self):
        (self.folder / 'bench').mkdir()
        output = self.folder / 'out'
        with redirect_stdout(io.StringIO()) as printed:
            driver.main(['--output', str(output)])
        self.assertIn('regenerate, follow-up and edited follow-up', printed.getvalue())
        self.assertFalse(output.exists())
        with ExitStack() as stack:
            for name, value in dict(assert_no_model_server=None, require_pass=None, closure={'c': 1},
                                    verify_models={'m': 1}, verify_engine={'e': 1}, compare={'ok': True}).items():
                stack.enter_context(patch.object(driver, name, return_value=value))
            stack.enter_context(patch.object(driver, 'ROOT', self.folder))
            started = stack.enter_context(patch.object(driver.guarded, 'launch', return_value=dict(status='passed')))
            stack.enter_context(redirect_stdout(io.StringIO()))
            driver.main(['--output', str(output), '--run'])
        summary = json.loads((output / 'summary.json').read_text())
        self.assertEqual((summary['launches'], summary['analysis'], summary['engine']), (['passed'] * 4, {'ok': True},
                                                                                        {'e': 1}))
        self.assertEqual([c.args[1] for c in started.call_args_list], driver.launch_plan())
        self.assertEqual(started.call_args_list[0].args[0], output / 'launch-1-stale')


class StateEngineTests(unittest.TestCase):
    def test_engine_is_the_kept_engine_plus_the_speculative_file(self):
        self.assertEqual(EXPERIMENTS['m5-mtpstate'], 'm5_mtpstate_experiment.json')
        kept = json.loads((ROOT / 'config/m5_small_stack_experiment.json').read_text())
        manifest = json.loads((ROOT / 'config/m5_mtpstate_experiment.json').read_text())
        self.assertEqual(manifest['modified_files'], sorted(kept['modified_files'] + ['common/speculative.cpp']))
        self.assertEqual(manifest['features'], kept['features'] + ['m5-mtpstate'])
        self.assertEqual(manifest['components'], kept['components'])
        for switch in ('GGML_M5_LAB_MTP_STATE=restore', 'GGML_M5_LAB_MTP_STATE_TRACE=1', 'PR 30141'):
            self.assertIn(switch, manifest['scope'])


if __name__ == '__main__':
    unittest.main()
