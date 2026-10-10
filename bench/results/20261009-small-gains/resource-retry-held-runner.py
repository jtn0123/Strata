#!/usr/bin/env python3
"""One resource-only campaign retry using the unchanged canonical bracket runner."""
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
import benchmark_m5_small_gains as b
from profile_m5_routes import preflight


def main():
    b.require_pass();b.assert_no_model_server()
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        source=b.fingerprint();prerequisites=json.loads((b.BUNDLE/'native-checks.json').read_text())
        b.verify_native_prerequisites(prerequisites,source)
        saved=json.loads((b.BUNDLE/'model-source/pins.json').read_text())
        if saved!=source:raise ValueError('Retry requires unchanged first model-source closure')
        for name,digest in source.items():
            if b.sha256(b.BUNDLE/'model-source'/name)!=digest:raise ValueError('Original model archive changed')
        tracking=json.loads(b.TRACKER.read_text());plan=json.loads(b.PLAN.read_text())
        if tracking['status']!='stopped on failure' or tracking['runs'] or tracking.get('resource_retry_count',0):
            raise ValueError('Only one retry after initial resource-only failure is permitted')
        exclusion=json.loads((b.BUNDLE/'model-initial-excluded/exclusion.json').read_text())
        failed=json.loads((ROOT/exclusion['run']/'result.json').read_text())
        if (exclusion['id']!='X24' or not failed['memory']['guard'] or failed['cases'] or failed['checks']
                or failed['selected_engine']['engine']!='m5-copy'):
            raise ValueError('Failed initial run is not a response-free original-control resource exclusion')
        retry=dict(status='waiting for unchanged headroom/quiet preflight',source_pins=source,
                   runner_sha256=b.sha256(__file__),canonical_runner_sha256=b.sha256(ROOT/'scripts/benchmark_m5_small_gains.py'),
                   original_plan_sha256=b.sha256(b.PLAN),excluded_attempt=exclusion,
                   rule='One complete fresh resource-only retry; no partial pooling, no changed source/math/workloads/settings/guards, no performance retry. All subsequent failures stop.',
                   created_utc=datetime.now(timezone.utc).isoformat())
        retry_path=b.BUNDLE/'resource-retry-plan.json'
        retry_path.write_text(json.dumps(retry,indent=2)+'\n')
        def save():b.TRACKER.write_text(json.dumps(tracking,indent=2)+'\n')
        try:
            retry['headroom']=b.wait_for_headroom();retry['quiet_preflight']=preflight()
        except Exception as error:
            retry.update(status='held; no retry model launched',error=str(error))
            retry_path.write_text(json.dumps(retry,indent=2)+'\n')
            tracking['status']='held; resource retry awaits unchanged34GiB headroom and quiet host'
            tracking['retry_preflight']=dict(error=str(error),evidence=str(retry_path.relative_to(ROOT)))
            save();print('Resource retry HELD:',error,flush=True);return
        retry['status']='preregistered before retry model launches'
        retry_path.write_text(json.dumps(retry,indent=2)+'\n')
        tracking.update(status='running resource-only retry',resource_retry_count=1)
        for item in tracking['candidates']:item['status']='possible addition; fresh validation pending'
        save()
        def run_one(candidate,phase,cohort=None,features=None):
            try:
                path,decision=b.bracket(candidate,phase,source,cohort,features)
                tracking['runs'].append(dict(candidate=candidate['id'],phase=phase,cohort=cohort or candidate['cohort'],path=path,decision=decision));save()
                print(candidate['id'],phase,decision,flush=True);return decision
            except Exception as error:
                label=f"small-gains-{candidate['id'].lower()}-{phase}-{cohort or candidate['cohort']}"
                evidence=[str(path.relative_to(ROOT)) for path in sorted((ROOT/'bench/results').glob('*-m5-'+label))]
                tracking['exclusions'].append(dict(candidate=candidate['id'],phase=phase,cohort=cohort or candidate['cohort'],error=str(error),evidence=evidence,time_utc=datetime.now(timezone.utc).isoformat()))
                tracking['status']='stopped after one resource-only retry'
                item=next((c for c in tracking['candidates'] if c['id']==candidate['id']),None)
                if item is not None:item['status']='stopped; excluded failed bracket'
                save();shutil.copy2(b.TRACKER,b.BUNDLE/'tracking-stopped-retry.json')
                print(candidate['id'],phase,'STOPPED',error,flush=True);raise
        screened=[]
        for candidate in plan['candidates']:
            phase='screen-resource-retry1' if candidate['id']=='P11' else 'screen'
            first=run_one(candidate,phase)
            item=next(c for c in tracking['candidates'] if c['id']==candidate['id'])
            item.update(screen_decision=first,status='screened; awaiting confirmation' if first['eligible_for_confirmation'] else 'screened; no common qualified gain')
            if first['eligible_for_confirmation']:screened.append((candidate,first))
            save()
        confirmed=[]
        for candidate,first in screened:
            second=run_one(candidate,'confirmation')
            common=set(first['common_metric_scopes']) & set(second['common_metric_scopes'])
            item=next(c for c in tracking['candidates'] if c['id']==candidate['id'])
            item.update(confirmation_decision=second,confirmed_metric_scopes=sorted(common),status='confirmed possible addition' if common else 'confirmation inconclusive/negative')
            if common:confirmed.append(candidate)
            save()
        selected=[feature for feature in b.FEATURES if any(feature in c['features'] for c in confirmed)]
        tracking['selected_combined_features']=selected;save()
        if len(selected)>=2:
            combined=dict(id='combined',features=selected,cohort='short')
            cohorts=['short'] if any(feature in selected for feature in ('reduce','top10')) else []
            if 'compact' in selected:cohorts.append('long')
            (b.BUNDLE/'combined-plan.json').write_text(json.dumps(dict(status='preregistered_before_combined_gpu',features=selected,cohorts=cohorts,source_pins=source,individual_runs=tracking['runs']),indent=2)+'\n')
            decisions=[run_one(combined,'combined',cohort,selected) for cohort in cohorts]
            tracking.update(combined_status='tested; see metric/workload decisions',combined_decisions=decisions)
        else:tracking['combined_status']='No two independently confirmed candidates; no combination launched.'
        tracking['status']='completed';save();b.assert_no_model_server()
        shutil.copy2(b.TRACKER,b.BUNDLE/'tracking-final.json')
        print('Final candidate tracker:',b.TRACKER,flush=True)


if __name__=='__main__':main()
