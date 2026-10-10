#!/usr/bin/env python3
"""Confirm small gains in fresh launch brackets, then test the confirmed subset."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import shutil

from benchmark_m5 import execute
from benchmark_m5_next import wait_for_headroom
from benchmark_m5_compact_models import signatures, dispatch as compact_dispatch
from benchmark_m5_top10_models import dispatch as top10_dispatch
from benchmark_metrics import metrics, change, METRICS
from check_memory import assert_no_model_server
from engines import ROOT, sha256, verify_engine
from metal_environment import configure, TUNING
from validate_offline import require_pass, fingerprint

BUNDLE = ROOT/'bench/results/20261009-small-gains'
TRACKER = ROOT/'bench/small-gain-candidates.json'
PLAN = ROOT/'config/m5_small_gains_plan.json'
FEATURES = ('reduce', 'top10', 'compact')
DELTA = dict(generation_tok_s='generation_increase_percent', prompt_tok_s='prompt_increase_percent',
             ttft_s='ttft_reduction_percent', wall_s='total_time_reduction_percent')


def feature_receipts(text, features):
    features = set(features)
    if not features <= set(FEATURES):
        raise ValueError('Unknown feature')
    result = dict(compact=compact_dispatch(text, 'compact' in features),
                  top10=top10_dispatch(text, 'top10' in features))
    rows = [json.loads(line.split('M5_REDUCE10_DISPATCH ',1)[1]) for line in text.splitlines()
            if 'M5_REDUCE10_DISPATCH ' in line]
    if len(rows) != int('reduce' in features):
        raise ValueError('Actual reduction encoding marker missing or unexpected')
    for row in rows:
        if (set(row) != {'rows','channels','experts','stage'} or row['stage'] != 'encoded'
                or any(type(row[key]) is not int for key in ('rows','channels','experts'))
                or not 1 <= row['rows'] <= 512 or row['channels'] != 2560 or row['experts'] != 10):
            raise ValueError('Invalid reduction encoding marker')
    result['reduce'] = dict(encoded=bool(rows),markers=rows,shader_frequency_proven=False)
    return result


def launch_row(values):
    """Four launch medians in A/B/B/A order; repetitions are not independent launches."""
    if len(values) != 4:
        raise ValueError('Four independent launch medians required')
    for value in values:
        # change validates every positive finite metric.
        change(value,value)
    control = {key:(values[0][key]+values[3][key])/2 for key in METRICS}
    candidate = {key:(values[1][key]+values[2][key])/2 for key in METRICS}
    gain, drift = change(control,candidate), change(values[0],values[3])
    candidate_drift = change(values[1],values[2])
    wins, regressions = {}, []
    for key in METRICS:
        name = DELTA[key]
        better = ((lambda b,a:b > a) if key.endswith('tok_s') else (lambda b,a:b < a))
        direction = all(better(values[b][key],values[a][key]) for b in (1,2) for a in (0,3))
        wins[name] = gain[name] > 0 and gain[name] > 2*abs(drift[name]) and direction
        if key != 'prompt_tok_s' and gain[name] < -max(1,2*abs(drift[name])):
            regressions.append(name)
    return dict(control=control,candidate=candidate,vs_control=gain,control_drift=drift,
                candidate_drift=candidate_drift,qualifying_metrics=wins,regressions=regressions,
                launch_medians=values,independent_launches_per_arm=2)


def scope_decision(rows, memory_clean=True):
    real = [row for row in rows if not row['cached'] and row['workload'] in ('code','prose')]
    if len(real) != 2 or {row['workload'] for row in real} != {'code','prose'}:
        raise ValueError('Both English tasks required')
    scopes = {}
    for row in real:
        scope = []
        if memory_clean and not row['regressions']:
            q = row['qualifying_metrics']
            if q['generation_increase_percent']: scope.append('generation')
            if q['total_time_reduction_percent']: scope.append('reply')
            if q['ttft_reduction_percent'] and q['total_time_reduction_percent']: scope.append('prompt-latency')
        scopes[row['workload']] = scope
    common = sorted(set(scopes['code']) & set(scopes['prose']))
    return dict(eligible_for_confirmation=bool(common),common_metric_scopes=common,
                workload_scopes=scopes,memory_clean=memory_clean,
                rule='No fixed minimum gain. Positive gain above2x own control drift and both candidate launches better than both controls; no material TPS/TTFT/reply regression. Prompt latency also requires reply benefit. Two tasks for common scope; exact/resource/activation gates mandatory.')


def cached_followups(rows):
    flags=[]
    for row in rows:
        if not row['cached']: continue
        for metric in DELTA.values():
            limit=max(5,2*abs(row['control_drift'][metric]))
            gain=row['vs_control'][metric]
            if gain < -limit:
                flags.append(dict(workload=row['workload'],input_tokens=row['input_tokens'],
                                  metric=metric,change_percent=gain,loss_threshold_percent=limit))
    return dict(required=bool(flags),flags=flags,default_promotion_blocked=bool(flags),
                note='Cached timing is a separate diagnostic. Flagged losses require independent follow-up before default promotion.')


def summarize(records):
    if len(records) != 4 or any(record['status'] != 'passed' for record in records):
        raise ValueError('Complete accepted launch bracket required')
    keys = {(c['workload'],c['prompt_tokens']) for c in records[0]['cases']}
    rows = []
    for cached, tasks in ((False,sorted(keys)),(True,[('cached-ledger',512),('cached-ledger',2048)])):
        for name,length in tasks:
            selected = [[c for c in record['cached_cases'] if not c['warmup'] and c['history_budget']==length]
                        if cached else [c for c in record['cases'] if (c['workload'],c['prompt_tokens'])==(name,length)]
                        for record in records]
            if any(len(group)!=3 for group in selected):
                raise ValueError('Three raw repetitions per launch required')
            result = launch_row([metrics(group,cached) for group in selected])
            result.update(workload=name,input_tokens=length,cached=cached,
                          raw_repetitions=[[{key:(c['native_timings']['predicted_per_second'] if key=='generation_tok_s' else
                                                    c['native_timings']['prompt_per_second'] if key=='prompt_tok_s' else c[key])
                                               if cached else c[key] for key in METRICS} for c in group] for group in selected])
            rows.append(result)
    rss = [record['memory']['peak_rss_bytes'] for record in records]
    extra = (rss[1]+rss[2]-rss[0]-rss[3])/2
    limit = max(128*1024**2,2*abs(rss[3]-rss[0]))
    memory = dict(peak_rss_bytes=rss,candidate_extra_average_rss_bytes=extra,allowed_bytes=limit,
                  clean=extra<=limit,note='RSS is not unique total Metal memory; allocation logs remain separate.')
    return rows,memory


def specification(profile, cohort, label):
    result = dict(id=label,engine='m5-small-stack',depth=3,axis='m5_tuning',control='conv-direct',
                  candidates=[profile],predict=256,prompts=[],zero_new_swap=True,
                  engine_for_value={'conv-direct':'m5-copy',profile:'m5-small-stack'})
    if cohort=='long': result['workloads_file']='config/m5_compact_workloads.json'
    elif cohort!='short': raise ValueError('Unknown workload cohort')
    return result


def render(record):
    lines=['# Small-gain validation: '+record['experiment']['id'],'',
           'Fresh A/B/B/A; each task has an excluded warmup and three repetitions per launch. Each arm aggregates two launch medians. This is bracket confirmation, not a statistical-significance claim.','',
           '| Task/input | Baseline TPS | Candidate TPS | TPS change | First-token change | Reply change | Reply saved | Qualified scopes |',
           '| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
    for row in record['launch_summary']:
        a,b,d=row['control'],row['candidate'],row['vs_control']
        scopes=record['small_gain_decision']['workload_scopes'].get(row['workload'],['separate cached diagnostic'])
        lines.append(f"| {row['workload']}/{row['input_tokens']} | {a['generation_tok_s']:.4f} | {b['generation_tok_s']:.4f} | {d['generation_increase_percent']:+.4f}% | {d['ttft_reduction_percent']:+.4f}% | {d['total_time_reduction_percent']:+.4f}% | {1000*(a['wall_s']-b['wall_s']):+.3f}ms | {', '.join(scopes) or 'inconclusive/negative'} |")
    lines+=['','Decision: '+json.dumps(record['small_gain_decision']),
            '', 'Cached follow-up: '+json.dumps(record['cached_followup']),
            '', 'Exact fresh/warmup/cache output parity and feature encoding receipts verified. All launches zero new swap. Native allocation logs and raw variation retained; no automatic app default change.','', '[Raw comparison](comparison.json).']
    return '\n'.join(lines)+'\n'


def bracket(candidate, phase, source, cohort=None, features=None):
    cohort=cohort or candidate['cohort'];features=features or candidate['features']
    profile='small-'+'-'.join(name for name in FEATURES if name in features)
    spec=specification(profile,cohort,f"small-gains-{candidate['id'].lower()}-{phase}-{cohort}")
    reference=None;activation=[]
    def check(record,value):
        nonlocal reference
        if fingerprint()!=source: raise ValueError('Source closure changed during model test')
        actual=signatures(record)
        if reference is None: reference=actual
        if actual!=reference: raise ValueError('Fresh/warmup/cache token IDs or text changed')
        enabled=features if value==profile else []
        activation.append(dict(run_id=record['run_id'],**feature_receipts((ROOT/'bench/results'/record['run_id']/'server.log').read_text(),enabled)))
    folder=execute(spec,3,before_pass=wait_for_headroom,after_pass=check)
    record=json.loads((folder/'comparison.json').read_text())
    records=[json.loads((ROOT/'bench/results'/item['run_id']/'result.json').read_text()) for item in record['runs']]
    rows,memory=summarize(records)
    record.update(launch_summary=rows,small_gain_memory=memory,small_gain_decision=scope_decision(rows,memory['clean']),
                  cached_followup=cached_followups(rows),
                  output_parity_including_warmups=True,feature_encoding_receipts=activation,source_pins=source,
                  plan_sha256=sha256(PLAN),scope_cohort=cohort)
    (folder/'comparison.json').write_text(json.dumps(record,indent=2)+'\n')
    (folder/'REPORT.md').write_text(render(record))
    return str(folder.relative_to(ROOT)),record['small_gain_decision']


def verify_native_prerequisites(prerequisites, source):
    engines={name:verify_engine(name) for name in ('m5-copy','m5-top10','m5-small-stack')}
    profiles=['conv-direct']+[name for name in TUNING if name.startswith('small-')]
    kinds=('compact','top10','reduce')
    if (prerequisites['status']!='passed' or prerequisites['engine']!=engines['m5-small-stack']
            or prerequisites['source_pins']!=source or prerequisites['profiles']!=profiles):
        raise ValueError('Native checks must cover current complete source closure and profiles')
    if sha256(BUNDLE/'native-check.py')!=prerequisites['runner_sha256']:
        raise ValueError('Native check runner changed')
    expected_sources={kind:sha256(ROOT/f'native/m5_{kind}_probe.cpp') for kind in kinds}
    if prerequisites['sources']!=expected_sources:
        raise ValueError('Native fixture changed')
    expected_archive=set(source)|{f'native/m5_{kind}_probe.cpp' for kind in kinds}|{
        str((BUNDLE/'native-check.py').relative_to(ROOT)),
        *[f'patches/mtp-m5-{name}.patch' for name in ('small-stack','copy','reduce','top10','compact')]}
    if set(prerequisites['archive'])!=expected_archive:
        raise ValueError('Incomplete native source archive')
    for name,digest in prerequisites['archive'].items():
        if sha256(BUNDLE/'native-source'/name)!=digest or sha256(ROOT/name)!=digest:
            raise ValueError('Native source archive changed')
    builds={}
    for build in prerequisites['builds']:
        key=(build['kind'],build['scope'])
        if key in builds or key not in {(k,s) for k in kinds for s in ('control','stack')}:
            raise ValueError('Duplicate or unexpected native build')
        kind,scope=key
        name=('m5-top10' if kind=='top10' else 'm5-copy') if scope=='control' else 'm5-small-stack'
        binary=ROOT/f'bench/runtime/m5-small-stack/{kind}-{scope}-probe'
        command=build['command']
        if (build['engine']!=engines[name] or sha256(binary)!=build['binary_sha256']
                or command[command.index('-o')+1]!=str(binary)
                or str(ROOT/f'native/m5_{kind}_probe.cpp') not in command):
            raise ValueError('Native build provenance changed')
        builds[key]=build
    if len(builds)!=6:
        raise ValueError('Six unique native build receipts required')
    expected={(profile,kind) for profile in ['original']+profiles for kind in kinds}
    actual=set()
    for path in prerequisites['runs']:
        folder=ROOT/path;record=json.loads((folder/'result.json').read_text())
        key=(record['profile'],record['kind'])
        if key not in expected or key in actual:
            raise ValueError('Duplicate or unexpected native run')
        actual.add(key);profile,kind=key
        scope='control' if profile=='original' else 'stack';build=builds[(kind,scope)]
        _,flags=configure({},build['engine']['engine'],'on','conv-direct' if profile=='original' else profile)
        memory=record['memory']
        if (record['engine']!=build['engine'] or record['binary_sha256']!=build['binary_sha256']
                or record['metal_environment']!=flags or record['status']!='passed'
                or record['native_returncode'] or memory['swap_growth_bytes'] or memory['guard']
                or not memory['monitor_healthy'] or not memory['child_exited']
                or sha256(folder/'native.log')!=record['native_log_sha256']
                or sha256(folder/('outputs.bin' if kind=='reduce' else 'outputs.jsonl'))!=record['outputs_sha256']):
            raise ValueError('Native raw evidence incomplete or changed')
    if actual!=expected:
        raise ValueError('Complete unique 27-run native inventory required')


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',action='store_true');args=ap.parse_args()
    plan=json.loads(PLAN.read_text())
    if not args.run: print('Prepared small-gain confirmations:',[c['id'] for c in plan['candidates']]);return
    require_pass();assert_no_model_server()
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        prerequisites=json.loads((BUNDLE/'native-checks.json').read_text())
        source=fingerprint()
        verify_native_prerequisites(prerequisites,source)
        archive=BUNDLE/'model-source';archive.mkdir()
        for name in source:
            dest=archive/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,dest)
        (archive/'pins.json').write_text(json.dumps(source,indent=2)+'\n')
        tracking=json.loads(TRACKER.read_text());tracking['status']='running'
        def save(): TRACKER.write_text(json.dumps(tracking,indent=2)+'\n')
        def run_one(candidate,phase,cohort=None,features=None):
            try:
                path,decision=bracket(candidate,phase,source,cohort,features)
                tracking['runs'].append(dict(candidate=candidate['id'],phase=phase,cohort=cohort or candidate['cohort'],path=path,decision=decision));save()
                print(candidate['id'],phase,decision,flush=True);return decision
            except Exception as error:
                label=f"small-gains-{candidate['id'].lower()}-{phase}-{cohort or candidate['cohort']}"
                evidence=[str(path.relative_to(ROOT)) for path in sorted((ROOT/'bench/results').glob('*-m5-'+label))]
                tracking['exclusions'].append(dict(candidate=candidate['id'],phase=phase,cohort=cohort or candidate['cohort'],error=str(error),evidence=evidence,time_utc=datetime.now(timezone.utc).isoformat()))
                tracking['status']='stopped on failure'
                item=next((c for c in tracking['candidates'] if c['id']==candidate['id']),None)
                if item is not None:item['status']='stopped; excluded failed bracket'
                save();shutil.copy2(TRACKER,BUNDLE/'tracking-stopped.json')
                print(candidate['id'],phase,'STOPPED',error,flush=True);raise
        screened=[]
        for candidate in plan['candidates']:
            item=next(c for c in tracking['candidates'] if c['id']==candidate['id'])
            first=run_one(candidate,'screen');item['screen_decision']=first;item['status']='screened; awaiting confirmation' if first and first['eligible_for_confirmation'] else 'screened; no common qualified gain'
            if first and first['eligible_for_confirmation']: screened.append((candidate,first))
            save()
        confirmed=[]
        for candidate,first in screened:
            second=run_one(candidate,'confirmation')
            common=set(first['common_metric_scopes']) & set(second['common_metric_scopes']) if second else set()
            item=next(c for c in tracking['candidates'] if c['id']==candidate['id'])
            item.update(confirmation_decision=second,confirmed_metric_scopes=sorted(common),status='confirmed possible addition' if common else 'confirmation inconclusive/negative')
            if common: confirmed.append(candidate)
            save()
        selected=[feature for feature in FEATURES if any(feature in c['features'] for c in confirmed)]
        tracking['selected_combined_features']=selected;save()
        if len(selected)>=2:
            combined=dict(id='combined',features=selected,cohort='short')
            cohorts=['short'] if any(feature in selected for feature in ('reduce','top10')) else []
            if 'compact' in selected: cohorts.append('long')
            (BUNDLE/'combined-plan.json').write_text(json.dumps(dict(status='preregistered_before_combined_gpu',features=selected,cohorts=cohorts,source_pins=source,individual_runs=tracking['runs']),indent=2)+'\n')
            decisions=[run_one(combined,'combined',cohort,selected) for cohort in cohorts]
            tracking['combined_status']='tested; see metric/workload decisions';tracking['combined_decisions']=decisions
        else: tracking['combined_status']='No two independently confirmed candidates; no combination launched.'
        tracking['status']='completed';save();assert_no_model_server()
        shutil.copy2(TRACKER,BUNDLE/'tracking-final.json')
        print('Final candidate tracker:',TRACKER,flush=True)


if __name__=='__main__':main()
