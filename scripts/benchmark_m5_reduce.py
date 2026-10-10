#!/usr/bin/env python3
"""Check ten-expert reduction and measure complete operator graphs, not model TPS."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import statistics
import subprocess

import numpy as np

from benchmark import Monitor
from check_memory import assert_no_model_server
from engines import ROOT, sha256, verify_engine
from metal_environment import configure

SOURCE = ROOT / 'native/m5_reduce_probe.cpp'
WORK = ROOT / 'bench/runtime/m5-reduce'
BINARY = WORK / 'reduce-probe'


def build():
    pin = verify_engine('m5-reduce'); native = ROOT / pin['directory']
    command = ['/usr/bin/c++', '-O3', '-ffp-contract=off', '-std=gnu++17', '-arch', 'arm64',
               '-I'+str(native/'ggml/include'), '-I'+str(native/'vendor'), str(SOURCE),
               '-o', str(BINARY), '-Wl,-rpath,'+str(native/'build/bin'),
               *[str(native/'build/bin'/n) for n in ('libggml.0.26.0.dylib','libggml-base.0.26.0.dylib')]]
    WORK.mkdir(exist_ok=True)
    with (WORK/'build.log').open('w') as log:
        subprocess.run(command, stdout=log, stderr=log, check=True)
    record = {'engine':pin,'source_sha256':sha256(SOURCE),'runner_sha256':sha256(__file__),
              'binary_sha256':sha256(BINARY),'command':command}
    (WORK/'build.json').write_text(json.dumps(record,indent=2)+'\n')
    return record


def verify():
    record = json.loads((WORK/'build.json').read_text())
    if (record['engine'] != verify_engine('m5-reduce') or record['source_sha256'] != sha256(SOURCE)
            or record['runner_sha256'] != sha256(__file__)
            or record['binary_sha256'] != sha256(BINARY)):
        raise RuntimeError('Reduction probe provenance changed')
    return record


def parse(text, mode):
    def markers(name): return [json.loads(line.split(name+' ',1)[1]) for line in text.splitlines() if name+' ' in line]
    cases = markers('M5_REDUCE_CASE'); done = markers('M5_REDUCE_DONE')
    count = 120 if mode == 'check' else 4
    if done != [{'mode':mode,'cases':count}] or len(cases) != count or 'M5_REDUCE_ERROR' in text:
        raise ValueError('Incomplete operator validation or timing coverage')
    keys = [(c['width'],c['rows'],c['experts'],c['layout']) for c in cases]
    expected = ({(w,r,10,l) for w in (7,2560,2563) for r in (1,3,4,5)
                 for l in ('plain','strided','exposed','reversed','cancel','special','alias')}
                | {(67,r,e,'plain') for r in (1,3,4,5) for e in (2,3,4,5,6,7,8,9,11)}) if mode=='check' else {
                    (2560,r,10,'plain') for r in (1,3,4,5)}
    if set(keys) != expected: raise ValueError('Wrong operator shape or fallback coverage')
    if len(set(keys)) != count or any(not c['input_preserved'] or c['samples'] != (1 if mode=='check' else 100)
            or c['elements'] != c['width']*c['rows'] or c['wall_us'] <= 0 for c in cases):
        raise ValueError('Invalid or duplicate operator evidence')
    return cases


def execute(mode, tuning):
    assert_no_model_server(); pin = verify()
    folder = ROOT/'bench/features'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-m5-reduce-'+mode+'-'+tuning)
    folder.mkdir(); env,flags = configure(os.environ,'m5-reduce','on',tuning)
    record = {'status':'running','probe':pin,'mode':mode,'metal_environment':flags,
              'models_loaded':False,'tps_measured':False,
              'scope':'Fusion statistics enabled only for checks; perf uses normal encoding and fusion'}
    process = monitor = None
    try:
        with (folder/'native.log').open('w') as log:
            baseline = Monitor.baseline()
            process = subprocess.Popen([BINARY,mode,folder/'outputs.bin'],stdout=log,stderr=log,env=env)
            monitor = Monitor(process,folder/'memory.jsonl',0,1024**3,baseline=baseline); monitor.thread.start()
            code = process.wait(timeout=180)
        monitor.thread.join(timeout=5); record['memory'] = monitor.finish()
        if code or record['memory']['guard'] or record['memory']['swap_growth_bytes'] or not record['memory']['monitor_healthy']:
            raise RuntimeError('Operator run or memory guard failed')
        record['cases'] = parse((folder/'native.log').read_text(),mode)
        record['outputs_sha256'] = sha256(folder/'outputs.bin')
        if (folder/'outputs.bin').stat().st_size != sum(c['elements'] for c in record['cases'])*4:
            raise RuntimeError('Incomplete tensor output evidence')
        if verify() != pin: raise RuntimeError('Probe changed during execution')
        record['status']='passed'
    except BaseException as error:
        record.update(status='failed',error=f'{type(error).__name__}: {error}'); raise
    finally:
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
        if monitor: monitor.thread.join(timeout=5)
        (folder/'probe.json').write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
        print(f'{mode} {tuning}: {record["status"]}; {folder}',flush=True)
    return folder


def compare(control, candidate):
    a,b = [json.loads((p/'probe.json').read_text()) for p in (control,candidate)]
    if a['status'] != 'passed' or b['status'] != 'passed' or a['mode'] != b['mode'] or a['probe'] != b['probe']:
        raise ValueError('Unmatched operator runs')
    x,y = [np.fromfile(p/'outputs.bin',dtype=np.uint32) for p in (control,candidate)]
    if len(x) != len(y): raise ValueError('Tensor evidence length differs')
    same = x==y
    same |= np.isnan(x.view(np.float32)) & np.isnan(y.view(np.float32))
    if not same.all(): raise ValueError(f'{int((~same).sum())} non-NaN output bits changed')
    offset = 0; rows=[]
    for ca,cb in zip(a['cases'],b['cases']):
        keys=('width','rows','experts','layout','elements','samples')
        if any(ca[k] != cb[k] for k in keys): raise ValueError('Operator case identity differs')
        expected = cb['experts']==10 and cb['layout'] in ('plain','cancel','special')
        if a['mode']=='check':
            # Each check graph is executed four warmups plus one measured validation call.
            label = 'MUL'+'+ADD'*9
            fused=cb['fusions'].get(label,0)-ca['fusions'].get(label,0)
            # Upstream counts this reduction in both its dispatcher and its handler.
            if fused != (10 if expected else 0): raise ValueError(f'Fusion activation/fallback mismatch: {cb}')
            if cb['experts']==10 and cb['layout']!='special' and (ca['cpu_bit_differences'] or cb['cpu_bit_differences']):
                raise ValueError('Finite F32 reference arithmetic differs')
        rows.append({**{k:ca[k] for k in keys},'control_us':ca['wall_us'],'candidate_us':cb['wall_us'],
                     'operator_time_reduction_percent':100*(1-cb['wall_us']/ca['wall_us']),
                     'same_output_bits_except_nan_payload':True,'fused10_expected':expected})
        offset += ca['elements']
    return {'cases':rows,'tensor_elements_compared':offset,'same_output_bits_except_nan_payload':True}


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--build',action='store_true')
    ap.add_argument('--run',action='store_true');ap.add_argument('--mode',choices=('check','perf'),default='check')
    args=ap.parse_args()
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.build: build()
        if args.run:
            paths=[execute(args.mode,t) for t in ('conv-direct','reduce10')]
            result=compare(*paths);result['runs']=[str(p.relative_to(ROOT)) for p in paths]
            output=paths[-1]/'comparison.json';output.write_text(json.dumps(result,indent=2)+'\n')
            print(f'Compared {result["tensor_elements_compared"]} tensor elements; {output}')
        else: print('Prepared only; --run starts small GPU operator checks. No model inference.')


if __name__=='__main__': main()
