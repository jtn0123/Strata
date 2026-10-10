#!/usr/bin/env python3
"""Matched original-engine control for all-pool QSA ranking removal."""
import argparse
import fcntl
import json
import shutil
from pathlib import Path

from benchmark_m5 import execute
from benchmark_m5_next import finish, output_signatures, wait_for_headroom
from benchmark_m5_encoder_models import adoption
from benchmark_m5_qsa import RESULTS, SOURCE, BINARY, parse
from engines import ROOT, sha256, verify_engine
from validate_offline import require_pass, fingerprint

BUNDLE = ROOT/'bench/results/20261009-next-speed-pass'

def prerequisites():
    comparison = json.loads((RESULTS/'comparison.json').read_text())
    receipt = json.loads((ROOT/'bench/runtime/m5-qsa/build.json').read_text())
    if (comparison['status'] != 'passed' or receipt['engine'] != verify_engine('m5-copy')
            or receipt['source_sha256'] != sha256(SOURCE)
            or receipt['runner_sha256'] != sha256(ROOT/'scripts/benchmark_m5_qsa.py')
            or receipt['binary_sha256'] != sha256(BINARY)):
        raise ValueError('Component/native source or binary changed')
    # Engine registration followed the component screen. Its original dependencies
    # were archived before edits; the unchanged control receipt is also checked above.
    historical = {}
    for name, expected in receipt['dependencies'].items():
        current = ROOT/'scripts'/name
        if sha256(current) != expected:
            original = BUNDLE/'before/scripts'/name
            if name not in ('engines.py', 'metal_environment.py') or sha256(original) != expected:
                raise ValueError('Unexplained component dependency change: '+name)
            historical[name] = dict(component_sha256=expected, current_sha256=sha256(current),
                                    reason='Added isolated engine registration/profile after component screen')
    rows = []
    paths = comparison['checks'] + comparison['runs']
    if len(paths) != 6:
        raise ValueError('Complete component bracket required')
    for path in paths:
        folder = ROOT/path
        record = json.loads((folder/'result.json').read_text())
        if (record['status'] != 'passed' or record['probe'] != receipt
                or record['memory']['swap_growth_bytes'] or record['memory']['guard']
                or sha256(folder/'native.log') != record['native_log_sha256']
                or sha256(folder/'outputs.jsonl') != record['evidence_sha256']
                or parse((folder/'native.log').read_text(), record['scope'], record['mode']) != record['cases']):
            raise ValueError('Component evidence incomplete or changed')
        rows.append(record)
    keys = ('id', 'mask_sha256', 'score_sha256', 'input_sha256', 'mask_elements')
    if any(any(a[k] != b[k] for k in keys) for a,b in zip(rows[0]['cases'],rows[1]['cases'])):
        raise ValueError('Exact mask/score parity failed')
    qualified = []
    for i, first in enumerate(rows[2]['cases']):
        values = [r['cases'][i] for r in rows[2:]]
        if any(any(v[k] != first[k] for k in keys) for v in values):
            raise ValueError('Timed component outputs changed')
        a = (values[0]['median_us']+values[3]['median_us'])/2
        b = (values[1]['median_us']+values[2]['median_us'])/2
        gain = 100*(1-b/a)
        drift = 100*abs(values[3]['median_us']/values[0]['median_us']-1)
        # Small-pool/512-token cases are synthetic; they cannot qualify the trial.
        if first['pools'] <= 512 and (first['tokens'] <= 4 or first['pools'] == 512) and gain >= 3 and gain > 2*drift:
            qualified.append(first['id'])
        if first['pools'] > 512 and gain < -1:
            raise ValueError('Fallback boundary regression')
    if not qualified:
        raise ValueError('No realizable component improvement above drift')
    return dict(comparison=comparison, historical_dependencies=historical, qualifying_cases=qualified)

def dispatch(text, candidate):
    records = [json.loads(line.split('M5_QSA_INPUT ',1)[1]) for line in text.splitlines() if 'M5_QSA_INPUT ' in line]
    if len(records) != int(candidate):
        raise ValueError('Eligible input marker missing or unexpected')
    for row in records:
        if (set(row) != {'pools','tokens','n_sel','stage'} or row['stage'] != 'input-prepared'
                or any(type(row[k]) is not int or row[k] <= 0 for k in ('pools','tokens','n_sel'))
                or row['pools'] > 512 or row['pools'] % 64 or row['n_sel'] < 4*row['pools']):
            raise ValueError('Invalid all-pool input marker')
    return dict(markers=records, actual_input_prepared=candidate, shader_frequency_proven=False)

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
    lines = ['# All-pool QSA ranking removal: matched model result', '',
        'Original m5-copy/conv-direct versus isolated m5-qsa/qsa-all-pools. Qwen3.8-Flash-Next Q2_0, shared Q3 helper, mixed placement, eight helper workers, depth3/confidence0, Tensor API on, F16/4K/batch512.', '',
        'Fresh ABBA,256 output tokens, excluded warmup and three repetitions. Exact token/text parity includes warmups and cached continuations. Scores, cache writes and attention dispatch remain unchanged.', '',
        '| Workload/input | Control TPS | Candidate TPS | TPS gain | Reply quicker | First token quicker | TPS drift | Reply drift |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for r in record['summary']:
        a,b = r['profiles']['conv-direct'],r['profiles']['qsa-all-pools']
        d,f = r['vs_control']['qsa-all-pools'],r['control_drift']
        lines.append(f"| {r['workload']}/{r['input_budget']} | {a['generation_tok_s']:.3f} | {b['generation_tok_s']:.3f} | {d['generation_increase_percent']:+.3f}% | {d['total_time_reduction_percent']:+.3f}% | {d['ttft_reduction_percent']:+.3f}% | {f['generation_increase_percent']:+.3f}% | {f['total_time_reduction_percent']:+.3f}% |")
    lines += ['', 'Strict speed acceptance: '+str(record['decision']['measured_speed_candidate'])+'. '+record['decision']['rule'], '',
        'The once-per-process marker proves an eligible input was prepared, not shader execution frequency. Successful graph completion and exact tested answers qualify the run. No new swap; original launchers remain unchanged.', '', '[Raw comparison](comparison.json).']
    return '\n'.join(lines)+'\n'

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run',action='store_true')
    ap.add_argument('--resume',type=Path)
    args = ap.parse_args()
    spec = dict(id='qsa-all-pools',engine='m5-qsa',depth=3,axis='m5_tuning',control='conv-direct',
                candidates=['qsa-all-pools'],predict=256,
                engine_for_value={'conv-direct':'m5-copy','qsa-all-pools':'m5-qsa'})
    if not args.run: print('Prepared:',spec); return
    require_pass()
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        proof = prerequisites()
        source = fingerprint()
        archive = BUNDLE/'qsa-model-source'
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
                receipts.append(dict(run_id=r['run_id'],**dispatch((ROOT/'bench/results'/r['run_id']/'server.log').read_text(),entry['value']=='qsa-all-pools')))
        def check_pass(record,value):
            nonlocal reference
            if fingerprint()!=source: raise ValueError('Model benchmark closure changed')
            current=signatures(record)
            if reference is None: reference=current
            if current != reference: raise ValueError('Fresh, warmup or cache outputs differ from control')
            receipts.append(dict(run_id=record['run_id'],**dispatch((ROOT/'bench/results'/record['run_id']/'server.log').read_text(),value=='qsa-all-pools')))
        folder=execute(spec,3,resume=args.resume,before_pass=wait_for_headroom,after_pass=check_pass)
        record=finish(folder)
        decision=adoption(record['summary'],'qsa-all-pools')
        decision['rule']='At least1% TPS and reply gain on both English code/prose, each above its own absolute control drift; exact tested outputs and zero new swap.'
        record.update(component_prerequisites=proof,qsa_input_receipts=receipts,source_pins=source,
                      output_parity_including_warmups=True,decision=decision)
        (folder/'comparison.json').write_text(json.dumps(record,indent=2)+'\n')
        (folder/'REPORT.md').write_text(render(record))
        print('Matched model result:',folder,decision,flush=True)

if __name__=='__main__':main()
