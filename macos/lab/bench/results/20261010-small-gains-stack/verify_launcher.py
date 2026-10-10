#!/usr/bin/env python3
"""Check the promoted launcher through Strata's actual API, then stop owned work."""
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import urllib.request

import psutil

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from answer_checks import run_answer_checks
from check_memory import assert_no_model_server, snapshot
from engines import sha256, verify_engine
from lab import request
from profile_m5_routes import preflight
from benchmark_m5_small_gains import feature_receipts
from benchmark_m5_next import wait_for_headroom
from metal_environment import configure
from run import assert_ports_available


def main():
    tracking=json.loads((HERE/'tracking.json').read_text())
    if tracking['status']!='completed' or not tracking['promotion_eligible']:
        raise ValueError('No safety-qualified winner to verify')
    assert_no_model_server(); assert_ports_available((8095,8096))
    headroom=wait_for_headroom()
    pre=preflight()
    baseline=psutil.swap_memory().used
    process=None; samples=[]; done=threading.Event(); guard=[]
    record=dict(status='running', winner=tracking['winner'], winner_profile=tracking['winner_profile'],
                created_utc=datetime.now(timezone.utc).isoformat(), preflight=pre, headroom=headroom, checks=[],
                launcher_sha256=sha256(ROOT/'Start Strata.command'), runner_sha256=sha256(__file__),
                samples=samples, claims='Application correctness/lifecycle check; not a new performance benchmark.')
    def save(): (HERE/'launcher-verification.json').write_text(json.dumps(record, indent=2)+'\n')
    def watch():
        while not done.is_set():
            sample=dict(time=time.time(), available_bytes=psutil.virtual_memory().available,
                        swap_used_bytes=psutil.swap_memory().used)
            samples.append(sample)
            if sample['swap_used_bytes']>baseline or sample['available_bytes']<1024**3:
                guard.append(sample)
                if process and process.poll() is None: process.terminate()
                return
            done.wait(.25)
    save()
    watcher=threading.Thread(target=watch, daemon=True)
    with (HERE/'launcher.stdout.log').open('w') as log:
        try:
            process=subprocess.Popen(['/bin/zsh', str(ROOT/'Start Strata.command')], stdout=log, stderr=log)
            watcher.start()
            deadline=time.monotonic()+150
            while True:
                if process.poll() is not None: raise RuntimeError('Owned launcher exited before API was ready')
                try:
                    health=request('http://127.0.0.1:8095','/health', timeout=2)
                    break
                except (OSError, ValueError):
                    if time.monotonic()>=deadline: raise TimeoutError('Strata API did not become ready')
                    time.sleep(.25)
            active=json.loads((ROOT/'bench/runtime/active.json').read_text())
            if active['pid']!=process.pid or active['engine']!='m5-small-stack' or active['model']!='flash':
                raise ValueError('Active launcher does not match owned winner process')
            runtime=Path(active['log_directory'])
            record.update(health=health, active=active, engine=json.loads((runtime/'engine.json').read_text()),
                          native_command=json.loads((runtime/'command.json').read_text()),
                          metal_environment=json.loads((runtime/'metal-environment.json').read_text()),
                          models=request('http://127.0.0.1:8095','/v1/models'))
            _, expected=configure({}, 'm5-small-stack', 'on', tracking['winner_profile'])
            if record['metal_environment']!=expected or record['engine']!=verify_engine('m5-small-stack'):
                raise ValueError('Promoted launcher selected a different engine or profile')
            record['checks']=run_answer_checks('http://127.0.0.1:8095','flash',multilingual=False)
            if not all(c['passed'] for c in record['checks']): raise ValueError('Real application answer checks failed')
            payload=dict(model='flash', messages=[dict(role='user', content='What is 17 multiplied by 23? Reply with only the number.')],
                         stream=True, temperature=0, seed=1234, max_tokens=96,
                         reasoning_effort='none', chat_template_kwargs=dict(enable_thinking=False))
            req=urllib.request.Request('http://127.0.0.1:8095/v1/chat/completions',
                                       data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})
            pieces=[]; terminal=False
            with urllib.request.urlopen(req, timeout=60) as response:
                for line in response:
                    if not line.startswith(b'data: '): continue
                    body=line[6:].strip()
                    if body==b'[DONE]': terminal=True; break
                    value=json.loads(body)
                    for c in value.get('choices',[]): pieces.append(c.get('delta',{}).get('content') or '')
            text=''.join(pieces).strip()
            record['streaming_check']=dict(passed=text=='391' and terminal, text=text, terminal=terminal)
            if not record['streaming_check']['passed']: raise ValueError('Application streaming failed')
            record['feature_encoding_receipts']=feature_receipts((runtime/'native.log').read_text(), tracking['winner'])
            if guard: raise ValueError('Zero-swap/resource guard triggered')
            record['status']='passed'
        except BaseException as error:
            record.update(status='failed', error=str(error)); raise
        finally:
            if process and process.poll() is None:
                process.terminate()
                try: process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(); record['forced_parent_stop']=True
            done.set()
            if watcher.ident is not None: watcher.join(timeout=5)
            record.update(exit_code=process.returncode if process else None, resource_guard=guard,
                          swap_growth_bytes=max(0,max([baseline]+[s['swap_used_bytes'] for s in samples])-baseline),
                          postflight=snapshot())
            ports={}
            for port in (8095,8096):
                with socket.socket() as sock: ports[str(port)]=sock.connect_ex(('127.0.0.1',port))!=0
            record['ports_closed_after_stop']=ports
            try: assert_no_model_server(); record['no_model_server_remaining']=True
            except RuntimeError as error: record['no_model_server_remaining']=False; record['cleanup_error']=str(error)
            if (not all(ports.values()) or not record['no_model_server_remaining']
                    or record['swap_growth_bytes'] or record.get('forced_parent_stop')):
                record['status']='failed'
            if 'active' in record:
                runtime=Path(record['active']['log_directory'])
                if (runtime/'memory-summary.json').exists():
                    record['native_memory']=json.loads((runtime/'memory-summary.json').read_text())
                record['native_log_sha256']=sha256(runtime/'native.log')
            save()
            print('Launcher verification:', record['status'], 'checks:',len(record['checks']), flush=True)
    if record['status']!='passed': raise SystemExit(1)


if __name__=='__main__': main()
