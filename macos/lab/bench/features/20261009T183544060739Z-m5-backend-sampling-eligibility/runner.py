import fcntl,json,os,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
from benchmark import Monitor
from check_memory import assert_no_model_server,snapshot
from engines import ENGINES,sha256,verify_engine
from metal_environment import configure
from validate_offline import require_pass
with (ROOT/'bench/.lock').open('w') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);require_pass();assert_no_model_server()
 folder=ROOT/'bench/features'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-m5-backend-sampling-eligibility');folder.mkdir()
 pins={e:verify_engine(e) for e in ENGINES};(ROOT/'bench/runtime/m5-sampling-next-research/existing-engines.json').write_text(json.dumps(pins,indent=2)+'\n')
 native=ROOT/pins['m5-copy']['directory'];source=ROOT/'native/m5_sampling_probe.cpp';binary=folder/'sampling-probe'
 command=['/usr/bin/c++','-O3','-ffp-contract=off','-std=gnu++17','-arch','arm64','-I'+str(native/'include'),'-I'+str(native/'ggml/include'),'-I'+str(native/'vendor'),str(source),'-o',str(binary),'-Wl,-rpath,'+str(native/'build/bin'),*[str(native/'build/bin'/f) for f in ('libllama.0.6.0.dylib','libggml.0.26.0.dylib','libggml-base.0.26.0.dylib','libggml-metal.0.26.0.dylib')]]
 record=dict(status='running',models_loaded=False,timings_measured=False,engine=pins['m5-copy'],command=command,source_sha256=sha256(source),runner_sha256=sha256(__file__),host_before=snapshot())
 process=monitor=None
 try:
  with (folder/'build.log').open('w') as log:subprocess.run(command,stdout=log,stderr=log,check=True)
  record['binary_sha256']=sha256(binary);env,flags=configure(os.environ,'m5-copy','on','conv-direct');record['metal_environment']=flags
  with (folder/'native.log').open('w') as log:
   baseline=Monitor.baseline();process=subprocess.Popen([binary],env=env,stdout=log,stderr=log);monitor=Monitor(process,folder/'memory.jsonl',0,2**30,baseline=baseline);monitor.thread.start();code=process.wait(timeout=90)
  record['memory']=monitor.finish();text=(folder/'native.log').read_text();cases=[json.loads(l.split(' ',1)[1]) for l in text.splitlines() if l.startswith('M5_SAMPLING_CASE ')];done=[json.loads(l.split(' ',1)[1]) for l in text.splitlines() if l.startswith('M5_SAMPLING_DONE ')]
  if code or len(cases)!=8 or len(done)!=1 or done[0]['cases']!=8 or record['memory']['guard'] or record['memory']['swap_growth_bytes'] or not record['memory']['monitor_healthy']:raise RuntimeError('Incomplete or unsafe native screen')
  if any(not c['boundary'] and not c['identical_eligibility'] for c in cases):raise RuntimeError('Separated control eligibility changed')
  if any(not c['input_bytes_preserved'] or not c['all_ops_supported_on_metal'] for c in cases):raise RuntimeError('Wrong input or backend path')
  record.update(status='passed',cases=cases,completion=done[0],decision='park-full-backend-sampling' if done[0]['eligibility_mismatches'] else 'requires-more-accuracy-tests',scope='Controlled min-p stage; not a model-quality evaluation, complete-chain sampling trial or TPS benchmark.')
 except BaseException as e:record.update(status='failed',error=str(e));raise
 finally:
  if process and process.poll() is None:process.terminate();process.wait(timeout=5)
  if monitor and 'memory' not in record:record['memory']=monitor.finish()
  record['host_after']=snapshot();record['existing_engines_unchanged']=all(verify_engine(e)==pin for e,pin in pins.items());assert_no_model_server();(folder/'checks.json').write_text(json.dumps(record,indent=2,allow_nan=False)+'\n');(folder/'runner.py').write_bytes(Path(__file__).read_bytes());(folder/'m5_sampling_probe.cpp').write_bytes(source.read_bytes());print(json.dumps(dict(folder=str(folder),status=record['status'],decision=record.get('decision'),completion=record.get('completion'),existing_engines_unchanged=record['existing_engines_unchanged'])),flush=True)
