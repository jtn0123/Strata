#!/usr/bin/env python3
"""Reclaim clean idle native-build cache, retaining files and benchmark gates."""
import fcntl
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import time

import psutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
helper = HERE / 'model-cache-trial.py'
spec = importlib.util.spec_from_file_location('cache_trial', helper)
cache = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cache)


def assert_idle():
    cache.assert_no_model_server()
    for process in psutil.process_iter(['pid', 'name', 'exe']):
        name = process.info.get('name') or ''
        exe = process.info.get('exe') or ''
        if name.startswith(('llama-', 'test-backend-ops')) or exe.startswith(str(ROOT / 'vendor/llama')):
            raise RuntimeError(f'Native workload still active: PID {process.pid}, {name}')


def main():
    candidates = json.loads(Path('/tmp/strata-idle-native-cache-candidates.json').read_text())
    if not candidates:
        raise RuntimeError('No previously inspected native cache candidates')
    for entry in candidates:
        path = ROOT / entry['path']
        relative = path.resolve().relative_to(ROOT / 'vendor')
        parts = relative.parts
        if (path.is_symlink() or len(parts) != 4 or not parts[0].startswith('llama')
                or not parts[1].startswith('build') or parts[2] != 'bin'
                or cache.identity(path) != entry['identity']):
            raise RuntimeError('Candidate is outside the inspected idle build outputs or changed')
    out = HERE / ('idle-build-cache-trial-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    record = dict(status='prepared', model_benchmark_launched=False, files=[], samples=[],
                  candidates=candidates, source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  helper_sha256=hashlib.sha256(helper.read_bytes()).hexdigest(),
                  method='Idle native build/bin files only; O_RDONLY/PROT_READ/MAP_SHARED/MS_INVALIDATE; no mapped reads/writes',
                  limitation='mincore residency is not a full physical-cache inventory; available RAM gain is measured separately')

    def save():
        (out / 'result.json').write_text(json.dumps(record, indent=2) + '\n')

    def capture(phase):
        sample = cache.measure.snapshot(phase)
        record['samples'].append(sample)
        save()
        return sample

    print('Evidence:', out, flush=True)
    with (ROOT / 'bench/.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            assert_idle()
            before = capture('before')
            record['before'] = before
            for entry in candidates:
                assert_idle()
                record['files'].append(cache.release(entry))
            immediate = capture('immediate-after')
            print(f"Available {before['available_gib']:.3f} -> {immediate['available_gib']:.3f} GiB", flush=True)
            record['status'] = 'cache released; measuring 60-second settle'
            save()
            for index in range(30):
                time.sleep(2)
                sample = capture('quiet-settle')
                if index % 5 == 4:
                    print(f"Settle {(index+1)*2}s: {sample['available_gib']:.3f} GiB; swap={sample['swap_used_bytes']} bytes", flush=True)
            assert_idle()
            unchanged = all(cache.identity(ROOT / entry['path']) == entry['identity'] for entry in candidates)
            if not unchanged:
                raise RuntimeError('An inspected build output changed')
            settled = [sample for sample in record['samples'] if sample['phase'] == 'quiet-settle']
            growth = max(0, max(sample['swap_used_bytes'] for sample in record['samples']) - before['swap_used_bytes'])
            eligible = min(sample['available_gib'] for sample in settled) >= 34 and growth == 0 and all(sample['pressure_level'] == 1 for sample in settled)
            record.update(status='measured; eligible for canonical preflight' if eligible else 'measured; existing benchmark gate not met',
                          after=settled[-1], available_gain_gib=settled[-1]['available_gib']-before['available_gib'],
                          settled_min_available_gib=min(sample['available_gib'] for sample in settled),
                          settled_max_available_gib=max(sample['available_gib'] for sample in settled),
                          swap_growth_bytes=growth, identities_unchanged=unchanged,
                          eligible_for_canonical_preflight=eligible,
                          gate='All settle samples >=34 GiB, normal pressure, zero new swap')
            save()
            print(json.dumps({key: record[key] for key in ('status', 'available_gain_gib', 'settled_min_available_gib', 'swap_growth_bytes', 'eligible_for_canonical_preflight')}, indent=2), flush=True)
        except BaseException as error:
            record.update(status='stopped; no benchmark launched', error=str(error))
            save()
            raise


if __name__ == '__main__':
    main()
