"""Single bounded MLX paged reply, with exact source/model/build pins and owned cleanup."""
from datetime import datetime,timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
from benchmark import Monitor,host_snapshot
from check_memory import assert_no_model_server
from engines import sha256,verify_engine
from model_provenance import assert_unchanged,verify_models
from profile_m5_routes import preflight

def main():
    destination=HERE/'receipt.json'
    if destination.exists(): raise ValueError('Preserve the attempt; no automatic retry')
    if json.loads((HERE.parent/'mlx-load/receipt.json').read_text())['status']!='passed':
        raise ValueError('F32 loader check must pass first')
    source=ROOT/'vendor/strata-mlx-u10'
    preparation=json.loads((ROOT/'bench/results/20261010-next-tests/mlx/preparation.json').read_text())
    pins={name:sha256(source/name) for name in preparation['source_files']}
    if pins!=preparation['source_files']: raise ValueError('Prepared MLX sources changed')
    revision=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if revision!=preparation['revision']: raise ValueError('MLX revision changed')
    if subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip():
        raise ValueError('MLX checkout dirty')
    native=verify_engine('m5-small-stack')
    build=json.loads((HERE/'vocab-build.json').read_text())
    if build['engine']!=native or sha256(HERE/'vocab.cpp')!=build['source_sha256'] or sha256(build['binary'])!=build['binary_sha256']:
        raise ValueError('Vocabulary helper build is stale')
    plan_hash=sha256(HERE/'plan.json')
    model=ROOT/'models/flash/Q2_0/Qwen3.8-Flash-Next-GSQ-RCO-Q2_0-00001-of-00002.gguf'
    command=[str(ROOT/'bench/runtime/u10-mlx/.venv/bin/python'),str(HERE/'reply-check.py'),str(model),build['binary']]
    env=dict(os.environ,PYTHONPATH=str(source),PYTHONNOUSERSITE='1')
    record=dict(status='running',created_utc=datetime.now(timezone.utc).isoformat(),command=command,
        source_revision=revision,source_files=pins,vocab_build=build,plan_sha256=plan_hash,
        supervisor_sha256=sha256(__file__),reply_check_sha256=sha256(HERE/'reply-check.py'),
        adoption=False,matched_speed_gain=None,models_loaded=False,scope='Cold paged English feasibility; no paired TPS claim')
    def save(): destination.write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    with (ROOT/'bench/.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert_no_model_server(); before=preflight(small=True)
        if before['memory']['available']<24*1024**3: raise ValueError('Need 24 GiB available for the bounded reply')
        models=verify_models(['flash'])
        record.update(preflight=before,models=models,host_before=host_snapshot())
        process=monitor=None; save()
        try:
            with (HERE/'native.log').open('w') as log:
                baseline=Monitor.baseline()
                process=subprocess.Popen(command,stdout=log,stderr=log,env=env)
                monitor=Monitor(process,HERE/'memory.jsonl',0,8*1024**3,baseline=baseline)
                monitor.thread.start(); code=process.wait(timeout=300)
            memory=monitor.finish(); record.update(returncode=code,memory=memory)
            if code or memory['guard'] or memory['swap_growth_bytes'] or not memory['monitor_healthy'] or not memory['child_exited']:
                raise ValueError('Reply or resource guard failed; preserve this attempt')
            events=[json.loads(line) for line in (HERE/'native.log').read_text().splitlines() if line.startswith('{')]
            output=events[-1]
            if output.get('phase')!='complete' or output.get('status')!='passed' or output.get('generation_run') is not True or output.get('adoption') is not False:
                raise ValueError('Incomplete or changed reply scope')
            assert_unchanged(models)
            if {name:sha256(source/name) for name in pins}!=pins or verify_engine('m5-small-stack')!=native or sha256(HERE/'plan.json')!=plan_hash:
                raise ValueError('Sources, native helper engine or plan changed during the reply')
            record.update(status='passed',output=output,models_loaded=True,host_after=host_snapshot())
        except BaseException as error:
            record.update(status='failed',error=f'{type(error).__name__}: {error}'); raise
        finally:
            if process and process.poll() is None:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
            if monitor and 'memory' not in record: record['memory']=monitor.finish()
            save()
    print(json.dumps({key:record[key] for key in ('status','output','memory')},indent=2))

if __name__=='__main__': main()
