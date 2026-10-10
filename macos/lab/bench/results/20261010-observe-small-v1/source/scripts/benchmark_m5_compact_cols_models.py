#!/usr/bin/env python3
"""Matched original-engine control for compact expert tile scheduling."""
import argparse
import fcntl
import json
import shutil
from pathlib import Path

from benchmark_m5 import execute
from benchmark_m5_next import finish, output_signatures, wait_for_headroom
from benchmark_m5_encoder_models import adoption
from benchmark_m5_compact_cols import RESULTS, SOURCE, WORK, parse, markers, pins, compare_exact, summarize
from engines import ROOT, sha256, verify_engine
from validate_offline import require_pass, fingerprint

BUNDLE = ROOT/'bench/results/20261009-compact-tiles'

def prerequisites():
    comparison = json.loads((RESULTS/'comparison.json').read_text())
    receipts = json.loads((WORK/'build.json').read_text())
    plan = json.loads((RESULTS/'plan.json').read_text())
    if comparison['status'] != 'passed' or not comparison['qualifies_for_model_trial']:
        raise ValueError('Qualified component comparison required')
    for scope, engine in (('control','m5-copy'),('compact','m5-compact-cols')):
        current = pins(engine)
        saved = receipts[scope]
        if current != {key:saved[key] for key in current} or sha256(WORK/(scope+'-probe')) != saved['binary_sha256']:
            raise ValueError('Component/native source or binary changed')
    for name, expected in plan['archive'].items():
        if sha256(RESULTS/'source'/name) != expected or sha256(ROOT/name) != expected:
            raise ValueError('Component source archive changed: '+name)
    paths = comparison['checks'] + comparison['runs']
    order = [('control','check'),('compact','check'),('control','perf'),('compact','perf'),('compact','perf'),('control','perf')]
    if len(paths) != len(order):
        raise ValueError('Complete component bracket required')
    records = []
    for path,(scope,mode) in zip(paths,order):
        folder = ROOT/path
        record = json.loads((folder/'result.json').read_text())
        text = (folder/'native.log').read_text()
        if (record['status'] != 'passed' or record['scope'] != scope or record['mode'] != mode
                or record['probe'] != receipts[scope] or record['memory']['swap_growth_bytes']
                or record['memory']['guard'] or not record['memory']['monitor_healthy']
                or sha256(folder/'native.log') != record['native_log_sha256']
                or sha256(folder/'outputs.jsonl') != record['evidence_sha256']
                or parse(text,mode,scope) != record['cases']):
            raise ValueError('Component evidence incomplete or changed')
        evidence = [json.loads(line) for line in (folder/'outputs.jsonl').read_text().splitlines()]
        if evidence != record['cases']+markers(text,'M5_COMPACT_DONE'):
            raise ValueError('Component raw artifacts disagree')
        records.append((record,folder))
    compare_exact(records[0][0]['cases'],records[1][0]['cases'])
    calculated = summarize(records[2:])
    calculated['checks'] = paths[:2]
    if calculated != comparison:
        raise ValueError('Component aggregate disagrees with raw bracket')
    return comparison


def dispatch(text, candidate):
    records = [json.loads(line.split('M5_COMPACT_INPUT ',1)[1]) for line in text.splitlines() if 'M5_COMPACT_INPUT ' in line]
    if len(records) != int(candidate):
        raise ValueError('Eligible compact encoding marker missing or unexpected')
    for row in records:
        if (set(row) != {'rows','k','m','experts','selected','stage'} or row['stage'] != 'encoded'
                or any(type(row[key]) is not int for key in ('rows','k','m','experts','selected'))
                or not 32 <= row['rows'] <= 512 or (row['k'],row['m']) not in ((2560,640),(640,2560))
                or row['experts'] != 512 or row['selected'] != 10):
            raise ValueError('Invalid compact encoding marker')
    return dict(markers=records, actual_eligible_encoding=candidate, shader_frequency_proven=False)


def latency_decision(summary):
    winning = []
    real = [row for row in summary if not row['cached'] and row['workload'] in ('code','prose')]
    if len(real) != 2 or {row['workload'] for row in real} != {'code','prose'}:
        raise ValueError('Both contextual English tasks required')
    for row in real:
        gain, drift = row['vs_control']['compact-cols'], row['control_drift']
        if (gain['ttft_reduction_percent'] >= 1
                and gain['ttft_reduction_percent'] > 2*abs(drift['ttft_reduction_percent'])
                and gain['total_time_reduction_percent'] > abs(drift['total_time_reduction_percent'])
                and gain['generation_increase_percent'] > -max(1,abs(drift['generation_increase_percent']))):
            winning.append(row['workload'])
    return dict(measured_prompt_latency_candidate=len(winning)==2,winning_real_workloads=winning,
                rule='At least1% first-token improvement on BOTH contextual English tasks above twice own TTFT drift; whole reply improves above own drift, no material TPS regression, exact tested outputs and zero new swap. This is a latency decision, not a decode-TPS gain.')

def signatures(record):
    result = output_signatures(record)
    for c in record['warmups']:
        key = ('warmup',c['workload'],c['prompt_sha256'],c['repeat'])
        if key in result: raise ValueError('Duplicate warmup')
        result[key] = (c['response']['generated_token_ids'],c['response']['text'])
    for c in record['cached_cases']:
        if c['warmup']:
            key = ('cache-warmup',c['history_budget'],c['prompt_sha256'],c['repeat'])
            if key in result: raise ValueError('Duplicate cache warmup')
            result[key] = (c['token_ids'],c['text'])
    return result

def render(record):
    lines = ['# Compact expert tile scheduling: matched model result','',
        'Original m5-copy/conv-direct versus isolated m5-compact-cols/compact-cols. Qwen3.8-Flash-Next Q2_0, shared Q3 helper, mixed placement, eight helper workers, depth3/confidence0, Tensor API on, F16/4K/batch512.','',
        'Practical English scheduler review and incident analysis use complete context from the hashed fixture. Fresh ABBA,256 outputs, excluded warmup plus three repetitions. Cached ledgers are separate.','',
        '| Workload/input | Control TPS | Candidate TPS | TPS change | Reply quicker | First token quicker | TPS drift | Reply drift | TTFT drift |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for row in record['summary']:
        a,b = row['profiles']['conv-direct'],row['profiles']['compact-cols']
        d,f = row['vs_control']['compact-cols'],row['control_drift']
        lines.append(f"| {row['workload']}/{row['input_budget']} | {a['generation_tok_s']:.3f} | {b['generation_tok_s']:.3f} | {d['generation_increase_percent']:+.3f}% | {d['total_time_reduction_percent']:+.3f}% | {d['ttft_reduction_percent']:+.3f}% | {f['generation_increase_percent']:+.3f}% | {f['total_time_reduction_percent']:+.3f}% | {f['ttft_reduction_percent']:+.3f}% |")
    lines += ['', 'General TPS/reply acceptance: '+str(record['decision']['measured_speed_candidate'])+'. '+record['decision']['rule'],
        '', 'Prompt-latency acceptance: '+str(record['latency_decision']['measured_prompt_latency_candidate'])+'. '+record['latency_decision']['rule'],
        '', 'Candidate encoding marker proves one eligible native operation was encoded. It does not measure branch frequency. Exact complete outputs and zero new swap are required; defaults remain unchanged.','', '[Raw comparison](comparison.json).']
    return '\n'.join(lines)+'\n'

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run',action='store_true')
    ap.add_argument('--resume',type=Path)
    args = ap.parse_args()
    spec = dict(id='compact-cols',engine='m5-compact-cols',depth=3,axis='m5_tuning',control='conv-direct',
                candidates=['compact-cols'],predict=256,
                engine_for_value={'conv-direct':'m5-copy','compact-cols':'m5-compact-cols'},
                workloads_file='config/m5_compact_workloads.json',prompts=[])
    if not args.run: print('Prepared:',spec); return
    require_pass()
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        proof = prerequisites()
        source = fingerprint()
        archive = BUNDLE/'columns-model-source'
        archive.mkdir(exist_ok=True)
        if args.resume:
            if json.loads((archive/'pins.json').read_text()) != source:
                raise ValueError('Model benchmark closure changed before resume')
        else:
            for name in source:
                dest=archive/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,dest)
            (archive/'pins.json').write_text(json.dumps(source,indent=2)+'\n')
        reference = None
        receipts = []
        if args.resume:
            prior=json.loads(args.resume.read_text())
            for entry in prior['runs']:
                r=json.loads((ROOT/'bench/results'/entry['run_id']/'result.json').read_text())
                if reference is None: reference=signatures(r)
                if signatures(r)!=reference: raise ValueError('Resume output changed')
                receipts.append(dict(run_id=r['run_id'],**dispatch((ROOT/'bench/results'/r['run_id']/'server.log').read_text(),entry['value']=='compact-cols')))
        def check_pass(record,value):
            nonlocal reference
            if fingerprint()!=source: raise ValueError('Model benchmark closure changed')
            current=signatures(record)
            if reference is None: reference=current
            if current != reference: raise ValueError('Fresh, warmup or cache outputs differ from control')
            receipts.append(dict(run_id=record['run_id'],**dispatch((ROOT/'bench/results'/record['run_id']/'server.log').read_text(),value=='compact-cols')))
        folder=execute(spec,3,resume=args.resume,before_pass=wait_for_headroom,after_pass=check_pass)
        record=finish(folder)
        decision=adoption(record['summary'],'compact-cols')
        decision['rule']='At least1% TPS and reply gain on both English code/prose, each above its own absolute control drift; exact tested outputs and zero new swap.'
        record.update(component_prerequisites=proof,compact_encoding_receipts=receipts,source_pins=source,
                      output_parity_including_warmups=True,decision=decision,latency_decision=latency_decision(record['summary']))
        (folder/'comparison.json').write_text(json.dumps(record,indent=2)+'\n')
        (folder/'REPORT.md').write_text(render(record))
        print('Matched model result:',folder,decision,flush=True)

if __name__=='__main__':main()
