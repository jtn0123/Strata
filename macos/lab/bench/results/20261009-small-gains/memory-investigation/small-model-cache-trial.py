#!/usr/bin/env python3
"""Release the idle small-model cache; preserve files and full-model benchmark gates."""
import ctypes
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
from check_memory import assert_no_model_server
from model_provenance import assert_unchanged, identity, verify_models

spec = importlib.util.spec_from_file_location('purge_metrics', HERE / 'purge-trial.py')
measure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measure)

libc = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int,
                      ctypes.c_int, ctypes.c_int64]
libc.mmap.restype = ctypes.c_void_p
libc.msync.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
libc.msync.restype = ctypes.c_int
libc.mincore.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
libc.mincore.restype = ctypes.c_int
libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
libc.munmap.restype = ctypes.c_int
PAGE = os.sysconf('SC_PAGE_SIZE')
WINDOW = 256 * 1024**2


def resident(address, length):
    pages = 0
    for offset in range(0, length, WINDOW):
        size = min(WINDOW, length - offset)
        vector = (ctypes.c_ubyte * ((size + PAGE - 1) // PAGE))()
        if libc.mincore(address + offset, size, vector):
            raise OSError(ctypes.get_errno(), 'mincore failed')
        pages += sum(bool(value & 1) for value in vector)
    return pages * PAGE


def release(entry):
    path = ROOT / entry['path']
    before = identity(path)
    if before != entry['identity']:
        raise RuntimeError('Model identity changed before cache release')
    descriptor = os.open(path, os.O_RDONLY)
    address = None
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
                before['device'], before['inode'], before['size']):
            raise RuntimeError('Opened model differs from verified path')
        # PROT_READ=1, MAP_SHARED=1: no model data are read/written through this mapping.
        address = libc.mmap(None, before['size'], 1, 1, descriptor, 0)
        if address in (None, ctypes.c_void_p(-1).value):
            address = None
            raise OSError(ctypes.get_errno(), 'read-only mmap failed')
        observed_before = resident(address, before['size'])
        # MS_INVALIDATE=2, verified in this Mac's sys/mman.h and msync(2).
        ctypes.set_errno(0)
        result = libc.msync(address, before['size'], 2)
        error = ctypes.get_errno() if result else None
        observed_after = resident(address, before['size'])
        unchanged = identity(path) == before
        receipt = dict(path=entry['path'], identity_before=before,
                       identity_unchanged=unchanged, mapped_resident_before_bytes=observed_before,
                       mapped_resident_after_bytes=observed_after, msync_return=result, errno=error)
        if result or not unchanged:
            raise RuntimeError('Cache-release or file-identity failure: ' + json.dumps(receipt))
        return receipt
    finally:
        if address is not None and libc.munmap(address, before['size']):
            raise OSError(ctypes.get_errno(), 'munmap failed')
        os.close(descriptor)


def main():
    if sys.platform != 'darwin':
        raise RuntimeError('This cleanup is macOS-only')
    out = HERE / ('small-model-cache-trial-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    samples = []
    record = dict(status='prepared', method='Owned model files only; O_RDONLY/PROT_READ/MAP_SHARED/MS_INVALIDATE; no mapped content reads or writes',
                  mincore_limitation='Only residency visible to these new mappings; not a complete system-cache inventory',
                  model_benchmark_launched=False, samples=samples, files=[],
                  runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  metrics_runner_sha256=hashlib.sha256((HERE/'purge-trial.py').read_bytes()).hexdigest())
    def save():
        (out / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
    def capture(phase):
        value = measure.snapshot(phase)
        samples.append(value)
        save()
        return value
    print('Evidence:', out, flush=True)
    with (ROOT/'bench/.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert_no_model_server()
        try:
            proof = verify_models(['small'])
            record['model_provenance'] = proof
            before = capture('before')
            record['before'] = before
            print(f"Before: available={before['available_gib']:.3f} GiB; swap={before['swap_used_bytes']} bytes", flush=True)
            for model in proof['models'].values():
                for entry in model['files']:
                    assert_no_model_server()
                    receipt = release(entry)
                    record['files'].append(receipt)
                    current = capture('after-file')
                    print(f"Released {entry['path']}: visible cache {receipt['mapped_resident_before_bytes']/2**30:.3f} -> "
                          f"{receipt['mapped_resident_after_bytes']/2**30:.3f} GiB; available={current['available_gib']:.3f} GiB", flush=True)
            assert_unchanged(proof)
            record['status'] = 'cache release completed; measuring 60-second settle'
            save()
            for index in range(30):
                time.sleep(2)
                current = capture('quiet-settle')
                if index % 5 == 4:
                    print(f"Settle {(index+1)*2}s: available={current['available_gib']:.3f} GiB; swap={current['swap_used_bytes']} bytes", flush=True)
            settled = [s for s in samples if s['phase'] == 'quiet-settle']
            growth = max(0, max(s['swap_used_bytes'] for s in samples) - before['swap_used_bytes'])
            eligible = (min(s['available_gib'] for s in settled) >= 34 and
                        all(s['pressure_level'] == 1 for s in settled) and growth == 0)
            record.update(status='measured; eligible for canonical preflight' if eligible else 'measured; existing benchmark gate not met',
                          after=settled[-1], available_gain_gib=settled[-1]['available_gib']-before['available_gib'],
                          settled_min_available_gib=min(s['available_gib'] for s in settled),
                          settled_max_available_gib=max(s['available_gib'] for s in settled),
                          swap_growth_bytes=growth, eligible_for_canonical_preflight=eligible,
                          model_identities_unchanged=True,
                          gate='all settle samples >=34 GiB, normal pressure, zero new swap')
            save()
            print(json.dumps({k:record[k] for k in ['status','available_gain_gib','settled_min_available_gib',
                            'settled_max_available_gib','swap_growth_bytes','eligible_for_canonical_preflight']}, indent=2), flush=True)
        except BaseException as error:
            record.update(status='stopped on cleanup failure; no benchmark launched', error=str(error))
            save()
            raise


if __name__ == '__main__':
    main()
