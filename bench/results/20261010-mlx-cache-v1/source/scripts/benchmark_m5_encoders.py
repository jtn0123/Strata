#!/usr/bin/env python3
"""Correctness-only Metal encoder-count checks; no speed or model benchmark."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess

from benchmark import Monitor
from check_memory import assert_no_model_server
from engines import ROOT, sha256, verify_engine
from metal_environment import configure

WORK = ROOT/'bench/runtime/m5-encoders'
SOURCE = ROOT/'native/m5_encoder_probe.cpp'
BINARY = WORK/'encoder-probe'
VARIANTS = {'unset': None, '0': '0', '1': '1', '2': '2', 'empty': '',
            'space-prefix': ' 2', 'signed': '+2', 'zero-prefix': '02', 'suffix': '2x',
            'out-of-range': '3', 'negative': '-1', 'space-suffix': '2 ', 'stats': '2'}


def inventory():
    return [('add', n) for n in (61, 62, 63, 64, 128, 648)]+[('alias', n) for n in (21, 43, 217)]


def expected_count(variant):
    value = VARIANTS[variant]
    return 0 if variant == 'stats' else (int(value) if value in ('0', '1', '2') else 1)


def build():
    pin = verify_engine('m5-encoders')
    native = ROOT/pin['directory']
    WORK.mkdir(parents=True, exist_ok=True)
    command = ['/usr/bin/c++', '-O3', '-ffp-contract=off', '-std=gnu++17', '-arch', 'arm64',
               '-I'+str(native/'ggml/include'), '-I'+str(native/'vendor'), str(SOURCE), '-o', str(BINARY),
               '-Wl,-rpath,'+str(native/'build/bin'),
               *[str(native/'build/bin'/name) for name in
                 ('libggml.0.26.0.dylib', 'libggml-base.0.26.0.dylib', 'libggml-metal.0.26.0.dylib')]]
    with (WORK/'probe-build.log').open('w') as log:
        subprocess.run(command, stdout=log, stderr=log, check=True)
    record = dict(engine=pin, source_sha256=sha256(SOURCE), runner_sha256=sha256(__file__),
                  binary_sha256=sha256(BINARY), command=command)
    (WORK/'probe-build.json').write_text(json.dumps(record, indent=2)+'\n')
    return record


def verify():
    record = json.loads((WORK/'probe-build.json').read_text())
    if (record['engine'] != verify_engine('m5-encoders') or record['source_sha256'] != sha256(SOURCE)
            or record['runner_sha256'] != sha256(__file__) or record['binary_sha256'] != sha256(BINARY)):
        raise RuntimeError('Encoder probe provenance changed')
    return record


def parse(text, constructor, variant):
    def markers(name):
        return [json.loads(line[len(name)+1:]) for line in text.splitlines() if line.startswith(name+' ')]
    init, start, cases, done = [markers(name) for name in
                              ('M5_ENCODER_INIT', 'M5_ENCODERS_START', 'M5_ENCODERS_CASE', 'M5_ENCODERS_DONE')]
    count, stats = expected_count(variant), variant == 'stats'
    requested = int(VARIANTS[variant]) if VARIANTS[variant] in ('0', '1', '2') else 1
    if (len(init) != 1 or init[0] != dict(path='public' if constructor == 'legacy' else 'device',
                                       requested_n_cb=requested, effective_n_cb=count, stats=stats)):
        raise ValueError('Wrong constructor or effective startup count')
    expected_initial = [count, 0, 0, 0, 1, int(stats), 1, 1]
    if start != [dict(constructor=constructor, effective_n_cb=count, plan=expected_initial)]:
        raise ValueError('Initial effective encoding plan differs')
    if (done != [dict(constructor=constructor, cases=len(inventory()), cpu_bit_exact=True, timings_measured=False)]
            or len(cases) != len(inventory()) or 'M5_ENCODERS_ERROR' in text):
        raise ValueError('Incomplete correctness evidence')
    for case, (kind, steps) in zip(cases, inventory()):
        nodes = steps*(3 if kind == 'alias' else 1)+2
        main = nodes if count == 0 else min(nodes, max(64, int(0.1*nodes)))
        remaining = nodes-main
        per_worker = (remaining+count-1)//count if count else 0
        partitions = [[0, main]]+[[main+i*per_worker, main+min(remaining, (i+1)*per_worker)] for i in range(count)]
        plan = [count, main, remaining, per_worker, 1, int(stats), 1, 1]
        if (case['kind'] != kind or case['steps'] != steps or case['raw_nodes'] != nodes
                or case['plan'] != plan or case['partitions'] != partitions
                or case['crossed_boundaries'] != sum(a < nodes for a, _ in partitions[1:])
                or case['scheduler_splits'] != 1 or case['all_nodes_metal'] is not True
                or case['cpu_bit_exact'] is not True or case['inputs_preserved'] is not True
                or case['padding_preserved'] is not True or case['digest_buffers'] != 2
                or case['checked_values'] != 538):
            raise ValueError('Partition, cross-boundary dependency, or CPU bit-reference evidence differs')
    return cases


def read_buffers(folder):
    actual = [json.loads(line) for line in (Path(folder)/'outputs.jsonl').read_text().splitlines()]
    expected = [dict(id=f'{kind}/{steps}/{label}', bytes=n*4)
                for kind, steps in inventory() for label, n in (('output', 256), ('storage', 282))]
    if len(actual) != len(expected) or len({x['id'] for x in actual}) != len(expected):
        raise ValueError('Missing or duplicated tensor evidence')
    for got, want in zip(actual, expected):
        if (set(got) != {'id', 'bytes', 'sha256'} or got['id'] != want['id'] or got['bytes'] != want['bytes']
                or not re.fullmatch('[0-9a-f]{64}', got['sha256'])):
            raise ValueError('Wrong complete-buffer digest inventory')
    return actual


def execute(constructor, variant):
    if constructor not in ('legacy', 'registry') or variant not in VARIANTS:
        raise ValueError('Unknown encoder correctness case')
    assert_no_model_server()
    pin = verify()
    folder = ROOT/'bench/features'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-m5-encoders-check-'+constructor+'-'+variant)
    folder.mkdir()
    env, flags = configure(os.environ, 'm5-encoders', 'on', 'conv-direct')
    for name in ('GGML_SCHED_DEBUG', 'GGML_SCHED_DEBUG_REALLOC'):
        env.pop(name, None)
    if VARIANTS[variant] is not None:
        env['GGML_M5_LAB_N_CB'] = VARIANTS[variant]
        flags['variables']['GGML_M5_LAB_N_CB'] = VARIANTS[variant]
    if variant == 'stats':
        env['GGML_METAL_FUSION_DEBUG'] = '1'
        flags['variables']['GGML_METAL_FUSION_DEBUG'] = '1'
    command = [str(BINARY), constructor, str(expected_count(variant)), str(folder/'outputs.jsonl')]
    record = dict(status='running', probe=pin, constructor=constructor, variant=variant, command=command,
                  effective_n_cb=expected_count(variant), metal_environment=flags, models_loaded=False,
                  timings_measured=False, tps_measured=False, stats_case_excluded_from_speed=variant == 'stats',
                  scope='Dependent dyadic ADD fusion and shared-state ADD/CPY chains across command-buffer partitions. Scheduler optimizer on; CPU bit reference and all returned buffer digests. No timings or callbacks.')
    process = monitor = None
    try:
        with (folder/'native.log').open('w') as log:
            baseline = Monitor.baseline()
            process = subprocess.Popen(command, env=env, stdout=log, stderr=log)
            monitor = Monitor(process, folder/'memory.jsonl', 0, 2**30, baseline=baseline)
            monitor.thread.start()
            code = process.wait(timeout=180)
        monitor.thread.join(timeout=5)
        record['memory'] = monitor.finish()
        memory = record['memory']
        if (code or memory['guard'] or memory['swap_growth_bytes'] != 0 or not memory['monitor_healthy']
                or not memory['child_exited'] or not memory['baseline_before_launch']):
            raise RuntimeError('Encoder probe or memory check failed')
        record['cases'] = parse((folder/'native.log').read_text(), constructor, variant)
        record['buffers'] = read_buffers(folder)
        record['outputs_sha256'] = sha256(folder/'outputs.jsonl')
        record['native_log_sha256'] = sha256(folder/'native.log')
        if verify() != pin:
            raise RuntimeError('Engine or probe changed during execution')
        record['status'] = 'passed'
    except BaseException as error:
        record.update(status='failed', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if monitor:
            monitor.thread.join(timeout=5)
            if 'memory' not in record:
                record['memory'] = monitor.finish()
        (folder/'probe.json').write_text(json.dumps(record, indent=2)+'\n')
        print(constructor, variant, record['status'], folder, flush=True)
    return folder


def read_record(folder):
    folder = Path(folder)
    record = json.loads((folder/'probe.json').read_text())
    memory = record.get('memory', {})
    if (record['status'] != 'passed' or record['probe'] != verify() or memory.get('swap_growth_bytes') != 0
            or memory.get('guard') or not memory.get('monitor_healthy') or not memory.get('child_exited')
            or not memory.get('baseline_before_launch') or record['timings_measured'] is not False
            or record['metal_environment']['tensor_api'] != 'on' or record['metal_environment']['profile']
            or record['outputs_sha256'] != sha256(folder/'outputs.jsonl')
            or record['native_log_sha256'] != sha256(folder/'native.log')
            or record['cases'] != parse((folder/'native.log').read_text(), record['constructor'], record['variant'])
            or record['buffers'] != read_buffers(folder)):
        raise ValueError('Invalid or changed encoder correctness evidence')
    return record


def compare(control, candidate):
    control, candidate = Path(control), Path(candidate)
    try:
        a, b = read_record(control), read_record(candidate)
        if a['variant'] != 'unset' or a['buffers'] != b['buffers']:
            raise ValueError('Encoding count or constructor changed output/cache/padding bits')
        result = dict(status='passed', control=str(control.relative_to(ROOT)), candidate=str(candidate.relative_to(ROOT)),
                      buffers_with_identical_sha256=len(a['buffers']), values_covered=sum(x['bytes']//4 for x in a['buffers']),
                      cpu_bit_exact=True, timings_measured=False, raw_values_stored=False)
    except BaseException as error:
        result = dict(status='failed', error=f'{type(error).__name__}: {error}')
        (candidate/'comparison.json').write_text(json.dumps(result, indent=2)+'\n')
        raise
    (candidate/'comparison.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true')
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.build:
            build()
        if args.run:
            runs = {}
            for constructor in ('legacy', 'registry'):
                for variant in VARIANTS:
                    folder = execute(constructor, variant)
                    runs[constructor+'/'+variant] = str(folder.relative_to(ROOT))
                    control = ROOT/runs['legacy/unset']
                    compare(control, folder)
            (WORK/'checks.json').write_text(json.dumps(dict(status='passed', probe=verify(), runs=runs,
                timings_measured=False), indent=2)+'\n')


if __name__ == '__main__':
    main()
