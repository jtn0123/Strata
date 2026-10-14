from contextlib import ExitStack, redirect_stdout
import copy
from io import StringIO
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import benchmark_prompt_chunks as chunks
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


ANSWER='{"owner":"Grove","timeout_seconds":38,"retry_limit":2}'
CLEAN=dict(monitor_healthy=True,child_exited=True,normal_pressure_required=True,normal_pressure_observed=True,
           pressure_live_samples=1,guard=None,swap_growth_bytes=0,peak_rss_bytes=1000)


def native_log(batch,ubatch):
    return ('M5_REDUCE10_DISPATCH {"rows":4,"channels":2560,"experts":10,"stage":"encoded"}\n'
            +f'llama_context: n_batch = {batch}\nllama_context: n_ubatch = {ubatch}\n'*2)


def reply(text,prompt_n):
    return dict(text=text,generated_token_ids=[1,2,3],ttft_s=0.8,wall_s=5,final=dict(stop=True,stop_type='eos',timings=dict(
        predicted_per_second=60,prompt_per_second=500,predicted_n=3,draft_n=3,draft_n_accepted=2,prompt_ms=6,
        predicted_ms=33,prompt_n=prompt_n)))


class Server:
    def __init__(self):self.returncode=None;self.pid=31337;self.calls=[]

    def poll(self):return self.returncode

    def terminate(self):self.calls.append('terminate');self.returncode=0

    def wait(self,timeout=None):return self.returncode


class Monitor:
    def __init__(self,memory):self.memory=memory;self.thread=SimpleNamespace(start=lambda:None)

    def finish(self):return dict(self.memory)


class Sampler:
    """Owned hardware sampler stand-in recording what the launch published to it."""

    def __init__(self,folder,coverage):
        self.folder=folder;self.coverage=coverage;self.model_pid=None;self.pin=None

    def start(self,pin):self.pin=pin

    def stop(self):return self.coverage

    def window(self,begin,end):return dict(seconds=end-begin)


class PromptChunkLaunchTests(unittest.TestCase):
    """Real launch/finalization/campaign flow; the server, sampler, host probes and model API are fixtures."""

    def setUp(self):
        self.folder=Path(tempfile.mkdtemp(prefix='strata-prompt-chunks-'))
        self.addCleanup(shutil.rmtree,self.folder)
        self.answers={}

    def tokens(self,base,content):
        case=next(c for c in cases('code-edit')+cases() if c['content']==content)
        ids=[len(self.answers)+1]*(2200 if case['name'].startswith('long-') else 120)
        if case['kind']=='editing':text=case['fixture']['source'].replace(case['fixture']['old'],case['fixture']['new'])
        else:text=ANSWER if case['kind']=='retrieval' else 'Prose.'
        self.answers[tuple(ids)]=text
        return ids

    def complete(self,base,payload,observer=None):
        if observer:
            for item,elapsed in ((dict(tokens=[1]),0.1),(dict(tokens=[]),0.12),(dict(tokens=[2,3]),0.15),(dict(stop=True),0.2)):
                observer(item,elapsed)
        return reply(self.answers[tuple(payload['prompt'])],len(payload['prompt']))

    def patched(self,stack,profile='1536',memory=CLEAN,coverage=None,**overrides):
        self.server=Server();self.sampler=None
        def popen(command,env,stdout,stderr):
            stdout.write(native_log(*chunks.PROFILES[profile]));stdout.flush()
            return self.server
        def sampler(folder):
            self.sampler=Sampler(folder,coverage);return self.sampler
        replaced=dict(assert_no_model_server=lambda:None,check_frozen=lambda frozen:None,
                      wait_for_headroom=lambda:dict(settled=True),preflight=lambda strict:dict(strict=strict),
                      power=lambda:dict(on_ac=True,mode=0),free_port=lambda:9124,Sampler=sampler,
                      kept_server=lambda port,b,u:['server','-b',str(b),'-ub',str(u),'--spec-type','draft-mtp','--spec-draft-n-max','3'],
                      configure=lambda environ,engine,api,tuning:(dict(FIXTURE='1'),dict(tuning=tuning)),
                      admit_model=lambda model:dict(model=model),app_monitor=lambda process,path,policy:Monitor(memory),
                      wait_ready=lambda process,base:2.0,prompt_tokens=self.tokens,stream_completion=self.complete)
        replaced.update(overrides)
        stack.enter_context(patch.multiple(chunks,**replaced))
        stack.enter_context(patch.object(chunks.subprocess,'Popen',side_effect=popen))
        stack.enter_context(redirect_stdout(StringIO()))

    def launch(self,frozen=None,**options):
        with ExitStack() as stack:
            self.patched(stack,**options)
            try:result=chunks.launch(self.folder/'arm',options.get('role','candidate'),options.get('profile','1536'),frozen or {});error=None
            except RuntimeError as caught:error=caught
        saved=json.loads((self.folder/'arm/result.json').read_text())
        if error is None:self.assertEqual(saved,result)
        return error,saved

    def test_clean_launch_records_chunks_activation_and_every_repeat(self):
        error,result=self.launch()
        self.assertIsNone(error)
        self.assertEqual((result['status'],result['models_loaded'],result['ready_s']),('passed',True,2.0))
        self.assertEqual(result['settings']['batch'],1536)
        self.assertEqual(result['actual_chunks'],{'n_batch':[1536,1536],'n_ubatch':[1536,1536]})
        self.assertEqual(len(result['cases']),len(cases())*REPEATS)
        self.assertTrue(all(r['quality_passed'] for r in result['cases']))
        self.assertNotIn('stream_events',result['cases'][0])
        self.assertEqual(self.server.calls,['terminate'])

    def test_hardware_sampler_follows_the_owned_server_and_windows_each_request(self):
        healthy=dict(healthy=True,sensor_fields_observed=dict(gpu=True,thermal=True))
        error,result=self.launch(frozen=dict(hardware_tool=dict(pin='tool')),coverage=healthy)
        self.assertIsNone(error)
        self.assertEqual((self.sampler.pin,self.sampler.model_pid),(dict(pin='tool'),31337))
        self.assertEqual(result['hardware'],healthy)
        row=result['cases'][0]
        self.assertIn('seconds',row['hardware_window'])
        self.assertEqual(row['observed_output_gaps']['samples'],1)
        self.assertAlmostEqual(row['observed_output_gaps']['median_s'],0.05)
        self.assertEqual(len(row['stream_events']),4)

    def test_missing_sensor_coverage_or_dirty_memory_rejects_the_launch(self):
        partial=dict(healthy=True,sensor_fields_observed=dict(gpu=True,thermal=False))
        error,result=self.launch(frozen=dict(hardware_tool=dict(pin='tool')),coverage=partial)
        self.assertIn('Hardware diagnostic coverage failed',str(error))
        self.assertEqual((result['status'],len(result['cases'])),('failed',len(cases())*REPEATS))
        shutil.rmtree(self.folder/'arm')
        error,result=self.launch(memory=dict(CLEAN,swap_growth_bytes=4096))
        self.assertIn('RAM/swap/cleanup gate failed',result['error'])

    def test_failed_start_or_changed_sources_keep_the_original_failure(self):
        def exited(process,base):raise RuntimeError('server exited before ready')
        error,result=self.launch(wait_ready=exited)
        self.assertIn('server exited before ready',str(error))
        self.assertEqual((result['status'],result['models_loaded'],self.server.calls),('failed',True,['terminate']))
        shutil.rmtree(self.folder/'arm')
        calls=[]
        def drift(frozen):
            calls.append(1)
            if len(calls)>1:raise RuntimeError('Frozen source or engine changed; start a new campaign')
        error,result=self.launch(check_frozen=drift)
        self.assertIn('start a new campaign',result['error'])
        self.assertNotIn('actual_chunks',result)

    def test_request_scope_and_counts_are_checked_before_scoring(self):
        long_case,edit=cases()[0],cases()[2]
        owned=chunks.OwnedLaunch();result=dict(role='candidate',profile='1536',cases=[])
        with ExitStack() as stack:
            self.patched(stack,prompt_tokens=lambda base,content:[1]*3400)
            with self.assertRaisesRegex(ValueError,'4K context'):chunks.measure_case(self.folder,result,owned,'base',edit)
            stack.enter_context(patch.object(chunks,'prompt_tokens',return_value=[1]*1200))
            with self.assertRaisesRegex(ValueError,'predeclared scope'):chunks.measure_case(self.folder,result,owned,'base',long_case)
            stack.enter_context(patch.object(chunks,'stream_completion',return_value=reply('Prose.',1199)))
            with self.assertRaisesRegex(ValueError,'exact output token counts'):chunks.measure_repeat('base',edit,[1]*1200,0,False)

    def test_quality_requires_exact_edit_and_plain_prose(self):
        edit=cases()[2];f=edit['fixture']
        self.assertTrue(quality(edit,'\n'+f['source'].replace(f['old'],f['new'])+'\n'))
        self.assertFalse(quality(edit,f['source']))
        self.assertFalse(quality(cases()[0],'not json'))
        self.assertTrue(quality(cases()[-1],'Warmup matters.'))
        self.assertFalse(quality(cases()[-1],'<think>plan</think>'))
        self.assertIsNone(chunks.output_gaps([])['median_s'])

    def test_frozen_closure_rejects_source_model_or_sampler_changes(self):
        replaced=dict(require_pass=lambda:None,fingerprint=lambda:{'scripts/a.py':'1'},sha256=lambda path:path.name,
                      verify_engine=lambda name:dict(name=name),assert_unchanged=lambda models:None,tool_pin=lambda:dict(pin=1))
        with patch.multiple(chunks,**replaced):
            frozen=dict(closure=chunks.closure(),models={})
            chunks.check_frozen(frozen)
            chunks.check_frozen(dict(frozen,hardware_tool=dict(pin=1)))
            with self.assertRaisesRegex(RuntimeError,'sampler tool changed'):chunks.check_frozen(dict(frozen,hardware_tool=dict(pin=2)))
            with self.assertRaisesRegex(RuntimeError,'start a new campaign'):
                chunks.check_frozen(dict(frozen,closure=dict(frozen['closure'],fixture_sha256='old')))

    def campaign(self,launch):
        (self.folder/'bench').mkdir(exist_ok=True);(self.folder/'scripts').mkdir(exist_ok=True)
        (self.folder/'scripts/a.py').write_text('source\n')
        output=self.folder/'campaign';output.mkdir()
        frozen=dict(closure=dict(sources={'scripts/a.py':'sha'}),models={})
        with patch.object(chunks,'ROOT',self.folder), patch.object(chunks,'launch',side_effect=launch) as launched:
            try:chunks.campaign(output,'1536','balanced',frozen);error=None
            except RuntimeError as caught:error=caught
        return error,json.loads((output/'campaign.json').read_text()),launched

    def test_campaign_scores_a_complete_bracket_and_keeps_launch_receipts(self):
        arms=bracket()
        def launch(folder,role,profile,frozen,draft_profile):
            folder.mkdir();arm=arms.pop(0);(folder/'result.json').write_text(json.dumps(arm))
            return arm
        error,result,launched=self.campaign(launch)
        self.assertIsNone(error)
        self.assertEqual((result['status'],len(result['launches']),len(result['comparison']['rows'])),('passed',4,8))
        self.assertEqual([c.args[1:3] for c in launched.call_args_list],
                         [('control','512'),('candidate','1536'),('candidate','1536'),('control','512')])
        self.assertEqual((self.folder/'campaign/source/scripts/a.py').read_text(),'source\n')

    def test_campaign_stops_at_the_first_failed_launch(self):
        def launch(folder,role,profile,frozen,draft_profile):
            folder.mkdir();(folder/'result.json').write_text(json.dumps(dict(status='failed',role=role)))
            raise RuntimeError('RAM/swap/cleanup gate failed')
        error,result,launched=self.campaign(launch)
        self.assertIn('RAM/swap/cleanup gate failed',str(error))
        self.assertEqual((result['status'],launched.call_count,result['launches']),('failed',1,[dict(status='failed',role='control')]))
        self.assertNotIn('comparison',result)

    def test_run_freezes_inputs_and_pins_the_sampler_only_when_requested(self):
        replaced=dict(assert_no_model_server=lambda:None,require_pass=lambda:None,closure=lambda:dict(sources={}),
                      verify_models=lambda names:dict(models=names),tool_pin=lambda:dict(pin='tool'))
        with patch.multiple(chunks,**replaced), patch.object(chunks,'campaign') as ran, redirect_stdout(StringIO()) as printed:
            main(['--candidate','1024','--output',str(self.folder/'plain'),'--run'])
            main(['--candidate','256','--draft-profile','code-edit','--telemetry','--output',str(self.folder/'sampled'),'--run'])
            with self.assertRaises(FileExistsError):main(['--candidate','256','--output',str(self.folder/'plain'),'--run'])
        plain,sampled=(c.args for c in ran.call_args_list)
        self.assertEqual((plain[1:3],'hardware_tool' in plain[3]),(('1024','balanced'),False))
        self.assertEqual((sampled[1:3],sampled[3]['hardware_tool']),(('256','code-edit'),dict(pin='tool')))
        self.assertIn('Trial passed:',printed.getvalue())


if __name__ == '__main__': unittest.main()
