"""N02 lookup-row advice per request, the comparison between advice modes and the advice driver, without a model."""
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
from advise_ops import change_pct, compare, parse, request_advice, total
from engines import EXPERIMENTS
from metal_environment import configure
import profile_advise as driver

RECEIPT = ['llama_context: n_batch = 512', 'llama_context: n_ubatch = 512'] * 2


def call(t_us, rows, cold=0, mode='madvise', advice_us=100, check_us=50, failures=0, capped=0, outside=0):
    return dict(t_us=t_us, mode=mode, rows=rows, spans=rows // 2, pages=rows // 2, bytes=rows * 8192,
                capped_spans=capped, overflow_rows=0, outside_spans=outside, cold_before=cold, cold_after=-1,
                advice_us=advice_us, check_us=check_us, failures=failures, errno=0)


def line(advice):
    return 'M5_ADVISE ' + json.dumps(advice)


def summed(cold=0, advice_ms=1.0, failures=0, skipped=0):
    return dict(calls=3, rows=100, pages=50, cold_before=cold, advice_ms=advice_ms, check_ms=0.5, failures=failures,
                skipped_spans=skipped)


def request(name, kind, prompt_ms, cold=0, content='a', tok_s=50.0, disk=2**20, advice_ms=1.0):
    return dict(name=name, kind=kind, prompt_tokens=2080, prompt_ms=prompt_ms, tok_s=tok_s, content=content,
                disk_read_bytes=disk, advice={'prompt': summed(cold, advice_ms), 'reply': summed()})


def launch(mode, documents, warm=(('long', 60.0, 'w'),), peak=40):
    """documents: (name, first ms, replay ms, cold pages) per document."""
    requests = []
    for name, first, replay, cold in documents:
        requests += [request(name, 'first', first, cold), request(name, 'replay', replay)]
    requests += [request(name, 'warm', 500.0, tok_s=speed, content=text) for name, speed, text in warm]
    return dict(mode=mode, requests=requests,
                memory=dict(peak_rss_bytes=peak, minimum_available_bytes=100 - peak, swap_growth_bytes=0))


class RequestAdviceTests(unittest.TestCase):
    def test_parse_reads_only_advice_lines(self):
        advice = call(5, 8192)
        self.assertEqual(parse(['noise', 'x ' + line(advice), 'M5_ADVISED {}']), [advice])

    def test_prompt_calls_follow_the_chunks_and_the_rest_are_the_reply(self):
        calls = [call(900, 8192), call(1000, 8192, cold=300, failures=1), call(1100, 8192, cold=200, capped=2),
                 call(1200, 64, outside=1), call(1300, 64), call(1400, 64), call(9000, 8192)]
        split = request_advice(calls, 1000, 5000, [512, 512, 4])
        self.assertEqual(split['prompt'], dict(calls=3, rows=16448, pages=8224, cold_before=500, advice_ms=0.3,
                                               check_ms=0.15, failures=1, skipped_spans=3))
        self.assertEqual((split['reply']['calls'], split['reply']['rows']), (2, 128))
        self.assertEqual(total([])['calls'], 0)

    def test_requests_whose_calls_do_not_match_the_chunks_are_refused(self):
        calls = [call(1000, 8192), call(1100, 8100)]
        with self.assertRaisesRegex(ValueError, 'do not follow'):
            request_advice(calls, 0, 2000, [512, 500])
        uneven = [call(1000, 8191)]
        with self.assertRaisesRegex(ValueError, 'do not follow'):
            request_advice(uneven, 0, 2000, [512])
        with self.assertRaisesRegex(ValueError, 'Expected 3 prompt advice calls, found 2'):
            request_advice(calls, 0, 2000, [512, 512, 4])
        with self.assertRaisesRegex(ValueError, 'Expected 0'):
            request_advice(calls, 0, 2000, [])


class ComparisonTests(unittest.TestCase):
    def test_penalty_cold_pages_fit_and_changes_against_the_control(self):
        launches = [launch('no-advice', [('a', 300.0, 100.0, 1000), ('b', 500.0, 100.0, 3000)]),
                    launch('madvise', [('c', 200.0, 110.0, 1000), ('d', 260.0, 110.0, 3000)], peak=45)]
        analysis = compare(launches)
        control, advised = analysis['documents']['no-advice'], analysis['documents']['madvise']
        self.assertEqual((control['penalty_ms'], control['cold_pages'], control['documents']), (300.0, 2000, 2))
        self.assertEqual(control['penalty_ms_per_1000_cold_pages'], 600 / 4000 * 1000)
        self.assertEqual(control['fit'], dict(ms_per_1000_cold_pages=100.0, intercept_ms=100.0, points=2))
        self.assertEqual((advised['penalty_ms'], advised['replay_prompt_ms']), (120.0, 110.0))
        self.assertTrue(control['first_replay_identical'])
        self.assertEqual((control['first_disk_read_mib'], control['failures'], control['skipped_spans']), (1.0, 0, 0))
        self.assertEqual(analysis['changes']['madvise']['penalty_ms'], -60.0)
        self.assertAlmostEqual(analysis['changes']['madvise']['replay_prompt_ms'], 10.0)
        self.assertEqual(analysis['launches'], ['no-advice', 'madvise'])
        self.assertEqual(analysis['memory']['madvise']['peak_rss_bytes'], 45)
        self.assertNotIn('rdadvise', analysis['documents'])

    def test_warm_speed_and_text_per_mode(self):
        launches = [launch('no-advice', [], warm=(('long', 60.0, 'w'), ('long', 62.0, 'w'))),
                    launch('rdadvise', [], warm=(('long', 58.0, 'other'),))]
        warm = compare(launches)['warm']
        self.assertEqual(warm['tok_s'], {'long': {'no-advice': 61.0, 'rdadvise': 58.0}})
        self.assertEqual((warm['parity']['identical'], warm['parity']['differing_cases']), (False, ['long']))

    def test_missing_figures_and_control_leave_changes_empty(self):
        launches = [launch('madvise', [('c', 200.0, 200.0, 0)])]
        launches[0]['requests'][0]['disk_read_bytes'] = None
        analysis = compare(launches)
        row = analysis['documents']['madvise']
        self.assertEqual((row['penalty_ms_per_1000_cold_pages'], row['fit'], row['first_disk_read_mib']),
                         (None, None, None))
        self.assertEqual(analysis['changes'], {})
        self.assertEqual((change_pct(1.0, 0), change_pct(None, 1.0), change_pct(3, 2)), (None, None, 50.0))

    def test_launches_of_other_modes_are_refused(self):
        launches = [launch('overlap', [])]
        with self.assertRaisesRegex(ValueError, 'Unknown advice launch mode overlap'):
            compare(launches)


class DocumentTests(unittest.TestCase):
    def test_windows_are_paragraph_runs_and_each_launch_gets_its_own(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / driver.SOURCE
            (source / 'docs').mkdir(parents=True)
            paragraph = 'word ' * 999
            (source / 'docs/a.md').write_text('\n\n'.join([paragraph] * 5))
            (source / 'b.md').write_text(paragraph)
            tracked = 'docs/a.md\nb.md\n'
            with patch.object(driver, 'WINDOW_CHARS', 9000), \
                    patch.object(driver.subprocess, 'check_output', return_value=tracked) as listed:
                # Two runs of two paragraphs; the fifth paragraph and b.md are too short to make one.
                found = driver.windows(root)
                self.assertEqual(listed.call_args.args[0], ['git', '-C', str(source), 'ls-files', '*.md'])
                self.assertEqual([d['name'] for d in found], ['docs/a.md#0', 'docs/a.md#1'])
                self.assertEqual(len(found[0]['text']), 2 * 4995 + 2)
                dealt = driver.assign(2, 1, root=root)
                self.assertEqual(sorted(d[0]['name'] for d in dealt), ['docs/a.md#0', 'docs/a.md#1'])
                with self.assertRaisesRegex(ValueError, 'Only 2 documents for 3'):
                    driver.assign(1, 1, offset=2, root=root)
                kept = driver.assign(1, 1, root=root, exclude=frozenset({dealt[0][0]['name']}))
                self.assertEqual(kept[0][0]['name'], dealt[1][0]['name'])

    def test_earlier_runs_list_the_excerpts_they_were_dealt_and_the_short_ones(self):
        with tempfile.TemporaryDirectory() as tmp:
            for i, (read, short) in enumerate([(['a', 'b'], ['z']), (['c'], ['z'])]):
                folder = Path(tmp) / f'launch-{i + 1}-madvise-check'
                folder.mkdir()
                (folder / 'result.json').write_text(json.dumps(dict(
                    documents=[dict(name=n, sha256='s') for n in read], short_documents=short)))
            self.assertEqual(driver.dealt(Path(tmp)), frozenset('abcz'))
            # a stopped full-run launch lists what it was dealt and has no short list
            folder = Path(tmp) / 'full/launch-3-rdadvise'
            folder.mkdir(parents=True)
            (folder / 'result.json').write_text(json.dumps(dict(status='failed', documents=[dict(name='d', sha256='s')])))
            self.assertEqual(driver.dealt(Path(tmp) / 'full'), frozenset('d'))

    def test_excerpts_are_cut_to_the_same_token_count(self):
        document = dict(name='d', sha256='x', text='t')
        replies = {'/tokenize': {'tokens': list(range(3000))}, '/detokenize': {'content': 'cut'}}
        with patch.object(driver, 'request', side_effect=lambda base, path, body: replies[path]) as sent, \
                patch.object(driver, 'prompt_tokens', return_value=[1, 2]) as rendered:
            self.assertEqual(driver.document_tokens('b', document), [1, 2])
        self.assertEqual(sent.call_args_list[1].args[2], {'tokens': list(range(driver.DOCUMENT_TOKENS))})
        rendered.assert_called_once_with('b', driver.INSTRUCTION + 'cut')
        short = {'/tokenize': {'tokens': [1]}}
        with patch.object(driver, 'request', side_effect=lambda base, path, body: short[path]):
            with self.assertRaisesRegex(ValueError, 'd has only 1 tokens'):
                driver.document_tokens('b', document)


class DriverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_plan_rotates_the_modes_and_checks_use_both_advice_calls(self):
        self.assertEqual(driver.launch_plan(), ['no-advice', 'madvise', 'rdadvise', 'rdadvise', 'madvise', 'no-advice'])
        self.assertEqual(driver.launch_plan(True), ['madvise-check', 'rdadvise-check'])

    def test_each_mode_sets_only_its_advice_and_trace_level(self):
        env, settings = driver.advice_env('no-advice')
        self.assertNotIn('GGML_M5_LAB_ADVISE', env)
        self.assertEqual(settings['diagnostic_env'], {'GGML_M5_LAB_ADVISE_TRACE': '1'})
        env, _ = driver.advice_env('rdadvise-check')
        self.assertEqual((env['GGML_M5_LAB_ADVISE'], env['GGML_M5_LAB_ADVISE_TRACE']), ('rdadvise', '2'))
        control, _ = configure({}, 'm5-small-stack', 'on', 'small-reduce')
        self.assertEqual({k: v for k, v in env.items() if k.startswith('GGML_')},
                         {**{k: v for k, v in control.items() if k.startswith('GGML_')},
                          'GGML_M5_LAB_ADVISE': 'rdadvise', 'GGML_M5_LAB_ADVISE_TRACE': '2'})

    def test_command_is_the_kept_launch_on_the_verified_advice_engine(self):
        with patch.object(driver, 'verify_engine') as verify, \
                patch.object(driver, 'kept_server', return_value=('server',)) as server:
            self.assertEqual(driver.advice_command(7, '512', 'madvise'), ['server'])
        verify.assert_called_once_with('m5-advise')
        server.assert_called_once_with(7, 512, 512, 'm5-advise')

    def test_ask_records_the_window_timings_and_disk_reads(self):
        response = {'content': 'c', 'timings': dict(prompt_n=2, prompt_ms=10.0, predicted_n=3,
                                                     predicted_per_second=50.0, draft_n=4, draft_n_accepted=2)}
        counters = [unittest.mock.Mock(read_bytes=100), unittest.mock.Mock(read_bytes=612)]
        with patch.object(driver, 'request', return_value=response) as sent, \
                patch.object(driver.psutil, 'disk_io_counters', side_effect=counters), \
                patch.object(driver, 'monotonic_us', side_effect=[5, 9]):
            row = driver.ask('b', {'name': 'd', 'kind': 'first'}, [1, 2], 32)
        self.assertEqual(sent.call_args.args[2]['n_predict'], 32)
        self.assertEqual(row, dict(name='d', kind='first', prompt_tokens=2, begin_us=5, end_us=9, prompt_ms=10.0,
                                   predicted_n=3, tok_s=50.0, drafted=4, accepted=2, content='c',
                                   disk_read_bytes=512))
        response['timings']['prompt_n'] = 1
        with patch.object(driver, 'request', return_value=response), \
                patch.object(driver.psutil, 'disk_io_counters', return_value=None):
            with self.assertRaisesRegex(ValueError, 'whole fresh prompt'):
                driver.ask('b', {}, [1, 2], 32)
        self.assertGreater(driver.monotonic_us(), 0)

    def run_requests(self, mode):
        folder = self.folder / mode
        folder.mkdir()
        documents = [dict(name='d1', sha256='s1', text='x'), dict(name='d2', sha256='s2', text='y')]
        driver.ASSIGNED[folder] = documents
        result = dict(mode=mode, requests=[])
        rows = iter(dict(name=n, kind=k, prompt_tokens=1, prompt_ms=1.0, predicted_n=1, tok_s=1.0)
                    for n, k in [('q', 'warmup'), ('d1', 'first'), ('d1', 'replay'), ('d2', 'first'), ('d2', 'replay')]
                    + [(c, 'warm') for c in 'pq' for _ in range(driver.WARM_REPLIES)])
        cases = [dict(name='p', content='P'), dict(name='q', content='Q')]
        with patch.object(driver, 'document_tokens', return_value=[1]), \
                patch.object(driver, 'ask', side_effect=lambda base, row, tokens, n: next(rows)) as ask, \
                patch.object(driver, 'cases', return_value=cases), \
                patch.object(driver, 'prompt_tokens', return_value=[2]), \
                patch.object(driver, 'windows', return_value=documents), \
                patch.object(driver, 'text_tokens', side_effect=[[0] * driver.DOCUMENT_TOKENS, [0]]), \
                redirect_stdout(io.StringIO()):
            driver.advice_requests(folder, result, 'b')
        del driver.ASSIGNED[folder]
        return result, ask

    def test_documents_are_read_twice_then_warm_cases_get_replies(self):
        result, ask = self.run_requests('madvise')
        self.assertEqual(result['documents'], [{'name': 'd1', 'sha256': 's1'}, {'name': 'd2', 'sha256': 's2'}])
        self.assertEqual([r['kind'] for r in result['requests']], ['warmup'] + ['first', 'replay'] * 2 + ['warm'] * 4)
        self.assertEqual([c.args[3] for c in ask.call_args_list], [1] + [32] * 4 + [128] * 4)
        self.assertEqual(ask.call_args_list[0].args[1], {'name': 'q', 'kind': 'warmup'})
        result, _ = self.run_requests('madvise-check')
        self.assertEqual((len(result['requests']), result['short_documents']), (5, ['d2']))

    def analyze(self, mode, lines):
        folder = self.folder / mode
        folder.mkdir()
        (folder / 'native.log').write_text('\n'.join(RECEIPT + lines))
        result = dict(mode=mode, profile='512', requests=[dict(prompt_tokens=48, begin_us=0, end_us=100)])
        driver.advice_analyze(folder, result)
        return result

    def test_analysis_checks_the_markers_and_splits_each_request(self):
        markers = [driver.ELIGIBLE, 'lab: lazy-row advice rdadvise, trace level 2']
        calls = [line(call(10, 704, mode='rdadvise')), line(call(20, 64, mode='rdadvise')),
                 line(call(30, 64, mode='rdadvise'))]
        result = self.analyze('rdadvise-check', markers + calls)
        self.assertEqual(result['requests'][0]['advice']['prompt']['calls'], 2)
        self.assertEqual(result['check'], [dict(rows=704, pages=352, cold_before=0, cold_after=-1, advice_us=100,
                                                check_us=50)])
        control = self.analyze('no-advice', [driver.ELIGIBLE, 'lab: lazy-row advice off, trace level 1',
                                             line(call(10, 704, mode='off')), line(call(20, 64, mode='off'))])
        self.assertNotIn('check', control)
        with self.assertRaisesRegex(ValueError, 'Missing engine marker: lab: lazy-row advice madvise'):
            self.analyze('madvise', [driver.ELIGIBLE])
        unadvised = [driver.ELIGIBLE, 'lab: lazy-row advice rdadvise, trace level 1', line(call(10, 704, mode='off'))]
        with self.assertRaisesRegex(ValueError, 'did not reach the engine'):
            self.analyze('rdadvise', unadvised)

    def test_the_guarded_launch_uses_these_steps_for_every_advice_mode(self):
        import profile_prompt_ops as guarded
        for mode in (*driver.MODES, *driver.CHECKS):
            self.assertIs(guarded.steps(mode), driver.STEPS)
        self.assertEqual(guarded.steps('timing').limitation, guarded.LIMITATION)

    def test_main_prints_the_plan_and_runs_each_launch_under_the_lock(self):
        (self.folder / 'bench').mkdir()
        output = self.folder / 'out'
        with redirect_stdout(io.StringIO()) as printed, patch.object(driver, 'launch_plan') as plan:
            plan.return_value = ['madvise-check']
            driver.main(['--output', str(output), '--check'])
        self.assertIn('2 unseen documents per launch', printed.getvalue())
        self.assertFalse(output.exists())
        documents = [[dict(name=f'd{i}', sha256='s', text='t')] for i in range(6)]
        with ExitStack() as stack:
            for name, value in dict(ROOT=self.folder, assert_no_model_server=None, require_pass=None,
                                    closure={'c': 1}, verify_models={'m': 1}, verify_engine={'e': 1},
                                    assign=documents, compare={'ok': True}).items():
                if name == 'ROOT':
                    stack.enter_context(patch.object(driver, name, value))
                else:
                    stack.enter_context(patch.object(driver, name, return_value=value))
            started = stack.enter_context(patch.object(driver.guarded, 'launch', return_value=dict(status='passed')))
            stack.enter_context(redirect_stdout(io.StringIO()))
            driver.main(['--output', str(output), '--run', '--documents', '5'])
        summary = json.loads((output / 'summary.json').read_text())
        self.assertEqual((summary['launches'], summary['analysis'], summary['engine'], summary['excluded']),
                         (['passed'] * 6, {'ok': True}, {'e': 1}, []))
        self.assertEqual(summary['documents_per_launch'], 5)
        self.assertEqual([c.args[1] for c in started.call_args_list], driver.launch_plan())
        self.assertEqual(started.call_args_list[0].args[0], output / 'launch-1-no-advice')
        with ExitStack() as stack:
            for name, value in dict(assert_no_model_server=None, require_pass=None, closure={'c': 1},
                                    verify_models={'m': 1}, verify_engine={'e': 1}, assign=documents[:2]).items():
                stack.enter_context(patch.object(driver, name, return_value=value))
            stack.enter_context(patch.object(driver, 'ROOT', self.folder))
            stack.enter_context(patch.object(driver, 'dealt', side_effect=lambda f: frozenset({f.name})))
            stack.enter_context(patch.object(driver.guarded, 'launch', return_value=dict(status='passed')))
            stack.enter_context(redirect_stdout(io.StringIO()))
            driver.main(['--output', str(self.folder / 'check'), '--check', '--run', '--exclude', 'c', '--exclude', 'x'])
        summary = json.loads((self.folder / 'check/summary.json').read_text())
        self.assertEqual(('analysis' in summary, summary['excluded'], summary['documents_per_launch']),
                         (False, ['c', 'x'], 2))


class AdviseEngineTests(unittest.TestCase):
    def test_engine_is_the_kept_engine_plus_the_advice_file(self):
        self.assertEqual(EXPERIMENTS['m5-advise'], 'm5_advise_experiment.json')
        kept = json.loads((ROOT / 'config/m5_small_stack_experiment.json').read_text())
        manifest = json.loads((ROOT / 'config/m5_advise_experiment.json').read_text())
        self.assertEqual(manifest['modified_files'], sorted(kept['modified_files'] + ['src/llama-mmap.cpp']))
        self.assertEqual(manifest['features'], kept['features'] + ['m5-advise'])
        self.assertEqual(manifest['components'], kept['components'])
        for switch in ('GGML_M5_LAB_ADVISE=madvise', '=rdadvise', 'GGML_M5_LAB_ADVISE_TRACE=1', '=2'):
            self.assertIn(switch, manifest['scope'])


if __name__ == '__main__':
    unittest.main()
