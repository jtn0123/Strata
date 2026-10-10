"""Run the device smoke once under the lab lock and an owned-child memory monitor."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import fcntl

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT/'scripts'))
from benchmark import Monitor, host_snapshot
from check_memory import assert_no_model_server
from engines import sha256
from profile_m5_routes import preflight


def main():
    destination = HERE/'receipt.json'
    if destination.exists():
        raise ValueError('Preserve the completed attempt; no automatic retry')
    source = ROOT/'vendor/strata-mlx-u10'
    preparation = json.loads((ROOT/'bench/results/20261010-next-tests/mlx/preparation.json').read_text())
    pins = {name: sha256(source/name) for name in preparation['source_files']}
    if pins != preparation['source_files']:
        raise ValueError('MLX source differs from prepared revision')
    revision = subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if revision != preparation['revision']:
        raise ValueError('MLX revision changed')
    if subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip():
        raise ValueError('MLX source checkout is dirty')
    command = [str(ROOT/'bench/runtime/u10-mlx/.venv/bin/python'),str(HERE/'device-smoke.py')]
    env = dict(os.environ, PYTHONPATH=str(source), PYTHONNOUSERSITE='1')
    record = dict(status='running', command=command, revision=revision,
        created_utc=datetime.now(timezone.utc).isoformat(), models_loaded=False,
        throughput_measured=False, adoption=False, source_files=pins,
        smoke_sha256=sha256(HERE/'device-smoke.py'), supervisor_sha256=sha256(__file__),
        guard='Zero new swap; 8 GiB admission, 4 GiB sustained availability floor, 90s timeout. Allocator limit is only a guideline.')
    def save():
        destination.write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    with (ROOT/'bench/.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert_no_model_server()
        before = preflight(small=True)
        if before['memory']['available'] < 8*1024**3:
            raise ValueError('Need 8 GiB available before the device check')
        record.update(preflight=before, host_before=host_snapshot())
        process = monitor = None
        save()
        try:
            with (HERE/'native.log').open('w') as log:
                baseline = Monitor.baseline()
                process = subprocess.Popen(command,stdout=log,stderr=log,env=env)
                monitor = Monitor(process,HERE/'memory.jsonl',0,4*1024**3,baseline=baseline)
                monitor.thread.start()
                code = process.wait(timeout=90)
            memory = monitor.finish()
            record.update(returncode=code,memory=memory)
            if code or memory['guard'] or memory['swap_growth_bytes'] or not memory['monitor_healthy'] or not memory['child_exited']:
                raise ValueError('Device or resource check failed; preserve the log')
            output = json.loads((HERE/'native.log').read_text())
            if output['status']!='passed' or output['models_loaded'] or output['throughput_measured']:
                raise ValueError('Unexpected device check scope')
            if {name:sha256(source/name) for name in pins} != pins:
                raise ValueError('Source changed during the check')
            record.update(status='passed',output=output,host_after=host_snapshot())
        except BaseException as error:
            record.update(status='failed',error=f'{type(error).__name__}: {error}')
            raise
        finally:
            if process and process.poll() is None:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
            if monitor and 'memory' not in record:
                record['memory']=monitor.finish()
            save()
    print(json.dumps({key:record[key] for key in ('status','output','memory')},indent=2))


if __name__=='__main__':
    main()
