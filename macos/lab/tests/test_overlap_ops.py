"""N15 helper-overlap timelines, the overlap/serial comparison and the overlap driver mode, without a model."""
from contextlib import redirect_stdout
import hashlib
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
from overlap_ops import OVERLAP_MARKERS, change_pct, compare, length, request_busy, shared, union
import profile_prompt_ops as driver
from prompt_ops import command_buffers

RECEIPT = ['llama_context: n_batch = 512', 'llama_context: n_ubatch = 512'] * 2


def profile(context, graph, start, ms, nodes):
    row = dict(context=context, graph=graph, cb=0, original_nodes=nodes, gpu_start_s=start,
               gpu_end_s=start + ms / 1000, gpu_ms=ms, valid=True, completed=True, op_counts={'MUL_MAT': 1})
    return 'M5_PROFILE ' + json.dumps(row)


def timeline():
    """A 48-token request: target chunks of 44 and 4 tokens; the helper's 44-token work runs during the 4-token chunk,
    then its 4-token work runs alone after a 5 ms gap."""
    return [profile('t', 1, 1.000, 20, 900), profile('t', 2, 1.030, 10, 900), profile('h', 1, 1.032, 6, 90),
            profile('h', 2, 1.045, 2, 90)]


def busy(target=100.0, helper=10.0, during=8.0, idle=2.0):
    return dict(span_ms=target + helper - during + idle, target_ms=target, helper_ms=helper,
                helper_during_target_ms=during, idle_ms=idle)


def launch(mode, profile_name='512', prompt_ms=(100.0, 90.0), tok_s=(60.0,), content='a', drafted=10, peak=40):
    token = {'content': 'x', 'probabilities': [{'id': 1}]}
    requests = [dict(name='long', repeat=i, prompt_ms=ms, busy=busy(target=ms), output=token)
                for i, ms in enumerate(prompt_ms)]
    replies = [dict(name='long', repeat=i, predicted_n=128, tok_s=speed, drafted=drafted, accepted=drafted - 1,
                    content=content) for i, speed in enumerate(tok_s)]
    return dict(mode=mode, profile=profile_name, requests=requests, generations=replies,
                memory=dict(peak_rss_bytes=peak, minimum_available_bytes=100 - peak, swap_growth_bytes=0))


class IntervalTests(unittest.TestCase):
    def test_unions_merge_touching_intervals_and_shared_time_counts_each_overlap_once(self):
        merged = union([(3.0, 4.0), (0.0, 1.0), (1.0, 2.0), (0.5, 1.5)])
        self.assertEqual(merged, [(0.0, 2.0), (3.0, 4.0)])
        self.assertEqual(length(merged), 3.0)
        self.assertEqual(shared(merged, [(1.5, 3.5), (3.75, 5.0)]), 1.25)
        self.assertEqual(shared([(0.0, 1.0)], [(2.0, 3.0)]), 0.0)
        self.assertEqual((union([]), shared([], merged)), ([], 0.0))

    def test_request_busy_splits_target_and_helper_time_and_finds_idle_gaps(self):
        figures = request_busy(command_buffers(timeline()), 't', 0.9, 2.0)
        expected = dict(span_ms=47, target_ms=30, helper_ms=8, helper_during_target_ms=6, idle_ms=15)
        for field, value in expected.items():
            with self.subTest(field=field):
                self.assertAlmostEqual(figures[field], value, places=6)
        outside = request_busy(command_buffers(timeline()), 't', 0.9, 1.044)
        self.assertAlmostEqual(outside['helper_ms'], 6, places=6)
        buffers = command_buffers(timeline())
        with self.assertRaisesRegex(ValueError, 'No target GPU work'):
            request_busy(buffers, 't', 1.031, 2.0)


class ComparisonTests(unittest.TestCase):
    def test_prompt_rows_drop_each_launchs_first_request_and_compare_medians(self):
        launches = [launch('overlap', prompt_ms=(999.0, 90.0, 92.0)), launch('serial', prompt_ms=(999.0, 100.0)),
                    launch('serial', prompt_ms=(5.0, 100.0))]
        prompt = compare(launches)['512']['prompt']['long']
        self.assertEqual(prompt['prompt_ms'], dict(overlap_samples=2, serial_samples=2, overlap=91.0, serial=100.0,
                                                   difference=-9.0, change_pct=-9.0))
        self.assertEqual(prompt['helper_during_target_ms']['overlap'], 8.0)
        for row in launches[1:]:
            for request in row['requests']:
                request['busy']['helper_during_target_ms'] = 0.0
        during = compare(launches)['512']['prompt']['long']['helper_during_target_ms']
        self.assertEqual((during['difference'], 'change_pct' in during), (8.0, False))
        self.assertEqual(change_pct(110.0, 100.0), 10.0)

    def test_reply_speed_drafts_parity_and_memory_per_profile(self):
        launches = [launch('serial', '1536', tok_s=(60.0, 62.0), peak=41), launch('overlap', '1536', tok_s=(63.0,)),
                    launch('overlap', '512', content='b', drafted=12)]
        analysis = compare(launches)
        self.assertEqual(list(analysis), ['512', '1536'])
        wide = analysis['1536']
        self.assertEqual(wide['launches'], ['serial', 'overlap'])
        self.assertEqual(wide['generation']['long']['tok_s'],
                         dict(overlap_samples=1, serial_samples=2, overlap=63.0, serial=61.0, difference=2.0,
                              change_pct=(63.0 - 61.0) / 61.0 * 100))
        self.assertTrue(wide['drafts']['replies']['identical'])
        self.assertEqual(wide['drafts']['drafted_accepted'], {'long': {'serial': [20, 18], 'overlap': [10, 9]}})
        self.assertTrue(wide['prompt_parity']['identical'])
        self.assertEqual(wide['memory']['serial'], dict(launches=1, peak_rss_bytes=41, minimum_available_bytes=59,
                                                        swap_growth_bytes=0))
        narrow = analysis['512']
        self.assertEqual(list(narrow['memory']), ['overlap'])
        self.assertNotIn('change_pct', narrow['generation']['long']['tok_s'])
        self.assertEqual(narrow['generation']['long']['tok_s']['serial_samples'], 0)
        moved = compare([launch('overlap'), launch('serial', content='b')])['512']['drafts']['replies']
        self.assertEqual((moved['identical'], moved['differing_cases']), (False, ['long']))

    def test_launches_of_other_modes_are_refused(self):
        launches = [launch('segments')]
        with self.assertRaisesRegex(ValueError, 'Unknown overlap launch mode segments'):
            compare(launches)


class OverlapDriverTests(unittest.TestCase):
    def test_pairs_mirror_within_each_profile_and_use_the_isolated_engine(self):
        self.assertEqual(driver.launch_plan('overlap', ['512', '1536']),
                         [('overlap', '512'), ('serial', '512'), ('serial', '512'), ('overlap', '512'),
                          ('serial', '1536'), ('overlap', '1536'), ('overlap', '1536'), ('serial', '1536')])
        with patch.object(driver, 'kept_server', return_value=['server', '--verbosity', '4']) as server:
            driver.launch_command(1, '512', 'serial')
            driver.launch_command(1, '512', 'overlap')
        self.assertEqual([call.args[3] for call in server.call_args_list], ['m5-overlap', 'm5-overlap'])
        env, settings = driver.launch_env('overlap')
        self.assertEqual((env['GGML_M5_LAB_CONTEXT_QUEUE'], env['GGML_M5_LAB_HELPER_OVERLAP']), ('1', '1'))
        self.assertEqual((settings['diagnostic_env'], env['GGML_M5_LAB_PROFILE']), (driver.OVERLAP_ENV, '1'))
        env, settings = driver.launch_env('serial')
        self.assertFalse(set(driver.OVERLAP_ENV) & set(env))
        self.assertEqual(settings['diagnostic_env'], {})

    def test_plan_names_both_variants_and_the_replies(self):
        output = io.StringIO()
        with redirect_stdout(output):
            driver.main(['--mode', 'overlap', '--profile', '1536', '--output', '/nonexistent'])
        self.assertIn('overlap launches overlap-1536/serial-1536/serial-1536/overlap-1536; m5-overlap engine',
                      output.getvalue())
        self.assertIn('then 3 128-token replies.', output.getvalue())

    def test_prompts_record_probabilities_and_replies_record_speed_drafts_and_text(self):
        prompt = dict(timings=dict(prompt_n=2, prompt_ms=3.0, prompt_per_second=9.0), content='a',
                      completion_probabilities=[{'id': 7}])
        case = dict(name='short-prose', kind='prose', content='x')
        with patch.object(driver, 'request', return_value=prompt) as call:
            row = driver.measure('http://x', case, [1, 2], 0, 'serial')
        self.assertEqual(call.call_args.args[2]['n_probs'], driver.PROBABILITIES)
        self.assertEqual(row['output'], {'content': 'a', 'probabilities': [{'id': 7}]})
        timings = dict(prompt_n=2, prompt_ms=3.0, predicted_n=128, predicted_per_second=61.5, draft_n=40,
                       draft_n_accepted=33)
        with patch.object(driver, 'request', return_value=dict(timings=timings, content='abc')) as call:
            row = driver.reply('http://x', case, [1, 2], 1)
        payload = call.call_args.args[2]
        self.assertEqual((payload['n_predict'], payload['temperature'], payload['cache_prompt']), (128, 0, False))
        self.assertEqual(row, dict(name='short-prose', repeat=1, prompt_ms=3.0, predicted_n=128, tok_s=61.5,
                                   drafted=40, accepted=33, content='abc'))
        bare = {key: timings[key] for key in ('prompt_n', 'prompt_ms', 'predicted_n', 'predicted_per_second')}
        with patch.object(driver, 'request', return_value=dict(timings=bare, content='')):
            self.assertEqual(driver.reply('http://x', case, [1, 2], 0)['drafted'], 0)
        with patch.object(driver, 'request', return_value=dict(timings=dict(timings, prompt_n=1), content='')), \
                self.assertRaisesRegex(ValueError, 'whole fresh prompt'):
            driver.reply('http://x', case, [1, 2], 0)

    def test_each_case_is_read_three_times_then_answered_three_times(self):
        cases = [dict(name='a', kind='prose', content='x'), dict(name='b', kind='prose', content='y')]
        reply = dict(predicted_n=128, tok_s=60.0, drafted=40, accepted=33)
        result = dict(mode='overlap', profile='512', requests=[])
        with tempfile.TemporaryDirectory() as tmp, patch.object(driver, 'cases', return_value=cases), \
                patch.object(driver, 'prompt_tokens', return_value=[1, 2]), \
                patch.object(driver, 'measure', return_value=dict(prompt_tok_s=100.0)), \
                patch.object(driver, 'reply', side_effect=lambda b, c, t, r: dict(reply, name=c['name'], repeat=r)), \
                redirect_stdout(io.StringIO()) as printed:
            driver.run_requests(Path(tmp), result, 'http://x')
            written = json.loads((Path(tmp) / 'result.json').read_text())
        self.assertEqual([(row['name'], row['repeat']) for row in written['generations']],
                         [('a', 0), ('a', 1), ('a', 2), ('b', 0), ('b', 1), ('b', 2)])
        self.assertEqual(len(written['requests']), 6)
        self.assertIn('overlap/512: b reply 2: 128 tokens, 60.00 tok/s, drafted 40, accepted 33', printed.getvalue())

    def analyze(self, mode, markers):
        lines = [*RECEIPT, *markers, *timeline()]
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'native.log').write_text('\n'.join(lines))
            request = dict(repeat=0, begin_monotonic_s=0.9, end_monotonic_s=2.0, prompt_tokens=48)
            result = dict(mode=mode, profile='512', requests=[request])
            driver.analyze(Path(tmp), result)
        return result

    def test_analysis_checks_both_switches_and_adds_request_timelines(self):
        result = self.analyze('overlap', OVERLAP_MARKERS)
        self.assertAlmostEqual(result['requests'][0]['busy']['helper_during_target_ms'], 6, places=6)
        self.assertEqual(result['timing']['all_requests']['4']['helper_ms'], 8)
        serial = self.analyze('serial', [])
        self.assertAlmostEqual(serial['requests'][0]['busy']['idle_ms'], 15, places=6)
        for mode, markers in (('overlap', OVERLAP_MARKERS[:1]), ('serial', OVERLAP_MARKERS[1:])):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'overlap settings did not reach'):
                self.analyze(mode, markers)

    def test_main_runs_mirrored_pairs_and_writes_the_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'bench').mkdir()
            output = folder / 'out'
            with patch.object(driver, 'ROOT', folder), patch.object(driver, 'assert_no_model_server'), \
                    patch.object(driver, 'require_pass'), patch.object(driver, 'closure', return_value={}), \
                    patch.object(driver, 'verify_models', return_value={}), \
                    patch.object(driver, 'launch', side_effect=lambda f, m, p, z: dict(status='passed', mode=m)) \
                    as run, patch.object(driver, 'overlap_compare', return_value={'512': 'ok'}) as analysis, \
                    redirect_stdout(io.StringIO()):
                driver.main(['--mode', 'overlap', '--profile', '512', '--output', str(output), '--run'])
            self.assertEqual([call.args[0].name for call in run.call_args_list],
                             ['launch-1-overlap-512', 'launch-2-serial-512', 'launch-3-serial-512',
                              'launch-4-overlap-512'])
            self.assertEqual([r['mode'] for r in analysis.call_args.args[0]],
                             ['overlap', 'serial', 'serial', 'overlap'])
            self.assertEqual(json.loads((output / 'summary.json').read_text())['analysis'], {'512': 'ok'})

    def test_launch_records_the_reply_limitation_only_for_overlap_modes(self):
        def finish(folder, result, owned, frozen):
            result['status'] = 'passed'

        with tempfile.TemporaryDirectory() as tmp, patch.object(driver, 'run_launch'), \
                patch.object(driver, 'finish_launch', side_effect=finish):
            paired = driver.launch(Path(tmp) / 'a', 'serial', '512', {})
            plain = driver.launch(Path(tmp) / 'b', 'timing', '512', {})
        self.assertTrue(paired['limitation'].endswith(driver.OVERLAP_LIMITATION))
        self.assertEqual(plain['limitation'], driver.LIMITATION)


class OverlapEngineTests(unittest.TestCase):
    def test_engine_is_registered_beside_the_kept_engine_with_the_same_settings(self):
        self.assertEqual(EXPERIMENTS['m5-overlap'], 'm5_overlap_experiment.json')
        control, _ = configure({}, 'm5-small-stack', 'on', 'small-reduce', profile=True)
        candidate, _ = configure({}, 'm5-overlap', 'on', 'small-reduce', profile=True)
        self.assertEqual(candidate, control)
        for tuning in ('compact-cols', 'route-map', 'encoders0'):
            with self.subTest(tuning=tuning), self.assertRaises(ValueError):
                configure({}, 'm5-overlap', 'on', tuning)

    def test_the_app_setting_adds_only_the_two_overlap_switches_and_needs_the_overlap_engine(self):
        kept, _ = configure({}, 'm5-small-stack', 'on', 'small-reduce')
        app, receipt = configure({'GGML_M5_LAB_HELPER_OVERLAP': '0'}, 'm5-overlap', 'on', 'overlap-reduce')
        self.assertEqual(app, {**kept, 'GGML_M5_LAB_CONTEXT_QUEUE': '1', 'GGML_M5_LAB_HELPER_OVERLAP': '1'})
        self.assertEqual(receipt['tuning'], 'overlap-reduce')
        for engine in ('m5-small-stack', 'm5-segments', 'm5-advise'):
            with self.subTest(engine=engine), self.assertRaisesRegex(ValueError, 'isolated m5-overlap engine'):
                configure({}, engine, 'on', 'overlap-reduce')

    def test_manifest_binds_the_patch_and_every_kept_stack_component(self):
        manifest = json.loads((ROOT / 'config/m5_overlap_experiment.json').read_text())
        patch_hash = hashlib.sha256((ROOT / manifest['patch']).read_bytes()).hexdigest()
        self.assertEqual((manifest['patch_sha256'], manifest['source_diff_sha256']), (patch_hash, patch_hash))
        kept = json.loads((ROOT / 'config/m5_small_stack_experiment.json').read_text())
        self.assertEqual(manifest['modified_files'],
                         sorted([*kept['modified_files'], 'common/speculative.cpp', 'common/speculative.h',
                                 'tools/server/server-context.cpp']))
        self.assertEqual(manifest['features'], [*kept['features'], 'm5-overlap'])
        self.assertIn({'patch': kept['patch'], 'sha256': kept['patch_sha256']}, manifest['components'])
        for component in manifest['components']:
            self.assertEqual(hashlib.sha256((ROOT / component['patch']).read_bytes()).hexdigest(), component['sha256'])
        for switch in ('GGML_M5_LAB_CONTEXT_QUEUE', 'GGML_M5_LAB_HELPER_OVERLAP', 'GGML_M5_LAB_OVERLAP_TRACE'):
            self.assertIn(switch, manifest['scope'])


if __name__ == '__main__':
    unittest.main()
