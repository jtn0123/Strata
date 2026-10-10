#!/usr/bin/env python3
"""Freeze/run a native monitoring baseline; no model is loaded without --run."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import threading

import psutil
from benchmark import Monitor, host_snapshot, stream_completion, wait_ready
from benchmark_mlx_cache import watch_pressure
from check_memory import assert_no_model_server, snapshot
from engines import sha256, verify_engine
from lab import ROOT, request, server_command
from metal_environment import configure
from model_provenance import assert_unchanged, verify_models
from observe_metrics import allocation_entries, parse
from validate_offline import fingerprint, require_pass

PLAN = ROOT / 'config/m5_observe_plan.json'


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def freeze(folder, model):
    gate = require_pass()
    engines = {n:verify_engine(n) for n in ('m5-small-stack', 'm5-observe')}
    models = verify_models(['small'] if model == 'small' else ['flash', 'mtp_shared_packed_q3'])
    sources = fingerprint()
    frozen = dict(schema=1, frozen_utc=datetime.now(timezone.utc).isoformat(), model=model,
                  plan=json.loads(PLAN.read_text()), engines=engines, models=models, sources=sources,
                  adopted=False, speed_gain_claimed=False)
    folder.mkdir()  # Refuse overwrite of every attempted or merely prepared campaign.
    for name in sources:
        dest=folder/'source'/name;dest.parent.mkdir(parents=True, exist_ok=True);shutil.copy2(ROOT/name,dest)
    shutil.copy2(ROOT/'patches/mtp-m5-observe.patch',folder/'observer.patch')
    shutil.copy2(ROOT/'bench/features/offline-validation.json',folder/'offline-validation.json')
    shutil.copy2(Path(gate['log']),folder/'offline-validation.log')
    write(folder/'frozen.json',frozen)
    return frozen


def unchanged(folder, f):
    if fingerprint() != f['sources'] or json.loads(PLAN.read_text()) != f['plan']:
        raise ValueError('Monitoring source/config closure changed')
    for name, digest in f['sources'].items():
        if sha256(folder/'source'/name) != digest:
            raise ValueError('Archived monitoring source changed')
    if sha256(folder/'observer.patch') != f['engines']['m5-observe']['patch']['patch_sha256']:
        raise ValueError('Archived observer patch changed')
    for name, pin in f['engines'].items():
        if verify_engine(name) != pin: raise ValueError('Native engine changed')
    assert_unchanged(f['models'])


def admit(plan, model):
    assert_no_model_server()
    state = snapshot()
    state['pressure_level'] = int(subprocess.check_output(['sysctl','-n','kern.memorystatus_vm_pressure_level'],text=True))
    state['required_available_bytes'] = plan['admission_gib'][model] * 2**30
    state['cpu_samples'] = [psutil.cpu_percent(interval=1) for _ in range(3)]
    state['accepted'] = (state['memory']['available'] >= state['required_available_bytes'] and
                         state['pressure_level'] == plan['pressure_level'] and
                         max(state['cpu_samples']) <= 25 and statistics.mean(state['cpu_samples']) <= 15)
    return state


def launch(folder, model, arm, plan):
    folder.mkdir()
    record = dict(status='preflight', model=model, arm=arm, cases=[], model_process_launched=False,
                  timings_excluded_from_optimization_results=True)
    process=monitor=timer=watcher=None
    done=threading.Event();pressure=dict(samples=0,error=None)
    try:
        record['preflight'] = admit(plan,model)
        write(folder/'result.json',record)
        if not record['preflight']['accepted']:
            raise RuntimeError('Resource admission refused before model launch')
        engine=plan['control_engine'] if arm=='control' else plan['observer_engine']
        enabled=arm=='observer-on'
        env,flags=configure(os.environ,engine,'on',plan['tuning'],profile=enabled)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        command=server_command(model,port,plan['context'],plan['batch'],plan['batch'],
            spec='draft-mtp' if model=='flash' else 'none',draft=3 if model=='flash' else 0,
            cache_type=plan['cache_type'],engine=engine,draft_placement='mixed' if model=='flash' else 'gpu',
            draft_model='mtp_shared_packed_q3' if model=='flash' else 'mtp',
            draft_threads=8 if model=='flash' else None,draft_p_min=0.0 if model=='flash' else None)
        record.update(command=command,metal_environment=flags,host_before=host_snapshot())
        baseline=Monitor.baseline()
        record['final_admission']=dict(**baseline,pressure_level=int(subprocess.check_output(
            ['sysctl','-n','kern.memorystatus_vm_pressure_level'],text=True)))
        write(folder/'result.json',record)
        if (baseline['available_bytes']<plan['admission_gib'][model]*2**30 or
                baseline['swap_used_bytes']>record['preflight']['swap']['used'] or record['final_admission']['pressure_level']!=1):
            raise RuntimeError('Final resource admission refused before model launch')
        with (folder/'native.log').open('w') as log:
            process=subprocess.Popen(command,env=env,stdout=log,stderr=log,start_new_session=True)
            record.update(status='running',model_process_launched=True);write(folder/'result.json',record)
            monitor=Monitor(process,folder/'memory.jsonl',0,plan['floor_gib']*2**30,baseline=baseline)
            monitor.thread.start()
            watcher=threading.Thread(target=watch_pressure,args=(process,folder/'pressure.jsonl',done,pressure),daemon=True)
            watcher.start()
            timer=threading.Timer(plan['child_timeout_s'],lambda:process.terminate() if process.poll() is None else None)
            timer.start();base=f'http://127.0.0.1:{port}';record['ready_s']=wait_ready(process,base)
            for name,content in plan['workloads'].items():
                rendered=request(base,'/apply-template',{'messages':[{'role':'user','content':content}],
                    'chat_template_kwargs':{'enable_thinking':False}})['prompt']
                ids=request(base,'/tokenize',{'content':rendered,'add_special':False,'parse_special':True})['tokens']
                for repetition in range(-plan['warmups_per_workload'],plan['repeats']):
                    payload=dict(prompt=ids,n_predict=plan['output_tokens'][model],stream=True,
                        temperature=plan['temperature'],seed=plan['seed'],cache_prompt=False,ignore_eos=True,return_tokens=True)
                    response=stream_completion(base,payload);t=response['final']['timings']
                    if (t['prompt_n']!=len(ids) or t['predicted_n']!=payload['n_predict'] or
                            len(response['generated_token_ids'])!=payload['n_predict'] or not response['final']['stop']):
                        raise ValueError('Incomplete baseline output or prompt count')
                    if any(type(i) is not int or i<0 for i in response['generated_token_ids']):raise ValueError('Invalid output token ID')
                    for key in ('predicted_per_second','prompt_per_second'):
                        from benchmark_metrics import positive
                        positive(t[key],key)
                    record['cases'].append(dict(workload=name,repeat=repetition,warmup=repetition<0,input_ids=ids,
                                               request=payload,response=response))
                    write(folder/'result.json',record)
                    print(f'{arm}: {name} repeat={repetition} {t["predicted_per_second"]:.3f} TPS',flush=True)
            record['status']='completed'
    except BaseException as error:
        record.update(status='failed',error=f'{type(error).__name__}: {error}')
    finally:
        if timer:timer.cancel()
        if process and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        done.set()
        if watcher:watcher.join(timeout=5)
        if monitor:record['memory']=monitor.finish()
        record['pressure']=pressure;record['host_after']=host_snapshot()
        if record['status']=='completed':
            try:
                m=record['memory']
                if m['guard'] or m['swap_growth_bytes'] or not m['monitor_healthy'] or not m['child_exited'] or not pressure['samples'] or pressure['error'] or watcher.is_alive():
                    raise ValueError('Resource monitor or shutdown failed')
                text=(folder/'native.log').read_text()
                record['allocations']=allocation_entries(text)
                if arm=='observer-on':
                    record['diagnostics']=parse(text,len(record['cases']),max_clock_spread_us=plan['clock_spread_us'],
                                                max_anchor_width_us=plan['clock_anchor_width_us'])
                elif 'M5_CPU_CALL ' in text or 'M5_PHASE ' in text:raise ValueError('Disabled monitoring emitted records')
                record['status']='passed'
            except BaseException as error:record.update(status='failed',postcheck_error=f'{type(error).__name__}: {error}')
        write(folder/'result.json',record)
    return record


def signature(r):
    return [(c['workload'],c['repeat'],c['input_ids'],c['response']['generated_token_ids'],c['response']['text'],
             c['response']['final'].get('stop_type'),c['response']['final']['timings'].get('draft_n'),
             c['response']['final']['timings'].get('draft_n_accepted')) for c in r['cases']]


def summarize(records):
    if len(records)!=4 or any(r['status']!='passed' for r in records) or any(signature(r)!=signature(records[0]) for r in records):
        raise ValueError('Complete four-arm exact output/topology baseline required')
    rows=[]
    for name in ('code','prose'):
        arms=[]
        for r in records:
            cases=[c['response'] for c in r['cases'] if c['workload']==name and not c['warmup']]
            if len(cases)!=3:raise ValueError('Three measured repeats required')
            arms.append(dict(tps=statistics.median(c['final']['timings']['predicted_per_second'] for c in cases),
                             ttft_s=statistics.median(c['ttft_s'] for c in cases),reply_s=statistics.median(c['wall_s'] for c in cases)))
        base={k:(arms[0][k]+arms[3][k])/2 for k in arms[0]}
        rows.append(dict(workload=name,baseline=base,arm_medians=arms,
            control_drift_percent={k:100*abs(arms[3][k]-arms[0][k])/base[k] for k in base},
            monitoring_perturbation_percent={k:100*(arms[2][k]/base[k]-1) for k in base},
            observer_off_build_difference_percent={k:100*(arms[1][k]/base[k]-1) for k in base}))
    return rows


def run(folder):
    if (folder/'result.json').exists() or list(folder.glob('[0-9][0-9]-*')):
        raise ValueError('Campaign already attempted; no retry or partial resume')
    f=json.loads((folder/'frozen.json').read_text());plan=f['plan']
    result=dict(status='running',runs=[],baseline_complete=False,adoption=False,speed_gain_claimed=False)
    records=[]
    with (folder/'result.json').open('x') as stream:
        stream.write(json.dumps(result,indent=2)+'\n')
    try:
        with (ROOT/'bench/.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged(folder,f)
            for index,arm in enumerate(plan['order']):
                dest=folder/f'{index:02d}-{arm}';r=launch(dest,f['model'],arm,plan)
                result['runs'].append(str(dest.relative_to(ROOT)));write(folder/'result.json',result)
                if r['status']!='passed':raise RuntimeError(r.get('error',r.get('postcheck_error')))
                if index and signature(r)!=signature(records[0]):raise ValueError('Output, helper counts or input history diverged')
                records.append(r);unchanged(folder,f)
            result.update(status='passed',baseline_complete=True,summary=summarize(records),
                          diagnostic_scope='small-model monitor validation' if f['model']=='small' else 'P07 short English native baseline')
    except BaseException as error:result.update(status='held-before-load' if not result['runs'] or not json.loads((ROOT/result['runs'][-1]/'result.json').read_text())['model_process_launched'] else 'failed',error=f'{type(error).__name__}: {error}')
    finally:
        write(folder/'result.json',result)
        lines=['# Native monitoring baseline','',f'Status: **{result["status"]}**','',
               'No optimization or adoption. Instrumented timings measure monitoring overhead; controls establish the baseline. Small-model diagnostics cannot identify full-model helper bottlenecks.','']
        if result.get('summary'):
            lines+=['| Workload | Control TPS | First token (s) | Reply (s) | Monitor TPS change |','| --- | ---: | ---: | ---: | ---: |']
            for row in result['summary']:
                b=row['baseline'];lines.append(f'| {row["workload"]} | {b["tps"]:.4f} | {b["ttft_s"]:.4f} | {b["reply_s"]:.4f} | {row["monitoring_perturbation_percent"]["tps"]:+.4f}% |')
        if result.get('error'):lines+=['',result['error']]
        lines+=['','[Frozen protocol](frozen.json), [all results](result.json). Raw per-arm logs, outputs and resource samples retained.']
        (folder/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print(f'Saved {folder}: {result["status"]}',flush=True)
    return result


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--model',choices=['small','flash'],default='small');ap.add_argument('--freeze',action='store_true');ap.add_argument('--run',action='store_true')
    ap.add_argument('--campaign',type=Path);args=ap.parse_args(argv)
    if args.freeze and args.run:ap.error('Freeze before running, as separate actions')
    if not args.freeze and not args.run:print('Plan: memory/allocation and CPU/GPU/helper monitoring; freeze then --run explicitly.');return
    if not args.campaign:ap.error('--campaign required inside bench/results')
    folder=(ROOT/args.campaign).resolve()
    if not folder.is_relative_to((ROOT/'bench/results').resolve()) or folder==(ROOT/'bench/results').resolve():ap.error('Campaign must be a child of bench/results')
    if args.freeze:
        with (ROOT/'bench/.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);freeze(folder,args.model)
    elif run(folder)['status']!='passed':raise SystemExit(1)


if __name__=='__main__':main()
