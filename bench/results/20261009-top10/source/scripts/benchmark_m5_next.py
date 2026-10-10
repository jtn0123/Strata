#!/usr/bin/env python3
"""Run one independently gated next experiment with fresh bracketing controls."""
import argparse
import fcntl
import json
from pathlib import Path
import time

from benchmark_m5 import execute, plan
from check_memory import assert_no_model_server, snapshot
from engines import ROOT, verify_engine
from metal_environment import configure
from validate_offline import require_pass


def output_signatures(record):
    result = {}
    for c in record['cases']:
        key=('fresh',c['workload'],c['prompt_sha256'],c['repeat'])
        if key in result: raise ValueError('Duplicate output case')
        result[key]=(c['response']['generated_token_ids'],c['response']['text'])
    for c in record['cached_cases']:
        if c['warmup']: continue
        key=('cached',c['history_budget'],c['prompt_sha256'],c['repeat'])
        if key in result: raise ValueError('Duplicate cached output case')
        result[key]=(c['token_ids'],c['text'])
    if not result: raise ValueError('Missing model output evidence')
    return result


def finish(folder):
    path=folder/'comparison.json';record=json.loads(path.read_text())
    runs=[json.loads((ROOT/'bench/results'/r['run_id']/'result.json').read_text()) for r in record['runs']]
    reference=output_signatures(runs[0]);matched=[]
    try:
        for r in runs:
            if output_signatures(r)!=reference: raise ValueError('Fresh or cached model output tokens/text changed')
            matched.append(r['run_id'])
        record['output_parity']={'passed':True,'runs':matched,'cases_per_run':len(reference)}
    except BaseException as error:
        record.update(status='failed',error=str(error),output_parity={'passed':False,'matched_runs':matched})
        path.write_text(json.dumps(record,indent=2)+'\n');raise
    candidate=record['experiment']['candidates'][0]
    writing=[r for r in record['summary'] if not r['cached'] and r['workload'] in ('code','prose')]
    winning=[r for r in writing if r['vs_control'][candidate]['generation_increase_percent']>=1
             and r['vs_control'][candidate]['total_time_reduction_percent']>=1
             and r['vs_control'][candidate]['generation_increase_percent']>abs(r['control_drift']['generation_increase_percent'])]
    record['decision']={'measured_speed_candidate':len(winning)>=2,
        'winning_real_workloads':[r['workload'] for r in winning],
        'rule':'At least 1% TPS and total-reply improvement on two real workloads, above bracket TPS drift; exact tested output parity and zero new swap.'}
    path.write_text(json.dumps(record,indent=2)+'\n')
    lines=['# Next M5 experiment: '+record['experiment']['id'],'',
        'Fresh bracketing controls; 256 output tokens per fresh response. These percentages use this suite only.',
        'All tested fresh and cached token IDs and text match the control. Cached fixtures are separate.', '',
        '| Workload | Control TPS | Candidate TPS | TPS gain | Reply quicker | Control drift |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    control=record['experiment']['control']
    for r in record['summary']:
        d=r['vs_control'][candidate]
        lines.append(f"| {r['workload']}/{r['input_budget']} | {r['profiles'][control]['generation_tok_s']:.3f} | {r['profiles'][candidate]['generation_tok_s']:.3f} | {d['generation_increase_percent']:+.2f}% | {d['total_time_reduction_percent']:+.2f}% | {r['control_drift']['generation_increase_percent']:+.2f}% |")
    lines+=['',f"Passed {sum(len(r['checks']) for r in runs)} answer/cache checks; compared {len(reference)*len(runs)} fresh/cached outputs. Zero new swap.",
            f"Speed acceptance: {record['decision']['measured_speed_candidate']}. Default launchers remain unchanged.",
            '', '[Raw evidence](comparison.json)']
    (folder/'REPORT.md').write_text('\n'.join(lines)+'\n')
    return record


def wait_for_headroom():
    required=json.loads((ROOT/'config/m5_future_plan.json').read_text())['comparison']['minimum_available_before_full_model_bytes']
    started=time.monotonic();samples=[]
    while True:
        assert_no_model_server();info=snapshot()
        samples.append({'elapsed_s':time.monotonic()-started,'available_bytes':info['memory']['available'],
                        'swap_used_bytes':info['swap']['used']})
        if info['memory']['available']>=required:
            return {'required_bytes':required,'samples':samples}
        if time.monotonic()-started>=90: raise RuntimeError('Headroom did not settle within 90 seconds; model launch held')
        print('Waiting for macOS to release model memory:',round(info['memory']['available']/2**30,2),'GiB available',flush=True)
        time.sleep(2)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--engine',required=True);ap.add_argument('--candidate',required=True)
    ap.add_argument('--name',required=True);ap.add_argument('--repeats',type=int,default=3)
    ap.add_argument('--resume',type=Path)
    ap.add_argument('--run',action='store_true');args=ap.parse_args()
    if args.repeats<2: ap.error('Use at least two repeats per pass')
    configure({},args.engine,'on','conv-direct');configure({},args.engine,'on',args.candidate)
    spec={'id':args.name,'engine':args.engine,'depth':3,'axis':'m5_tuning','control':'conv-direct',
          'candidates':[args.candidate],'predict':256}
    print('Plan:',plan(spec),'on',args.engine,'; 256 fresh output tokens',flush=True)
    if not args.run: return
    require_pass();verify_engine(args.engine)
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        folder=execute(spec,args.repeats,resume=args.resume,before_pass=wait_for_headroom);finish(folder)
        print('Validated model output parity:',folder/'REPORT.md',flush=True)


if __name__=='__main__': main()
