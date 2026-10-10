"""Bounded 4B screening run; preserve production harness and all raw evidence."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import argparse, fcntl, hashlib, json, os, statistics, subprocess, threading
from datetime import datetime, timezone
from unittest.mock import patch
import psutil
from benchmark import Monitor, run
from benchmark_metrics import metrics, change, counter
from benchmark_tuning import watch_resources
from check_memory import assert_no_model_server
from engines import verify_engine, sha256
from metal_environment import configure
from model_provenance import verify_models, assert_unchanged
from validate_offline import require_pass, fingerprint
from verify_q2 import check_case

folder = ROOT / 'bench/results' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-small-m5-screening')
folder.mkdir(parents=True)
source = Path(__file__).read_bytes()
(folder / 'runner.py').write_bytes(source)
record = {'schema': 1, 'kind': 'small-model-screening', 'status': 'running',
          'model': 'Qwen3.5-4B-Q4_K_M', 'order': ['m5-lab', 'm5-correctness', 'm5-correctness', 'm5-lab'],
          'runner_sha256': hashlib.sha256(source).hexdigest(), 'runs': [], 'admissions': [],
          'limits': 'Small dense 4B model, no MTP/expert streaming. Four matched launches screen for regressions; small differences are not established gains. RSS is not total Metal allocation.'}
original_baseline = Monitor.baseline
done = threading.Event()
watcher = threading.Thread(target=watch_resources, args=(folder / 'resources.jsonl', done), daemon=True)

def save():
    (folder / 'comparison.json').write_text(json.dumps(record, indent=2, allow_nan=False) + '\n')

def admission():
    samples = [psutil.cpu_percent(interval=1) for _ in range(3)]
    assert_no_model_server()
    assert_unchanged(record['model_provenance'])
    baseline = original_baseline()
    pressure = int(subprocess.check_output(['sysctl', '-n', 'kern.memorystatus_vm_pressure_level'], text=True))
    item = {**baseline, 'pressure': pressure, 'cpu_percent_samples': samples}
    record['admissions'].append(item); save()
    if baseline['available_bytes'] < 6 * 1024**3 or pressure != 1:
        raise RuntimeError('Final small-model admission needs 6 GiB available and normal pressure')
    if max(samples) > 25 or statistics.mean(samples) > 15:
        raise RuntimeError(f'Host busy at final admission: {samples}')
    return baseline

def settings(engine, label, context=4096):
    return argparse.Namespace(model='small', engine=engine, label=label, context=context,
        batch=512, ubatch=512, spec='none', draft=3, draft_placement='gpu', draft_model='mtp',
        threads=8, draft_threads=None, draft_p_min=None, cache_type='f16', draft_vocab='off',
        tensor_api='on', m5_tuning='stock', temperature=0, predict=128, prompts=[512,2048],
        repeats=3, warmups=1, real_workloads=True, cached_workloads=True, extended_checks=True,
        swap_guard_bytes=128*1024**2, minimum_available_bytes=2*1024**3, require_quiet_host=True,
        retrieval_budget=6144 if context==8192 else None)

def validate(result, context=4096):
    mem = result['memory']
    assert mem['monitor_healthy'] is True and mem['child_exited'] is True
    assert mem['guard'] is None and mem['swap_growth_bytes'] == 0
    expected_groups = {('synthetic',512), ('synthetic',2048), ('code',None), ('prose',None), ('chinese',None)}
    groups = {}
    for c in result['cases']:
        key = (c['workload'],c['prompt_tokens'] if c['workload']=='synthetic' else None)
        groups.setdefault(key,[]).append(c)
        t = c['response']['final']['timings']
        for name in ('prompt_n','cache_n','predicted_n'): counter(t[name],name)
        assert t['prompt_n']==c['prompt_tokens'] and t['cache_n']==0 and t['predicted_n']==128
        assert c['output_tokens']==128
    assert set(groups)==expected_groups
    for cases in groups.values():
        assert len(cases)==3 and sorted(c['repeat'] for c in cases)==[1,2,3]
        assert len({c['prompt_sha256'] for c in cases})==1
        metrics(cases)
    cached = result['cached_cases']
    assert len(cached)==8
    for budget in (512,2048):
        selected = [c for c in cached if c['history_budget']==budget]
        assert sorted(c['repeat'] for c in selected)==[0,1,2,3]
        for c in selected:
            t=c['native_timings']
            for name in ('prompt_n','cache_n','predicted_n'): counter(t[name],name)
            assert t['cache_n']>0 and 0<t['predicted_n']<=96
            assert t['prompt_n']+t['cache_n']==c['prompt_tokens']
            assert c['warmup'] is (c['repeat']==0)
            metrics([c],cached=True)
    assert len(result['checks'])==(35 if context==8192 else 32)
    assert all(type(c['passed']) is bool for c in result['checks'])
    assert len([c for c in result['checks'] if 'temperature' in c])==22
    assert len([c for c in result['checks'] if c.get('name')=='cached-ledger'])==8
    return {'measurement_valid':True, 'quality_passed':all(c['passed'] is True for c in result['checks']),
            'checks_passed':sum(c['passed'] for c in result['checks']), 'checks_total':len(result['checks'])}

def summarize(results):
    rows=[]
    for key in sorted({(c['workload'],c['prompt_tokens']) for c in results[0]['cases']}):
        samples = [[c for c in r['cases'] if (c['workload'],c['prompt_tokens'])==key] for r in results]
        assert len({c['prompt_sha256'] for group in samples for c in group})==1
        perlaunch = [metrics(s) for s in samples]
        control = metrics(samples[0]+samples[3]); candidate=metrics(samples[1]+samples[2])
        rows.append({'workload':key[0],'prompt_tokens':key[1], 'control':control,'candidate':candidate,
                     'change':change(control,candidate),'per_launch':perlaunch,
                     'control_drift_percent':100*(perlaunch[3]['generation_tok_s']/perlaunch[0]['generation_tok_s']-1)})
    for budget in (512,2048):
        samples=[[c for c in r['cached_cases'] if c['history_budget']==budget and not c['warmup']] for r in results]
        control=metrics(samples[0]+samples[3],True); candidate=metrics(samples[1]+samples[2],True)
        rows.append({'workload':'cached-ledger','history_budget':budget,'control':control,'candidate':candidate,
                     'change':change(control,candidate),'per_launch':[metrics(s,True) for s in samples]})
    return rows

print(f'BATCH {folder}', flush=True)
results=[]
try:
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert_no_model_server()
        record['offline_gate']=require_pass()
        record['harness_sources']=fingerprint()
        record['engines']={name:verify_engine(name) for name in ('m5-lab','m5-correctness')}
        record['model_provenance']=verify_models(['small'])
        tester=ROOT/record['engines']['m5-correctness']['directory']/'build/bin/test-backend-ops'
        record['tester_sha256']=sha256(tester)
        save(); watcher.start()
        for index,engine in enumerate(record['order']):
            if index==1:
                print('GPU residual correctness: exactly 16 selected CPU-reference cases',flush=True)
                env,_=configure(os.environ,'m5-correctness','on')
                check=check_case(tester,folder,'residual-16',r'n=(2|3|5|8),.*mode=mm2\+mm',env,'MUL_MAT_ADD')
                record['residual_check']=check; save()
                assert check['passed'] is True and check['counts']==[(16,16)]
                assert check['system_swap_growth_bytes']==0 and sha256(tester)==record['tester_sha256']
            print(f'LAUNCH {index+1}/4: {engine}',flush=True)
            with patch.object(Monitor,'baseline',side_effect=admission):
                result=run(settings(engine,f'small-m5-{index+1}-{engine}'))
            entry={'run_id':result['run_id'],'engine':engine,'status':result['status'],'memory':result['memory']}
            record['runs'].append(entry); save()
            entry.update(validate(result)); results.append(result); save()
            assert verify_engine(engine)==record['engines'][engine]
            assert_unchanged(record['model_provenance'])
            assert fingerprint()==record['harness_sources']
        record['summary']=summarize(results); save()
        if all(r['quality_passed'] for r in record['runs']):
            print('8K context check on 4B candidate: three exact 6144-token retrieval fixtures',flush=True)
            with patch.object(Monitor,'baseline',side_effect=admission):
                extra=run(settings('m5-correctness','small-m5-8k-capacity',8192))
            record['context_8k']={'run_id':extra['run_id'],'memory':extra['memory'],**validate(extra,8192)}
            save()
        record['status']='passed' if all(r['quality_passed'] for r in record['runs']) and record.get('context_8k',{}).get('quality_passed',True) else 'completed-check-failure'
except BaseException as error:
    record.update(status='failed',error=f'{type(error).__name__}: {error}')
    raise
finally:
    done.set()
    if watcher.ident is not None: watcher.join(timeout=3)
    record['harness_unchanged']=fingerprint()==record.get('harness_sources')
    record['final_available_bytes']=psutil.virtual_memory().available
    record['final_swap_bytes']=psutil.swap_memory().used
    save()
    print(f'COMPLETE {record["status"]}: {folder}',flush=True)
