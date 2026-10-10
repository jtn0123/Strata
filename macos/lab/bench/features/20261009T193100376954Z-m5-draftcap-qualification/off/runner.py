#!/usr/bin/env python3
"""Bounded, untimed MTP cap qualification; native successful decode counters."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark import Monitor, stream_completion, wait_ready
from benchmark_m5_next import wait_for_headroom
from capture_m5_native import PROMPTS, normalized_command
from check_memory import assert_no_model_server
from engines import sha256, verify_engine
from lab import request, server_command
from metal_environment import configure
from model_provenance import assert_unchanged, verify_models
from profile_m5_routes import preflight
from validate_offline import require_pass

MODES = {
    'stock': ('m5-copy', 0, 0, 0),
    'off': ('m5-draftcap', 0, 0, 0),
    'tail': ('m5-draftcap', 1, 0, 0),
    'two-off': ('m5-draftcap', 0, 2, 0),
    'two': ('m5-draftcap', 1, 2, 0),
    'schedule': ('m5-draftcap', 1, 0, 1),
}


def markers(text, name):
    values = []
    for line in text.splitlines():
        if name not in line: continue
        match = re.fullmatch(r'(?:[0-9]+\.[0-9]{2}\.[0-9]{3}\.[0-9]{3} I )?'+re.escape(name)+r' (.+)', line)
        if not match: raise ValueError('Malformed native marker: '+line)
        values.append(json.loads(match.group(1)))
    return values


def acceptance(text):
    return [dict(accepted=int(m[1]), drafted=int(m[2]), restored=bool(m[3]))
            for m in re.finditer(r' I slot .*?accepted\s+(\d+)/\s*(\d+) draft tokens( \(restore checkpoint\))?', text)]


def parse_native(record, text):
    mode = record['mode']; engine, early, cap, schedule = MODES[mode]
    if engine == 'm5-copy':
        if 'M5_DRAFT_' in text: raise ValueError('Stock control unexpectedly traced lab cap')
    else:
        init = markers(text, 'M5_DRAFT_INIT')
        if init != [dict(configured=3, early_stop=bool(early), trace=True)]:
            raise ValueError('Actual helper max, early-stop or trace selection differs')
        calls = markers(text, 'M5_DRAFT_NATIVE')
        if not calls or [r['call'] for r in calls] != list(range(1, len(calls)+1)):
            raise ValueError('Missing, reordered or duplicate successful helper calls')
    raw = (record['_folder'] / 'native.log').read_bytes()
    counts = Counter(); cycles = 0; discarded = 0
    for req in record['requests']:
        part = raw[req['log_begin']:req['log_end']].decode()
        accepted = acceptance(part)
        req['acceptance'] = accepted
        for event in accepted:
            if not 0 <= event['accepted'] <= event['drafted'] <= 3:
                raise ValueError('Invalid acceptance prefix')
            category = 'zero' if event['accepted'] == 0 else ('full' if event['accepted'] == event['drafted'] else 'partial')
            counts[category] += 1; counts['checkpoint_restore'] += event['restored']
        if engine == 'm5-copy': continue
        offers, native, verify, target = [markers(part, n) for n in
            ('M5_DRAFT_OFFER','M5_DRAFT_NATIVE','M5_DRAFT_VERIFY','M5_DRAFT_TARGET')]
        if len(offers) != len(native) or len(native) != len(verify):
            raise ValueError('Offer/native/verification invocation counts differ')
        if offers and [r['cycle'] for r in offers] != list(range(1, len(offers)+1)):
            raise ValueError('Fresh draft cycle did not reset at request boundary')
        for offer, n, v in zip(offers, native, verify):
            expected = min(offer['budget_cap'], cap or 3,
                           (3,1,2,3)[(offer['cycle']-1)%4] if schedule else 3)
            if (offer['seq'] != 0 or n['seq'] != 0 or v['seq'] != 0 or
                not 1 <= offer['budget_cap'] <= 3 or offer['offered'] != expected or
                n['requested'] != expected or n['configured'] != 3 or
                n['pos0'] != offer['pos0'] or n['early_stop'] is not bool(early) or
                n['steps'] != (expected if early else 3) or n['produced'] != n['steps'] or
                v['task'] != offer['task'] or v['cycle'] != offer['cycle'] or
                v['drafts'] != expected or v['rows'] != expected+1):
                raise ValueError('Effective cap, successful helper steps or target verification differs')
            discarded += n['produced']-v['drafts']; cycles += 1
        if offers and not target: raise ValueError('Missing actual target decode evidence')
        if any(type(t['rows']) is not int or t['rows'] < 1 for t in target):
            raise ValueError('Invalid actual target decode rows')
        req['native'] = dict(offers=offers, helper=native, verification=verify, actual_target=target)
    record['native_summary'] = dict(cycles=cycles, discarded_helper_steps=discarded,
        acceptance_counts=dict(counts), actual_successful_helper_decode_calls=True,
        hidden_state_bit_identity_measured=False, speed_gain_measured=False)
    if not all(counts[k] for k in ('zero','partial','full')):
        raise ValueError('Missing zero, partial or full prefix acceptance coverage')


def capture(mode, folder, proof):
    folder.mkdir(); engine, early, cap, schedule = MODES[mode]
    source = sha256(__file__); (folder/'runner.py').write_bytes(Path(__file__).read_bytes())
    pin = verify_engine(engine); env, flags = configure(os.environ, engine, 'on', 'conv-direct')
    # Diagnostic trace only. Timing driver separately removes these inherited settings.
    for name in ('LLAMA_TRACE','LLAMA_SERVER_SLOTS_DEBUG','LLAMA_SERVER_SLOTS_N_DIFF'):
        env.pop(name, None)
    env['LLAMA_TRACE'] = '1'; flags['variables']['LLAMA_TRACE'] = '1'
    if engine != 'm5-copy':
        for name, value in dict(DRAFT_EARLY_STOP=early,DRAFT_CAP=cap,DRAFT_SCHEDULE=schedule,DRAFT_TRACE=1).items():
            key = 'GGML_M5_LAB_'+name; env[key] = str(value); flags['variables'][key] = str(value)
    record = dict(schema=1,status='running',mode=mode,engine=pin,model_proof=proof,
        runner_sha256=source,metal_environment=flags,requests=[],timings_excluded_from_speed_results=True,
        scope='Single slot; global max3 allocation; helper greedy; n_min0; confidence0; normal scheduler and no callback',
        models_loaded=False)
    save = lambda: (folder/'capture.json').write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    process = monitor = log_guard = None; stop_guard = threading.Event()
    try:
        require_pass(); assert_no_model_server(); assert_unchanged(proof)
        record['headroom'] = wait_for_headroom(); record['preflight'] = preflight(False)
        with socket.socket() as sock: sock.bind(('127.0.0.1',0)); port = sock.getsockname()[1]
        command = server_command('flash',port,4096,512,512,'draft-mtp',3,draft_placement='mixed',
            draft_model='mtp_shared_packed_q3',engine=engine,draft_threads=8,draft_p_min=0.0)
        if '--spec-draft-n-min' not in command:
            command.extend(['--spec-draft-n-min','0','--spec-draft-sampling','greedy'])
        command.append('--slots'); record['command'] = command; save()
        log_path = folder/'native.log'
        with log_path.open('w') as log:
            baseline = Monitor.baseline(); process = subprocess.Popen(command,env=env,stdout=log,stderr=log)
            record['models_loaded'] = True
            monitor = Monitor(process,folder/'memory.jsonl',0,1024**3,baseline=baseline); monitor.thread.start()
            def guard_log():
                while not stop_guard.wait(0.25):
                    if log_path.stat().st_size > 64*1024**2:
                        record['log_guard'] = '64 MiB diagnostic log cap exceeded'; monitor.stop_owned_child(); return
            log_guard = threading.Thread(target=guard_log,daemon=True); log_guard.start()
            base = f'http://127.0.0.1:{port}'; record['ready_s'] = wait_ready(process,base)
            print(mode,'ready',round(record['ready_s'],2),flush=True)
            def encode(text): return request(base,'/tokenize',dict(content=text,add_special=False,parse_special=True))['tokens']
            def render(text): return request(base,'/apply-template',dict(messages=[dict(role='user',content=text)],chat_template_kwargs={'enable_thinking':False}))['prompt']
            encoded = {name:encode(render(content)) for name,content in PROMPTS.items()}
            def complete(name,tokens,count=32,temp=0,cached=False,eos=False):
                time.sleep(0.15); begin = log_path.stat().st_size
                payload = dict(prompt=tokens,n_predict=count,temperature=temp,seed=1234,
                    ignore_eos=not eos,cache_prompt=cached,return_tokens=True,stream=True)
                response = stream_completion(base,payload)
                time.sleep(0.15); end = log_path.stat().st_size; final = response['final']; timing = final['timings']
                if not eos and (timing['predicted_n'] != count or len(response['generated_token_ids']) != count):
                    raise RuntimeError('Fixed output count mismatch')
                if eos and final['stop_type'] != 'eos': raise RuntimeError('Expected normal EOS finish')
                if not cached and timing['prompt_n'] != len(tokens): raise RuntimeError('Fresh prompt count differs')
                if cached and not (timing['cache_n'] > 0 and timing['prompt_n'] < len(tokens)):
                    raise RuntimeError('Cached follow-up did not reuse prefix')
                settings = final['generation_settings']
                if (settings['seed'] != 1234 or abs(settings['temperature']-temp) > 1e-6 or
                    settings['backend_sampling'] is not False): raise RuntimeError('Target sampling settings changed')
                record['requests'].append(dict(workload=name,prompt_sha256=hashlib.sha256(json.dumps(tokens).encode()).hexdigest(),
                    policy=dict(count=count,temperature=temp,cached=cached,ignore_eos=not eos,seed=1234),
                    log_begin=begin,log_end=end,response=response)); save(); print(mode,name,'ok',flush=True)
                return response
            complete('warmup',encoded['prose'],8)
            for count in (1,2,3,4,5,7,8,16): complete('limit'+str(count),encoded['code'],count)
            for name in PROMPTS:
                for temp in (0,0.6): complete(name+'-'+str(temp),encoded[name],64,temp)
            complete('seed-repeat',encoded['code'],64,0.6)
            a = next(r['response'] for r in record['requests'] if r['workload']=='code-0.6')
            if any(a[k] != record['requests'][-1]['response'][k] for k in ('text','generated_token_ids')):
                raise RuntimeError('Repeated seed output differs')
            short = encode(render('What is 17 plus 25? Reply with only the number.'))
            eos_response = complete('normal-eos',short,64,eos=True)
            if eos_response['text'].strip() != '42': raise RuntimeError('Arithmetic answer changed')
            first = complete('continuation-first',encoded['prose'],32)
            followup = encoded['prose']+first['generated_token_ids']+encode('\nGive one concrete example.\n')
            cached = complete('cached-followup',followup,32,cached=True)
            fresh = complete('fresh-followup',followup,32)
            if any(cached[k] != fresh[k] for k in ('text','generated_token_ids')):
                raise RuntimeError('Cached/fresh continuation differs')
            # Close a live stream after receiving tokens, then require idle and a clean reply.
            payload = dict(prompt=encoded['prose'],n_predict=2048,ignore_eos=True,temperature=0,
                seed=1234,cache_prompt=False,stream=True,return_tokens=True)
            seen=[]; begin=log_path.stat().st_size
            req=urllib.request.Request(base+'/completion',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=60) as stream:
                for line in stream:
                    if not line.startswith(b'data: '): continue
                    item=json.loads(line[6:]); seen.extend(item.get('tokens',[]))
                    if len(seen)>=5: break
            start=time.monotonic(); polls=[]
            while True:
                slots=request(base,'/slots',timeout=10); polls.append(slots)
                if all(not slot['is_processing'] for slot in slots): break
                if time.monotonic()-start>15: raise RuntimeError('Cancellation did not release slot')
                time.sleep(0.1)
            time.sleep(0.15); record['cancellation']=dict(received_token_ids=seen,slots=polls,
                idle_s=time.monotonic()-start,log_begin=begin,log_end=log_path.stat().st_size)
            complete('after-cancel',short,16)
            # Explicit context admission failure, followed by recovery; not a context-shift proof.
            oversized = (encoded['code'] * (4200//len(encoded['code'])+1))[:4200]
            error=None
            try: request(base,'/completion',dict(prompt=oversized,n_predict=1,cache_prompt=False),timeout=30)
            except RuntimeError as e: error=str(e)
            if error is None or 'HTTP 400' not in error: raise RuntimeError('Oversized prompt was not rejected')
            record['oversized_prompt_rejection']=dict(prompt_tokens=len(oversized),error=error,
                context_shift_exercised=False)
            complete('after-context-rejection',short,16)
        record['status']='completed'
    except BaseException as error:
        record.update(status='failed',error=f'{type(error).__name__}: {error}')
    finally:
        stop_guard.set()
        if log_guard: log_guard.join(timeout=2)
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        if monitor: record['memory']=monitor.finish()
        try:
            assert_no_model_server()
            if record['status']=='completed':
                m=record['memory']
                if record.get('log_guard') or m['guard'] or m['swap_growth_bytes'] or not m['monitor_healthy'] or not m['child_exited']:
                    raise RuntimeError('Resource/cleanup gate failed')
                text=log_path.read_text()
                if 'borrowing target embeddings/output; draft KV remains separate' not in text:
                    raise RuntimeError('Shared helper did not activate')
                record['_folder']=folder
                try: parse_native(record,text)
                finally: record.pop('_folder',None)
                if verify_engine(engine)!=pin or sha256(__file__)!=source: raise RuntimeError('Capture provenance changed')
                assert_unchanged(proof); require_pass(); record['status']='passed'
        except BaseException as error: record.update(status='failed',error=f'{type(error).__name__}: {error}')
        save(); print(mode,record['status'],folder,flush=True)
    if record['status']!='passed': raise RuntimeError(record.get('error','capture failed'))
    return record


def compare(a,b, require_rows=False):
    if a['status']!='passed' or b['status']!='passed' or a['model_proof']!=b['model_proof'] or normalized_command(a['command'])!=normalized_command(b['command']):
        raise RuntimeError('Invalid provenance or unmatched settings')
    if len(a['requests'])!=len(b['requests']): raise RuntimeError('Missing request coverage')
    differences=[]; target_differences=[]; accept_differences=[]
    for x,y in zip(a['requests'],b['requests']):
        if any(x[k]!=y[k] for k in ('workload','prompt_sha256','policy')): raise RuntimeError('Request identity differs')
        if any(x['response'][k]!=y['response'][k] for k in ('text','generated_token_ids')):
            ax,bx=x['response']['generated_token_ids'],y['response']['generated_token_ids']
            first=next((i for i,(u,v) in enumerate(zip(ax,bx)) if u!=v),min(len(ax),len(bx)))
            differences.append(dict(workload=x['workload'],first_different_token=first,control_tokens=ax,candidate_tokens=bx))
        if require_rows:
            if x['native']['actual_target']!=y['native']['actual_target']: target_differences.append(x['workload'])
            if x['acceptance']!=y['acceptance']: accept_differences.append(x['workload'])
    return dict(status='passed' if not (differences or target_differences or accept_differences) else 'failed',
        control=a['mode'],candidate=b['mode'],requests=len(a['requests']),output_differences=differences,
        actual_target_differences=target_differences,acceptance_differences=accept_differences,
        tokens_compared=sum(len(r['response']['generated_token_ids']) for r in a['requests']),
        speed_gain_measured=False)


def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--modes',nargs='+',choices=MODES,default=['stock','off','tail'])
    args=ap.parse_args()
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB); require_pass(); assert_no_model_server()
        proof=verify_models(['flash','mtp_shared_packed_q3'])
        folder=ROOT/'bench/features'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-m5-draftcap-qualification')
        folder.mkdir(); print(folder,flush=True)
        batch=dict(schema=1,status='running',modes=args.modes,runs={},comparisons=[])
        try:
            records={}
            for mode in args.modes:
                if records: time.sleep(10)
                records[mode]=capture(mode,folder/mode,proof); batch['runs'][mode]=str((folder/mode).relative_to(ROOT))
                (folder/'batch.json').write_text(json.dumps(batch,indent=2)+'\n')
            for control,candidate in (('stock','off'),('off','tail'),('two-off','two'),('tail','two')):
                if control in records and candidate in records:
                    pair=compare(records[control],records[candidate],require_rows=control in ('off','two-off'))
                    batch['comparisons'].append(pair)
                    if pair['status']!='passed': batch['status']='parity-failed'
            if batch['status']=='running': batch['status']='passed'
        except BaseException as error:
            batch.update(status='failed',error=f'{type(error).__name__}: {error}'); raise
        finally: (folder/'batch.json').write_text(json.dumps(batch,indent=2)+'\n')
        print('Qualification',batch['status'],folder,flush=True)


if __name__=='__main__': main()
