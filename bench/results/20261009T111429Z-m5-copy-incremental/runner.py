"""Run the user-authorized prepared full-model queue with strict live guards.

The maintained benchmark/diagnostic implementations remain unchanged. This
saved adapter tightens their guards and records the exact adapter and sources.
"""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import ctypes, fcntl, hashlib, json, os, statistics, threading, time
from datetime import datetime, timezone
from unittest.mock import patch
import psutil
import benchmark, benchmark_m5, benchmark_context, profile_m5_routes, profile_lookup_io, benchmark_m5_copy
from benchmark_tuning import watch_resources
from benchmark_metrics import metrics
from check_memory import assert_no_model_server
from engines import ENGINES, verify_engine
from model_provenance import verify_models, assert_unchanged, identity
from validate_offline import require_pass, fingerprint

GIB = 1024**3
folder = ROOT / 'bench/results' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-m5-copy-incremental')
folder.mkdir()
source = Path(__file__).read_bytes()
(folder / 'runner.py').write_bytes(source)
record = {'schema': 1, 'status': 'running', 'runner_sha256': hashlib.sha256(source).hexdigest(),
          'stages': [], 'admissions': [], 'cache_resets': [],
          'policy': {'minimum_available_before_bytes': 34*GIB, 'new_swap_stop_bytes': 0,
                     'pressure_stop_above': 1, 'minimum_available_during_bytes': GIB,
                     'minimum_available_grace_seconds': 4, 'measured_repeats': 3},
          'scope': 'Isolated native copy widths stock,scalar,4,8 bracketed by fresh stock controls. Three measured repeats, five fresh workloads, cached workloads and strict answer checks. No weights, model settings or existing launcher defaults change.'}
lib = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
lib.sysctlbyname.argtypes = [ctypes.c_char_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_size_t),ctypes.c_void_p,ctypes.c_size_t]
lib.sysctlbyname.restype = ctypes.c_int
lib.mmap.argtypes = [ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_longlong]
lib.mmap.restype = ctypes.c_void_p
lib.msync.argtypes = [ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int]
lib.msync.restype = ctypes.c_int
lib.munmap.argtypes = [ctypes.c_void_p,ctypes.c_size_t]
lib.munmap.restype = ctypes.c_int

def pressure():
    value = ctypes.c_int(); size = ctypes.c_size_t(ctypes.sizeof(value))
    if lib.sysctlbyname(b'kern.memorystatus_vm_pressure_level',ctypes.byref(value),ctypes.byref(size),None,0):
        raise OSError(ctypes.get_errno(),'Cannot read memory pressure')
    return value.value

def save():
    (folder/'batch.json').write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')

def verify_all():
    assert_no_model_server()
    assert_unchanged(record['model_provenance'])
    if fingerprint() != record['harness_sources']: raise RuntimeError('Harness sources changed')
    if any(verify_engine(name) != pin for name,pin in record['engines'].items()):
        raise RuntimeError('Native source or binary changed')
    if benchmark_m5_copy.verify() != record['diagnostic']: raise RuntimeError('Copy diagnostic changed')

def recover_idle_cache():
    """If needed, release only unused owned model file pages outside timing."""
    assert_no_model_server(); assert_unchanged(record['model_provenance'])
    before = psutil.virtual_memory().available
    if before >= 34*GIB: return
    entry = {'before_available_bytes':before,'files':[],'read_only':True}
    for model in record['model_provenance']['models'].values():
        for spec in model['files']:
            path = ROOT/spec['path']; before_id = identity(path)
            fd = os.open(path,os.O_RDONLY)
            address = None
            try:
                address = lib.mmap(None,before_id['size'],1,1,fd,0) # PROT_READ, MAP_SHARED
                if address == ctypes.c_void_p(-1).value:
                    address = None; raise OSError(ctypes.get_errno(),'Read-only mmap failed')
                if lib.msync(address,before_id['size'],2): # Darwin MS_INVALIDATE
                    raise OSError(ctypes.get_errno(),'Read-only cache invalidation failed')
            finally:
                if address is not None:
                    if lib.munmap(address,before_id['size']): raise OSError(ctypes.get_errno(),'munmap failed')
                os.close(fd)
            if identity(path) != before_id: raise RuntimeError('Model file identity changed')
            entry['files'].append({'path':spec['path'],'identity_unchanged':True})
    time.sleep(1)
    entry['after_available_bytes'] = psutil.virtual_memory().available
    record['cache_resets'].append(entry); save()
    print(f'Idle owned-file cache reset: {before/GIB:.2f} -> {entry["after_available_bytes"]/GIB:.2f} GiB available',flush=True)

original_monitor = benchmark.Monitor
original_baseline = original_monitor.baseline
def admission():
    recover_idle_cache()
    samples = [psutil.cpu_percent(interval=1) for _ in range(3)]
    assert_no_model_server(); assert_unchanged(record['model_provenance'])
    if fingerprint() != record['harness_sources']: raise RuntimeError('Harness sources changed before launch')
    base = original_baseline(); level = pressure()
    record['admissions'].append({**base,'pressure_level':level,'cpu_percent_samples':samples}); save()
    if base['available_bytes'] < 34*GIB or level != 1: raise RuntimeError('Full model deferred: insufficient RAM or increased pressure')
    if max(samples)>25 or statistics.mean(samples)>15: raise RuntimeError(f'Host busy: {samples}')
    return base

class GuardedMonitor(original_monitor):
    baseline = staticmethod(admission)
    def __init__(self,process,path,swap_guard_bytes=0,minimum_available_bytes=GIB,*,baseline=None):
        super().__init__(process,path,0,GIB,baseline=baseline)
    def sample(self,mem=None):
        sample = super().sample(mem); sample['pressure_level'] = pressure()
        if self.process.poll() is None and sample['pressure_level']>1:
            self.guard = f'Stopped owned server: memory pressure level {sample["pressure_level"]}'
            self.stop_owned_child()
        return sample

original_settings = benchmark_m5.settings
def guarded_settings(*args,**kwargs):
    settings = original_settings(*args,**kwargs)
    settings.swap_guard_bytes = 0
    return settings

original_preflight = profile_m5_routes.preflight
def guarded_preflight(small=False,quiet=True):
    if not small: recover_idle_cache()
    return original_preflight(small,quiet)

def artifact_paths():
    return set((ROOT/'bench/results').glob('*/comparison.json')) | set((ROOT/'bench/features').glob('*-batch/batch.json')) | set((ROOT/'bench/features').glob('*-lookup-io/probe.json'))

def validate_speed_records(paths):
    runs=[]
    for path in paths:
        obj=json.loads(path.read_text())
        if 'order' not in obj: continue
        for ref in obj.get('runs',[]):
            run=ref if 'cases' in ref else json.loads((ROOT/'bench/results'/ref['run_id']/'result.json').read_text())
            memory=run['memory']
            if memory['guard'] or not memory['monitor_healthy'] or not memory['child_exited'] or memory['swap_growth_bytes']!=0:
                raise RuntimeError('Run memory acceptance failed')
            expected={('synthetic',512),('synthetic',2048),('code',48),('prose',53),('chinese',56)}
            groups={}
            for case in run['cases']:
                groups.setdefault((case['workload'],case['prompt_tokens']),[]).append(case)
            if set(groups)!=expected: raise RuntimeError('Unexpected/incomplete measured workloads')
            for cases in groups.values():
                if sorted(c['repeat'] for c in cases)!=[1,2,3]: raise RuntimeError('Measured repeats incomplete')
                if len({c['prompt_sha256'] for c in cases})!=1: raise RuntimeError('Prompt drift')
                metrics(cases)
            if len(run['checks']) not in (32,35) or not all(c['passed'] is True for c in run['checks']):
                raise RuntimeError('Incomplete or failed answer checks')
            runs.append({'run_id':run['run_id'],'checks':len(run['checks']),'memory':memory})
    return runs

def stage(name,callback):
    verify_all(); before=artifact_paths()
    entry={'name':name,'status':'running','started_utc':datetime.now(timezone.utc).isoformat()}
    record['stages'].append(entry); save(); print(f'STAGE {name}',flush=True)
    try:
        callback()
        verify_all()
        paths=sorted(artifact_paths()-before)
        entry['artifacts']=[str(p.relative_to(ROOT)) for p in paths]
        if not paths or any(json.loads(p.read_text())['status']!='passed' for p in paths):
            raise RuntimeError('Missing or rejected stage artifact')
        entry['speed_run_acceptance']=validate_speed_records(paths)
        entry['status']='passed'
    except Exception as error:
        entry.update(status='failed',error=f'{type(error).__name__}: {error}',
                     artifacts=[str(p.relative_to(ROOT)) for p in sorted(artifact_paths()-before)])
        print(f'STAGE FAILED {name}: {entry["error"]}',flush=True)
        verify_all() # Source drift or failed child cleanup halts the entire batch.
    finally:
        entry['ended_utc']=datetime.now(timezone.utc).isoformat(); save()
    print(f'STAGE COMPLETE {name}: {entry["status"]}',flush=True)

def lookup():
    inventory=ROOT/'bench/results/flash-gguf-inventory.json'
    spec=profile_lookup_io.plan(json.loads(inventory.read_text()),128,os.sysconf('SC_PAGE_SIZE'))
    spec['inventory_sha256']=hashlib.sha256(inventory.read_bytes()).hexdigest()
    spec['preflight']=original_preflight(small=True)
    dest=ROOT/'bench/features'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-lookup-io')
    profile_lookup_io.execute(spec,ROOT/'models/flash'/spec['file'],dest)


def shape_inventory():
    import socket,subprocess
    from lab import request,server_command
    from metal_environment import configure
    verify_all()
    dest=folder/'shape-inventory';dest.mkdir()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    command=server_command('flash',port,4096,512,512,'draft-mtp',3,draft_placement='mixed',draft_model='mtp_shared_packed_q3',engine='m5-copy',draft_threads=8,draft_p_min=0.0)
    env,flags=configure(os.environ,'m5-copy','on','copy-v4')
    env['GGML_M5_LAB_COPY_TRACE']='1'
    entry={'status':'running','command':command,'metal_environment':flags,'trace_variable':'GGML_M5_LAB_COPY_TRACE=1','timings_excluded_from_speed_results':True,'requests':[]}
    proc=monitor=None
    try:
        with (dest/'native.log').open('w') as log:
            baseline=admission()
            proc=subprocess.Popen(command,stdout=log,stderr=log,env=env)
            monitor=GuardedMonitor(proc,dest/'memory.jsonl',baseline=baseline);monitor.thread.start()
            base=f'http://127.0.0.1:{port}';benchmark.wait_ready(proc,base)
            filler='Explain how to compare AI inference speed and memory usage in plain language. '*1000
            rendered=request(base,'/apply-template',{'messages':[{'role':'user','content':filler}],'chat_template_kwargs':{'enable_thinking':False}})['prompt']
            tokens=request(base,'/tokenize',{'content':rendered,'add_special':False,'parse_special':True})['tokens']
            for length,predict in ((512,16),(512,32),(2048,32)):
                prompt=tokens[:length-48]+tokens[-48:]
                response=request(base,'/completion',{'prompt':prompt,'n_predict':predict,'ignore_eos':True,'temperature':0,'seed':1234,'cache_prompt':False,'return_tokens':True})
                if response['timings']['prompt_n']!=length or response['timings']['predicted_n']!=predict:raise RuntimeError('Diagnostic token count mismatch')
                entry['requests'].append({'prompt_tokens':length,'output_tokens':predict,'response':response})
        entry['status']='completed'
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
        if monitor:entry['memory']=monitor.finish()
        text=(dest/'native.log').read_text()
        entry['shapes']=[json.loads(s.split('M5_COPY_SHAPE ',1)[1]) for s in text.splitlines() if 'M5_COPY_SHAPE ' in s]
        entry['eligible_large_state_shapes']=[s for s in entry['shapes'] if s['eligible'] and s['src_ne'][0]==786432 and s['src_ne'][2] in (4,5)]
        if entry['status']=='completed' and entry['eligible_large_state_shapes'] and not entry['memory']['guard'] and entry['memory']['monitor_healthy'] and entry['memory']['swap_growth_bytes']==0:entry['status']='passed'
        else:entry['status']='failed'
        (dest/'inventory.json').write_text(json.dumps(entry,indent=2)+'\n')
    if entry['status']!='passed':raise RuntimeError('Shape diagnostic incomplete or guarded')
    print(f"COPY SHAPES {len(entry['shapes'])}, eligible state shapes {len(entry['eligible_large_state_shapes'])}",flush=True)
    verify_all()

done=threading.Event()
watcher=threading.Thread(target=watch_resources,args=(folder/'resources.jsonl',done),daemon=True)
print(f'BATCH {folder}',flush=True);save()
try:
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        record.update(offline_gate=require_pass(),harness_sources=fingerprint(),
                      engines={n:verify_engine(n) for n in ENGINES},diagnostic=benchmark_m5_copy.verify(),
                      model_provenance=verify_models(['flash','mtp_shared_packed_q3']))
        save(); watcher.start()
        with patch.object(benchmark,'Monitor',GuardedMonitor), \
             patch.object(profile_m5_routes,'Monitor',GuardedMonitor), \
             patch.object(profile_m5_routes,'preflight',guarded_preflight), \
             patch.object(benchmark_m5,'settings',guarded_settings), \
             patch.object(benchmark_context,'base_settings',guarded_settings):
            shape_inventory()
            stage('copy-kernels',lambda:benchmark_m5.execute(next(s for s in benchmark_m5.experiments() if s['id']=='copy-kernels'),3))
        verify_all()
        record['status']='passed' if all(s['status']=='passed' for s in record['stages']) else 'partial'
except BaseException as error:
    record.update(status='failed',error=f'{type(error).__name__}: {error}'); raise
finally:
    done.set()
    if watcher.ident is not None:watcher.join(timeout=3)
    record['final_available_bytes']=psutil.virtual_memory().available
    record['final_swap_bytes']=psutil.swap_memory().used
    record['final_pressure_level']=pressure()
    record['harness_unchanged']=fingerprint()==record.get('harness_sources')
    save(); print(f'BATCH COMPLETE {record["status"]}: {folder}',flush=True)
