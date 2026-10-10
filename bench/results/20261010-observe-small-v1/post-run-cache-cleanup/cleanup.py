#!/usr/bin/env python3
"""Release the owned small-model clean cache freshly touched by this campaign."""
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
from check_memory import assert_no_model_server
from model_provenance import assert_unchanged, verify_models

HELPER = ROOT / 'bench/results/20261009-small-gains/memory-investigation/model-cache-trial.py'
spec = importlib.util.spec_from_file_location('owned_cache', HELPER)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def main():
    output = HERE / 'receipt.json'
    if output.exists():
        raise RuntimeError('Cleanup already attempted; preserve its receipt')
    samples = []
    record = dict(status='prepared', started_utc=datetime.now(timezone.utc).isoformat(),
        reason='The completed four-arm small-model baseline freshly touched this model cache',
        method='Owned small model only: read-only mapping and MS_INVALIDATE; no content reads, writes or deletion',
        limitation='mincore measures residency visible to these mappings, not unique physical cache or available RAM',
        model_benchmark_launched=False, unrelated_processes_stopped=False, samples=samples, files=[],
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        helper_sha256=hashlib.sha256(HELPER.read_bytes()).hexdigest(),
        metrics_helper_sha256=hashlib.sha256((HELPER.parent/'purge-trial.py').read_bytes()).hexdigest())

    def save():
        output.write_text(json.dumps(record, indent=2, allow_nan=False) + '\n')

    def capture(phase):
        value = helper.measure.snapshot(phase)
        samples.append(value)
        save()
        return value

    with (ROOT/'bench/.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert_no_model_server()
        try:
            proof = verify_models(['small'])
            record['model_provenance'] = proof
            before = capture('before')
            print(f"Before: {before['available_gib']:.3f} GiB available", flush=True)
            for model in proof['models'].values():
                for entry in model['files']:
                    assert_no_model_server()
                    record['files'].append(helper.release(entry))
                    capture('after-file')
            assert_unchanged(proof)
            for index in range(30):
                time.sleep(2)
                current = capture('quiet-settle')
                if index % 5 == 4:
                    print(f"Settle {(index+1)*2}s: {current['available_gib']:.3f} GiB available", flush=True)
            settled = [s for s in samples if s['phase']=='quiet-settle']
            growth = max(0, max(s['swap_used_bytes'] for s in samples)-before['swap_used_bytes'])
            record.update(status='completed', model_identities_unchanged=True,
                available_gain_gib=settled[-1]['available_gib']-before['available_gib'],
                settled_min_available_gib=min(s['available_gib'] for s in settled),
                settled_max_available_gib=max(s['available_gib'] for s in settled),
                swap_growth_bytes=growth,
                eligible_for_canonical_preflight=min(s['available_gib'] for s in settled)>=34 and
                    all(s['pressure_level']==1 for s in settled) and growth==0)
            save()
        except BaseException as error:
            record.update(status='failed', error=f'{type(error).__name__}: {error}')
            save()
            raise


if __name__=='__main__':
    main()
