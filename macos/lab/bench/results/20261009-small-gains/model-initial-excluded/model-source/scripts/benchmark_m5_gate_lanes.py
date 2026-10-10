#!/usr/bin/env python3
"""Exact gate fusion with lane-distributed activation; real scheduler checks and component timing."""
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

WORK=ROOT/'bench/runtime/m5-gate-lanes';SOURCE=ROOT/'native/m5_gate_probe.cpp';BINARY=WORK/'gate-probe'
FIXTURE=ROOT/'config/m5_group_routes.json'
LAYOUTS=('input-strided','weights-strided','ids-contiguous','ids-offset','retained','external','bias','clamp',
         'different-ids','different-input','reversed','activation-unfused','cancel','wide')
POSITIVE={'plain','chain','ids-contiguous','ids-offset','reversed','wide','cancel'}
TUNINGS={'gate-up8':8,'gate-up4':4}


def inventory(mode):
    if mode=='perf': return [(r,route,'plain',0) for r in (4,5) for route in ('real','distinct','shared')]
    return ([(r,'distinct','plain',0) for r in (1,2,3,6)]
            +[(r,route,layout,index) for r in (4,5) for route,layout,index in
              ([('real','plain',i) for i in range(8)]
               +[(route,'plain',0) for route in ('distinct','shared','duplicate','mixed')]
               +[('mixed',layout,0) for layout in LAYOUTS])]
            +[(r,'real','chain',0) for r in (4,5)])


def output_elements(rows,layout,copies):
    return (34560+(12800 if layout=='retained' else 6400 if layout=='external' else 0))*rows*copies


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
    fixtures();pin=verify_engine('m5-gate-lanes');native=ROOT/pin['directory'];WORK.mkdir(parents=True,exist_ok=True)
    cmd=['/usr/bin/c++','-O3','-ffp-contract=off','-std=gnu++17','-arch','arm64',
         '-I'+str(native/'ggml/include'),'-I'+str(native/'vendor'),str(SOURCE),'-o',str(BINARY),
         '-Wl,-rpath,'+str(native/'build/bin'),
         *[str(native/'build/bin'/n) for n in ('libggml.0.26.0.dylib','libggml-base.0.26.0.dylib')]]
    with (WORK/'probe-build.log').open('w') as log:subprocess.run(cmd,stdout=log,stderr=log,check=True)
    record={'engine':pin,'source_sha256':sha256(SOURCE),'runner_sha256':sha256(__file__),
            'fixture_sha256':sha256(FIXTURE),'binary_sha256':sha256(BINARY),'command':cmd}
    (WORK/'probe-build.json').write_text(json.dumps(record,indent=2)+'\n');return record


def verify():
    record=json.loads((WORK/'probe-build.json').read_text());fixtures()
    if (record['engine']!=verify_engine('m5-gate-lanes') or record['source_sha256']!=sha256(SOURCE)
        or record['runner_sha256']!=sha256(__file__) or record['fixture_sha256']!=sha256(FIXTURE)
        or record['binary_sha256']!=sha256(BINARY)):raise RuntimeError('Gate probe provenance changed')
    return record


def parse(text,mode,tuning):
    def markers(name):return [json.loads(line.split(name+' ',1)[1]) for line in text.splitlines() if line.startswith(name+' ')]
    cases=markers('M5_GATE_CASE');done=markers('M5_GATE_DONE');expected=inventory(mode)
    weight_bytes=6*512*(2560//64*18)*640+2*512*(2560//64*18)*641+512*(640//64*18)*2561
    if (len(done)!=1 or done[0]['mode']!=mode or done[0]['cases']!=len(expected)
        or done[0]['weights_preserved'] is not True or done[0]['allocated_weight_bytes']!=weight_bytes
        or done[0]['scheduler'] is not True or done[0]['cpu_compute_nodes']!=0):raise ValueError('Incomplete scheduled gate evidence')
    if [(c['rows'],c['route'],c['layout'],c['route_index']) for c in cases]!=expected or 'M5_GATE_ERROR' in text:
        raise ValueError('Case order/coverage differs or native error occurred')
    for c in cases:
        copies=8 if mode=='perf' or c['layout']=='chain' else 1
        samples=60 if mode=='perf' else 1
        if (c['samples']!=samples or c['triplets_per_graph']!=copies or c['input_ids_preserved'] is not True
            or c['output_elements']!=output_elements(c['rows'],c['layout'],copies)
            or c['eligible']!=(c['rows'] in (4,5) and c['layout'] in POSITIVE)
            or c['scheduler'] is not True or c['cpu_compute_nodes']!=0 or c['graph_buffer_bytes']<=0
            or len(c['distinct_experts'])!=copies or any(type(n)!=int or not 1<=n<=10*c['rows'] for n in c['distinct_experts'])
            or any(not math.isfinite(c[f]) or c[f]<0 for f in ('cpu_nmse','max_absolute_error','max_scaled_error','wall_us_per_triplet'))
            or c['cpu_nmse']>=1e-8 or c['max_scaled_error']>=1e-4 or c['wall_us_per_triplet']<=0
            or len(c['wall_samples_us_per_triplet'])!=samples
            or any(not math.isfinite(t) or t<=0 for t in c['wall_samples_us_per_triplet'])
            or sorted(c['wall_samples_us_per_triplet'])[samples//2]!=c['wall_us_per_triplet']):
            raise ValueError('Invalid reference, placement, preservation or timing evidence')
    routes=markers('M5_GATE_ROUTE');want=Counter()
    if mode=='check' and tuning in TUNINGS:
        for rows,_,layout,_ in expected:
            if rows in (4,5) and layout in POSITIVE:
                want[(2560,640,rows,TUNINGS[tuning],3)]+=5*(8 if layout=='chain' else 1)
    dispatch=[]
    for route in routes:
        if route['phase'] not in ('structural','dispatch'):raise ValueError('Unknown gate marker phase')
        if route['phase']=='dispatch':dispatch.append(route)
    got=Counter((r['k'],r['m'],r['rows'],r['tile'],r['nodes']) for r in dispatch)
    if got!=want or (routes and (mode=='perf' or tuning=='conv-direct')):
        raise ValueError('Fusion/fallback proof differs or timing includes diagnostics')
    return cases


def execute(mode,tuning):
    if tuning not in ('conv-direct',*TUNINGS):raise ValueError('Unknown gate tuning')
    assert_no_model_server();pin=verify()
    folder=ROOT/'bench/features'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-m5-gate-lanes-'+mode+'-'+tuning)
    folder.mkdir();env,flags=configure(os.environ,'m5-gate-lanes','on',tuning)
    if mode=='check':env['GGML_M5_LAB_GATE_TRACE']='1';flags['variables']['GGML_M5_LAB_GATE_TRACE']='1'
    record={'status':'running','probe':pin,'mode':mode,'metal_environment':flags,'models_loaded':False,'tps_measured':False,
        'scope':'Normal backend scheduler/optimizer and allocation dependencies; all graph nodes forced to Metal and placement verified. Eight sequential gate/up/SwiGLU/down blocks with weighted reduction/residual per perf graph, two full512 weight sets and eight recorded routes. Full dispatch/sync costs included. No callbacks, perf traces or CPU graph work.'}
    process=monitor=None
    try:
        with (folder/'native.log').open('w') as log:
            baseline=Monitor.baseline();process=subprocess.Popen([BINARY,mode,FIXTURE,folder/'outputs.bin'],env=env,stdout=log,stderr=log)
            monitor=Monitor(process,folder/'memory.jsonl',0,2**30,baseline=baseline);monitor.thread.start();code=process.wait(timeout=1200)
        monitor.thread.join(timeout=5);record['memory']=monitor.finish()
        record['native_returncode']=code
        if code or record['memory']['guard'] or record['memory']['swap_growth_bytes'] or not record['memory']['monitor_healthy']:
            raise RuntimeError('Gate probe or memory check failed')
        record['cases']=parse((folder/'native.log').read_text(),mode,tuning)
        record['outputs_sha256']=sha256(folder/'outputs.bin')
        size=sum(c['output_elements'] for c in record['cases'])*4 if mode=='check' else 0
        if (folder/'outputs.bin').stat().st_size!=size:raise RuntimeError('Wrong tensor evidence size')
        if verify()!=pin:raise RuntimeError('Engine/probe changed during execution')
        record['status']='passed'
    except BaseException as error:
        record.update(status='failed',error=f'{type(error).__name__}: {error}');raise
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        if monitor:monitor.thread.join(timeout=5)
        (folder/'probe.json').write_text(json.dumps(record,indent=2)+'\n');print(mode,tuning,record['status'],folder,flush=True)
    return folder


def compare(control,candidate):
    try:
        a,b=[json.loads((p/'probe.json').read_text()) for p in (control,candidate)]
        if (a['status']!='passed' or b['status']!='passed' or a['probe']!=b['probe'] or a['mode']!=b['mode']
            or a['metal_environment']['tuning']!='conv-direct' or b['metal_environment']['tuning'] not in TUNINGS):
            raise ValueError('Unmatched gate evidence')
        for p,r in ((control,a),(candidate,b)):
            m=r['memory']
            if (m['swap_growth_bytes']!=0 or m['guard'] or not m['monitor_healthy'] or not m['child_exited']
                or r['metal_environment']['tensor_api']!='on' or r['metal_environment']['profile']
                or r['outputs_sha256']!=sha256(p/'outputs.bin')):raise ValueError('Environment/memory/output provenance failed')
        key=lambda c:(c['rows'],c['route'],c['layout'],c['route_index'])
        if list(map(key,a['cases']))!=list(map(key,b['cases'])):raise ValueError('Coverage differs')
        if a['mode']=='check':
            x,y=[np.fromfile(p/'outputs.bin',dtype=np.uint32) for p in (control,candidate)]
            if len(x)!=sum(c['output_elements'] for c in a['cases']) or not np.array_equal(x,y):
                raise ValueError('Activated/down/bridge or exposed fallback outputs changed bits')
            result={'elements_bit_identical':len(x),'all_CPU_references_passed':True}
        else:
            result={'cases':[dict(rows=x['rows'],route=x['route'],control_us=x['wall_us_per_triplet'],candidate_us=y['wall_us_per_triplet'],
                time_reduction_percent=100*(1-y['wall_us_per_triplet']/x['wall_us_per_triplet'])) for x,y in zip(a['cases'],b['cases'])]}
        result.update(status='passed',control=str(control.relative_to(ROOT)),candidate=str(candidate.relative_to(ROOT)))
    except BaseException as error:
        (candidate/'comparison.json').write_text(json.dumps(dict(status='failed',error=f'{type(error).__name__}: {error}'),indent=2)+'\n');raise
    (candidate/'comparison.json').write_text(json.dumps(result,indent=2)+'\n');return result


def require_check(path,tuning):
    record=json.loads((path/'probe.json').read_text());comparison=json.loads((path/'comparison.json').read_text())
    if (record['mode']!='check' or record['status']!='passed' or comparison['status']!='passed'
        or record['metal_environment']['tuning']!=tuning or record['probe']!=verify()
        or record['outputs_sha256']!=sha256(path/'outputs.bin') or comparison.get('elements_bit_identical',0)<=0):
        raise RuntimeError('A current exact-parity check is required before perf')


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--build',action='store_true');ap.add_argument('--run',action='store_true')
    ap.add_argument('--mode',choices=('check','perf'),default='check');ap.add_argument('--tuning',choices=tuple(TUNINGS),default='gate-up8')
    ap.add_argument('--check-result',type=lambda p:ROOT/p);args=ap.parse_args()
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.build:build()
        if args.run:
            if args.mode=='check':compare(execute('check','conv-direct'),execute('check',args.tuning))
            else:
                if not args.check_result:raise ValueError('--check-result is required for perf')
                require_check(args.check_result,args.tuning)
                a1=execute('perf','conv-direct');b1=execute('perf',args.tuning)
                b2=execute('perf',args.tuning);a2=execute('perf','conv-direct')
                compare(a1,b1);compare(a2,b2)
                result={'status':'passed','order':'ABBA','control_before':str(a1.relative_to(ROOT)),
                    'candidate_first':str(b1.relative_to(ROOT)),'candidate_second':str(b2.relative_to(ROOT)),
                    'control_after':str(a2.relative_to(ROOT)),'check':str(args.check_result.relative_to(ROOT))}
                (b2/'abba.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)


if __name__=='__main__':main()
