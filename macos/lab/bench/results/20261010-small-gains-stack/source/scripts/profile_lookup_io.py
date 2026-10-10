#!/usr/bin/env python3
"""Plan bounded reads of the lazy lookup file. Only --run performs payload I/O."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import time

from lab import ROOT

MAX_READ_BYTES = 8 * 1024**2


def spans(tensor, file_size, count=128, seed=1234, page_size=16384):
    if type(count) is not int or not 1 <= count <= 128: raise ValueError('Use 1-128 sampled rows')
    if tensor['quant'] != 'IQ4_NL' or len(tensor['shape']) != 2: raise ValueError('Unsupported lazy lookup layout')
    width, rows = tensor['shape']
    if width % 32 or tensor['size_bytes'] != rows * (width // 32 * 18): raise ValueError('Invalid IQ4_NL row geometry')
    row_bytes = width // 32 * 18
    start = tensor['offset']
    if min(rows, page_size) <= 0 or start < 0 or start + tensor['size_bytes'] > file_size: raise ValueError('Lookup exceeds shard bounds')
    result=[]
    for row in random.Random(seed).sample(range(rows), count):
        offset = start + row * row_bytes
        aligned = offset // page_size * page_size
        end = min(file_size, ((offset + row_bytes + page_size - 1) // page_size) * page_size)
        result.append({'row': row, 'offset': aligned, 'length': end-aligned})
    if sum(r['length'] for r in result) * 3 > MAX_READ_BYTES: raise ValueError('Probe exceeds total 8 MiB read bound')
    return result


def plan(inventory, count=128, page_size=16384):
    found=[(s,t) for s in inventory['shards'] for t in s['tensors'] if 'per_layer_token_embd' in t['name']]
    if len(found) != 1: raise ValueError('Expected exactly one separate lazy lookup tensor')
    shard, tensor = found[0]
    return {'schema':1,'status':'not-run','models_loaded':False,'gpu_tests_run':False,'benchmark_run':False,
            'file':shard['path'],'expected_file_bytes':shard['expected_file_bytes'],
            'tensor':tensor,'page_size':page_size,'samples':spans(tensor,shard['expected_file_bytes'],count,page_size=page_size),
            'passes':['sampled-first-pass','same-offset-repeat','ordered-repeat'],
            'maximum_total_read_bytes':MAX_READ_BYTES,'changes_model_files':False,'cache_purge':False,
            'limits':'Read-only pread fixture, not mmap-fault or native inference wait measurement. First pass cache state is unknown; repeat passes may be cached. No SSD-to-RAM equivalence or TPS gain can be inferred.'}


def execute(record, path, folder):
    before = path.stat()
    if before.st_size != record['expected_file_bytes']: raise RuntimeError('Lookup shard size changed')
    folder.mkdir(parents=True,exist_ok=False)
    output=folder/'probe.json'
    def save(): output.write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    record.update(status='running',benchmark_run=True,runs=[],file_identity={'size':before.st_size,'mtime_ns':before.st_mtime_ns,'inode':before.st_ino})
    save()
    try:
        with path.open('rb') as source:
            for name in record['passes']:
                samples=sorted(record['samples'],key=lambda s:s['offset']) if name=='ordered-repeat' else record['samples']
                reads=[]
                for sample in samples:
                    started=time.perf_counter_ns()
                    data=os.pread(source.fileno(),sample['length'],sample['offset'])
                    elapsed=time.perf_counter_ns()-started
                    if len(data)!=sample['length'] or elapsed<=0: raise RuntimeError('Short lookup read or invalid latency')
                    reads.append({**sample,'elapsed_ns':elapsed,'sha256':hashlib.sha256(data).hexdigest()})
                times=sorted(r['elapsed_ns'] for r in reads)
                record['runs'].append({'pass':name,'reads':reads,'bytes':sum(r['length'] for r in reads),
                    'median_read_us':statistics.median(times)/1000,'p95_read_us':times[(len(times)*95-1)//100]/1000})
                save()
        digests=[{(r['offset'],r['length']):r['sha256'] for r in run['reads']} for run in record['runs']]
        after=path.stat()
        if any(d!=digests[0] for d in digests) or (after.st_size,after.st_mtime_ns,after.st_ino)!=(before.st_size,before.st_mtime_ns,before.st_ino):
            raise RuntimeError('Lookup file or sampled bytes changed')
        record['status']='passed'
    except BaseException as error:
        record.update(status='failed',error=f'{type(error).__name__}: {error}')
        raise
    finally: save()
    return output


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run',action='store_true');ap.add_argument('--samples',type=int,default=128)
    ap.add_argument('--save-plan',type=Path)
    args=ap.parse_args(argv)
    header=ROOT/'bench/results/flash-gguf-inventory.json'
    record=plan(json.loads(header.read_text()),args.samples,os.sysconf('SC_PAGE_SIZE'))
    record['inventory_sha256']=hashlib.sha256(header.read_bytes()).hexdigest()
    record['registered_model']=json.loads((ROOT/'config/models.json').read_text())['flash']
    if args.save_plan:
        args.save_plan.parent.mkdir(parents=True,exist_ok=True)
        args.save_plan.write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    print(f"Plan: {len(record['samples'])} lookup offsets, three read-only passes, total at most 8 MiB. Cache state is unknown.")
    if not args.run:
        print('Testing is on hold. No model payload was read.');return
    from profile_m5_routes import preflight
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        record['preflight']=preflight(small=True)
        folder=ROOT/'bench/features'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-lookup-io')
        print(execute(record,ROOT/'models/flash'/record['file'],folder))


if __name__=='__main__':main()
