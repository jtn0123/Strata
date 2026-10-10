"""One owned-child MLX F32 loader attempt; guarded, source/model pinned and not retried."""
from datetime import datetime, timezone
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
from engines import sha256
from model_provenance import assert_unchanged,verify_models
from profile_m5_routes import preflight

def main():
    destination=HERE/'receipt.json'
    if destination.exists(): raise ValueError('Keep the completed attempt; no automatic retry')
    smoke=json.loads((HERE.parent/'mlx-device/receipt.json').read_text())
    if smoke['status']!='passed': raise ValueError('Device smoke did not pass')
    source=ROOT/'vendor/strata-mlx-u10'
    preparation=json.loads((ROOT/'bench/results/20261010-next-tests/mlx/preparation.json').read_text())
    pins={name:sha256(source/name) for name in preparation['source_files']}
    if pins!=preparation['source_files']: raise ValueError('Prepared MLX sources changed')
    revision=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if revision!=preparation['revision']: raise ValueError('MLX revision changed')
    if subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip():
        raise ValueError('MLX checkout is dirty')
    model=ROOT/'models/flash/Q2_0/Qwen3.8-Flash-Next-GSQ-RCO-Q2_0-00001-of-00002.gguf'
    command=[str(ROOT/'bench/runtime/u10-mlx/.venv/bin/python'),str(HERE/'load-check.py'),str(model)]
    env=dict(os.environ,PYTHONPATH=str(source),PYTHONNOUSERSITE='1')
    record=dict(status='running',created_utc=datetime.now(timezone.utc).isoformat(),command=command,
        source_revision=revision,source_files=pins,supervisor_sha256=sha256(__file__),
        load_check_sha256=sha256(HERE/'load-check.py'),expert_budget_bytes=12_000_000_000,
        sampling='No prompt or generation',adoption=False,
        scope='Physical full-model F32 loader and initial-state check, empty expert cache; not a filled-cache capacity or TPS claim',
        guard='24 GiB available admission, normal pressure; zero new swap, 8 GiB sustained availability floor, 300s timeout. MLX 20 GiB allocator limit is only a guideline.')
    def save(): destination.write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    with (ROOT/'bench/.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert_no_model_server()
        before=preflight(small=True)
        if before['memory']['available']<24*1024**3: raise ValueError('Need 24 GiB available for F32 loader check')
        models=verify_models(['flash'])
        record.update(preflight=before,models=models,host_before=host_snapshot())
        process=monitor=None
        save()
        try:
            with (HERE/'native.log').open('w') as log:
                baseline=Monitor.baseline()
                process=subprocess.Popen(command,stdout=log,stderr=log,env=env)
                monitor=Monitor(process,HERE/'memory.jsonl',0,8*1024**3,baseline=baseline)
                monitor.thread.start(); code=process.wait(timeout=300)
            memory=monitor.finish(); record.update(returncode=code,memory=memory)
            if code or memory['guard'] or memory['swap_growth_bytes'] or not memory['monitor_healthy'] or not memory['child_exited']:
                raise ValueError('Loader or resource guard failed; retain this attempt')
            events=[json.loads(line) for line in (HERE/'native.log').read_text().splitlines() if line.startswith('{')]
            output=events[-1]
            if output.get('phase')!='complete' or output.get('status')!='passed' or output.get('generation_run') is not False:
                raise ValueError('Incomplete or changed loader scope')
            assert_unchanged(models)
            if {name:sha256(source/name) for name in pins}!=pins: raise ValueError('MLX source changed during load')
            record.update(status='passed',output=output,host_after=host_snapshot())
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
