#!/usr/bin/env python3
"""Exact shared-projection checks and complete graph timings; never model TPS."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import math
import os
import subprocess

import numpy as np
from benchmark import Monitor
from check_memory import assert_no_model_server
from engines import ROOT, sha256, verify_engine
from metal_environment import configure

WORK=ROOT/'bench/runtime/m5-hc';SOURCE=ROOT/'native/m5_hc_probe.cpp';BINARY=WORK/'hc-probe'
CANDIDATES=('hc-special',*[f'hc-down-ks{s}' for s in (1,2,4,8,16)],'hc-up')


def build():
    pin=verify_engine('m5-hc');native=ROOT/pin['directory'];WORK.mkdir(exist_ok=True)
    cmd=['/usr/bin/c++','-O3','-ffp-contract=off','-std=gnu++17','-arch','arm64',
         '-I'+str(native/'ggml/include'),'-I'+str(native/'vendor'),str(SOURCE),'-o',str(BINARY),
         '-Wl,-rpath,'+str(native/'build/bin'),
         *[str(native/'build/bin'/n) for n in ('libggml.0.26.0.dylib','libggml-base.0.26.0.dylib')]]
    with (WORK/'build.log').open('w') as log: subprocess.run(cmd,stdout=log,stderr=log,check=True)
    r={'engine':pin,'source_sha256':sha256(SOURCE),'runner_sha256':sha256(__file__),'binary_sha256':sha256(BINARY),'command':cmd}
    (WORK/'build.json').write_text(json.dumps(r,indent=2)+'\n');return r


def verify():
    r=json.loads((WORK/'build.json').read_text())
    if (r['engine']!=verify_engine('m5-hc') or r['source_sha256']!=sha256(SOURCE)
        or r['runner_sha256']!=sha256(__file__) or r['binary_sha256']!=sha256(BINARY)):
        raise RuntimeError('HC probe provenance changed')
    return r


def parse(text,mode,tuning,tensor):
    def markers(name): return [json.loads(line.split(name+' ',1)[1]) for line in text.splitlines() if line.startswith(name+' ')]
    cases=markers('M5_HC_CASE');done=markers('M5_HC_DONE');count=72 if mode=='check' else 24
    if done!=[{'mode':mode,'cases':count}] or len(cases)!=count or 'M5_HC_ERROR' in text:
        raise ValueError('Incomplete HC operator evidence')
    keys=[(c['k'],c['m'],c['rows'],c['layout']) for c in cases]
    expected={(k,m,r,l) for k,m in ((10240,320),(320,10240)) for r in (1,2,3,4,5,8)
              for l in (('plain','residual','exposed','strided','cancel','wide') if mode=='check' else ('plain','residual'))}
    if len(set(keys))!=count or set(keys)!=expected: raise ValueError('Wrong shape/layout or duplicate HC cases')
    if any(not c['input_preserved'] or c['samples']!=(1 if mode=='check' else 60) or
           c['copies_per_graph']!=(1 if mode=='check' else 20) or c['cpu_nmse']>=1e-8 or
           c['max_absolute_error']>=0.0001 or c['wall_us_per_op']<=0 or c['elements']!=c['m']*c['rows'] or
           c['distinct_weight_bytes']!=c['k']*c['m']*2*c['copies_per_graph'] or
           any(not math.isfinite(c[field]) or c[field]<0 for field in ('cpu_nmse','max_absolute_error','wall_us_per_op')) for c in cases):
        raise ValueError('Invalid HC timing or CPU reference')
    routes=[line.split()[1:] for line in text.splitlines() if line.startswith('M5_HC_ROUTE ')]
    if mode=='check':
        from collections import Counter
        got=Counter(tuple(int(x.split('=')[1]) for x in route) for route in routes)
        want=Counter()
        if tensor=='on' and (tuning.startswith('hc-down-') or tuning=='hc-up'):
            k,m,split=(10240,320,int(tuning.split('ks')[1])) if tuning.startswith('hc-down-') else (320,10240,1)
            for r in (4,5): want[(k,m,r,0,split)]=20;want[(k,m,r,1,split)]=5
        if got!=want: raise ValueError('New-kernel route or fallback coverage differs')
    elif routes: raise ValueError('Diagnostic route logging contaminated timings')
    return cases


def execute(mode,tuning,tensor='on'):
    assert_no_model_server();pin=verify()
    folder=ROOT/'bench/features'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-m5-hc-'+mode+'-'+tuning+'-'+tensor)
    folder.mkdir();env,flags=configure(os.environ,'m5-hc',tensor,tuning)
    if mode=='check': env['GGML_M5_LAB_HC_TRACE']='1';flags['variables']['GGML_M5_LAB_HC_TRACE']='1'
    record={'status':'running','probe':pin,'mode':mode,'metal_environment':flags,'models_loaded':False,'tps_measured':False,
            'scope':'Checks include masked short rows, strides, residual fusion and exposed intermediates. Perf uses normal fusion and 20 distinct 6.55MB weight copies per graph; no per-op callbacks.'}
    process=monitor=None
    try:
        with (folder/'native.log').open('w') as log:
            baseline=Monitor.baseline();process=subprocess.Popen([BINARY,mode,folder/'outputs.bin'],env=env,stdout=log,stderr=log)
            monitor=Monitor(process,folder/'memory.jsonl',0,2**30,baseline=baseline);monitor.thread.start()
            code=process.wait(timeout=300)
        monitor.thread.join(timeout=5);record['memory']=monitor.finish()
        if code or record['memory']['guard'] or record['memory']['swap_growth_bytes'] or not record['memory']['monitor_healthy']:
            raise RuntimeError('HC run or memory guard failed')
        record['cases']=parse((folder/'native.log').read_text(),mode,tuning,tensor)
        record['outputs_sha256']=sha256(folder/'outputs.bin')
        expected=sum(c['elements'] for c in record['cases'])*4 if mode=='check' else 0
        if (folder/'outputs.bin').stat().st_size!=expected: raise RuntimeError('Wrong HC tensor evidence size')
        if verify()!=pin: raise RuntimeError('HC engine or probe changed')
        record['status']='passed'
    except BaseException as error:
        record.update(status='failed',error=f'{type(error).__name__}: {error}');raise
    finally:
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill();process.wait()
        if monitor: monitor.thread.join(timeout=5)
        (folder/'probe.json').write_text(json.dumps(record,indent=2)+'\n');print(mode,tuning,tensor,record['status'],folder,flush=True)
    return folder


def compare(control,candidate):
    a,b=[json.loads((p/'probe.json').read_text()) for p in (control,candidate)]
    if a['status']!='passed' or b['status']!='passed' or a['probe']!=b['probe'] or a['mode']!=b['mode']:
        raise ValueError('Unmatched HC evidence')
    keys=lambda r:[(c['k'],c['m'],c['rows'],c['layout']) for c in r['cases']]
    if keys(a)!=keys(b): raise ValueError('HC comparison case order differs')
    if a['mode']=='check':
        x,y=[np.fromfile(p/'outputs.bin',dtype=np.float32) for p in (control,candidate)]
        if len(x)!=len(y) or len(x)!=sum(c['elements'] for c in a['cases']): raise ValueError('Missing tensor values')
        start=0;unchanged=0
        for c in a['cases']:
            end=start+c['elements'];tuning=b['metal_environment']['tuning'];tensor=b['metal_environment']['tensor_api']
            affected=tensor=='on' and c['rows'] in (4,5) and c['layout']!='strided' and (
                (tuning.startswith('hc-down-') and c['k']==10240) or (tuning=='hc-up' and c['k']==320))
            if not affected:
                if not np.array_equal(x[start:end].view(np.uint32),y[start:end].view(np.uint32)): raise ValueError('Untouched HC/fallback output bits changed')
                unchanged+=c['elements']
            start=end
        result={'elements_compared':len(x),'unchanged_elements_bit_identical':unchanged,'all_CPU_references_passed':True}
    else:
        result={'cases':[dict(k=x['k'],m=x['m'],rows=x['rows'],layout=x['layout'],control_us=x['wall_us_per_op'],candidate_us=y['wall_us_per_op'],
                             time_reduction_percent=100*(1-y['wall_us_per_op']/x['wall_us_per_op'])) for x,y in zip(a['cases'],b['cases'])]}
    result.update(status='passed',control=str(control.relative_to(ROOT)),candidate=str(candidate.relative_to(ROOT)))
    (candidate/'comparison.json').write_text(json.dumps(result,indent=2)+'\n');return result


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--build',action='store_true');ap.add_argument('--run',action='store_true')
    ap.add_argument('--mode',choices=('check','perf'),default='check');ap.add_argument('--tuning',choices=CANDIDATES,nargs='+',default=list(CANDIDATES))
    ap.add_argument('--tensor-api',choices=('on','off'),default='on');args=ap.parse_args()
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.build: build()
        if args.run:
            control=execute(args.mode,'conv-direct',args.tensor_api)
            for tuning in args.tuning: compare(control,execute(args.mode,tuning,args.tensor_api))


if __name__=='__main__': main()
