#!/usr/bin/env python3
"""Q2_0 expert grouping correctness and complete graph timing; not model TPS."""
import argparse
from collections import Counter
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

WORK=ROOT/'bench/runtime/m5-group';SOURCE=ROOT/'native/m5_group_probe.cpp';BINARY=WORK/'group-probe'
FIXTURE=ROOT/'config/m5_group_routes.json'


def inventory(mode):
    if mode=='perf': return [(r,route,'plain',0) for r in (4,5) for route in ('real','distinct','shared')]
    return ([(r,'distinct','plain',0) for r in (1,2,3,6)]
            +[(r,route,layout,index) for r in (4,5) for route,layout,index in
              ([('real','plain',i) for i in range(8)]
               +[(route,'plain',0) for route in ('distinct','shared','duplicate','mixed')]
               +[('mixed',layout,0) for layout in ('input-strided','ids-contiguous','ids-offset','weights-strided','cancel','wide')])]
            +[(r,'real','chain',0) for r in (4,5)])


def fixtures():
    data=json.loads(FIXTURE.read_text())
    if data['schema']!=1 or len(data['sources'])!=2 or set(data['routes'])!={'4','5'}: raise ValueError('Wrong real route fixture inventory')
    for source,rows in zip(data['sources'],(4,5)):
        path=ROOT/source['path']
        if sha256(path)!=source['sha256']: raise ValueError('Recorded routing source changed')
        capture=json.loads(path.read_text())
        if capture['status']!='passed' or capture['depth']!=rows-1: raise ValueError('Routing source failed or wrong depth')
        events={r['serial']:r for r in capture['diagnostics']['routing_events']}
        routes=data['routes'][str(rows)]
        if len(routes)!=8 or len({r['source_serial'] for r in routes})!=8: raise ValueError('Missing or duplicate real routes')
        for route in routes:
            event=events[route['source_serial']]
            if event['ids']!=route['ids'] or event['role']!='target' or event['rows']!=rows or event['layer']!=route['layer']:
                raise ValueError('Route fixture does not match target capture')
            if len(route['ids'])!=rows or any(len(row)!=10 or len(set(row))!=10 or any(type(i)!=int or not 0<=i<512 for i in row) for row in route['ids']):
                raise ValueError('Invalid actual expert route')
            if len({i for row in route['ids'] for i in row})!=route['unique_experts']: raise ValueError('Wrong real expert reuse count')
    return data


def build():
    fixtures();pin=verify_engine('m5-group');native=ROOT/pin['directory'];WORK.mkdir(exist_ok=True)
    cmd=['/usr/bin/c++','-O3','-ffp-contract=off','-std=gnu++17','-arch','arm64',
         '-I'+str(native/'ggml/include'),'-I'+str(native/'vendor'),str(SOURCE),'-o',str(BINARY),
         '-Wl,-rpath,'+str(native/'build/bin'),
         *[str(native/'build/bin'/n) for n in ('libggml.0.26.0.dylib','libggml-base.0.26.0.dylib')]]
    with (WORK/'probe-build.log').open('w') as log: subprocess.run(cmd,stdout=log,stderr=log,check=True)
    record={'engine':pin,'source_sha256':sha256(SOURCE),'runner_sha256':sha256(__file__),
            'fixture_sha256':sha256(FIXTURE),'binary_sha256':sha256(BINARY),'command':cmd}
    (WORK/'probe-build.json').write_text(json.dumps(record,indent=2)+'\n');return record


def verify():
    record=json.loads((WORK/'probe-build.json').read_text());fixtures()
    if (record['engine']!=verify_engine('m5-group') or record['source_sha256']!=sha256(SOURCE)
        or record['runner_sha256']!=sha256(__file__) or record['fixture_sha256']!=sha256(FIXTURE)
        or record['binary_sha256']!=sha256(BINARY)): raise RuntimeError('Group probe provenance changed')
    return record


def parse(text,mode,tuning):
    def markers(name): return [json.loads(line.split(name+' ',1)[1]) for line in text.splitlines() if line.startswith(name+' ')]
    cases=markers('M5_GROUP_CASE');done=markers('M5_GROUP_DONE');expected=inventory(mode)
    if len(done)!=1 or done[0]['mode']!=mode or done[0]['cases']!=len(expected) or done[0]['weights_preserved'] is not True:
        raise ValueError('Incomplete group operator evidence')
    # Nine full-512-expert buffers, six contiguous and three with a padding row.
    weight_bytes=6*512*ggml_row_bytes(2560)*640+2*512*ggml_row_bytes(2560)*641+512*ggml_row_bytes(640)*2561
    if done[0]['allocated_weight_bytes']!=weight_bytes: raise ValueError('Unexpected expert-weight working set')
    if [(c['rows'],c['route'],c['layout'],c['route_index']) for c in cases]!=expected or 'M5_GROUP_ERROR' in text:
        raise ValueError('Group coverage/order differs or native error occurred')
    for c in cases:
        copies=8 if mode=='perf' or c['layout']=='chain' else 1
        if (c['samples']!=(60 if mode=='perf' else 1) or c['triplets_per_graph']!=copies
            or c['input_ids_preserved'] is not True or c['elements']!=3840*10*c['rows']*copies
            or len(c['distinct_experts'])!=copies or any(type(n)!=int or not 1<=n<=10*c['rows'] for n in c['distinct_experts'])
            or any(not math.isfinite(c[f]) or c[f]<0 for f in ('cpu_nmse','max_absolute_error','wall_us_per_triplet'))
            or c['cpu_nmse']>=1e-8 or c['max_absolute_error']>=0.0001 or c['wall_us_per_triplet']<=0):
            raise ValueError('Invalid accuracy, memory or timing evidence')
    routes=markers('M5_GROUP_ROUTE')
    want=Counter()
    if mode=='check' and tuning=='expert-group':
        for r,_,layout,_ in expected:
            if r in (4,5) and layout!='weights-strided':
                copies=8 if layout=='chain' else 1
                want[(2560,640,r,10*r,28*10*r,False)]+=10*copies
                want[(640,2560,r,10*r,28*10*r,False)]+=5*copies
    got=Counter((r['k'],r['m'],r['rows'],r['assignments'],r['map_bytes'],r['map_reused']) for r in routes)
    if got!=want: raise ValueError('Candidate dispatch or fallback proof differs; diagnostic timing forbidden')
    return cases


def ggml_row_bytes(k):
    # Pinned Q2_0 block: 64 values, F16 scale + 16 packed bytes.
    return k//64*18


def execute(mode,tuning):
    assert_no_model_server();pin=verify()
    folder=ROOT/'bench/features'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-m5-group-'+mode+'-'+tuning)
    folder.mkdir();env,flags=configure(os.environ,'m5-group','on',tuning)
    if mode=='check': env['GGML_M5_LAB_GROUP_TRACE']='1';flags['variables']['GGML_M5_LAB_GROUP_TRACE']='1'
    record={'status':'running','probe':pin,'mode':mode,'metal_environment':flags,'models_loaded':False,'tps_measured':False,
        'scope':'Eight sequential gate/up/SwiGLU/down triplets with weighted expert reduction and residual per triplet. All maps, barriers and bridge cost included; two distinct full512 weight sets and eight actual routes per real graph. No callbacks or perf diagnostics. Operator times are not model TPS.'}
    process=monitor=None
    try:
        with (folder/'native.log').open('w') as log:
            baseline=Monitor.baseline();process=subprocess.Popen([BINARY,mode,FIXTURE,folder/'outputs.bin'],env=env,stdout=log,stderr=log)
            monitor=Monitor(process,folder/'memory.jsonl',0,2**30,baseline=baseline);monitor.thread.start();code=process.wait(timeout=900)
        monitor.thread.join(timeout=5);record['memory']=monitor.finish()
        if code or record['memory']['guard'] or record['memory']['swap_growth_bytes'] or not record['memory']['monitor_healthy']:
            raise RuntimeError('Group probe or memory check failed')
        record['cases']=parse((folder/'native.log').read_text(),mode,tuning)
        record['outputs_sha256']=sha256(folder/'outputs.bin')
        size=sum(c['elements'] for c in record['cases'])*4 if mode=='check' else 0
        if (folder/'outputs.bin').stat().st_size!=size: raise RuntimeError('Wrong operator tensor evidence size')
        if verify()!=pin: raise RuntimeError('Engine or probe changed')
        record['status']='passed'
    except BaseException as error:
        record.update(status='failed',error=f'{type(error).__name__}: {error}');raise
    finally:
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill();process.wait()
        if monitor: monitor.thread.join(timeout=5)
        (folder/'probe.json').write_text(json.dumps(record,indent=2)+'\n');print(mode,tuning,record['status'],folder,flush=True)
    return folder


def _compare(control,candidate):
    a,b=[json.loads((p/'probe.json').read_text()) for p in (control,candidate)]
    if (a['status']!='passed' or b['status']!='passed' or a['probe']!=b['probe'] or a['mode']!=b['mode']
        or a['metal_environment']['tuning']!='conv-direct' or b['metal_environment']['tuning']!='expert-group'):
        raise ValueError('Unmatched operator evidence')
    for record in (a,b):
        memory=record.get('memory',{})
        if (memory.get('swap_growth_bytes')!=0 or memory.get('guard') or not memory.get('monitor_healthy')
            or not memory.get('child_exited') or record['metal_environment']['tensor_api']!='on'
            or record['metal_environment']['profile']): raise ValueError('Memory or environment evidence failed')
    key=lambda c:(c['rows'],c['route'],c['layout'],c['route_index'])
    if list(map(key,a['cases']))!=list(map(key,b['cases'])): raise ValueError('Case coverage differs')
    if a['mode']=='check':
        x,y=[np.fromfile(p/'outputs.bin',dtype=np.uint32) for p in (control,candidate)]
        if len(x)!=sum(c['elements'] for c in a['cases']) or not np.array_equal(x,y):
            raise ValueError('Expert projections changed output bits')
        result={'elements_bit_identical':len(x),'all_CPU_references_passed':True}
    else:
        result={'cases':[dict(rows=x['rows'],route=x['route'],control_us=x['wall_us_per_triplet'],candidate_us=y['wall_us_per_triplet'],
                             time_reduction_percent=100*(1-y['wall_us_per_triplet']/x['wall_us_per_triplet'])) for x,y in zip(a['cases'],b['cases'])]}
    result.update(status='passed',control=str(control.relative_to(ROOT)),candidate=str(candidate.relative_to(ROOT)))
    (candidate/'comparison.json').write_text(json.dumps(result,indent=2)+'\n');return result


def compare(control,candidate):
    try: return _compare(control,candidate)
    except BaseException as error:
        (candidate/'comparison.json').write_text(json.dumps(dict(status='failed',control=str(control.relative_to(ROOT)),
            candidate=str(candidate.relative_to(ROOT)),error=f'{type(error).__name__}: {error}'),indent=2)+'\n')
        raise


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--build',action='store_true');ap.add_argument('--run',action='store_true')
    ap.add_argument('--mode',choices=('check','perf'),default='check');args=ap.parse_args()
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.build: build()
        if args.run: compare(execute(args.mode,'conv-direct'),execute(args.mode,'expert-group'))


if __name__=='__main__': main()
