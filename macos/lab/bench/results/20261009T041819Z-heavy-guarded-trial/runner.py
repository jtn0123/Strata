"""User-authorized full-model capacity trial with stricter live memory guards."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import argparse,ctypes,fcntl,hashlib,json,statistics,subprocess,threading,time
from datetime import datetime,timezone
from unittest.mock import patch
import psutil
import benchmark
from benchmark_metrics import metrics,counter
from benchmark_m5 import settings as preset
from benchmark_tuning import watch_resources
from check_memory import assert_no_model_server
from engines import verify_engine
from model_provenance import verify_models,assert_unchanged
from validate_offline import require_pass,fingerprint

folder=ROOT/'bench/results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-heavy-guarded-trial')
folder.mkdir(parents=True)
source=Path(__file__).read_bytes();(folder/'runner.py').write_bytes(source)
record={'schema':1,'kind':'user-authorized-heavy-capacity-and-benchmark','status':'running',
        'usual_admission_bytes':34*1024**3,'trial_admission_bytes':31*1024**3,
        'live_swap_growth_stop_bytes':0,'pressure_stop_above':1,'minimum_available_during_bytes':1024**3,
        'runner_sha256':hashlib.sha256(source).hexdigest(),'runs':[],'admissions':[],
        'method':'Try the unchanged optimized writing preset first. If its owned server stops on a memory guard, clean up and retry the same heavy target with prediction disabled. No change to the normal 34 GiB policy. Attempt below that policy is a capacity experiment, not a permission to adopt defaults. At most two matched launches of one successful profile; three measured repeats plus one excluded warmup, 128 output tokens, 4K context. No performance gain is implied.'}
lib=ctypes.CDLL('/usr/lib/libSystem.B.dylib',use_errno=True)
lib.sysctlbyname.argtypes=[ctypes.c_char_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_size_t),ctypes.c_void_p,ctypes.c_size_t]
lib.sysctlbyname.restype=ctypes.c_int

def pressure():
    value=ctypes.c_int();size=ctypes.c_size_t(ctypes.sizeof(value))
    if lib.sysctlbyname(b'kern.memorystatus_vm_pressure_level',ctypes.byref(value),ctypes.byref(size),None,0):
        raise OSError(ctypes.get_errno(),'Could not read native memory pressure')
    return value.value

def save():
    (folder/'trial.json').write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')

original_monitor=benchmark.Monitor
original_baseline=original_monitor.baseline

def admission():
    samples=[psutil.cpu_percent(interval=1) for _ in range(3)]
    assert_no_model_server();assert_unchanged(record['model_provenance'])
    base=original_baseline();level=pressure()
    record['admissions'].append({**base,'pressure_level':level,'cpu_percent_samples':samples});save()
    if base['available_bytes']<record['trial_admission_bytes'] or level!=1:
        raise RuntimeError('Capacity trial deferred: need 31 GiB and normal pressure immediately before launch')
    if max(samples)>25 or statistics.mean(samples)>15:
        raise RuntimeError(f'Host busy before launch: {samples}')
    return base

class TrialMonitor(original_monitor):
    baseline=staticmethod(admission)
    def sample(self,mem=None):
        sample=super().sample(mem)
        sample['pressure_level']=pressure()
        if self.process.poll() is None and sample['pressure_level']>1:
            self.guard=f'Stopped owned server: memory pressure became {sample["pressure_level"]}'
            self.stop_owned_child()
        return sample

def settings(profile,index):
    args=preset({'engine':'mtp-mma','axis':'engine','depth':3},'mtp-mma',f'heavy-trial-{profile}-{index}',3)
    args.require_quiet_host=False # Final admission above supplies the explicit trial policy and quiet CPU gate.
    args.swap_guard_bytes=0
    args.minimum_available_bytes=1024**3
    if profile=='target-only':
        args.spec='none';args.draft_threads=None;args.draft_p_min=None
    args.capacity_trial=True
    return args

def validation(result):
    mem=result['memory']
    assert mem['guard'] is None and mem['monitor_healthy'] is True and mem['child_exited'] is True
    assert mem['swap_growth_bytes']==0
    expected={('synthetic',512),('synthetic',2048),('code',None),('prose',None),('chinese',None)}
    groups={}
    for case in result['cases']:
        key=(case['workload'],case['prompt_tokens'] if case['workload']=='synthetic' else None)
        groups.setdefault(key,[]).append(case)
        native=case['response']['final']['timings']
        for name in ('prompt_n','cache_n','predicted_n'):counter(native[name],name)
        assert native['cache_n']==0 and native['prompt_n']==case['prompt_tokens'] and native['predicted_n']==128
        assert case['output_tokens']==128
    assert set(groups)==expected
    for cases in groups.values():
        assert len(cases)==3 and sorted(c['repeat'] for c in cases)==[1,2,3]
        assert len({c['prompt_sha256'] for c in cases})==1
        metrics(cases)
    assert len(result['cached_cases'])==8
    for budget in (512,2048):
        cases=[c for c in result['cached_cases'] if c['history_budget']==budget]
        assert sorted(c['repeat'] for c in cases)==[0,1,2,3]
        for case in cases:
            native=case['native_timings']
            for name in ('prompt_n','cache_n','predicted_n'):counter(native[name],name)
            assert native['cache_n']>0 and 0<native['predicted_n']<=96
            assert native['prompt_n']+native['cache_n']==case['prompt_tokens']
            assert case['warmup'] is (case['repeat']==0)
            metrics([case],True)
    assert len(result['checks'])==32
    assert all(type(c['passed']) is bool for c in result['checks'])
    assert len([c for c in result['checks'] if 'temperature' in c])==22
    return {'measurements_valid':True,'checks_passed':sum(c['passed'] for c in result['checks']),
            'checks_total':32,'quality_passed':all(c['passed'] is True for c in result['checks'])}

def newest_result(label):
    paths=sorted((ROOT/'bench/results').glob('*-'+label+'/result.json'),key=lambda p:p.stat().st_mtime)
    return json.loads(paths[-1].read_text()) if paths else None

def execute(profile,index):
    args=settings(profile,index)
    print(f'LAUNCH {profile} {index}: {psutil.virtual_memory().available/1024**3:.2f} GiB available',flush=True)
    result=None
    try:
        with patch.object(benchmark,'Monitor',TrialMonitor):result=benchmark.run(args)
    except Exception as error:
        result=newest_result(args.label)
        if result is None:raise
        result.setdefault('error',f'{type(error).__name__}: {error}')
    entry={'run_id':result['run_id'],'profile':profile,'status':result['status'],
           'error':result.get('error'),'memory':result.get('memory'),
           'cases_completed':len(result.get('cases',[]))}
    record['runs'].append(entry);save()
    assert_no_model_server();assert_unchanged(record['model_provenance'])
    assert verify_engine('mtp-mma')==record['engine']
    assert fingerprint()==record['harness_sources']
    if result.get('memory',{}).get('guard'):
        print(f'MEMORY GUARD: {result["memory"]["guard"]}',flush=True)
        return None
    if result['status']=='failed':raise RuntimeError(result.get('error','Native benchmark failed'))
    entry.update(validation(result));save()
    if args.spec=='draft-mtp':
        log=(ROOT/'bench/results'/result['run_id']/'server.log').read_text()
        assert 'borrowing target embeddings/output; draft KV remains separate' in log
    return result

def summarize(results):
    rows=[]
    for key in sorted({(c['workload'],c['prompt_tokens']) for c in results[0]['cases']}):
        selected=[[c for c in r['cases'] if (c['workload'],c['prompt_tokens'])==key] for r in results]
        assert len({c['prompt_sha256'] for group in selected for c in group})==1
        row={'workload':key[0],'input_tokens':key[1],'metrics':metrics([c for group in selected for c in group]),
             'pass_metrics':[metrics(group) for group in selected],'samples':sum(len(group) for group in selected)}
        if len(selected)==2:row['launch_drift_percent']=100*(row['pass_metrics'][1]['generation_tok_s']/row['pass_metrics'][0]['generation_tok_s']-1)
        rows.append(row)
    for budget in (512,2048):
        selected=[[c for c in r['cached_cases'] if c['history_budget']==budget and not c['warmup']] for r in results]
        rows.append({'workload':'cached-ledger','input_tokens':budget,'metrics':metrics([c for group in selected for c in group],True),
                     'pass_metrics':[metrics(group,True) for group in selected],'samples':sum(len(group) for group in selected)})
    return rows

done=threading.Event()
watcher=threading.Thread(target=watch_resources,args=(folder/'resources.jsonl',done),daemon=True)
print(f'TRIAL {folder}',flush=True)
save()
try:
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert_no_model_server()
        record.update(offline_gate=require_pass(),harness_sources=fingerprint(),engine=verify_engine('mtp-mma'),
                      model_provenance=verify_models(['flash','mtp_shared_packed_q3']))
        save();watcher.start()
        first=execute('optimized-mtp',1)
        profile='optimized-mtp'
        if first is None:
            # A changed profile is capacity fallback evidence, never a speed comparison with the failed profile.
            samples=[]
            for _ in range(10):
                samples.append({'available_bytes':psutil.virtual_memory().available,'pressure':pressure()})
                if samples[-1]['pressure']==1 and samples[-1]['available_bytes']>=record['trial_admission_bytes']:break
                time.sleep(1)
            record['recovery']=samples;save()
            profile='target-only';first=execute(profile,1)
        if first is None:
            record['status']='stopped-memory-guard'
        else:
            clean=[first]
            if record['runs'][-1]['quality_passed']:
                second=execute(profile,2)
                if second is not None:clean.append(second)
            record['selected_profile']=profile
            record['summary']=summarize(clean)
            record['successful_launches']=len(clean)
            record['status']='passed' if len(clean)==2 and all(r['status']=='passed' for r in clean) else 'partial'
except BaseException as error:
    record.update(status='failed',error=f'{type(error).__name__}: {error}')
    raise
finally:
    done.set()
    if watcher.ident is not None:watcher.join(timeout=3)
    record['harness_unchanged']=fingerprint()==record.get('harness_sources')
    record['final_available_bytes']=psutil.virtual_memory().available
    record['final_swap_bytes']=psutil.swap_memory().used
    record['final_pressure']=pressure()
    save()
    print(f'COMPLETE {record["status"]}: {folder}',flush=True)
