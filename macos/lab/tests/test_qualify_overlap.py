"""N15 qualification: lifecycle checks, memory, the decision and the bracket driver, without a model."""
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from qualify_ops import RSS_ALLOWANCE, checks, decision, lifecycle_bracket, memory
import qualify_overlap as driver

KINDS = ('first', 'regenerate', 'follow-up', 'edit')
MIB = 2**20


def turn(name, kind, content=None, drafted=10, accepted=7):
    return dict(name=name, kind=kind, prompt_n=4, cache_n=100, prompt_ms=5.0, predicted_n=20, tok_s=50.0,
                drafted=drafted, accepted=accepted, content=content or f'{name} {"first" if kind == "regenerate" else kind}')


def lifecycle(stopped=512, cache_n=512, good=True, repeat=True, restores=2, turns=None):
    return dict(cancel=dict(after_s=0.5, reply_started=False, prompt_tokens=2332, stopped_tokens=stopped),
                resume=dict(prompt_n=2332 - cache_n, cache_n=cache_n, drafted=20, accepted=15, quality_passed=good,
                            matches_fresh=True),
                repeat_matches=repeat, restores=restores,
                conversation=[turn('p', k) for k in KINDS] if turns is None else turns)


def row(name, phase='first-exposure', regressions=(), eligible=True):
    return dict(name=name, phase=phase, regressions=list(regressions), eligible_prompt_scope=eligible)


def bracket(rows=None, parity=True, good=True, passed=True, clean=True):
    rows = rows if rows is not None else [row('long-retrieval'), row('long-retrieval', 'replay'), row('short-prose',
                                                                                                    eligible=False)]
    return dict(rows=rows, exact_output_parity=parity, all_quality_checks_pass=good, lifecycle=dict(passed=passed),
                memory=dict(clean=clean))


class CheckTests(unittest.TestCase):
    def test_a_clean_launch_passes_every_check(self):
        self.assertEqual(checks(lifecycle()), dict(cancelled_mid_prompt=True, resumed=True, repeat_matches=True,
                                                   regenerate_matches=True, restored=True))

    def test_each_fault_fails_its_own_check(self):
        self.assertFalse(checks(lifecycle(stopped=2332))['cancelled_mid_prompt'])
        self.assertFalse(checks(lifecycle(good=False))['resumed'])
        self.assertFalse(checks(lifecycle(repeat=False))['repeat_matches'])
        self.assertFalse(checks(lifecycle(restores=0))['restored'])
        changed = [turn('p', 'first'), turn('p', 'regenerate', content='other')]
        self.assertFalse(checks(lifecycle(turns=changed))['regenerate_matches'])
        self.assertFalse(checks(lifecycle(turns=[turn('p', 'first')]))['regenerate_matches'])


class BracketTests(unittest.TestCase):
    def test_agreeing_launches_pass_and_report_their_cancel_and_resume(self):
        result = lifecycle_bracket([lifecycle(), lifecycle(stopped=1024, cache_n=1024)] * 2)
        self.assertTrue(result['passed'])
        self.assertEqual((result['conversation_parity'], result['same_drafts'], result['same_reuse_after_cancel']),
                         (True, True, True))
        self.assertEqual(result['stopped_tokens'], [512, 1024, 512, 1024])
        self.assertEqual(result['resume_cache_n'], [512, 1024, 512, 1024])
        self.assertEqual(result['resume_drafts'], [(15, 20)] * 4)
        self.assertEqual((result['restores'], result['resume_matches_fresh']), ([2] * 4, [True] * 4))

    def test_launches_that_disagree_fail(self):
        other_text = [turn('p', k, content='x') for k in KINDS]
        other_drafts = [turn('p', k, accepted=6) for k in KINDS]
        for launches, key in (([lifecycle(), lifecycle(turns=other_text)], 'conversation_parity'),
                              ([lifecycle(), lifecycle(turns=other_drafts)], 'same_drafts'),
                              ([lifecycle(), lifecycle(cache_n=0)], 'same_reuse_after_cancel')):
            result = lifecycle_bracket(launches)
            self.assertFalse(result[key])
            self.assertFalse(result['passed'])
        self.assertFalse(lifecycle_bracket([lifecycle(), lifecycle(restores=0)])['passed'])
        self.assertFalse(lifecycle_bracket([])['passed'])
        self.assertFalse(lifecycle_bracket([lifecycle(turns=[]), lifecycle(turns=[])])['conversation_parity'])


class MemoryTests(unittest.TestCase):
    def launches(self, *peaks):
        return [dict(peak_rss_bytes=p, minimum_available_bytes=10 * MIB) for p in peaks]

    def test_the_candidate_may_use_the_allowance_or_twice_the_control_spread(self):
        result = memory(self.launches(1000 * MIB, 1100 * MIB, 1120 * MIB, 1000 * MIB))
        self.assertEqual((result['candidate_extra_average_rss_bytes'], result['allowed_bytes']), (110 * MIB,
                                                                                                 RSS_ALLOWANCE))
        self.assertTrue(result['clean'])
        self.assertEqual(result['minimum_available_bytes'], [10 * MIB] * 4)
        self.assertFalse(memory(self.launches(1000 * MIB, 1200 * MIB, 1200 * MIB, 1000 * MIB))['clean'])
        wide = memory(self.launches(1000 * MIB, 1300 * MIB, 1300 * MIB, 1200 * MIB))
        self.assertEqual(wide['allowed_bytes'], 400 * MIB)
        self.assertTrue(wide['clean'])

    def test_only_a_complete_bracket_is_scored(self):
        with self.assertRaisesRegex(ValueError, 'Four launches'):
            memory(self.launches(1, 2))


class DecisionTests(unittest.TestCase):
    def test_every_bracket_passing_with_the_default_long_gain_qualifies(self):
        result = decision({'default': bracket(), 'code-edit': bracket(rows=[row('short-prose', eligible=False)])})
        self.assertEqual((result['qualified'], result['reasons'], result['brackets']),
                         (True, [], ['code-edit', 'default']))
        self.assertIn('Every bracket', result['rule'])

    def test_every_fault_is_a_reason(self):
        regressed = [row('long-retrieval'), row('long-retrieval', 'replay'),
                     row('short-prose', regressions=['generation TPS', 'whole reply'])]
        result = decision({'default': bracket(), 'long-documents': bracket(
            rows=regressed, parity=False, good=False, passed=False, clean=False)})
        self.assertFalse(result['qualified'])
        self.assertEqual(result['reasons'], [
            'long-documents: the outputs differ between launches',
            'long-documents: a quality check failed',
            'long-documents: a lifecycle check failed',
            'long-documents: the candidate used more memory than allowed',
            'long-documents: short-prose first-exposure regressed in generation TPS, whole reply'])

    def test_the_default_bracket_must_show_the_long_prompt_gain(self):
        slow = bracket(rows=[row('long-retrieval'), row('long-retrieval', 'replay', eligible=False)])
        self.assertEqual(decision({'default': slow})['reasons'],
                         ['default: no qualifying gain for long-retrieval replay'])
        self.assertEqual(decision({'code-edit': bracket()})['reasons'], ['default: no long-prompt rows to qualify'])
        self.assertEqual(decision({'default': bracket(rows=[])})['reasons'],
                         ['default: no long-prompt rows to qualify'])


class Connection:
    """Records the request, the socket shutdown and the close of one abort, and hands out what the server sent."""

    def __init__(self, netloc, timeout, sent):
        self.netloc, self.timeout, self.events, self.sent = netloc, timeout, [], list(sent)
        self.sock = self

    def request(self, method, path, body, headers):
        self.events.append((method, path, json.loads(body), headers))

    def recv(self, size):
        return self.sent.pop(0) if self.sent else b''

    def shutdown(self, how):
        self.events.append(('shutdown', how))

    def close(self):
        self.events.append('close')


class DriverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        (self.folder / 'native.log').write_text('loaded\n')

    def tearDown(self):
        self.tmp.cleanup()

    def append(self, *lines):
        with (self.folder / 'native.log').open('a') as log:
            log.write(''.join(f'{line}\n' for line in lines))

    def test_the_log_is_read_from_an_offset_and_stops_are_parsed(self):
        offset = driver.log_size(self.folder)
        self.append('srv: stop processing: n_tokens = 1024, truncated = 0', 'other')
        self.assertEqual(driver.log_since(self.folder, offset).splitlines()[1], 'other')
        self.assertEqual(driver.stops(driver.log_since(self.folder, offset)), [1024])
        self.assertEqual(driver.wait_stop(self.folder, offset), 1024)
        with self.assertRaisesRegex(RuntimeError, 'did not stop'):
            driver.wait_stop(self.folder, driver.log_size(self.folder), timeout_s=0.2)

    def abort(self, *sent):
        made = []

        def connect(netloc, timeout):
            made.append(Connection(netloc, timeout, sent))
            return made[-1]

        def select(r, w, x, t):
            return (r if made[0].sent else [], w, x)

        with patch.object(driver.http.client, 'HTTPConnection', side_effect=connect), \
                patch.object(driver.select, 'select', side_effect=select):
            started = driver.abort('http://127.0.0.1:7/', [1, 2], 0)
        return started, made[0]

    def test_abort_sends_a_cached_stream_and_reports_whether_reply_data_had_arrived(self):
        started, connection = self.abort()
        self.assertFalse(started)
        self.assertEqual((connection.netloc, connection.timeout), ('127.0.0.1:7', 60))
        method, path, payload, headers = connection.events[0]
        self.assertEqual((method, path, headers), ('POST', '/completion', {'Content-Type': 'application/json'}))
        self.assertEqual((payload['prompt'], payload['cache_prompt'], payload['stream'], payload['n_predict']),
                         ([1, 2], True, True, driver.MAX_OUTPUT))
        self.assertEqual(connection.events[1:], [('shutdown', socket.SHUT_RDWR), 'close'])
        headers = b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n\r\n'
        self.assertFalse(self.abort(headers)[0])
        self.assertTrue(self.abort(headers, b'data: {"content": "{"}\n\n')[0])

    def test_resume_keeps_the_cache_and_checks_quality_against_the_fresh_reply(self):
        response = dict(content='hello', timings=dict(prompt_n=1820, cache_n=512, draft_n=9, draft_n_accepted=6))
        case = dict(name='short-prose', kind='prose', content='c')
        with patch.object(driver, 'request', return_value=response) as sent:
            result = driver.resume('b', case, [1, 2], 'hello')
        payload = sent.call_args.args[2]
        self.assertEqual((payload['cache_prompt'], payload['prompt'], payload['n_predict']), (True, [1, 2],
                                                                                              driver.MAX_OUTPUT))
        self.assertEqual(result, dict(prompt_n=1820, cache_n=512, drafted=9, accepted=6, quality_passed=True,
                                      matches_fresh=True))
        del response['timings']['draft_n'], response['timings']['draft_n_accepted']
        response['content'] = ''
        with patch.object(driver, 'request', return_value=response):
            result = driver.resume('b', case, [1], 'hello')
        self.assertEqual((result['drafted'], result['quality_passed'], result['matches_fresh']), (0, False, False))

    def test_each_case_is_a_conversation_of_four_requests(self):
        sent = []

        def chat(base, row, messages, max_tokens):
            sent.append((row['kind'], messages, max_tokens))
            return dict(row, content=f"reply {row['name']} {row['kind']}")

        cases = [dict(name='p', content='P'), dict(name='q', content='Q')]
        with patch.object(driver, 'chat', side_effect=chat), patch.object(driver, 'cases', return_value=cases) as asked:
            turns = driver.conversation('b', 'code-edit')
        asked.assert_called_once_with('code-edit')
        self.assertEqual([(t['name'], t['kind']) for t in turns], [(n, k) for n in 'pq' for k in KINDS])
        opening = [{'role': 'user', 'content': 'P'}]
        reply = {'role': 'assistant', 'content': 'reply p first'}
        n = driver.CONVERSATION_TOKENS
        self.assertEqual(sent[:4], [('first', opening, n), ('regenerate', opening, n),
                                    ('follow-up', [*opening, reply, {'role': 'user', 'content': driver.FOLLOW_UP}], n),
                                    ('edit', [*opening, reply, {'role': 'user', 'content': driver.EDIT}], n)])

    def run_lifecycle(self, repeat_text='short'):
        cases = [dict(name='long-retrieval', kind='retrieval', content='L'), dict(name='x', kind='prose', content='X'),
                 dict(name='short-prose', kind='prose', content='S')]
        result = dict(role='candidate', draft_profile='balanced', cases=[
            dict(name='long-retrieval', repeat=0, response=dict(text='{}', generated_token_ids=[1])),
            *[dict(name='short-prose', repeat=r, response=dict(text='short', generated_token_ids=[2])) for r in (0, 1)]])

        def conversation(base, draft_profile):
            self.append('slot: restored context checkpoint (pos_min = 1)', 'restored context checkpoint (pos_min = 2)')
            return [turn('p', k) for k in KINDS]

        def abort(base, tokens, after_s):
            self.append('slot release: stop processing: n_tokens = 512, truncated = 0')
            return False

        resumed = dict(prompt_n=2, cache_n=512, drafted=0, accepted=0, quality_passed=True, matches_fresh=True)
        repeat = dict(response=dict(text=repeat_text, generated_token_ids=[2]))
        with ExitStack() as stack:
            stack.enter_context(patch.object(driver, 'cases', return_value=cases))
            stack.enter_context(patch.object(driver, 'conversation', side_effect=conversation))
            stack.enter_context(patch.object(driver, 'abort', side_effect=abort))
            tokens = stack.enter_context(patch.object(driver, 'prompt_tokens', side_effect=[[1] * 2332, [2] * 48]))
            sent = stack.enter_context(patch.object(driver, 'resume', return_value=resumed))
            measured = stack.enter_context(patch.object(driver, 'measure_repeat', return_value=repeat))
            printed = stack.enter_context(redirect_stdout(io.StringIO()))
            driver.lifecycle(self.folder, result, 'b')
        self.assertEqual([c.args[1] for c in tokens.call_args_list], ['L', 'S'])
        self.assertEqual(sent.call_args.args[1:], (cases[0], [1] * 2332, '{}'))
        self.assertEqual(measured.call_args.args[1:], (cases[-1], [2] * 48, driver.REPEATS, False))
        return result, printed.getvalue()

    def test_a_launch_records_its_lifecycle_after_the_timed_requests(self):
        result, printed = self.run_lifecycle()
        checked = result['lifecycle']
        self.assertEqual(checked['cancel'], dict(after_s=driver.CANCEL_AFTER_S, reply_started=False,
                                                 prompt_tokens=2332, stopped_tokens=512))
        self.assertEqual((checked['restores'], checked['repeat_matches'], len(checked['conversation'])), (2, True, 4))
        self.assertEqual(json.loads((self.folder / 'result.json').read_text())['lifecycle'], checked)
        self.assertIn('candidate: 4 conversation turns, 2 restores; cancel stopped at 512 of 2332 tokens', printed)
        self.assertFalse(self.run_lifecycle('changed')[0]['lifecycle']['repeat_matches'])

    def campaign_file(self, folder):
        arm = dict(lifecycle=lifecycle(), memory=dict(peak_rss_bytes=40 * 2**30, minimum_available_bytes=3 * 2**30))
        comparison = dict(rows=[row('long-retrieval'), row('long-retrieval', 'replay')], exact_output_parity=True,
                          all_quality_checks_pass=True)
        (folder / 'campaign.json').write_text(json.dumps(dict(comparison=comparison, arms=[arm] * 4)))

    def test_a_bracket_is_analyzed_from_its_campaign(self):
        self.campaign_file(self.folder)
        result = driver.analyze(self.folder)
        self.assertEqual((result['exact_output_parity'], result['all_quality_checks_pass']), (True, True))
        self.assertTrue(result['lifecycle']['passed'])
        self.assertTrue(result['memory']['clean'])
        self.assertEqual(len(result['rows']), 2)

    def test_main_prints_the_plan_and_runs_the_three_brackets(self):
        output = self.folder / 'out'
        with redirect_stdout(io.StringIO()) as printed:
            driver.main(['--output', str(output)])
        self.assertIn('Plan long-documents: kept/overlap/overlap/kept at 1536, balanced drafting', printed.getvalue())
        self.assertFalse(output.exists())
        ran = []

        def campaign(folder, candidate, draft_profile, frozen, chunks, lifecycle):
            ran.append((folder.name, candidate, draft_profile, chunks, lifecycle, frozen))
            self.campaign_file(folder)

        with ExitStack() as stack:
            for name, value in dict(assert_no_model_server=None, require_pass=None, verify_models={'m': 1}).items():
                stack.enter_context(patch.object(driver, name, return_value=value))
            closure = stack.enter_context(patch.object(driver, 'closure', return_value={'c': 1}))
            stack.enter_context(patch.object(driver, 'campaign', side_effect=campaign))
            stack.enter_context(redirect_stdout(io.StringIO()))
            driver.main(['--output', str(output), '--run'])
        closure.assert_called_once_with('m5-overlap')
        self.assertEqual([r[:5] for r in ran], [('default', 'overlap', 'balanced', '512', driver.lifecycle),
                                                ('code-edit', 'overlap', 'code-edit', '512', driver.lifecycle),
                                                ('long-documents', 'overlap', 'balanced', '1536', driver.lifecycle)])
        self.assertEqual(ran[0][5], {'closure': {'c': 1}, 'models': {'m': 1}})
        summary = json.loads((output / 'summary.json').read_text())
        self.assertEqual((summary['status'], summary['decision']['qualified']), ('passed', True))
        self.assertEqual(sorted(summary['brackets']), ['code-edit', 'default', 'long-documents'])

    def test_a_finished_run_is_recomputed_from_its_saved_launches(self):
        output = self.folder / 'out'
        for name in driver.BRACKETS:
            (output / name).mkdir(parents=True)
            self.campaign_file(output / name)
        recorded = dict(qualified=False, reasons=['default: a lifecycle check failed'])
        (output / 'summary.json').write_text(json.dumps(dict(status='passed', decision=recorded, brackets={})))
        for _ in range(2):
            with redirect_stdout(io.StringIO()) as printed:
                driver.main(['--output', str(output), '--analyze'])
        summary = json.loads((output / 'summary.json').read_text())
        self.assertEqual((summary['recorded_decision'], summary['recomputed'], summary['status']),
                         (recorded, True, 'passed'))
        self.assertTrue(summary['decision']['qualified'])
        self.assertEqual(sorted(summary['brackets']), ['code-edit', 'default', 'long-documents'])
        self.assertIn('"qualified": true', printed.getvalue())

    def test_a_failed_bracket_is_recorded_and_raised(self):
        output = self.folder / 'out'
        with ExitStack() as stack:
            for name, value in dict(assert_no_model_server=None, require_pass=None, verify_models={},
                                    closure={}).items():
                stack.enter_context(patch.object(driver, name, return_value=value))
            stack.enter_context(patch.object(driver, 'campaign', side_effect=RuntimeError('Launch failed')))
            stack.enter_context(redirect_stdout(io.StringIO()))
            with self.assertRaisesRegex(RuntimeError, 'Launch failed'):
                driver.main(['--output', str(output), '--run'])
        summary = json.loads((output / 'summary.json').read_text())
        self.assertEqual((summary['status'], summary['error'], summary['brackets']),
                         ('failed', 'RuntimeError: Launch failed', {}))


if __name__ == '__main__':
    unittest.main()
