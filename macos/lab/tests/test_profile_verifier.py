"""Profile verifier receipts: accept only after shutdown and every postflight check."""
from contextlib import ExitStack
from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import validate_offline
import verify_runtime_profiles as trial

NATIVE_LOG=('M5_REDUCE10_DISPATCH {"rows":4,"channels":2560,"experts":10,"stage":"encoded"}\n'
            +'llama_context: n_batch = 512\nllama_context: n_ubatch = 512\n'*2)
HEALTHY_MEMORY=dict(guard=None,normal_pressure_observed=True,swap_growth_bytes=0,monitor_healthy=True,child_exited=True)
STREAM=b'data: {"choices":[{"delta":{"content":"391"}}]}\n\ndata: [DONE]\n\n'


class Child:
    """Owned launcher stand-in; terminate() only takes effect after `hang` waits."""
    pid=42424

    def __init__(self,hang=0,interrupt=False):
        self.returncode=None;self.hang=hang;self.interrupt=interrupt;self.calls=[]

    def poll(self):return self.returncode

    def terminate(self):self.calls.append('terminate')

    def kill(self):self.calls.append('kill');self.returncode=-9

    def wait(self,timeout=None):
        self.calls.append('wait')
        if self.interrupt:
            self.interrupt=False;raise KeyboardInterrupt('Termination requested (SIGTERM)')
        if self.returncode is None and 'terminate' in self.calls:
            if self.hang:self.hang-=1;raise subprocess.TimeoutExpired('launcher',timeout)
            self.returncode=0
        return self.returncode


class Stream(BytesIO):
    def __enter__(self):return self

    def __exit__(self,*args):self.close()


class ProfileVerifierReceiptTests(unittest.TestCase):
    def setUp(self):
        self.folder=Path(tempfile.mkdtemp(prefix='strata-profile-verifier-'))
        self.addCleanup(shutil.rmtree,self.folder)
        for relative in ('scripts','bench/runtime/owned','tests/fixtures'):(self.folder/relative).mkdir(parents=True)
        (self.folder/'Start Strata.command').write_text('owned default fixture\n')
        self.source=self.folder/'scripts/runtime_profiles.py';self.source.write_text('owned profile source\n')
        shutil.copyfile(ROOT/'tests/fixtures/runtime-code-edit.json',self.folder/'tests/fixtures/runtime-code-edit.json')
        self.case=json.loads((self.folder/'tests/fixtures/runtime-code-edit.json').read_text())
        self.runtime=self.folder/'bench/runtime/owned'
        command=['--spec-type','draft-mtp','--spec-draft-n-max','3','--spec-draft-threads','8','--spec-draft-p-min','0.0','-b','512','-ub','512']
        (self.runtime/'command.json').write_text(json.dumps(command))
        (self.runtime/'metal-environment.json').write_text(json.dumps(dict(tuning='small-reduce',tensor_api='on')))
        (self.runtime/'memory-summary.json').write_text(json.dumps(HEALTHY_MEMORY))
        (self.runtime/'memory-policy.json').write_text('{}')
        (self.runtime/'native.log').write_text(NATIVE_LOG)
        (self.folder/'bench/runtime/active.json').write_text(json.dumps(dict(pid=Child.pid,log_directory=str(self.runtime))))
        self.integration=self.folder/'integration.json'
        self.integration.write_text(json.dumps(dict(passed=True)))
        self.child=Child()

    def request(self,base,endpoint,payload=None,timeout=600):
        if endpoint=='/health':return {}
        if endpoint=='/metrics':return dict(performance=dict(settings=dict(batch=1536,ubatch=1536)))
        prompt=payload['messages'][0]['content']
        if prompt==self.case['prompt']:text=self.case['expected']
        elif prompt.startswith('Extract the name'):text=json.dumps(dict(name='Morgan',age=29))
        elif prompt.startswith('Read the fictional notes'):text='{"owner":"Grove","timeout_seconds":38,"retry_limit":2}'
        else:text='391'
        return dict(choices=[dict(message=dict(content=text),finish_reason='stop')])

    def use_profile(self,profile,launcher):
        """Rewrite the owned runtime receipts as the named optional launcher would record them."""
        size='1536' if profile=='long-documents' else '512'
        command=['--spec-type','draft-mtp','--spec-draft-n-max','3','--spec-draft-threads','8','--spec-draft-p-min','0.0','-b',size,'-ub',size]
        if profile=='code-edit':
            command[1]='ngram-mod,draft-mtp'
            command+=['--spec-ngram-mod-n-match','16','--spec-ngram-mod-n-min','1','--spec-ngram-mod-n-max','3']
        (self.runtime/'command.json').write_text(json.dumps(command))
        (self.runtime/'native.log').write_text(NATIVE_LOG.replace('512',size))
        (self.folder/launcher).write_text('owned optional launcher fixture\n')
        return dict(options=SimpleNamespace(profile=profile),LAUNCHER=self.folder/launcher,
                    ROLE='lookup' if profile=='code-edit' else 'control')

    def run_verifier(self,stream=STREAM,returncode=0,**overrides):
        """Run the real main/finalization; replace only the launcher, model APIs and host probes."""
        replaced=dict(ROOT=self.folder,OUT=self.folder/'campaign',LAUNCHER=self.folder/'Start Strata.command',
                      SOURCE=self.source,options=SimpleNamespace(profile='balanced'),ROLE='control',
                      assert_no_model_server=lambda:None,verify_engine=lambda name:{},snapshot=lambda:{},
                      ports_closed=lambda:[8095,8096],request=self.request)
        replaced.update(overrides)
        with ExitStack() as stack:
            stack.enter_context(patch.multiple(trial,**replaced))
            stack.enter_context(patch.object(validate_offline,'require_pass'))
            stack.enter_context(patch.object(trial.subprocess,'Popen',return_value=self.child))
            stack.enter_context(patch.object(trial.subprocess,'run',return_value=SimpleNamespace(
                returncode=returncode,stdout='Saved '+str(self.integration)+'\n',stderr='integration fixture\n')))
            stack.enter_context(patch.object(trial.urllib.request,'urlopen',return_value=Stream(stream)))
            try:trial.main();error=None
            except Exception as caught:error=caught
        return error,json.loads((self.folder/'campaign/verification.json').read_text())

    def assert_failed_and_cleaned(self,receipt,text):
        self.assertEqual(receipt['status'],'failed')
        self.assertIn(text,receipt['error'])
        self.assertEqual(receipt['exit_code'],0)
        self.assertEqual(self.child.returncode,0)

    def test_complete_checks_and_postflight_accept_the_receipt(self):
        error,receipt=self.run_verifier()
        self.assertIsNone(error)
        self.assertEqual((receipt['status'],receipt['checks_status'],receipt['exit_code']),('passed','passed',0))
        self.assertTrue(receipt['activation']['reduce']['encoded'])
        self.assertEqual(receipt['actual_chunks'],{'n_batch':[512,512],'n_ubatch':[512,512]})
        self.assertTrue(receipt['source_unchanged'] and receipt['launcher_unchanged'] and receipt['default_launcher_unchanged'])

    def test_missing_activation_marker_saves_failed_receipt(self):
        (self.runtime/'native.log').write_text('llama_context: n_batch = 512\nllama_context: n_ubatch = 512\n'*2)
        error,receipt=self.run_verifier()
        self.assertIsInstance(error,ValueError)
        self.assert_failed_and_cleaned(receipt,'reduction encoding marker missing')
        self.assertEqual(receipt['checks_status'],'passed')

    def test_missing_chunk_marker_saves_failed_receipt(self):
        (self.runtime/'native.log').write_text(NATIVE_LOG.replace('n_ubatch = 512','n_ubatch = 256'))
        error,receipt=self.run_verifier()
        self.assertIsInstance(error,ValueError)
        self.assert_failed_and_cleaned(receipt,'batch sizes differ')

    def test_missing_memory_summary_saves_failed_receipt(self):
        (self.runtime/'memory-summary.json').unlink()
        error,receipt=self.run_verifier()
        self.assertIsInstance(error,FileNotFoundError)
        self.assert_failed_and_cleaned(receipt,'memory-summary.json')

    def test_memory_gate_failure_rejects_receipt(self):
        (self.runtime/'memory-summary.json').write_text(json.dumps(dict(HEALTHY_MEMORY,swap_growth_bytes=4096)))
        error,receipt=self.run_verifier()
        self.assertIsInstance(error,RuntimeError)
        self.assert_failed_and_cleaned(receipt,'pressure/swap/shutdown gate failed')

    def test_port_still_bound_saves_failed_receipt(self):
        def bound():raise OSError(48,'Address already in use')
        error,receipt=self.run_verifier(ports_closed=bound)
        self.assertIsInstance(error,OSError)
        self.assert_failed_and_cleaned(receipt,'Address already in use')

    def test_postflight_snapshot_failure_saves_failed_receipt(self):
        calls=[]
        def snapshot():
            calls.append(1)
            if len(calls)>1:raise RuntimeError('memory_pressure unavailable')
            return {}
        error,receipt=self.run_verifier(snapshot=snapshot)
        self.assertIsInstance(error,RuntimeError)
        self.assert_failed_and_cleaned(receipt,'memory_pressure unavailable')

    def test_profile_source_change_during_run_rejects_receipt(self):
        original=self.request
        def request(*args,**kwargs):
            self.source.write_text('changed while the app was running\n')
            return original(*args,**kwargs)
        error,receipt=self.run_verifier(request=request)
        self.assertIsInstance(error,RuntimeError)
        self.assert_failed_and_cleaned(receipt,'source changed')
        self.assertFalse(receipt['source_unchanged'])

    def test_answer_failure_keeps_original_error_after_postflight(self):
        def request(base,endpoint,payload=None,timeout=600):
            response=self.request(base,endpoint,payload,timeout)
            if endpoint!='/health':response['choices'][0]['message']['content']='392'
            return response
        (self.runtime/'memory-summary.json').unlink()  # A later postflight failure must not mask the cause.
        error,receipt=self.run_verifier(request=request)
        self.assertIsInstance(error,RuntimeError)
        self.assert_failed_and_cleaned(receipt,'Actual app answer check failed')
        self.assertIn('memory-summary.json',receipt['finalization_error'])
        self.assertNotIn('checks_status',receipt)

    def test_stop_during_checks_reaps_child_and_records_postflight(self):
        def request(base,endpoint,payload=None,timeout=600):
            if endpoint!='/health':raise KeyboardInterrupt('Termination requested (SIGTERM)')
            return {}
        with self.assertRaises(KeyboardInterrupt):self.run_verifier(request=request)
        receipt=json.loads((self.folder/'campaign/verification.json').read_text())
        self.assert_failed_and_cleaned(receipt,'SIGTERM')
        self.assertIn('postflight',receipt)


    def test_code_edit_profile_checks_lookup_command_and_accepts_fenced_json(self):
        def request(base,endpoint,payload=None,timeout=600):
            response=self.request(base,endpoint,payload,timeout)
            if payload and payload['messages'][0]['content'].startswith('Extract the name'):
                response['choices'][0]['message']['content']='```json\n{"name": "Morgan", "age": 29}\n```'
            return response
        error,receipt=self.run_verifier(stream=b': keep-alive\n\n'+STREAM,request=request,
                                        **self.use_profile('code-edit','Start Strata - Code Editing.command'))
        self.assertIsNone(error)
        self.assertEqual(receipt['status'],'passed')
        self.assertIn('--spec-ngram-mod-n-match',receipt['native_command'])
        fenced=[c for c in receipt['checks'] if c['name']=='json']
        self.assertEqual([(c['strict_json'],c['semantic_json']) for c in fenced],[(False,dict(name='Morgan',age=29))]*2)
        self.assertTrue(receipt['streaming_check']['done_marker'])

    def test_long_document_profile_checks_facts_and_ui_chunk_settings(self):
        state=self.use_profile('long-documents','Start Strata - Long Documents.command')
        error,receipt=self.run_verifier(**state)
        self.assertIsNone(error)
        self.assertEqual((receipt['status'],receipt['actual_chunks']['n_batch']),('passed',[1536,1536]))
        self.assertTrue(receipt['long_document_check']['passed'])
        shutil.rmtree(self.folder/'campaign');self.child=Child()
        def request(base,endpoint,payload=None,timeout=600):
            if endpoint=='/metrics':return dict(performance=dict(settings=dict(batch=512,ubatch=512)))
            return self.request(base,endpoint,payload,timeout)
        error,receipt=self.run_verifier(request=request,**state)
        self.assert_failed_and_cleaned(receipt,'chunk settings missing from UI metrics')
        self.assertNotIn('long_document_check',receipt)

    def test_unqualified_native_command_or_metal_profile_is_rejected(self):
        (self.runtime/'command.json').write_text(json.dumps(['--spec-type','ngram-mod,draft-mtp','--spec-draft-n-max','3',
            '--spec-draft-threads','8','--spec-draft-p-min','0.0','-b','512','-ub','512']))
        error,receipt=self.run_verifier()
        self.assert_failed_and_cleaned(receipt,'differs from qualified lookup profile')
        self.assertEqual(receipt['checks'],[])
        shutil.rmtree(self.folder/'campaign');self.child=Child();self.use_profile('balanced','Start Strata.command')
        (self.runtime/'metal-environment.json').write_text(json.dumps(dict(tuning='default',tensor_api='on')))
        error,receipt=self.run_verifier()
        self.assert_failed_and_cleaned(receipt,'Wrong P07/TensorAPI profile')

    def test_unfenced_prose_json_keeps_the_original_decode_error(self):
        def request(base,endpoint,payload=None,timeout=600):
            response=self.request(base,endpoint,payload,timeout)
            if payload and payload['messages'][0]['content'].startswith('Extract the name'):
                response['choices'][0]['message']['content']='Morgan is 29.'
            return response
        error,receipt=self.run_verifier(request=request)
        self.assertIsInstance(error,json.JSONDecodeError)
        self.assert_failed_and_cleaned(receipt,'JSONDecodeError')

    def test_broken_edit_stream_or_integration_fails_with_its_own_error(self):
        def request(base,endpoint,payload=None,timeout=600):
            response=self.request(base,endpoint,payload,timeout)
            if payload and payload['messages'][0]['content']==self.case['prompt']:
                response['choices'][0]['finish_reason']='length'
            return response
        error,receipt=self.run_verifier(request=request)
        self.assert_failed_and_cleaned(receipt,'whole-file edit failed')
        self.assertFalse(receipt['checks'][-1]['passed'])
        for stream,returncode,text in ((b'data: {"choices":[{"delta":{"content":"391"}}]}\n\n',0,'SSE output/completion failed'),
                                       (STREAM,1,'Full API integration failed')):
            with self.subTest(text=text):
                shutil.rmtree(self.folder/'campaign');self.child=Child()
                error,receipt=self.run_verifier(stream=stream,returncode=returncode)
                self.assert_failed_and_cleaned(receipt,text)
        self.assertEqual((receipt['integration_returncode'],(self.folder/'campaign/integration.log').read_text()),
                         (1,'Saved '+str(self.integration)+'\nintegration fixture\n'))

    def test_launcher_exit_or_unready_app_fails_before_any_check(self):
        self.child.returncode=1
        error,receipt=self.run_verifier()
        self.assertIn('exited before ready',str(error))
        self.assertEqual((receipt['status'],receipt['exit_code'],receipt['checks']),('failed',1,[]))
        self.assertNotIn('active',receipt)
        shutil.rmtree(self.folder/'campaign');self.child=Child()
        (self.folder/'bench/runtime/active.json').write_text(json.dumps(dict(pid=1,log_directory=str(self.runtime))))
        def unhealthy(base,endpoint,payload=None,timeout=600):raise OSError('connection refused')
        clock=SimpleNamespace(monotonic=iter([0,30,61]).__next__,sleep=lambda seconds:None)
        error,receipt=self.run_verifier(request=unhealthy,time=clock)
        self.assert_failed_and_cleaned(receipt,'readiness timed out')
        self.assertNotIn('native_memory',receipt)

    def test_previous_attempt_or_missing_options_never_starts_a_launcher(self):
        (self.folder/'campaign').mkdir()
        with patch.multiple(trial,OUT=self.folder/'campaign',LAUNCHER=self.folder/'Start Strata.command',
                            options=SimpleNamespace(profile='balanced')), \
                patch.object(trial.subprocess,'Popen',side_effect=AssertionError):
            with self.assertRaisesRegex(RuntimeError,'already attempted'):trial.main()
        with patch.object(trial,'options',None), self.assertRaisesRegex(RuntimeError,'as a script'):trial.main()


class StopChildTests(unittest.TestCase):
    def test_unresponsive_launcher_is_killed_after_bounded_wait(self):
        child=Child(hang=1)
        trial.stop_child(child)
        self.assertEqual(child.returncode,-9)
        self.assertEqual(child.calls,['terminate','wait','kill','wait'])

    def test_stop_request_during_wait_still_reaps_launcher(self):
        child=Child(interrupt=True)
        with self.assertRaises(KeyboardInterrupt):trial.stop_child(child)
        self.assertEqual(child.returncode,0)
        self.assertEqual(child.calls,['terminate','wait','terminate','wait'])

    def test_stop_during_checks_passed_cleanup_fails_receipt(self):
        test=ProfileVerifierReceiptTests('test_complete_checks_and_postflight_accept_the_receipt')
        test.setUp();self.addCleanup(test.doCleanups)
        test.child=Child(interrupt=True)
        with self.assertRaises(KeyboardInterrupt):test.run_verifier()
        receipt=json.loads((test.folder/'campaign/verification.json').read_text())
        self.assertEqual((receipt['status'],receipt['checks_status'],receipt['exit_code']),('failed','passed',0))
        self.assertIn('SIGTERM',receipt['finalization_error'])

    def test_launcher_that_survives_kill_is_reported(self):
        class Stuck(Child):
            def kill(self):self.calls.append('kill')
        child=Stuck(hang=3)
        with self.assertRaises(subprocess.TimeoutExpired):trial.stop_child(child)
        self.assertEqual(child.calls,['terminate','wait','kill','wait'])

    def test_ports_closed_binds_each_fixed_app_port(self):
        with patch.object(trial.socket,'socket') as made:
            self.assertEqual(trial.ports_closed(),[8095,8096])
        sock=made.return_value.__enter__.return_value
        self.assertEqual([c.args for c in sock.bind.call_args_list],[(('127.0.0.1',8095),),(('127.0.0.1',8096),)])
        sock.setsockopt.assert_called_with(trial.socket.SOL_SOCKET,trial.socket.SO_REUSEADDR,1)

    def test_absent_or_exited_child_needs_no_cleanup(self):
        trial.stop_child(None)
        child=Child();child.returncode=1
        trial.stop_child(child)
        self.assertEqual(child.calls,[])


if __name__=='__main__':unittest.main()
