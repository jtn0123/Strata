import importlib.util,pathlib,sys,json,os,time,fcntl,psutil,hashlib
from datetime import datetime,timezone
ROOT=pathlib.Path('/Users/justin/Documents/Github/Strata-Mac-Lab')
OUT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
from check_memory import assert_no_model_server
from model_provenance import verify_models,assert_unchanged
src=ROOT/'bench/results/20261009-small-gains/memory-investigation/model-cache-trial.py'
spec=importlib.util.spec_from_file_location('cache_release',src);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
record={'status':'prepared','user_authorized_safe_cleanup':True,'benchmark_run':False,'actions':[],'samples':[],'runner_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'no_service_disabled':True,'T3_Codex_preserved':True}
def save(): (OUT/'receipt.json').write_text(json.dumps(record,indent=2)+'\n')
def capture(phase):
 r=m.measure.snapshot(phase);record['samples'].append(r);save();return r
with (ROOT/'bench/.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);assert_no_model_server()
 try:
  record['before']=capture('before');print('Before',record['before']['available_gib'],flush=True)
  proof=verify_models(['flash','mtp_shared_packed_q3']); record['model_provenance']=proof
  for model in proof['models'].values():
   for entry in model['files']:
    assert_no_model_server();r=m.release(entry);record['actions'].append({'type':'owned_clean_file_cache_release',**r});s=capture('after-model-file');print('Released',r['path'],'residentGiB',r['mapped_resident_before_bytes']/2**30,'available',s['available_gib'],flush=True)
  assert_unchanged(proof);record['model_identities_unchanged']=True
  p=psutil.Process(31838);expected='/System/Library/PrivateFrameworks/MediaAnalysis.framework/Versions/A/mediaanalysisd'
  if p.exe()!=expected or p.uids().real!=os.getuid() or abs(p.create_time()-1791638548.595563)>0.001:raise RuntimeError('Media-analysis process identity changed; no signal sent')
  p.cpu_percent();time.sleep(1);cpu=p.cpu_percent()
  if cpu>1.0:raise RuntimeError('Media analysis is active; no signal sent')
  before=capture('before-media-stop');action={'type':'verified_idle_media_analysis_SIGTERM','pid':p.pid,'exe':p.exe(),'uid':p.uids().real,'created':p.create_time(),'cpu_percent':cpu,'rss_bytes':p.memory_info().rss};record['actions'].append(action);save()
  p.terminate();action['signal_sent']='SIGTERM'
  try:p.wait(timeout=5);action['original_process_exited']=True
  except psutil.TimeoutExpired:action['original_process_exited']=False;raise RuntimeError('Media process did not exit; no forced kill')
  s=capture('after-media-stop');print('After media stop',s['available_gib'],flush=True)
  record['status']='cleanup completed; settling';save()
  for i in range(30):
   time.sleep(2);s=capture('quiet-settle')
   if i%5==4:print('Settle',2*(i+1),'s available',s['available_gib'],flush=True)
  settled=[s for s in record['samples'] if s['phase']=='quiet-settle'];growth=max(0,max(s['swap_used_bytes'] for s in record['samples'])-record['before']['swap_used_bytes']);eligible=min(s['available_gib'] for s in settled)>=34 and all(s['pressure_level']==1 for s in settled) and growth==0
  record.update(status='completed; native resource settle qualified' if eligible else 'completed; native admission still held',after=settled[-1],available_gain_gib=settled[-1]['available_gib']-record['before']['available_gib'],settled_min_available_gib=min(s['available_gib'] for s in settled),settled_max_available_gib=max(s['available_gib'] for s in settled),swap_growth_bytes=growth,eligible_for_native_preflight=eligible,media_processes_after=[{'pid':p.pid,'name':p.info['name']} for p in psutil.process_iter(['name']) if p.info['name']=='mediaanalysisd']);save()
  print(json.dumps({k:record[k] for k in ['status','available_gain_gib','settled_min_available_gib','settled_max_available_gib','swap_growth_bytes','eligible_for_native_preflight']}),flush=True)
 except BaseException as e:
  record['status']='cleanup stopped';record['error']=repr(e);save();raise
