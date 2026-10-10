#!/usr/bin/env python3
"""Prepare U10-02 without execution; --run checks and times full synthetic MoE blocks."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess

import benchmark_m5_compact as oracle
from benchmark import Monitor
from check_memory import assert_no_model_server, snapshot
from engines import ROOT, sha256, verify_engine
from metal_environment import configure
from profile_m5_routes import preflight
from validate_offline import fingerprint, require_pass

SOURCE = ROOT / 'native/m5_tile16_probe.cpp'
WORK = ROOT / 'bench/runtime/m5-tile16'
RESULTS = ROOT / 'bench/results/20261010-next-tests-v2/tile16'
SEMANTICS = 'each eligible encoded tile16 MM_ID; elapsed complete graph measured separately'
ARMS = {
    'original': ('m5-small-stack', 'small-reduce', 'control'),
    'disabled': ('m5-tile16', 'prompt-tile32', 'control'),
    'tile16': ('m5-tile16', 'prompt-tile16', 'tile16'),
}
RULE = ('Exact complete P07-control F32 outputs for every correctness fixture, A/B/A input mutation, '
        'all eligible per-MM counters and all fallback counters, no extra scheduler splits or CPU placement. '
        'Fresh original/tile16/tile16/original component screen: positive time reduction above twice '
        'symmetric own control drift and both candidates faster than both controls for T508/T512 uniform. '
        'Other complete-block cases may not regress beyond max(1 percent, twice own control drift). '
        'No new swap, healthy resource monitor. This licenses a later model trial, not adoption or decode TPS.')


def write(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, allow_nan=False) + '\n')


def parse(text, mode, scope):
    """Reuse the strict unchanged fixture oracle, while requiring the new counter identity."""
    if scope not in ('control', 'tile16'):
        raise ValueError('Unknown tile16 scope')
    adapted = []
    for line in text.splitlines():
        if line.startswith(('M5_TILE16_CASE ', 'M5_TILE16_DONE ')):
            name, payload = line.split(' ', 1)
            row = json.loads(payload)
            if row.get('scope') != scope:
                raise ValueError('Tile16 scope changed')
            row['scope'] = 'compact' if scope == 'tile16' else 'control'
            if name == 'M5_TILE16_CASE':
                if row.get('counter_semantics') != SEMANTICS:
                    raise ValueError('Wrong tile16 activation counter')
                row['counter_semantics'] = oracle.COUNTER_SEMANTICS
            adapted.append(name.replace('M5_TILE16', 'M5_COMPACT') + ' ' + json.dumps(row))
    rows = oracle.parse('\n'.join(adapted), mode, 'compact' if scope == 'tile16' else 'control')
    for row in rows:
        row['scope'], row['counter_semantics'] = scope, SEMANTICS
    return rows


def source_pins():
    return dict(offline_sources=fingerprint(), native_source_sha256=sha256(SOURCE),
                patches={name: sha256(ROOT / name) for name in (
                    'patches/mtp-m5-small-stack.patch', 'patches/mtp-m5-tile16.patch')},
                engines={name: verify_engine(name) for name in ('m5-small-stack', 'm5-tile16')})


def build():
    assert_no_model_server()
    WORK.mkdir(parents=True, exist_ok=True)
    before = source_pins()
    binaries = {}
    for label, engine in (('original', 'm5-small-stack'), ('candidate', 'm5-tile16')):
        native = ROOT / before['engines'][engine]['directory']
        binary = WORK / (label + '-probe')
        command = ['/usr/bin/c++', '-O3', '-ffp-contract=off', '-std=gnu++17', '-arch', 'arm64',
                   '-I' + str(native / 'ggml/include'), '-I' + str(native / 'vendor'), str(SOURCE),
                   '-o', str(binary), '-Wl,-rpath,' + str(native / 'build/bin'),
                   *[str(native / 'build/bin' / name) for name in
                     ('libggml.0.26.0.dylib', 'libggml-base.0.26.0.dylib')]]
        with (WORK / (label + '-build.log')).open('w') as log:
            subprocess.run(command, stdout=log, stderr=log, check=True)
        binaries[label] = dict(path=str(binary), sha256=sha256(binary), command=command)
    if source_pins() != before:
        raise ValueError('Source changed during probe build')
    record = dict(status='built-awaiting-GPU-tests', sources=before, binaries=binaries,
                  models_loaded=False, gpu_tests_run=False, benchmarks_run=False)
    write(WORK / 'build.json', record)
    return record


def freeze():
    require_pass(); assert_no_model_server()
    if (RESULTS / 'frozen.json').exists():
        raise ValueError('Existing campaign is immutable; use a new campaign for changed inputs')
    record = json.loads((WORK / 'build.json').read_text())
    if record['sources'] != source_pins():
        raise ValueError('Probe build sources are stale')
    for item in record['binaries'].values():
        if sha256(item['path']) != item['sha256']:
            raise ValueError('Probe binary changed')
    paths = [ROOT / name for name in record['sources']['offline_sources']]
    paths += [ROOT / name for name in record['sources']['patches']] + [SOURCE]
    archive = RESULTS / 'source'
    archived = {}
    for path in paths:
        name = str(path.relative_to(ROOT)); dest = archive / name
        dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, dest)
        archived[name] = sha256(dest)
        if sha256(path) != archived[name]: raise ValueError('Archive changed')
    write(RESULTS / 'frozen.json', dict(
        status='prepared-not-run', created_utc=datetime.now(timezone.utc).isoformat(),
        build=record, archive=archived, rule=RULE, correctness_arms=list(ARMS),
        timing_arms=['original', 'tile16', 'tile16', 'original'],
        correctness_inventory=oracle.inventory('check'), timing_inventory=oracle.inventory('perf'),
        scope='Synthetic prompt blocks only; English model trials require a later fresh qualification.',
        models_loaded=False, gpu_tests_run=False, benchmarks_run=False))


def unchanged(frozen):
    if source_pins() != frozen['build']['sources']:
        raise ValueError('Frozen source or native engine changed')
    if frozen['rule'] != RULE:
        raise ValueError('Frozen rule changed')
    for item in frozen['build']['binaries'].values():
        if sha256(item['path']) != item['sha256']: raise ValueError('Frozen probe changed')
    for name, digest in frozen['archive'].items():
        if sha256(RESULTS / 'source' / name) != digest: raise ValueError('Frozen archive changed')


def summarize(groups):
    if len(groups) != 4: raise ValueError('ABBA screen missing')
    for group in groups[1:]: oracle.compare_exact(groups[0], group)
    rows = []
    for samples in zip(*groups):
        values = [row['median_ns'] for row in samples]
        a, b = (values[0] + values[3]) / 2, (values[1] + values[2]) / 2
        drift = 100 * abs(values[3] - values[0]) / a
        gain = 100 * (1 - b / a)
        rows.append(dict(id=samples[0]['id'], rows=samples[0]['rows'], route=samples[0]['route'],
                         control_ms=a / 1e6, candidate_ms=b / 1e6, time_reduction_percent=gain,
                         control_drift_percent=drift,
                         qualifies=gain > 2 * drift and max(values[1:3]) < min(values[0], values[3]),
                         safe=gain >= -max(1.0, 2 * drift)))
    required = [row for row in rows if row['rows'] in (508, 512) and row['route'] == 'uniform']
    return dict(rows=rows, qualifies_for_model_trial=len(required) == 2 and
                all(row['qualifies'] for row in required) and all(row['safe'] for row in rows),
                adoption=False, model_TPS=None, rule=RULE)


def execute(arm, mode, frozen):
    unchanged(frozen); assert_no_model_server()
    if snapshot()['memory']['available'] < 8 * 1024**3:
        raise ValueError('Component trial requires 8 GiB available; no automatic cleanup')
    engine, tuning, scope = ARMS[arm]
    item = frozen['build']['binaries']['original' if arm == 'original' else 'candidate']
    folder = RESULTS / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + mode + '-' + arm)
    folder.mkdir(parents=True)
    record = dict(status='running', arm=arm, mode=mode, scope=scope)
    process = monitor = None
    try:
        record['preflight'] = preflight(small=True)
        env, flags = configure(dict(os.environ), engine, 'on', tuning)
        record['environment'] = flags
        with (folder / 'native.log').open('w') as log:
            baseline = Monitor.baseline()
            process = subprocess.Popen([item['path'], mode, str(folder / 'outputs.jsonl'), scope],
                                       stdout=log, stderr=log, env=env)
            monitor = Monitor(process, folder / 'memory.jsonl', 0, 1024**3, baseline=baseline)
            monitor.thread.start(); code = process.wait(timeout=900)
        memory = monitor.finish(); record.update(memory=memory, returncode=code)
        if (code or memory['swap_growth_bytes'] or memory['guard'] or
                not memory['monitor_healthy'] or not memory['child_exited']):
            raise ValueError('Component or resource guard failed')
        text = (folder / 'native.log').read_text(); rows = parse(text, mode, scope)
        evidence = [json.loads(line) for line in (folder / 'outputs.jsonl').read_text().splitlines()]
        if evidence != rows + oracle.markers(text, 'M5_TILE16_DONE'):
            raise ValueError('Raw log and JSONL disagree')
        unchanged(frozen)
        record.update(status='passed', cases=rows, log_sha256=sha256(folder / 'native.log'),
                      evidence_sha256=sha256(folder / 'outputs.jsonl'))
        return rows
    except BaseException as error:
        record.update(status='failed', error=f'{type(error).__name__}: {error}'); raise
    finally:
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        if monitor and 'memory' not in record: record['memory'] = monitor.finish()
        write(folder / 'result.json', record)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--build', action='store_true'); mode.add_argument('--freeze', action='store_true')
    mode.add_argument('--run', action='store_true')
    args = ap.parse_args(argv)
    if not any((args.build, args.freeze, args.run)):
        print('Held tile16 screen. --build compiles; --freeze records inputs; --run executes GPU checks/ABBA.')
        return
    with (ROOT / 'bench/.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.build: build(); print('Probes built; no GPU or model run.'); return
        if args.freeze: freeze(); print('Frozen; no GPU or model run.'); return
        require_pass()
        frozen = json.loads((RESULTS / 'frozen.json').read_text())
        if (RESULTS / 'tracking.json').exists(): raise ValueError('No automatic retry or partial resume')
        state = dict(status='running', runs=[], adoption=False, models_loaded=False)
        write(RESULTS / 'tracking.json', state)
        try:
            checked = [execute(arm, 'check', frozen) for arm in ARMS]
            for group in checked[1:]: oracle.compare_exact(checked[0], group)
            timed = [execute(arm, 'perf', frozen) for arm in ('original', 'tile16', 'tile16', 'original')]
            state.update(status='passed', comparison=summarize(timed))
        except BaseException as error:
            state.update(status='failed', error=f'{type(error).__name__}: {error}'); raise
        finally:
            state['runs'] = [str(path.relative_to(ROOT)) for path in sorted(RESULTS.glob('*/result.json'))]
            write(RESULTS / 'tracking.json', state)


if __name__ == '__main__': main()
