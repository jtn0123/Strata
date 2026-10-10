#!/usr/bin/env python3
"""Fresh, prospectively frozen W02 validation and sequential stacking checks."""
import argparse
import copy
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import benchmark_m5_small_gains as b
from check_memory import snapshot
from profile_m5_routes import preflight


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def evaluate(rows, memory_clean, absolute_ttft):
    amended = copy.deepcopy(rows)
    for row in amended:
        if absolute_ttft and not row['cached']:
            values = row['launch_medians']
            worst = max(1000 * (values[c]['ttft_s'] - values[a]['ttft_s'])
                        for c in (1, 2) for a in (0, 3))
            row['original_regressions'] = row['regressions'][:]
            row['regressions'] = [r for r in row['regressions'] if r != 'ttft_reduction_percent']
            if worst > 10 + 1e-9:
                row['regressions'].append('ttft_absolute_10ms_ceiling')
            row['absolute_ttft_policy'] = dict(ceiling_ms=10, worst_launch_pair_slowdown_ms=worst,
                                               average_slowdown_ms=1000*(row['candidate']['ttft_s']-row['control']['ttft_s']),
                                               passed=worst <= 10 + 1e-9)
    decision = b.scope_decision(amended, memory_clean)
    decision['ttft_policy'] = ('Fixed 10 ms ceiling on every candidate/control launch pair; remaining criteria unchanged.'
                               if absolute_ttft else 'Original relative regression rule.')
    decision['rule'] = ('Positive gains above 2x own control drift; both candidate launches beat both controls; '
                        'same scope on English code/prose; generation/reply regressions use original floor; '
                        + decision['ttft_policy'] + ' Exact-output/resource/activation gates mandatory.')
    real = [r for r in amended if not r['cached']]
    decision['safety_passed'] = memory_clean and len(real) == 2 and all(not r['regressions'] for r in real)
    return amended, decision


def speed_passed(decision):
    return {'generation', 'reply'} <= set(decision['common_metric_scopes'])


def prepare():
    if (HERE/'frozen.json').exists():
        raise ValueError('Campaign already frozen; do not overwrite its declaration')
    b.require_pass(); b.assert_no_model_server()
    source = b.fingerprint()
    b.verify_native_prerequisites(json.loads((b.BUNDLE/'native-checks.json').read_text()), source)
    archive = HERE/'source'; archive.mkdir()
    for name in source:
        dest = archive/name; dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/name, dest)
    shutil.copy2(ROOT/'Start Strata.command', HERE/'Start Strata.before.command')
    record = dict(status='preregistered before all new model launches', created_utc=datetime.now(timezone.utc).isoformat(),
                  source_pins=source, plan_sha256=b.sha256(HERE/'plan.json'), runner_sha256=b.sha256(__file__),
                  test_sha256=b.sha256(HERE/'test_sequence.py'),
                  original_launcher_sha256=b.sha256(ROOT/'Start Strata.command'),
                  original_tracker_sha256=b.sha256(b.TRACKER), host_preparation=snapshot(),
                  native_prerequisite='bench/results/20261009-small-gains/native-checks.json',
                  engine_pins={n:b.verify_engine(n) for n in ('m5-copy','m5-small-stack')})
    write(HERE/'frozen.json', record)
    print('Frozen:', HERE/'frozen.json', flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--prepare', action='store_true'); ap.add_argument('--run', action='store_true')
    args = ap.parse_args()
    if args.prepare:
        prepare(); return
    if not args.run:
        print('Prepared sequential campaign; --prepare freezes, --run executes.'); return
    frozen = json.loads((HERE/'frozen.json').read_text())
    source = frozen['source_pins']
    state_path = HERE/'tracking.json'
    if state_path.exists():
        raise ValueError('A campaign state already exists; no automatic retry or selective resume')
    state = dict(status='running', plan=str((HERE/'plan.json').relative_to(ROOT)),
                 frozen_sha256=b.sha256(HERE/'frozen.json'), runs=[], winner=None,
                 promotion='not performed by benchmark driver', exclusions=[])
    def save(): write(state_path, state)
    def unchanged():
        if (b.fingerprint()!=source or b.sha256(HERE/'plan.json')!=frozen['plan_sha256']
                or b.sha256(__file__)!=frozen['runner_sha256']
                or b.sha256(HERE/'test_sequence.py')!=frozen['test_sha256']
                or b.sha256(HERE/'frozen.json')!=state['frozen_sha256']):
            raise ValueError('Frozen campaign inputs changed')
        for name, pin in frozen['engine_pins'].items():
            if b.verify_engine(name)!=pin: raise ValueError('Engine changed')
    def admission():
        unchanged()
        return dict(headroom=b.wait_for_headroom(), quiet_host=preflight())
    def run_one(label, features, cohort='short', predict=256, control_features=()):
        profile = 'small-'+'-'.join(f for f in b.FEATURES if f in features)
        control_profile = ('small-'+'-'.join(f for f in b.FEATURES if f in control_features)
                           if control_features else 'conv-direct')
        spec = b.specification(profile, cohort, 'stack-v2-'+label)
        spec.update(predict=predict, control=control_profile,
                    engine_for_value={control_profile:'m5-small-stack' if control_features else 'm5-copy',
                                      profile:'m5-small-stack'})
        reference=None; receipts=[]
        def check(record, value):
            nonlocal reference
            unchanged()
            actual=b.signatures(record)
            if reference is None: reference=actual
            if actual!=reference: raise ValueError('Fresh/warmup/cache output differs')
            enabled=features if value==profile else control_features
            receipts.append(dict(run_id=record['run_id'],
                **b.feature_receipts((ROOT/'bench/results'/record['run_id']/'server.log').read_text(), enabled)))
            print('Completed launch:', record['run_id'], flush=True)
        print('Starting bracket:', label, profile, 'vs', control_profile, cohort, predict, flush=True)
        state['active_bracket']=label; save()
        folder=b.execute(spec, 3, before_pass=admission, after_pass=check)
        record=json.loads((folder/'comparison.json').read_text())
        records=[json.loads((ROOT/'bench/results'/r['run_id']/'result.json').read_text()) for r in record['runs']]
        original_rows, memory=b.summarize(records)
        rows, decision=evaluate(original_rows, memory['clean'], 'top10' in features)
        cached=b.cached_followups(rows)
        record.update(launch_summary=rows, small_gain_memory=memory, small_gain_decision=decision,
                      original_relative_rule_decision=b.scope_decision(original_rows, memory['clean']),
                      cached_followup=cached, output_parity_including_warmups=True,
                      feature_encoding_receipts=receipts, source_pins=source,
                      plan=str((HERE/'plan.json').relative_to(ROOT)), plan_sha256=frozen['plan_sha256'],
                      campaign_frozen_sha256=state['frozen_sha256'], scope_cohort=cohort,
                      runner_sha256=frozen['runner_sha256'])
        write(folder/'comparison.json', record)
        (folder/'REPORT.md').write_text(b.render(record))
        result=dict(label=label, features=list(features), control_features=list(control_features),
                    cohort=cohort, output_tokens=predict, path=str(folder.relative_to(ROOT)),
                    decision=decision, cached_followup=cached,
                    comparison_sha256=b.sha256(folder/'comparison.json'))
        state['runs'].append(result); state.pop('active_bracket', None); save()
        print('Decision:', label, json.dumps(decision), 'cached followup:', cached['required'], flush=True)
        return result
    b.require_pass(); b.assert_no_model_server()
    with (ROOT/'bench/.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            unchanged()
            b.verify_native_prerequisites(json.loads((b.BUNDLE/'native-checks.json').read_text()), source)
            previous=json.loads(b.TRACKER.read_text())
            p07=next(c for c in previous['candidates'] if c['id']=='P07')
            if not {'generation','reply'} <= set(p07.get('confirmed_metric_scopes', [])):
                raise ValueError('Previously confirmed P07 prerequisite is missing')
            for r in previous['runs']:
                if r['candidate']=='P07':
                    old=json.loads((ROOT/r['path']/'comparison.json').read_text())
                    if old['source_pins']!=source or old['cached_followup']['required']:
                        raise ValueError('P07 source or cached qualification changed')
            state['preflight']=admission(); save()
            winner=['reduce']
            screen=run_one('w02-fresh-screen', ['top10'])
            if speed_passed(screen['decision']) and not screen['cached_followup']['required']:
                confirmation=run_one('w02-independent-confirmation', ['top10'])
                state['w02_confirmed']=speed_passed(confirmation['decision']) and not confirmation['cached_followup']['required']
                save()
                if state['w02_confirmed']:
                    combined=run_one('combined-vs-original', ['reduce','top10'])
                    if speed_passed(combined['decision']) and not combined['cached_followup']['required']:
                        incremental=run_one('combined-vs-p07', ['reduce','top10'], control_features=['reduce'])
                        if speed_passed(incremental['decision']) and not incremental['cached_followup']['required']:
                            winner=['reduce','top10']
            else:
                state['w02_confirmed']=False; save()
            def safety(features):
                prefix='combined' if 'top10' in features else 'p07'
                long=run_one(prefix+'-long-safety', features, cohort='long')
                if not long['decision']['safety_passed'] or long['cached_followup']['required']:
                    return False
                short=run_one(prefix+'-short-answer-safety', features, predict=32)
                return short['decision']['safety_passed'] and not short['cached_followup']['required']
            if not safety(winner):
                if 'top10' in winner:
                    state['combined_safety_failed']=True; save()
                    winner=['reduce'] if safety(['reduce']) else []
                else: winner=[]
            unchanged(); b.assert_no_model_server()
            state.update(status='completed', winner=winner,
                         winner_profile='small-'+'-'.join(winner) if winner else None,
                         promotion_eligible=bool(winner), host_after=snapshot(),
                         completed_utc=datetime.now(timezone.utc).isoformat())
            save(); print('Final winner:', winner, flush=True)
        except BaseException as error:
            label=state.get('active_bracket')
            evidence=[str(p.relative_to(ROOT)) for p in sorted((ROOT/'bench/results').glob('*-m5-stack-v2-'+str(label)))] if label else []
            state.update(status='stopped on failure', error=str(error), host_after=snapshot())
            state['exclusions'].append(dict(label=label, error=str(error), evidence=evidence,
                                           time_utc=datetime.now(timezone.utc).isoformat()))
            save(); raise


if __name__=='__main__': main()
