#!/usr/bin/env python3
"""Build or run small exact-copy checks; model inference is a separate benchmark."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import fcntl
import json
import os
import statistics
import subprocess
import threading

from benchmark import Monitor
from check_memory import assert_no_model_server
from engines import sha256, verify_engine
from lab import ROOT
from metal_environment import configure
from profile_m5 import parse as parse_buffers

SOURCE = ROOT / 'native/m5_copy_probe.cpp'
WORK = ROOT / 'bench/runtime/m5-copy'
BINARY = WORK / 'copy-probe'
RECEIPT = WORK / 'build.json'


def build():
    pin = verify_engine('m5-copy')
    native = ROOT / pin['directory']
    libs = [native / 'build/bin' / name for name in ('libggml.0.26.0.dylib', 'libggml-base.0.26.0.dylib')]
    command = ['/usr/bin/c++', '-O3', '-DNDEBUG', '-std=gnu++17', '-arch', 'arm64',
               '-I' + str(native/'ggml/include'), '-I' + str(native/'vendor'), str(SOURCE),
               '-o', str(BINARY), '-Wl,-rpath,' + str(native/'build/bin'), *map(str, libs)]
    WORK.mkdir(parents=True, exist_ok=True)
    with (WORK/'build.log').open('w') as stream:
        subprocess.run(command, stdout=stream, stderr=stream, check=True)
    record = {'schema': 1, 'engine': pin, 'source_sha256': sha256(SOURCE), 'binary_sha256': sha256(BINARY), 'command': command}
    if verify_engine('m5-copy') != pin: raise RuntimeError('Engine changed during copy probe build')
    RECEIPT.write_text(json.dumps(record, indent=2)+'\n')
    return record


def verify():
    r = json.loads(RECEIPT.read_text())
    if verify_engine('m5-copy') != r['engine'] or sha256(SOURCE) != r['source_sha256'] or sha256(BINARY) != r['binary_sha256']:
        raise RuntimeError('Copy probe source or binaries changed')
    return r


def markers(text, marker):
    return [json.loads(s.split(marker+' ',1)[1]) for s in text.splitlines() if marker+' ' in s]


def parse(text, mode):
    done = markers(text,'M5_COPY_DONE'); passes = markers(text,'M5_COPY_PASS')
    expected = 47 if mode == 'test' else 6
    if done != [{'mode':mode,'passed':expected}] or len(passes) != expected or 'M5_COPY_ERROR' in text:
        raise ValueError('Incomplete bit-exact values, padding or source preservation checks')
    result = {'cases_passed':expected}
    if mode == 'perf':
        calls = markers(text,'M5_COPY_CALL'); returns = markers(text,'M5_COPY_RETURN')
        buffers = parse_buffers(text)['command_buffers']
        if len(calls) != 258 or len(returns) != len(calls) or len(buffers) != len(calls) or len({b['context'] for b in buffers}) != 1:
            raise ValueError('Copy GPU timing coverage incomplete')
        groups = defaultdict(list)
        for index,(call,ret,b) in enumerate(zip(calls,returns,buffers),1):
            if b['graph'] != index or b['op_counts'].get('CPY') != 1 or any(op not in ('CPY','VIEW','TRANSPOSE') for op in b['op_counts']):
                raise ValueError('Timed graph has extra computation or mismatched labels')
            if {k:v for k,v in ret.items() if k != 'wall_us'} != call:
                raise ValueError('Copy call and completion differ')
            if call['phase'] == 'measure': groups[(call['rows'],call['layout'])].append({**ret,'gpu_us':b['gpu_ms']*1000})
        result['summary'] = []
        for (rows,layout),values in sorted(groups.items()):
            if sorted(v['sample'] for v in values) != list(range(40)): raise ValueError('Missing measured copy sample')
            result['summary'].append({'rows':rows,'layout':layout,'copy_bytes':values[0]['copy_bytes'], 'samples':40,
                                      'gpu_us':statistics.median(v['gpu_us'] for v in values),
                                      'wall_us':statistics.median(v['wall_us'] for v in values)})
        if len(result['summary']) != 6: raise ValueError('Missing copy layouts')
    return result


def execute(mode, tuning):
    assert_no_model_server(); pin = verify()
    folder = ROOT/'bench/features'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-m5-copy-'+mode+'-'+tuning)
    folder.mkdir(); env,flags = configure(os.environ,'m5-copy','on',tuning,profile=mode=='perf')
    record = {'schema':1,'status':'running','probe':pin,'mode':mode,'metal_environment':flags,
              'models_loaded':False,'tps_measured':False,'timing_scope':'Isolated copy graphs with GPU timestamps; not model speed'}
    process = monitor = worker = None
    try:
        with (folder/'native.log').open('w') as log:
            baseline = Monitor.baseline()
            process = subprocess.Popen([BINARY,mode],stdout=log,stderr=log,env=env)
            monitor = Monitor(process,folder/'memory.jsonl',0,1024**3,baseline=baseline)
            worker = monitor.thread; worker.start()
            code = process.wait(timeout=120)
        worker.join(timeout=5)
        record['memory'] = monitor.finish()
        if code or record['memory']['guard'] or record['memory']['swap_growth_bytes'] or not record['memory']['monitor_healthy']:
            raise RuntimeError('Copy probe failed or resource guard stopped it')
        record.update(parse((folder/'native.log').read_text(),mode))
        if verify() != pin: raise RuntimeError('Copy probe changed during testing')
        record['status'] = 'passed'
    except BaseException as error:
        record.update(status='failed',error=f'{type(error).__name__}: {error}'); raise
    finally:
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
        if worker: worker.join(timeout=5)
        (folder/'probe.json').write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
        print(f'Copy {mode} {tuning}: {record["status"]}; {folder}',flush=True)
    return str((folder/'probe.json').relative_to(ROOT))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build',action='store_true'); ap.add_argument('--run',action='store_true')
    ap.add_argument('--mode',choices=('test','perf'),default='test')
    ap.add_argument('--tuning',choices=('stock','copy-scalar','copy-v4','copy-v8'),nargs='+',default=['stock'])
    args = ap.parse_args()
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.build: build()
        if args.run:
            for tuning in args.tuning: execute(args.mode,tuning)
        else: print('Prepared only; no copy test, benchmark or model load. Add --run for small copy tests.')


if __name__ == '__main__': main()
