#!/usr/bin/env python3
"""Qualify all-pool ranking removal on unchanged Metal math before any model edit."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import math
import os
import subprocess
from pathlib import Path
from benchmark import Monitor
from check_memory import assert_no_model_server
from engines import ROOT, sha256, verify_engine
from metal_environment import configure
from validate_offline import require_pass

SOURCE = ROOT/'native/m5_qsa_probe.cpp'
WORK = ROOT/'bench/runtime/m5-qsa'
BINARY = WORK/'qsa-probe'
RESULTS = ROOT/'bench/results/20261009-next-speed-pass/qsa'

def pins():
    return dict(engine=verify_engine('m5-copy'), source_sha256=sha256(SOURCE), runner_sha256=sha256(__file__),
                dependencies={n:sha256(ROOT/'scripts'/n) for n in ('benchmark.py','engines.py','metal_environment.py','check_memory.py','validate_offline.py')})

def inventory(mode):
    values = [dict(pools=p,tokens=t,kind='finite') for p in (64,128,512,576) for t in ((1,4,512) if mode=='perf' else (1,2,3,4,31,32,33,128,512))]
    if mode=='check':
        values += [dict(pools=64,tokens=t,kind=k) for k in ('zeros','ties','signed-zero','permuted','subnormal','wide','inf','nan','injected','masked-nan','mixed-wide','restricted-mask','two-groups') for t in (1,4,32)]
        values += [dict(pools=64,tokens=t,kind=k) for k in ('sparse0','sparse1','sparse2','sparse62','sparse63') for t in (1,4,8)]
        values += [dict(pools=p,tokens=4,kind=k) for p in (192,256,320,384,448,512) for k in ('injected','masked-nan')]
    return values

def parse(text,scope,mode):
    def markers(name):
        return [json.loads(line[len(name)+1:]) for line in text.splitlines() if line.startswith(name+' ')]
    rows, done = markers('M5_QSA_CASE'), markers('M5_QSA_DONE')
    expected = inventory(mode)
    if done != [dict(mode=mode,scope=scope,cases=len(expected),models_loaded=False)] or len(rows)!=len(expected) or 'M5_QSA_ERROR' in text:
        raise ValueError('Incomplete or failed QSA qualification')
    for row,wanted in zip(rows,expected):
        if any(row[k]!=v for k,v in wanted.items()) or row['identity']!=(scope=='identity' and wanted['pools']<=512):
            raise ValueError('QSA fixture or fallback changed')
        if not all(row[k] for k in ('live_binary','scatter_in_bounds','inputs_preserved','all_nodes_metal')) or row['scheduler_splits']!=1:
            raise ValueError('QSA safety or preservation failed')
        if mode=='check' and not (row['cpu_mask_reference'] and row['pool_score_pairing']):
            raise ValueError('Integer reference or paired score/member proof missing')
        if mode=='perf' and (len(row['samples_us'])!=7 or any(not math.isfinite(v) or v<=0 for v in row['samples_us']) or row['median_us']!=sorted(row['samples_us'])[3]):
            raise ValueError('Incomplete sustained timings')
    return rows

def execute(scope,mode,receipt):
    assert_no_model_server()
    folder=RESULTS/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+mode+'-'+scope);folder.mkdir()
    record=dict(status='running',scope=scope,mode=mode,probe=receipt)
    process=monitor=None
    try:
        if pins()!={k:receipt[k] for k in pins()} or sha256(BINARY)!=receipt['binary_sha256']:
            raise ValueError('Probe provenance changed')
        env,flags=configure(dict(os.environ),'m5-copy','on','conv-direct');record['metal_environment']=flags
        with (folder/'native.log').open('w') as log:
            baseline=Monitor.baseline();process=subprocess.Popen([str(BINARY),mode,str(folder/'outputs.jsonl'),scope],stdout=log,stderr=log,env=env)
            monitor=Monitor(process,folder/'memory.jsonl',0,1024**3,baseline=baseline);monitor.thread.start();code=process.wait(timeout=900)
        record['memory']=monitor.finish();m=record['memory'];record['native_returncode']=code
        if code or m['swap_growth_bytes'] or m['guard'] or not m['monitor_healthy'] or not m['child_exited']:
            raise ValueError('QSA probe or resource guard failed')
        record.update(cases=parse((folder/'native.log').read_text(),scope,mode),status='passed')
        record.update(native_log_sha256=sha256(folder/'native.log'),evidence_sha256=sha256(folder/'outputs.jsonl'))
        if pins()!={k:receipt[k] for k in pins()}: raise ValueError('Source changed during run')
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
    if not args.run:print('Prepared exact QSA component qualification; no model edit/load.');return
    require_pass();RESULTS.mkdir(parents=True,exist_ok=True)
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);assert_no_model_server();before=pins();native=ROOT/before['engine']['directory'];WORK.mkdir(parents=True,exist_ok=True)
        command=['/usr/bin/c++','-O3','-ffp-contract=off','-std=gnu++17','-arch','arm64','-I'+str(native/'ggml/include'),'-I'+str(native/'vendor'),str(SOURCE),'-o',str(BINARY),'-Wl,-rpath,'+str(native/'build/bin'),*[str(native/'build/bin'/n) for n in ('libggml.0.26.0.dylib','libggml-base.0.26.0.dylib')]]
        with (WORK/'build.log').open('w') as log:subprocess.run(command,stdout=log,stderr=log,check=True)
        receipt=dict(**before,binary_sha256=sha256(BINARY),command=command);(WORK/'build.json').write_text(json.dumps(receipt,indent=2)+'\n')
        checked=[execute(s,'check',receipt) for s in ('control','identity')]
        for a,b in zip(checked[0][0]['cases'],checked[1][0]['cases']):
            if any(a[k]!=b[k] for k in ('id','mask_sha256','score_sha256','input_sha256','mask_elements')):raise ValueError('Exact mask or score/cache input parity failed')
        timed=[execute(s,'perf',receipt) for s in ('control','identity','identity','control')]
        rows=[]
        for i,a in enumerate(timed[0][0]['cases']):
            values=[r['cases'][i] for r,_ in timed]
            if any(any(r[k]!=a[k] for k in ('id','mask_sha256','score_sha256','input_sha256')) for r in values):raise ValueError('Timed math changed')
            control=(values[0]['median_us']+values[3]['median_us'])/2;candidate=(values[1]['median_us']+values[2]['median_us'])/2
            gain=100*(1-candidate/control);drift=100*abs(values[3]['median_us']/values[0]['median_us']-1)
            rows.append(dict(id=a['id'],control_us=control,candidate_us=candidate,time_reduction_percent=gain,control_drift_percent=drift,qualifies=a['pools']<=512 and gain>=3 and gain>2*drift))
        result=dict(status='passed',checks=[str(p.relative_to(ROOT)) for _,p in checked],runs=[str(p.relative_to(ROOT)) for _,p in timed],rows=rows,models_loaded=False)
        (RESULTS/'comparison.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(rows,indent=2),flush=True)

if __name__=='__main__':main()
