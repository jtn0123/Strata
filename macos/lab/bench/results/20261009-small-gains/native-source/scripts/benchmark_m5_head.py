#!/usr/bin/env python3
"""Single-token Q5_K full-vocabulary head correctness and bracketed operator timing."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import math
import os
from pathlib import Path
import re
import subprocess

from benchmark import Monitor
from check_memory import assert_no_model_server
from engines import ROOT, sha256, verify_engine
from metal_environment import configure
from validate_offline import require_pass

ENGINE='m5-head'
WORK=ROOT/'bench/runtime/m5-head'
SOURCE=ROOT/'native/m5_head_probe.cpp'
BINARY=WORK/'head-probe'
TUNINGS={'head2':2,'head4':4}
M=248320
DEPENDENCIES=('benchmark.py','check_memory.py','engines.py','metal_environment.py','validate_offline.py')


def inventory(mode):
    base=[dict(id=x,rows=1,k=2560,m=M,eligible=True) for x in
          ('mixed','alternating','one-hot','zeros','wide','cutoff-ties','dense-view')]
    if mode=='perf': return base[:2]
    return base+[
        dict(id='rows2',rows=2,k=2560,m=M,eligible=False),
        dict(id='rows4',rows=4,k=2560,m=M,eligible=False),
        dict(id='near-k',rows=1,k=2304,m=M,eligible=False),
        dict(id='near-m',rows=1,k=2560,m=M-2,eligible=False),
        *[dict(id=x,rows=1,k=2560,m=M,eligible=False) for x in
          ('input-padded','input-offset','weight-view','wrong-name','weight-padded')]]


def dependencies():
    return {name:sha256(ROOT/'scripts'/name) for name in DEPENDENCIES}


def build():
    require_pass();assert_no_model_server();pin=verify_engine(ENGINE)
    native=ROOT/pin['directory'];WORK.mkdir(parents=True,exist_ok=True)
    command=['/usr/bin/c++','-O3','-ffp-contract=off','-std=gnu++17','-arch','arm64',
             '-I'+str(native/'ggml/include'),'-I'+str(native/'vendor'),str(SOURCE),'-o',str(BINARY),
             '-Wl,-rpath,'+str(native/'build/bin'),
             *[str(native/'build/bin'/name) for name in ('libggml.0.26.0.dylib','libggml-base.0.26.0.dylib')]]
    before=dict(engine=pin,source_sha256=sha256(SOURCE),runner_sha256=sha256(__file__),dependencies=dependencies())
    with (WORK/'probe-build.log').open('w') as log:
        subprocess.run(command,stdout=log,stderr=log,check=True)
    if before!=dict(engine=verify_engine(ENGINE),source_sha256=sha256(SOURCE),runner_sha256=sha256(__file__),dependencies=dependencies()):
        raise RuntimeError('Build inputs changed')
    record={**before,'binary_sha256':sha256(BINARY),'command':command}
    (WORK/'probe-build.json').write_text(json.dumps(record,indent=2)+'\n');return record


def verify():
    record=json.loads((WORK/'probe-build.json').read_text())
    if (record['engine']!=verify_engine(ENGINE) or record['source_sha256']!=sha256(SOURCE)
        or record['runner_sha256']!=sha256(__file__) or record['dependencies']!=dependencies()
        or record['binary_sha256']!=sha256(BINARY)):
        raise RuntimeError('Head probe provenance changed')
    return record


def markers(text,name):
    return [json.loads(line[len(name)+1:]) for line in text.splitlines() if line.startswith(name+' ')]


def parse(text,mode,tuning):
    expected=inventory(mode);cases=markers(text,'M5_HEAD_CASE');done=markers(text,'M5_HEAD_DONE')
    if len(done)!=1 or len(cases)!=len(expected) or 'M5_HEAD_ERROR' in text:raise ValueError('Incomplete head evidence')
    d=done[0]
    if (d['mode']!=mode or d['cases']!=len(expected) or d['weights_preserved'] is not True
        or d['max_probe_bytes']!=3*1024**3 or d['expanded_weight_cache'] is not False or d['models_loaded'] is not False):
        raise ValueError('Invalid head completion summary')
    expected_weights=[(False,437043200)]+([(True,480747520)] if mode=='check' else [])
    if len(d['weights'])!=len(expected_weights):raise ValueError('Unexpected weight allocation inventory')
    for w,(padded,nbytes) in zip(d['weights'],expected_weights):
        if (w['padded']!=padded or w['bytes']!=nbytes or w['preserved'] is not True
            or not re.fullmatch('[0-9a-f]{64}',w['sha256'])):raise ValueError('Missing preserved packed weights')
    for c,want in zip(cases,expected):
        if any(c[k]!=v for k,v in want.items()):raise ValueError('Head case inventory changed')
        if (c['elements']!=want['rows']*want['m'] or c['inputs_preserved'] is not True
            or c['all_nodes_metal'] is not True or c['scheduler_splits']!=1 or c['cpu_compute_nodes']!=0
            or c['consumer_chain']!='head-top_k10-gather' or c['graph_buffer_bytes']<=0
            or not 0<c['allocation_bound_bytes']<3*1024**3
            or c['cpu_reference_values']!=(0 if mode=='perf' else c['elements'])):
            raise ValueError('Missing full-logit reference or placement/preservation proof')
        for field in ('output_sha256','input_sha256','weight_sha256'):
            if not re.fullmatch('[0-9a-f]{64}',c[field]):raise ValueError('Invalid digest')
        w=d['weights'][-1] if c['id']=='weight-padded' else d['weights'][0]
        if c['weight_sha256']!=w['sha256']:raise ValueError('Case weight identity differs')
        for field in ('max_absolute_error','max_bound_ratio','cpu_nmse'):
            if not math.isfinite(c[field]) or c[field]<0:raise ValueError('Invalid CPU error metric')
        if c['max_bound_ratio']>=(5e-6 if c['rows']==1 else 2e-4):raise ValueError('CPU reference tolerance failed')
        if len(c['consumers'])!=c['rows']:raise ValueError('Incomplete consumer rows')
        for consumer in c['consumers']:
            if (consumer['tie_safe'] is not True or len(consumer['ids'])!=10 or len(set(consumer['ids']))!=10
                or any(type(i)!=int or not 0<=i<c['m'] for i in consumer['ids'])
                or len(consumer['values'])!=10 or any(not math.isfinite(v) for v in consumer['values'])
                or not 0<=consumer['above_cutoff']<10 or not 1<=consumer['cutoff_ties']<=c['m']
                or consumer['above_cutoff']+consumer['cutoff_ties']<10):
                raise ValueError('Invalid top-k/tie evidence')
        if mode=='perf':
            if (c['pipeline_primed'] is not True or not math.isfinite(c['warmup_us']) or c['warmup_us']<500000 or c['warmup_iterations']<1
                or any(len(c[f])!=7 for f in ('block_us','block_iterations','block_us_per_iteration'))):
                raise ValueError('Insufficient timed blocks/warmup')
            for us,n,each in zip(c['block_us'],c['block_iterations'],c['block_us_per_iteration']):
                if not math.isfinite(us) or us<100000 or type(n)!=int or n<8 or not math.isfinite(each) or each<=0 or not math.isclose(each,us/n,rel_tol=1e-12):
                    raise ValueError('Invalid block duration/iteration count')
            if c['median_us']!=sorted(c['block_us_per_iteration'])[3]:raise ValueError('Wrong timing median')
        elif c['pipeline_primed'] or c['block_us'] or c['block_iterations'] or c['block_us_per_iteration'] or c['warmup_us'] or c['median_us']:
            raise ValueError('Correctness run unexpectedly timed')
    init=markers(text,'M5_HEAD_INIT');routes=markers(text,'M5_HEAD_DISPATCH')
    if mode=='perf':
        if init or routes:raise ValueError('Diagnostic logging contaminated performance')
    else:
        nr=TUNINGS.get(tuning,1)
        if init!=[dict(requested_nr0=nr,stock_nr0=1,nsg=2)]:raise ValueError('Wrong effective head startup')
        # Bind each ordinary pipeline-getter dispatch to its current fixture.
        grouped={};current=None
        for line in text.splitlines():
            if line.startswith('M5_HEAD_CASE_BEGIN '):
                current=json.loads(line.split(' ',1)[1])['id']
                if current in grouped:raise ValueError('Repeated case begin')
                grouped[current]=[]
            elif line.startswith('M5_HEAD_DISPATCH '):
                if current is None:raise ValueError('Unattributed head dispatch')
                grouped[current].append(json.loads(line.split(' ',1)[1]))
        if list(grouped)!=[c['id'] for c in expected]:raise ValueError('Missing head case boundaries')
        for c in cases:
            if len(grouped[c['id']])!=1:raise ValueError('Missing/repeated native head dispatch')
            r=grouped[c['id']][0];tensors=r['tensors']
            if (r['requested_nr0']!=nr or r['eligible']!=c['eligible'] or len(tensors)!=3 or r['nsg']<1 or r['nr0']<1
                or [t['type'] for t in tensors]!=['q5_K','f32','f32']
                or [t['ne'] for t in tensors]!=[[c['k'],c['m'],1,1],[c['k'],c['rows'],1,1],[c['m'],c['rows'],1,1]]):
                raise ValueError('Native shape/type/route evidence differs')
            for t in tensors:
                if len(t['nb'])!=4 or any(type(v)!=int or v<=0 for v in t['nb']):raise ValueError('Invalid native strides')
            if c['eligible']:
                kernel='kernel_mul_mv_q5_K_f32'+(f'_m5_head{nr}' if nr!=1 else '')
                if (r['kernel']!=kernel or r['pipeline_key']!=kernel+'_nsg=2_ne12=1_r2=1_r3=1_split=0' or r['nr0']!=nr or r['nsg']!=2
                    or [t['nb'] for t in tensors]!=[[176,1760,437043200,437043200],[4,10240,10240,10240],[4,993280,993280,993280]]
                    or tensors[0]['name']!='output.weight' or tensors[2]['name']!='result_output'
                    or any(t['address_mod16']!=0 or t['view_offset']!=0 for t in tensors)):
                    raise ValueError('Canonical dispatch did not use requested head kernel')
            elif '_m5_head' in r['kernel']:raise ValueError('Head specialization escaped exact guard')
        tied=next(c for c in cases if c['id']=='cutoff-ties')['consumers'][0]
        if tied['above_cutoff']!=8 or tied['cutoff_ties']!=12:raise ValueError('Designed cutoff-tie fixture missing')
        if not any(c['consumers'][0]['cutoff_ties']==1 for c in cases):raise ValueError('No separated-cutoff coverage')
    return cases,d


def load_evidence(folder,record):
    path=folder/'outputs.jsonl'
    if sha256(path)!=record['outputs_sha256']:raise ValueError('Full-logit evidence changed')
    items=[json.loads(line) for line in path.read_text().splitlines()]
    expected=[dict(id=c['id'],elements=c['elements'],sha256=c['output_sha256']) for c in record['cases']] if record['mode']=='check' else []
    if items!=expected:raise ValueError('Full-vocabulary logit digest inventory differs')
    return items


def execute(mode,tuning):
    if tuning not in ('conv-direct',*TUNINGS):raise ValueError('Unknown head tuning')
    require_pass();assert_no_model_server();pin=verify()
    folder=ROOT/'bench/features'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-m5-head-'+mode+'-'+tuning)
    folder.mkdir();env,flags=configure(os.environ,ENGINE,'on',tuning)
    for name in ('GGML_SCHED_DEBUG','GGML_SCHED_DEBUG_REALLOC'):env.pop(name,None)
    if mode=='check':env['GGML_M5_LAB_HEAD_TRACE']='1';flags['variables']['GGML_M5_LAB_HEAD_TRACE']='1'
    record=dict(status='running',probe=pin,mode=mode,metal_environment=flags,models_loaded=False,tps_measured=False,
                scope='Full Q5_K single-token head plus unchanged top-k10/gather consumer. Covers target and helper. Synthetic packed weights; no expanded cache. Normal single-split Metal scheduler; one terminal sync per dependent graph iteration.')
    process=monitor=None
    try:
        with (folder/'native.log').open('w') as log:
            baseline=Monitor.baseline();process=subprocess.Popen([BINARY,mode,folder/'outputs.jsonl'],env=env,stdout=log,stderr=log)
            monitor=Monitor(process,folder/'memory.jsonl',0,1024**3,baseline=baseline);monitor.thread.start()
            code=process.wait(timeout=1800)
        record['native_returncode']=code;record['memory']=monitor.finish();m=record['memory']
        if (code or m['guard'] or m['swap_growth_bytes'] or not m['monitor_healthy'] or not m['child_exited'] or m['peak_rss_bytes']>3*1024**3):
            raise RuntimeError('Native head probe or memory gate failed')
        record['cases'],record['done']=parse((folder/'native.log').read_text(),mode,tuning)
        record['native_log_sha256']=sha256(folder/'native.log');record['outputs_sha256']=sha256(folder/'outputs.jsonl')
        load_evidence(folder,record)
        if verify()!=pin:raise RuntimeError('Probe changed during run')
        require_pass();assert_no_model_server();record['status']='passed'
    except BaseException as error:
        record.update(status='failed',error=f'{type(error).__name__}: {error}');raise
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        if monitor:
            monitor.thread.join(timeout=5)
            if 'memory' not in record:record['memory']=monitor.finish()
        (folder/'probe.json').write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
        print(mode,tuning,record['status'],folder,flush=True)
    return folder


def validated(folder):
    record=json.loads((folder/'probe.json').read_text());m=record['memory'];flags=record['metal_environment']
    if (record['status']!='passed' or record['probe']!=verify() or m['guard'] or m['swap_growth_bytes']
        or not m['monitor_healthy'] or not m['child_exited'] or m['peak_rss_bytes']>3*1024**3
        or flags['tensor_api']!='on' or flags['profile'] or sha256(folder/'native.log')!=record['native_log_sha256']):
        raise ValueError('Head receipt/provenance/memory invalid')
    cases,done=parse((folder/'native.log').read_text(),record['mode'],flags['tuning'])
    if cases!=record['cases'] or done!=record['done']:raise ValueError('Parsed native record changed')
    load_evidence(folder,record);return record


def compare(control,candidate,write=True):
    a,b=[validated(p) for p in (control,candidate)]
    if (a['mode']!=b['mode'] or a['metal_environment']['tuning']!='conv-direct'
        or b['metal_environment']['tuning'] not in TUNINGS or a['probe']!=b['probe']):raise ValueError('Unmatched head cases')
    for x,y in zip(a['cases'],b['cases']):
        if (any(x[f]!=y[f] for f in ('id','rows','k','m','eligible','input_sha256','weight_sha256'))):
            raise ValueError('Head fixture identity differs')
    if a['mode']=='check':
        route_key=lambda r:(r['kernel'],r['pipeline_key'],r['nr0'],r['nsg'],r['tensors'])
        ar=markers((control/'native.log').read_text(),'M5_HEAD_DISPATCH')
        br=markers((candidate/'native.log').read_text(),'M5_HEAD_DISPATCH')
        for c,x,y in zip(a['cases'],ar,br):
            if not c['eligible'] and route_key(x)!=route_key(y):raise ValueError('Fallback pipeline or layout changed')
        if load_evidence(control,a)!=load_evidence(candidate,b):raise ValueError('Full-vocabulary logits changed bits')
        result=dict(elements_bit_identical=sum(c['elements'] for c in a['cases']),all_CPU_references_passed=True,tie_semantics_preserved=True)
    else:
        result=dict(cases=[dict(id=x['id'],control_us=x['median_us'],candidate_us=y['median_us'],
                    time_reduction_percent=100*(1-y['median_us']/x['median_us'])) for x,y in zip(a['cases'],b['cases'])])
    result.update(status='passed',control=str(control.relative_to(ROOT)),candidate=str(candidate.relative_to(ROOT)),tps_gain_measured=False)
    if write:(candidate/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def require_check(folder,tuning):
    record=validated(folder);old=json.loads((folder/'comparison.json').read_text())
    if record['mode']!='check' or record['metal_environment']['tuning']!=tuning:raise ValueError('Wrong prerequisite check')
    if compare(ROOT/old['control'],folder,False)!=old:raise ValueError('Current exact-parity check is required')


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--build',action='store_true');ap.add_argument('--run',action='store_true')
    ap.add_argument('--mode',choices=('check','perf'),default='check');ap.add_argument('--tuning',choices=tuple(TUNINGS),default='head2')
    ap.add_argument('--check-result',type=lambda p:ROOT/p);args=ap.parse_args()
    if not args.build and not args.run:print('Prepared Q5_K head probe; no execution.');return
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.build:build()
        if args.run:
            if args.mode=='check':compare(execute('check','conv-direct'),execute('check',args.tuning))
            else:
                if not args.check_result:raise ValueError('--check-result required before perf')
                require_check(args.check_result,args.tuning)
                a1=execute('perf','conv-direct');b1=execute('perf',args.tuning)
                b2=execute('perf',args.tuning);a2=execute('perf','conv-direct')
                first=compare(a1,b1);last=compare(a2,b2);summaries=[]
                for x,y in zip(first['cases'],last['cases']):
                    gain=100*(1-(x['candidate_us']+y['candidate_us'])/(x['control_us']+y['control_us']))
                    drift=100*(y['control_us']/x['control_us']-1)
                    summaries.append(dict(id=x['id'],time_reduction_percent=gain,control_drift_percent=drift,
                        first_pair_percent=x['time_reduction_percent'],last_pair_percent=y['time_reduction_percent']))
                result=dict(status='passed',order='ABBA',control_before=str(a1.relative_to(ROOT)),candidate_first=str(b1.relative_to(ROOT)),
                    candidate_second=str(b2.relative_to(ROOT)),control_after=str(a2.relative_to(ROOT)),check=str(args.check_result.relative_to(ROOT)),
                    cases=summaries,operator_gate_passed=all(c['time_reduction_percent']>=10 and c['first_pair_percent']>=10
                        and c['last_pair_percent']>=10 and abs(c['control_drift_percent'])<5 for c in summaries),
                    model_TPS_measured=False,normal_model_T1_dispatch_proof_required=True)
                (b2/'abba.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)


if __name__=='__main__':main()
