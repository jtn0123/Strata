#!/usr/bin/env python3
"""Small-model first-read, CPU/grammar sampling, and ready-output overhead checks."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
import statistics
import subprocess

from benchmark import Monitor
from check_memory import assert_no_model_server, snapshot
from engines import ROOT, sha256, verify_engine
from lab import model_path
from metal_environment import configure


def parse(text, test):
    markers = {'first_read':'sampling view first-read test PASSED',
               'common':'sampling view common test PASSED',
               'read_cost':'sampling view read-cost test PASSED'}
    if text.count(markers[test]) != 1 or 'skipping test' in text or 'GGML_ASSERT' in text:
        raise ValueError('Missing native sampling completion evidence')
    tokens = [list(map(int,line.split()[1:])) for line in text.splitlines() if line.startswith('SAMPLING_COMMON_TOKEN ')]
    costs = [line.split()[1:] for line in text.splitlines() if line.startswith('SAMPLING_READ_COST ')]
    if test == 'common' and (len(tokens) != 18 or {(m,i) for m,i,t in tokens} != {(m,i) for m in range(6) for i in range(3)}):
        raise ValueError('Incomplete CPU or grammar sampling inventory')
    if test == 'read_cost':
        if len(costs) != 16 or {(int(r),int(v)) for r,v,n,u in costs} != {(r,v) for r in range(8) for v in (0,1)}:
            raise ValueError('Incomplete paired getter timing inventory')
        if any(int(n) != 200000 or float(u) <= 0 for r,v,n,u in costs): raise ValueError('Invalid timing samples')
    return {'tokens':tokens,'costs':costs}


def execute(test, tuning, model, pin):
    assert_no_model_server()
    if snapshot()['memory']['available'] < 8*2**30: raise RuntimeError('Small-model headroom unavailable')
    binary=ROOT/pin['directory']/'build/bin/test-backend-sampler'
    env,flags=configure(os.environ,'m5-sampling','on',tuning)
    folder=ROOT/'bench/features'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-m5-sampling-'+test+'-'+tuning)
    folder.mkdir()
    record={'status':'running','test':test,'engine':pin,'tester_sha256':sha256(binary),
            'model':model,'metal_environment':flags,'models_loaded':True,'scope':'Small GPU model; CPU overhead is not model TPS.'}
    process=monitor=None
    try:
        with (folder/'native.log').open('w') as log:
            baseline=Monitor.baseline()
            process=subprocess.Popen([binary,'--model',model['path'],'--device','gpu',
                                      '--test','test_sampling_view_'+test],env=env,stdout=log,stderr=log)
            monitor=Monitor(process,folder/'memory.jsonl',0,2**30,baseline=baseline);monitor.thread.start()
            code=process.wait(timeout=300)
        monitor.thread.join(timeout=5);record['memory']=monitor.finish()
        if code or record['memory']['guard'] or record['memory']['swap_growth_bytes'] or not record['memory']['monitor_healthy']:
            raise RuntimeError('Native sampling run or memory guard failed')
        record.update(parse((folder/'native.log').read_text(),test))
        if verify_engine('m5-sampling')!=pin or sha256(binary)!=record['tester_sha256']: raise RuntimeError('Native provenance changed')
        record['status']='passed'
    except BaseException as error:
        record.update(status='failed',error=f'{type(error).__name__}: {error}');raise
    finally:
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill();process.wait()
        if monitor: monitor.thread.join(timeout=5)
        (folder/'checks.json').write_text(json.dumps(record,indent=2)+'\n')
        print(test,tuning,record['status'],folder,flush=True)
    return folder,record


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',action='store_true');args=ap.parse_args()
    if not args.run: print('Prepared; --run required for small-model GPU checks.');return
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        pin=verify_engine('m5-sampling');path=model_path('small')
        expected=json.loads((ROOT/'config/models.json').read_text())['small']['files'][0]
        model={'path':str(path),'size_bytes':path.stat().st_size,'sha256':sha256(path)}
        if model['size_bytes']!=expected['size_bytes'] or model['sha256']!=expected['sha256']: raise RuntimeError('Small model hash mismatch')
        runs=[execute(test,tuning,model,pin) for test in ('first_read','common') for tuning in ('conv-direct','sampling-view')]
        if runs[2][1]['tokens']!=runs[3][1]['tokens']: raise RuntimeError('CPU/grammar token outputs changed')
        cost_folder,cost=execute('read_cost','conv-direct',model,pin);runs.append((cost_folder,cost))
        medians={str(v):statistics.median(float(u) for r,w,n,u in cost['costs'] if int(w)==v) for v in (0,1)}
        report={'status':'passed','runs':[str(p.relative_to(ROOT)) for p,r in runs],
                'exact_common_token_parity':True,'ready_getter_us':medians,
                'saved_us_per_output_row':medians['0']-medians['1'],
                'note':'Already-ready retrieval overhead only; does not measure active GPU wait latency or model TPS.'}
        (cost_folder/'comparison.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)


if __name__=='__main__': main()
