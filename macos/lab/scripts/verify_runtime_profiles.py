"""Verify the separate editing launcher through Strata's real local API, then stop it."""
import ast
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from engines import sha256,verify_engine
from lab import request
from check_memory import assert_no_model_server,snapshot
from benchmark_m5_small_gains import feature_receipts
from benchmark_signals import cleanup_on_termination,defer_termination

import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--profile',choices=('balanced','code-edit','long-documents'),required=True)
parser.add_argument('--output',type=Path,required=True,help='New output directory; never overwrites a previous run')
options=parser.parse_args() if __name__=='__main__' else None
ROLE='lookup' if options and options.profile=='code-edit' else 'control'
OUT=options.output.resolve() if options else None
LAUNCHERS={'balanced':'Start Strata.command','code-edit':'Start Strata - Code Editing.command',
           'long-documents':'Start Strata - Long Documents.command'}
LAUNCHER=ROOT/LAUNCHERS[options.profile] if options else None
SOURCE=ROOT/'scripts/runtime_profiles.py'
PORTS=(8095,8096)


def stop_child(child):
    """Terminate, then kill, and always reap the owned launcher.

    A stop request that arrives during the bounded waits restarts the current
    step instead of abandoning the child; cleanup_on_termination ignores later
    requests, so this cannot loop on repeated signals.
    """
    if child is None:return
    stop=None;killing=False
    while child.poll() is None:
        try:
            if killing:child.kill();child.wait(timeout=3)
            else:child.terminate();child.wait(timeout=20)
        except subprocess.TimeoutExpired:
            if killing:raise
            killing=True
        except KeyboardInterrupt as error:stop=error
    if stop:raise stop


def ports_closed(ports=PORTS):
    closed=[]
    for port in ports:
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            sock.bind(('127.0.0.1',port));closed.append(port)
    return closed


def postflight(record,active,size):
    """Collect shutdown evidence; any missing or failed item raises or marks the receipt failed."""
    if active:
        runtime=Path(active['log_directory']);memory=json.loads((runtime/'memory-summary.json').read_text())
        record['native_memory']=memory
        record['memory_policy']=json.loads((runtime/'memory-policy.json').read_text())
        if memory['guard'] or not memory['normal_pressure_observed'] or memory['swap_growth_bytes'] or not memory['monitor_healthy'] or not memory['child_exited']:
            record.update(status='failed',error='Actual app continuous pressure/swap/shutdown gate failed')
        record['activation']=feature_receipts((runtime/'native.log').read_text(),['reduce'])
        from benchmark_prompt_chunks import chunk_receipt
        record['actual_chunks']=chunk_receipt((runtime/'native.log').read_text(), size)
    assert_no_model_server()
    record.update(ports_closed_after_stop=ports_closed(),no_model_server_remaining=True,postflight=snapshot(),
         default_launcher_unchanged=sha256(ROOT/'Start Strata.command')==record.get('default_launcher_before'),
         launcher_unchanged=sha256(LAUNCHER)==record.get('launcher_sha256'),source_unchanged=sha256(SOURCE)==record.get('source_sha256'))
    if not (record['default_launcher_unchanged'] and record['launcher_unchanged'] and record['source_unchanged']):
        record.update(status='failed',error='Launcher or profile source changed during verification')


@cleanup_on_termination()
def main():
    if OUT.exists():raise RuntimeError('App verification already attempted; no retry/overwrite')
    assert_no_model_server();OUT.mkdir()
    record=dict(status='attempting',created_utc=datetime.now(timezone.utc).isoformat(),checks=[])
    def save():(OUT/'verification.json').write_text(json.dumps(record,indent=2)+'\n')
    child=None;active=None;checks_passed=False
    size='1536' if options.profile=='long-documents' else '512'
    try:
        save()
        from validate_offline import require_pass
        require_pass()
        record.update(launcher_sha256=sha256(LAUNCHER),source_sha256=sha256(SOURCE),verifier_sha256=sha256(Path(__file__)),
           engine=verify_engine('m5-small-stack'),preflight=snapshot(),default_launcher_before=sha256(ROOT/'Start Strata.command'))
        save()
        with (OUT/'launcher.log').open('w') as log:
            launched=[str(LAUNCHER)]
            record['launched']=launched;save()
            # Publish the child before a stop request can unwind to cleanup.
            with defer_termination():
                child=subprocess.Popen(launched,stdout=log,stderr=log,cwd=ROOT)
            started=time.monotonic()
            while True:
                if child.poll() is not None:raise RuntimeError('Optional app launcher exited before ready')
                active_path=ROOT/'bench/runtime/active.json'
                if active_path.exists():
                    value=json.loads(active_path.read_text())
                    if value['pid']==child.pid:active=value
                try:
                    health=request('http://127.0.0.1:8095','/health',timeout=2)
                    if active:break
                except (OSError,RuntimeError):pass
                if time.monotonic()-started>60:raise RuntimeError('Optional app readiness timed out')
                time.sleep(.25)
            record.update(active=active,health=health)
            runtime=Path(active['log_directory'])
            command=json.loads((runtime/'command.json').read_text())
            expected={'--spec-type':'draft-mtp' if ROLE=='control' else 'ngram-mod,draft-mtp','--spec-draft-n-max':'3',
               '--spec-draft-threads':'8','--spec-draft-p-min':'0.0'}
            expected.update({'-b':size,'-ub':size})
            if ROLE=='lookup':expected.update({'--spec-ngram-mod-n-match':'16','--spec-ngram-mod-n-min':'1','--spec-ngram-mod-n-max':'3'})
            if any(command[command.index(k)+1]!=v for k,v in expected.items()):raise RuntimeError('Actual app command differs from qualified lookup profile')
            metal=json.loads((runtime/'metal-environment.json').read_text())
            if metal['tuning']!='small-reduce' or metal['tensor_api']!='on':raise RuntimeError('Wrong P07/TensorAPI profile')
            record.update(native_command=command,metal_environment=metal)
            fixtures=[('multiply','What is 17 multiplied by 23? Reply with only the number.','391'),
                      ('json','Extract the name and age as JSON only: Morgan is 29 years old.',{'name':'Morgan','age':29})]
            for temperature in (0,.6):
                for name,prompt,expected_answer in fixtures:
                    response=request('http://127.0.0.1:8095','/v1/chat/completions',dict(model='flash',messages=[dict(role='user',content=prompt)],
                              temperature=temperature,seed=1234,max_tokens=96,chat_template_kwargs=dict(enable_thinking=False)))
                    text=response['choices'][0]['message']['content'].strip()
                    checked=dict(name=name,temperature=temperature,response=response);record['checks'].append(checked);save()
                    if isinstance(expected_answer,dict):
                        try:actual=json.loads(text);strict=True
                        except json.JSONDecodeError:
                            strict=False
                            lines=text.splitlines()
                            if len(lines)<3 or not lines[0].startswith('```') or lines[-1]!='```':raise
                            actual=json.loads('\n'.join(lines[1:-1]))
                        passed=actual==expected_answer;checked.update(strict_json=strict,semantic_json=actual)
                    else:passed=text==expected_answer
                    checked['passed']=passed;save()
                    if not passed:raise RuntimeError('Actual app answer check failed')
            case=json.loads((ROOT/'tests/fixtures/runtime-code-edit.json').read_text())
            response=request('http://127.0.0.1:8095','/v1/chat/completions',dict(model='flash',messages=[dict(role='user',content=case['prompt'])],
                            temperature=.6,seed=1234,max_tokens=1536,chat_template_kwargs=dict(enable_thinking=False)))
            text=response['choices'][0]['message']['content']
            passed=ast.dump(ast.parse(text))==ast.dump(ast.parse(case['expected'])) and response['choices'][0]['finish_reason']=='stop'
            record['checks'].append(dict(name='full-code-edit',passed=passed,verbatim=text.strip()==case['expected'].strip(),response=response));save()
            if not passed:raise RuntimeError('Actual Strata whole-file edit failed')
            payload=dict(model='flash',messages=[dict(role='user',content='What is 17 multiplied by 23? Reply with only the number.')],temperature=0,seed=1234,max_tokens=32,stream=True,chat_template_kwargs=dict(enable_thinking=False))
            req=urllib.request.Request('http://127.0.0.1:8095/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
            pieces=[];done=False
            with urllib.request.urlopen(req,timeout=30) as stream:
                for line in stream:
                    if not line.startswith(b'data: '):continue
                    value=line[6:].strip()
                    if value==b'[DONE]':done=True;break
                    event=json.loads(value);pieces.append(event['choices'][0].get('delta',{}).get('content',''))
            if ''.join(pieces).strip()!='391' or not done:raise RuntimeError('Actual app SSE output/completion failed')
            record['streaming_check']=dict(passed=True,text=''.join(pieces),done_marker=done)
            if options.profile=='long-documents':
                from benchmark_prompt_chunks import cases, quality
                long_case=cases()[0]
                response=request('http://127.0.0.1:8095','/v1/chat/completions',dict(model='flash',
                    messages=[dict(role='user',content=long_case['content'])],temperature=0,seed=1234,
                    max_tokens=256,chat_template_kwargs=dict(enable_thinking=False)))
                choice=response['choices'][0]
                if choice['finish_reason']!='stop' or not quality(long_case,choice['message']['content']):
                    raise RuntimeError('Long-document API facts or normal stop failed')
                metrics=request('http://127.0.0.1:8095','/metrics')
                settings=metrics['performance']['settings']
                if settings.get('batch')!=1536 or settings.get('ubatch')!=1536:
                    raise RuntimeError('Actual chunk settings missing from UI metrics')
                record['long_document_check']=dict(passed=True,response=response,metrics=metrics)
            integration=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/verify_integration.py'),'--model','flash'],capture_output=True,text=True,timeout=90)
            (OUT/'integration.log').write_text(integration.stdout+integration.stderr)
            record['integration_returncode']=integration.returncode;save()
            if integration.returncode:raise RuntimeError('Full API integration failed; see integration.log')
            result_path=next(line[6:] for line in integration.stdout.splitlines() if line.startswith('Saved '))
            record['integration']=json.loads(Path(result_path).read_text())
            # Provisional only: the receipt is accepted after shutdown and postflight evidence.
            checks_passed=True;record['checks_status']='passed';save()
    except BaseException as error:
        record.update(status='failed',error=f'{type(error).__name__}: {error}');save();raise
    finally:
        failure=None
        try:stop_child(child)
        except BaseException as error:failure=error
        record['exit_code']=child.returncode if child else None;save()
        try:postflight(record,active,size)
        except BaseException as error:failure=failure or error
        if failure is not None:
            record.update(status='failed',finalization_error=f'{type(failure).__name__}: {failure}')
            record.setdefault('error',record['finalization_error'])
        elif checks_passed and record['status']=='attempting':record['status']='passed'
        save()
        # Without an earlier failure in flight, the shutdown/postflight failure is the result.
        if failure is not None and checks_passed:raise failure
    if record['status']!='passed':raise RuntimeError(record.get('error','App verification failed'))
    print('Profile API validation: English answers, complete code edit, SSE and integration passed; zero swap, normal pressure; both ports closed.',flush=True)


if __name__=='__main__':main()
