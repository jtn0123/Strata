import importlib.util,pathlib,os,psutil,time,json,fcntl,sys,hashlib
from datetime import datetime,timezone
ROOT=pathlib.Path('/Users/justin/Documents/Github/Strata-Mac-Lab');OUT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'));from check_memory import assert_no_model_server
source=ROOT/'bench/results/20261009-small-gains/memory-investigation/purge-trial.py';spec=importlib.util.spec_from_file_location('metrics',source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
r={'status':'prepared','benchmark_run':False,'samples':[],'no_service_disabled':True,'T3_Codex_preserved':True,'runner_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()}
def save():(OUT/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
def capture(phase):
 s=m.snapshot(phase);r['samples'].append(s);save();return s
with (ROOT/'bench/.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);assert_no_model_server()
 try:
  r['before']=capture('before');p=psutil.Process(7021)
  if p.exe()!='/usr/libexec/textunderstandingd' or p.uids().real!=os.getuid() or abs(p.create_time()-1791616932.486338)>0.001:raise RuntimeError('Process identity changed; no signal sent')
  p.cpu_percent();time.sleep(1);cpu=p.cpu_percent()
  if cpu>1:raise RuntimeError('Text analysis is active; no signal sent')
  r['process']={'pid':p.pid,'exe':p.exe(),'uid':p.uids().real,'created':p.create_time(),'cpu_percent':cpu,'rss_bytes':p.memory_info().rss};save();p.terminate();r['signal_sent']='SIGTERM'
  try:p.wait(timeout=5);r['original_process_exited']=True
  except psutil.TimeoutExpired:r['original_process_exited']=False;raise RuntimeError('No exit; no forced kill')
  s=capture('after');print('Immediate available',s['available_gib'],flush=True)
  for i in range(30):
   time.sleep(2);s=capture('quiet-settle')
   if i%5==4:print('Settle',2*(i+1),'available',s['available_gib'],flush=True)
  settled=[s for s in r['samples'] if s['phase']=='quiet-settle'];growth=max(0,max(s['swap_used_bytes'] for s in r['samples'])-r['before']['swap_used_bytes']);eligible=min(s['available_gib'] for s in settled)>=34 and all(s['pressure_level']==1 for s in settled) and growth==0
  r.update(status='completed',after=settled[-1],available_gain_gib=settled[-1]['available_gib']-r['before']['available_gib'],settled_min_available_gib=min(s['available_gib'] for s in settled),settled_max_available_gib=max(s['available_gib'] for s in settled),swap_growth_bytes=growth,eligible_for_native_preflight=eligible,text_processes_after=[{'pid':p.pid,'name':p.info['name']} for p in psutil.process_iter(['name']) if p.info['name']=='textunderstandingd']);save();print(json.dumps({k:r[k] for k in ['status','available_gain_gib','settled_min_available_gib','settled_max_available_gib','swap_growth_bytes','eligible_for_native_preflight']}),flush=True)
 except BaseException as e:r['status']='stopped';r['error']=repr(e);save();raise
