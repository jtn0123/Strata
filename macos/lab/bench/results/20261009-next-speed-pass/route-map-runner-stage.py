#!/usr/bin/env python3
"""Exact complete MoE prompt block screen for adjacent route-map reuse."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import math
import os
import shutil
import subprocess

from benchmark import Monitor
from check_memory import assert_no_model_server
from engines import ROOT, sha256, verify_engine
from metal_environment import configure
from validate_offline import require_pass

SOURCE=ROOT/'native/m5_route_map_probe.cpp'
WORK=ROOT/'bench/runtime/m5-route-map'
RESULTS=ROOT/'bench/results/20261009-next-speed-pass/route-map'

def inventory(mode):
    fixtures=[]
    for rows in ((32,33,64,127,508,512) if mode=='perf' else (31,32,33,64,127,508,512,513)):
        for route in ('uniform','shared','mixed'):
            for stride in ((2048,) if mode=='perf' else (40,2048)):
                fixtures.append(dict(rows=rows,route=route,id_stride_bytes=stride,layout='plain',precision='default'))
    if mode=='check':
        for rows in (33,512):
            for precision in ('all-f32','gate-f32-up-default','gate-default-up-f32'):
                fixtures.append(dict(rows=rows,route='mixed',id_stride_bytes=2048,layout='plain',precision=precision))
            for precision in ('gate-f32-up-default','gate-default-up-f32'):
                fixtures.append(dict(rows=rows,route='mixed',id_stride_bytes=2048,layout='plain',precision=precision,terminal_only=True))
            for layout in ('different-input','different-ids','intervening-gate-scale','activation-unfused'):
                fixtures.append(dict(rows=rows,route='mixed',id_stride_bytes=2048,layout=layout,precision='default'))
    return [dict(x,terminal_only=x.get('terminal_only',False),round=n) for x in fixtures for n in (range(3) if mode=='check' else range(1))]

def pins(engine):
    return dict(engine=verify_engine(engine),source_sha256=sha256(SOURCE),runner_sha256=sha256(__file__),
                dependencies={n:sha256(ROOT/'scripts'/n) for n in ('benchmark.py','engines.py','metal_environment.py','check_memory.py','validate_offline.py')})

def parse(text,mode,scope):
    def markers(name):return [json.loads(x[len(name)+1:]) for x in text.splitlines() if x.startswith(name+' ')]
    rows,done=markers('M5_ROUTE_MAP_CASE'),markers('M5_ROUTE_MAP_DONE')
    wanted=inventory(mode)
    if 'M5_ROUTE_MAP_ERROR' in text or len(done)!=1 or len(rows)!=len(wanted):
        raise ValueError('Incomplete route-map probe')
    end=done[0]
    if (end['mode']!=mode or end['scope']!=scope or end['cases']!=len(wanted)
            or end['models_loaded'] or not end['weights_preserved'] or end['route_source']!='synthetic'):
        raise ValueError('Route-map completion or preservation changed')
    for row,expected in zip(rows,wanted):
        if any(row[k]!=v for k,v in expected.items()) or row['mode']!=mode or row['scope']!=scope:
            raise ValueError('Route-map fixture coverage changed')
        eligible=32<=row['rows']<=512 and row['layout']=='plain'
        target=row['executions']*row['triplets_per_graph'] if scope=='reuse' and eligible else 0
        if row['count_delta']!=target or (scope=='reuse' and not row['counter_available']):
            raise ValueError('Complete eligible reuse/fallback coverage missing')
        if (not all(row[k] for k in ('inputs_preserved','ids_preserved','all_nodes_metal'))
                or row['scheduler_splits']!=1 or row['cpu_compute_nodes'] or row['evaluation_callbacks']
                or not row['outputs'] or not all(o['finite'] for o in row['outputs'])
                or row['allocation_estimate_bytes']>=3*1024**3 or row['triplets_per_graph']!=(2 if mode=='perf' else 1)):
            raise ValueError('Placement, preservation or allocation checks failed')
        if mode=='perf':
            samples=row['ns_samples']
            if (len(samples)!=7 or any(not math.isfinite(x) or x<=0 for x in samples)
                    or row['median_ns']!=sorted(samples)[3] or row['warmup_ns']<500000000
                    or not row['pipeline_primed'] or len(row['block_iterations'])!=7
                    or len(row['block_ns'])!=7
                    or any(x<8 for x in row['block_iterations']) or any(x<100000000 for x in row['block_ns'])
                    or any(v!=n/i for v,n,i in zip(samples,row['block_ns'],row['block_iterations']))):
                raise ValueError('Sustained complete-block timings missing')
    return rows

def comparable(row):
    return {k:row[k] for k in ('id','round','outputs','input_sha256','ids_sha256','coefficients_sha256','weights','triplets_per_graph')}

def execute(scope,mode,receipt):
    assert_no_model_server();folder=RESULTS/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+mode+'-'+scope);folder.mkdir()
    engine='m5-route-map' if scope=='reuse' else 'm5-copy'
    binary=WORK/(scope+'-probe');process=monitor=None
    record=dict(status='running',scope=scope,mode=mode,probe=receipt)
    try:
        if pins(engine)!={k:receipt[k] for k in pins(engine)} or sha256(binary)!=receipt['binary_sha256']:
            raise ValueError('Probe closure changed')
        env,flags=configure(dict(os.environ),engine,'on','route-map' if scope=='reuse' else 'conv-direct');record['metal_environment']=flags
        with (folder/'native.log').open('w') as log:
            baseline=Monitor.baseline();process=subprocess.Popen([str(binary),mode,str(folder/'outputs.jsonl'),scope],stdout=log,stderr=log,env=env)
            monitor=Monitor(process,folder/'memory.jsonl',0,1024**3,baseline=baseline);monitor.thread.start();code=process.wait(timeout=900)
        record['memory']=monitor.finish();m=record['memory'];record['native_returncode']=code
        if code or m['swap_growth_bytes'] or m['guard'] or not m['monitor_healthy'] or not m['child_exited']:
            raise ValueError('Probe or resource guard failed')
        rows=parse((folder/'native.log').read_text(),mode,scope)
        evidence=[json.loads(x) for x in (folder/'outputs.jsonl').read_text().splitlines()]
        if evidence[:-1]!=rows:raise ValueError('Native log/evidence disagree')
        record.update(status='passed',cases=rows,native_log_sha256=sha256(folder/'native.log'),evidence_sha256=sha256(folder/'outputs.jsonl'))
        if pins(engine)!={k:receipt[k] for k in pins(engine)}:raise ValueError('Source changed during probe')
    except BaseException as error:
        record.update(status='failed',error=f'{type(error).__name__}: {error}');raise
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        if monitor and 'memory' not in record:record['memory']=monitor.finish()
        (folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(scope,mode,record['status'],folder,flush=True)
    return record,folder

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',action='store_true');args=ap.parse_args()
    if not args.run:print('Prepared full prompt-block screen; no models loaded.');return
    require_pass();RESULTS.mkdir(parents=True,exist_ok=True);WORK.mkdir(parents=True,exist_ok=True)
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);assert_no_model_server()
        receipts={}
        for scope,engine in (('control','m5-copy'),('reuse','m5-route-map')):
            before=pins(engine);native=ROOT/before['engine']['directory'];binary=WORK/(scope+'-probe')
            command=['/usr/bin/c++','-O3','-ffp-contract=off','-std=gnu++17','-arch','arm64','-I'+str(native/'ggml/include'),'-I'+str(native/'vendor'),str(SOURCE),'-o',str(binary),'-Wl,-rpath,'+str(native/'build/bin'),*[str(native/'build/bin'/n) for n in ('libggml.0.26.0.dylib','libggml-base.0.26.0.dylib')]]
            with (WORK/(scope+'-build.log')).open('w') as log:subprocess.run(command,stdout=log,stderr=log,check=True)
            receipts[scope]=dict(**before,binary_sha256=sha256(binary),command=command)
        archive=RESULTS/'source';archive.mkdir()
        for path in (SOURCE,ROOT/'scripts/benchmark_m5_route_map.py',*[ROOT/'scripts'/n for n in receipts['control']['dependencies']],ROOT/'config/m5_route_map_experiment.json',ROOT/'patches/mtp-m5-route-map.patch'):
            dest=archive/path.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
        (WORK/'build.json').write_text(json.dumps(receipts,indent=2)+'\n')
        (RESULTS/'plan.json').write_text(json.dumps(dict(status='preregistered_before_gpu',source=receipts,check_inventory=inventory('check'),perf_inventory=inventory('perf'),gate='At least3% complete-block time reduction above twice absolute control drift for BOTH T508/512 uniform synthetic routes; unchanged fallback, exact all projection/residual bytes, no new swap. Component results are prompt-only, not model TPS.'),indent=2)+'\n')
        checked=[execute(s,'check',receipts[s]) for s in ('control','reuse')]
        if [comparable(x) for x in checked[0][0]['cases']] != [comparable(x) for x in checked[1][0]['cases']]:raise ValueError('Complete projection/residual bits changed')
        timed=[execute(s,'perf',receipts[s]) for s in ('control','reuse','reuse','control')]
        rows=[]
        for i,first in enumerate(timed[0][0]['cases']):
            values=[r['cases'][i] for r,_ in timed]
            if any(comparable(x)!=comparable(first) for x in values):raise ValueError('Timed complete-block math changed')
            a=(values[0]['median_ns']+values[3]['median_ns'])/2;b=(values[1]['median_ns']+values[2]['median_ns'])/2
            gain=100*(1-b/a);drift=100*abs(values[3]['median_ns']/values[0]['median_ns']-1)
            rows.append(dict(id=first['id'],tokens=first['rows'],route=first['route'],triplets_per_graph=first['triplets_per_graph'],control_ms=a/1e6,candidate_ms=b/1e6,time_reduction_percent=gain,control_drift_percent=drift,qualifies=gain>=3 and gain>2*drift))
        real=[x for x in rows if x['tokens'] in (508,512) and x['route']=='uniform']
        result=dict(status='passed',checks=[str(p.relative_to(ROOT)) for _,p in checked],runs=[str(p.relative_to(ROOT)) for _,p in timed],rows=rows,qualifies_for_model_trial=len(real)==2 and all(x['qualifies'] for x in real),models_loaded=False,route_source='synthetic')
        (RESULTS/'comparison.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(rows,indent=2),flush=True)

if __name__=='__main__':main()
