"""Reject false editing wins and unsafe speculative allocation settings."""
from contextlib import ExitStack, redirect_stdout
import copy
from io import BytesIO, StringIO
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import benchmark_editing as editing
from benchmark_editing import compare, fixtures, prompt, trial_command, validate_response
from engines import sha256
import trial_support


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


CLEAN=dict(monitor_healthy=True,child_exited=True,normal_pressure_required=True,normal_pressure_observed=True,
           pressure_live_samples=1,guard=None,swap_growth_bytes=0,peak_rss_bytes=1000)
ACTIVE_LOG=('M5_REDUCE10_DISPATCH {"rows":4,"channels":2560,"experts":10,"stage":"encoded"}\n'
            'borrowing target embeddings/output; draft KV remains separate\n'
            "adding speculative implementation 'ngram-mod'\n"
            'statistics ngram-mod: #gen drafts = 4, #acc drafts = 4, #gen tokens = 12, #acc tokens = 12\n')


def reply(text,prompt_n=20,cache_n=0):
    return dict(text=text,generated_token_ids=[1,2,3],ttft_s=0.8,wall_s=5,final=dict(stop=True,stop_type='eos',timings=dict(
        predicted_per_second=60,prompt_per_second=500,predicted_n=3,draft_n=3,draft_n_accepted=2,prompt_ms=6,
        predicted_ms=33,prompt_n=prompt_n,cache_n=cache_n)))


class Server:
    """Owned native server stand-in; terminate() is ignored while `hang` is set."""

    def __init__(self,hang=False):
        self.returncode=None;self.hang=hang;self.calls=[]

    def poll(self):return self.returncode

    def terminate(self):
        self.calls.append('terminate')
        if not self.hang:self.returncode=0

    def kill(self):self.calls.append('kill');self.returncode=-9

    def wait(self,timeout=None):
        if self.returncode is None:raise subprocess.TimeoutExpired('server',timeout)
        return self.returncode


class Monitor:
    def __init__(self,memory):
        self.memory=memory;self.started=False
        self.thread=SimpleNamespace(start=self.start)

    def start(self):self.started=True

    def finish(self):return dict(self.memory)


class Stream(BytesIO):
    def __enter__(self):return self

    def __exit__(self,*args):self.close()


class EditingLaunchTests(unittest.TestCase):
    """Real arm/bracket/campaign control flow; only the server, host probes and model API are replaced."""

    response=EditingBenchmarkTests.response
    arms=EditingBenchmarkTests.arms

    def setUp(self):
        self.folder=Path(tempfile.mkdtemp(prefix='strata-editing-'))
        self.addCleanup(shutil.rmtree,self.folder)
        self.texts={}

    def tokens(self,base,content):
        ids=[len(self.texts)+1]*20
        edits=[c['source'].replace(c['old'],c['new']) for c in fixtures() if prompt(c)==content]
        self.texts[tuple(ids)]=edits[0] if edits else 'Warmup, repeats, quiet machine and memory matter.'
        return ids

    def complete(self,base,payload):
        return reply(self.texts[tuple(payload['prompt'])],len(payload['prompt']))

    def launch(self,stack,log=ACTIVE_LOG,memory=CLEAN,**overrides):
        self.server=Server();self.monitor=Monitor(memory)
        def popen(command,stdout,stderr,env):
            stdout.write(log);stdout.flush()
            return self.server
        replaced=dict(assert_frozen=lambda frozen:None,assert_no_model_server=lambda:None,
                      power=lambda:dict(on_ac=True,mode=0),wait_for_headroom=lambda:dict(settled=True),
                      preflight=lambda:dict(quiet=True),admit_model=lambda model:dict(model=model),
                      configure=lambda environ,engine,api,tuning:(dict(FIXTURE='1'),dict(tuning=tuning)),
                      free_port=lambda:9123,wait_ready=lambda process,base,timeout:1.5,
                      kept_server=lambda port,b,u:['server','--port',str(port),'--spec-type','draft-mtp','--spec-draft-n-max','3'],
                      prompt_tokens=self.tokens,stream_completion=self.complete,lifecycle=lambda base:dict(passed=True),
                      app_monitor=lambda process,path,policy:self.monitor)
        replaced.update(overrides)
        stack.enter_context(patch.multiple(editing,**replaced))
        stack.enter_context(patch.object(editing.subprocess,'Popen',side_effect=popen))
        stack.enter_context(redirect_stdout(StringIO()))

    def run_arm(self,profile='code-edit',**overrides):
        with ExitStack() as stack:
            self.launch(stack,**overrides)
            record=editing.arm(self.folder/'arm-1',profile,'candidate','screen',{})
        self.assertEqual(json.loads((self.folder/'arm-1/result.json').read_text()),record)
        return record

    def test_guarded_arm_measures_every_file_and_repeat_then_stops_server(self):
        record=self.run_arm()
        self.assertEqual((record['status'],record['exit_code'],record['ready_s']),('passed',0,1.5))
        self.assertEqual(len(record['cases']),16)
        self.assertEqual({c['repeat'] for c in record['cases']},{0,1,2,3})
        self.assertIn('ngram-mod,draft-mtp',record['command'])
        self.assertEqual(record['drafting_receipts']['ngram-mod']['accepted_tokens'],12)
        self.assertEqual((record['memory'],record['lifecycle']),(CLEAN,dict(passed=True)))
        self.assertTrue(self.monitor.started)
        self.assertEqual(self.server.calls,['terminate'])

    def test_failed_launch_still_stops_server_and_keeps_failed_receipt(self):
        def exited(process,base,timeout):raise RuntimeError('server exited before ready')
        record=self.run_arm(wait_ready=exited)
        self.assertEqual(record['status'],'failed')
        self.assertIn('server exited before ready',record['error'])
        self.assertEqual((record['cases'],record['exit_code'],self.server.calls),([],0,['terminate']))

    def test_stop_before_launch_needs_no_server_cleanup(self):
        def stop(frozen):raise KeyboardInterrupt('Termination requested (SIGTERM)')
        record=self.run_arm(assert_frozen=stop)
        self.assertEqual(record['status'],'failed')
        self.assertNotIn('memory',record)
        self.assertNotIn('exit_code',record)

    def test_swap_growth_or_missing_activation_rejects_finished_arm(self):
        record=self.run_arm(memory=dict(CLEAN,swap_growth_bytes=4096))
        self.assertEqual((record['status'],record['resource_failure']),('failed',True))
        shutil.rmtree(self.folder/'arm-1')
        record=self.run_arm(log=ACTIVE_LOG.replace('borrowing target','missing'))
        self.assertEqual((record['status'],record['activation_error']),('failed','Shared helper activation missing'))

    def test_measurement_rejects_reused_prefix_and_oversized_prompt(self):
        task=editing.edit_tasks('screen')[-1]
        record=dict(profile='code-edit',cases=[]);path=self.folder/'result.json'
        with ExitStack() as stack:
            self.launch(stack,stream_completion=lambda base,payload:reply('Prose.',20,cache_n=4))
            with self.assertRaisesRegex(ValueError,'reused native prefix'):editing.measure_task('base',task,record,path)
            self.assertEqual(len(json.loads(path.read_text())['cases']),1)
            stack.enter_context(patch.object(editing,'prompt_tokens',return_value=[1]*3000))
            with self.assertRaisesRegex(ValueError,'budget'):editing.measure_task('base',task,record,path)

    def test_lifecycle_disconnects_after_first_text_then_checks_reuse(self):
        answer=dict(choices=[dict(message=dict(content='391\n'),finish_reason='stop')])
        events=b'data: {"content":""}\n\ndata: {"content":"Fair"}\n\n'
        with patch.object(editing.urllib.request,'urlopen',return_value=Stream(events)) as opened, \
                patch.object(editing,'request',return_value=answer) as asked:
            self.assertEqual(editing.lifecycle('http://fixture')['reuse_answer'],'391')
        self.assertTrue(json.loads(opened.call_args.args[0].data)['ignore_eos'])
        self.assertEqual(asked.call_args.args[1],'/v1/chat/completions')
        with patch.object(editing.urllib.request,'urlopen',return_value=Stream(b'data: {"content":""}\n')), \
                self.assertRaisesRegex(RuntimeError,'No first text'):
            editing.lifecycle('http://fixture')
        answer['choices'][0]['message']['content']='392'
        with patch.object(editing.urllib.request,'urlopen',return_value=Stream(events)), \
                patch.object(editing,'request',return_value=answer), self.assertRaisesRegex(RuntimeError,'reuse answer'):
            editing.lifecycle('http://fixture')

    def test_bracket_scores_only_complete_matching_launches(self):
        arms=self.arms()
        with patch.object(editing,'arm',side_effect=arms) as launched, patch.object(editing.time,'sleep') as slept:
            result=editing.bracket(self.folder/'screen',('balanced','code-edit'),'screen',{})
        self.assertEqual((result['status'],result['eligible_languages']),('completed',['javascript','json','python']))
        self.assertEqual([c.args[1:3] for c in launched.call_args_list],
                         [('balanced','control'),('code-edit','candidate'),('code-edit','candidate'),('balanced','control')])
        self.assertEqual(slept.call_count,3)
        self.assertEqual(json.loads((self.folder/'screen/comparison.json').read_text())['status'],'completed')

    def test_bracket_stops_at_failed_or_mismatched_launch_without_scoring(self):
        arms=self.arms();arms[1]['status']='failed';arms[1]['activation_error']='ngram-mod produced no accepted drafts'
        with patch.object(editing,'arm',side_effect=arms) as launched, patch.object(editing.time,'sleep'):
            result=editing.bracket(self.folder/'screen',('balanced','code-edit'),'screen',{})
        self.assertEqual((result['failed_arm'],result['error'],launched.call_count),(2,'ngram-mod produced no accepted drafts',2))
        arms=self.arms();arms[2]['cases'][0]['output_tokens']=4
        with patch.object(editing,'arm',side_effect=arms), patch.object(editing.time,'sleep'):
            result=editing.bracket(self.folder/'confirm',('balanced','code-edit'),'confirm',{})
        self.assertEqual((result['status'],result['failed_arm'],result['partial_results_not_scored']),('failed',3,True))
        self.assertIn('parity',json.loads((self.folder/'confirm/comparison.json').read_text())['error'])

    def test_mixed_cohorts_cannot_form_a_bracket(self):
        arms=self.arms();arms[3]['cohort']='confirm'
        with self.assertRaisesRegex(ValueError,'mix fixture cohorts'):editing.compare(arms)

    def test_campaign_confirms_only_scopes_qualified_in_both_cohorts(self):
        row=lambda language,cohort,scopes:dict(language=language,cohort=cohort,qualified_scopes=scopes)
        screen=dict(status='completed',eligible_languages=['json','python'],rows=[
            row('python','first-exposure',['reply','generation']),row('json','first-exposure',['reply']),
            row('python','warmed',['reply'])])
        confirm=dict(status='completed',eligible_languages=['python'],rows=[row('python','first-exposure',['reply'])])
        with patch.object(editing,'bracket',side_effect=[screen,confirm]) as run:
            record=editing.run_campaign(self.folder,'editing',{})
        self.assertEqual((record['status'],record['confirmed_languages'],record['confirmed_scopes']),
                         ('confirmed',['python'],{'python':['reply']}))
        self.assertEqual(run.call_args_list[1].args[1:3],(('balanced','code-edit'),'confirm'))
        self.assertEqual(json.loads((self.folder/'campaign.json').read_text()),record)
        with patch.object(editing,'bracket',return_value=dict(status='completed',eligible_languages=[],rows=[])) as run:
            record=editing.run_campaign(self.folder,'prompt-map',{})
        self.assertEqual((record['status'],run.call_count),('no confirmed gain',1))
        with patch.object(editing,'bracket',return_value=dict(status='failed',eligible_languages=[])):
            self.assertEqual(editing.run_campaign(self.folder,'editing',{})['status'],'failed')

    def test_main_prints_plan_and_parks_inactive_matcher_without_loading(self):
        output=self.folder/'campaign'
        with redirect_stdout(StringIO()) as printed:
            editing.main(['--experiment','editing','--output',str(output)])
        self.assertEqual(json.loads(printed.getvalue())['profiles'],['balanced','code-edit'])
        with redirect_stdout(StringIO()), self.assertRaisesRegex(RuntimeError,'E02 is parked'):
            editing.main(['--experiment','prompt-local','--output',str(output),'--run'])
        self.assertFalse(output.exists())

    def test_main_freezes_sources_models_and_proof_before_the_campaign(self):
        (self.folder/'bench').mkdir()
        results=[dict(status='confirmed',confirmed_languages=['python']),dict(status='failed',confirmed_languages=[])]
        replaced=dict(ROOT=self.folder,require_pass=lambda:None,assert_no_model_server=lambda:None,
                      power=lambda:dict(on_ac=True,mode=0),closure=lambda:dict(sources={}),
                      verify_models=lambda names:dict(models=names),matcher_proof=lambda:'proof-sha')
        with patch.multiple(editing,**replaced), patch.object(editing,'run_campaign',side_effect=results) as run, \
                redirect_stdout(StringIO()) as printed:
            editing.main(['--experiment','prompt-map','--output',str(self.folder/'map'),'--run'])
            with self.assertRaises(SystemExit):editing.main(['--experiment','editing','--output',str(self.folder/'edit'),'--run'])
            with self.assertRaises(FileExistsError):editing.main(['--experiment','editing','--output',str(self.folder/'edit'),'--run'])
        frozen=json.loads((self.folder/'map/frozen.json').read_text())
        self.assertEqual((frozen['matcher_proof_sha256'],frozen['models']),('proof-sha',dict(models=['flash','mtp_shared_packed_q3'])))
        self.assertIsNone(json.loads((self.folder/'edit/frozen.json').read_text())['matcher_proof_sha256'])
        self.assertEqual(run.call_args_list[0].args[1],'prompt-map')
        self.assertIn("Campaign: confirmed; independently confirmed languages: ['python']",printed.getvalue())


class FrozenEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.folder=Path(tempfile.mkdtemp(prefix='strata-editing-proof-'))
        self.addCleanup(shutil.rmtree,self.folder)

    def test_matcher_proof_must_match_current_native_inputs(self):
        proof_folder=self.folder/'bench/features/20261013-ngram-short-mechanism'
        obj=self.folder/'vendor/llama-m5-small-stack/build/common/CMakeFiles/llama-common.dir/ngram-map.cpp.o'
        for path,text in ((proof_folder/'probe','probe'),(obj,'object'),(self.folder/'native/ngram_short_probe.cpp','source')):
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
        proof=dict(status='passed',cases=18,models_loaded=False,gpu_tests=False,map_maximum_width=3,engine=dict(engine=1),
                   source_sha256=sha256(self.folder/'native/ngram_short_probe.cpp'),native_object_sha256=sha256(obj),
                   binary_sha256=sha256(proof_folder/'probe'))
        (proof_folder/'proof.json').write_text(json.dumps(proof))
        with patch.multiple(editing,ROOT=self.folder,verify_engine=lambda name:dict(engine=1)):
            self.assertEqual(editing.matcher_proof(),sha256(proof_folder/'proof.json'))
            obj.write_text('rebuilt object')
            with self.assertRaisesRegex(RuntimeError,'matcher proof'):editing.matcher_proof()

    def test_closure_and_frozen_checks_reject_any_change(self):
        replaced=dict(fingerprint=lambda:{'scripts/a.py':'1'},verify_engine=lambda name:dict(name=name),
                      sha256=lambda path:path.name,require_pass=lambda:None,assert_unchanged=lambda models:None,
                      matcher_proof=lambda:'proof')
        with patch.multiple(editing,**replaced):
            closure=editing.closure()
            self.assertEqual((closure['engine'],closure['native_probe_sha256']),(dict(name='m5-small-stack'),'ngram_short_probe.cpp'))
            frozen=dict(closure=closure,models={},matcher_proof_sha256=None)
            editing.assert_frozen(frozen)
            editing.assert_frozen(dict(frozen,matcher_proof_sha256='proof'))
            with self.assertRaisesRegex(RuntimeError,'proof changed'):editing.assert_frozen(dict(frozen,matcher_proof_sha256='old'))
            with self.assertRaisesRegex(RuntimeError,'start a new campaign'):
                editing.assert_frozen(dict(frozen,closure=dict(closure,fixture_sha256='old')))


class TrialSupportTests(unittest.TestCase):
    def test_fixture_inventory_rejects_unbalanced_or_ambiguous_files(self):
        spec=json.loads(trial_support.FIXTURES.read_text())
        broken=[dict(spec,schema=2),copy.deepcopy(spec),copy.deepcopy(spec),copy.deepcopy(spec)]
        broken[1]['cases'][0]['language']='json'
        broken[2]['cases'][0]['old']=broken[2]['cases'][0]['new']
        broken[3]['cases'][1]['source']='short'
        with tempfile.TemporaryDirectory() as folder:
            for index,value in enumerate(broken):
                path=Path(folder)/f'{index}.json';path.write_text(json.dumps(value))
                with self.subTest(index=index),self.assertRaises(ValueError):trial_support.fixtures(path)

    def test_kept_server_and_drafting_policies_preserve_mtp_width(self):
        with patch.object(trial_support,'server_command',return_value=['server']) as built:
            self.assertEqual(trial_support.kept_server(9000,512,256),['server'])
        self.assertEqual(built.call_args.args,('flash',9000,4096,512,256,'draft-mtp',3,'f16',8,'mixed','mtp_shared_packed_q3'))
        self.assertEqual(built.call_args.kwargs,dict(engine='m5-small-stack',draft_threads=8,draft_p_min=0.0))
        base=['server','--spec-type','draft-mtp','--spec-draft-n-max','3']
        self.assertEqual(trial_command(base,'balanced'),base)
        command=trial_command(base,'code-edit')
        self.assertEqual(command[2],'ngram-mod,draft-mtp')
        self.assertNotIn('--spec-ngram-map-k-size-n',command)
        with self.assertRaisesRegex(ValueError,'Unknown'):trial_command(base,'turbo')

    def test_missing_ids_or_unexpected_matcher_statistics_are_rejected(self):
        response=EditingBenchmarkTests.response(self);response['generated_token_ids']=[]
        with self.assertRaisesRegex(ValueError,'token IDs'):validate_response(response)
        text='statistics ngram-mod: #gen drafts = 1, #acc drafts = 1, #gen tokens = 3, #acc tokens = 3\n'
        with self.assertRaisesRegex(ValueError,'Unexpected ngram-mod statistics'):trial_support.drafting_receipts(text,'balanced')

    def test_power_requires_ac_and_automatic_mode(self):
        custom='Battery Power:\n powermode 1\nAC Power:\n powermode 0\n'
        with patch.object(trial_support.subprocess,'check_output',side_effect=["Now drawing from 'AC Power'",custom]) as ran:
            self.assertEqual(trial_support.power(),dict(on_ac=True,mode=0))
        self.assertEqual(ran.call_args_list[0].args[0],['pmset','-g','batt'])
        for battery,mode in (("Now drawing from 'Battery Power'",'0'),("Now drawing from 'AC Power'",'1')):
            with self.subTest(battery=battery,mode=mode), \
                    patch.object(trial_support.subprocess,'check_output',side_effect=[battery,f'AC Power:\n powermode {mode}\n']), \
                    self.assertRaisesRegex(RuntimeError,'AC power'):
                trial_support.power()

    def test_free_port_and_prompt_tokens_use_the_local_server(self):
        with patch.object(trial_support.socket,'socket') as made:
            sock=made.return_value.__enter__.return_value;sock.getsockname.return_value=('127.0.0.1',50123)
            self.assertEqual(trial_support.free_port(),50123)
        sock.bind.assert_called_once_with(('127.0.0.1',0))
        replies=[dict(prompt='<user>Hello</user>'),dict(tokens=[5,6])]
        with patch.object(trial_support,'request',side_effect=replies) as asked:
            self.assertEqual(trial_support.prompt_tokens('http://fixture','Hello'),[5,6])
        self.assertFalse(asked.call_args_list[0].args[2]['chat_template_kwargs']['enable_thinking'])
        self.assertEqual(asked.call_args_list[1].args[1:],('/tokenize',dict(content='<user>Hello</user>',add_special=False,parse_special=True)))

    def test_stop_owned_kills_only_an_unresponsive_live_server(self):
        server=Server(hang=True);trial_support.stop_owned(server,15,3)
        self.assertEqual((server.calls,server.returncode),(['terminate','kill'],-9))
        trial_support.stop_owned(server,15,3);trial_support.stop_owned(None,15,3)
        self.assertEqual(server.calls,['terminate','kill'])
