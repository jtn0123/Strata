#!/usr/bin/env python3
"""Freeze or run one immutable English MLX 6/12 GB cache comparison."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading

import psutil

from benchmark import Monitor, host_snapshot
from check_memory import assert_no_model_server
from engines import sha256, verify_engine
from lab import ROOT, model_path
from mlx_cache_protocol import schedule, summarize, validate_launch
from model_provenance import assert_unchanged, verify_models
from profile_m5_routes import preflight
from validate_offline import fingerprint, require_pass

RESULTS = ROOT / 'bench/results/20261010-mlx-cache-v1'
PREVIOUS = ROOT / 'bench/results/20261010-next-tests-v2/mlx-reply'
SOURCE = ROOT / 'vendor/strata-mlx-u10'
PYTHON = ROOT / 'bench/runtime/u10-mlx/.venv/bin/python'
CONFIG = ROOT / 'config/mlx_cache_comparison.json'


def write(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, allow_nan=False) + '\n')


def dependency_pins():
    # Read installed package metadata/code bytes only; do not import MLX or initialize a GPU.
    code = '''import importlib.metadata as m, sys, json, hashlib, fcntl
versions = {}; artifacts = {}
for dist in m.distributions():
    name = dist.metadata['Name']; versions[name] = {'version':dist.version, 'direct_url':dist.read_text('direct_url.json')}
    for file in dist.files or []:
        if str(file).endswith(('.py', '.so', '.dylib', '.metallib', 'direct_url.json')):
            path=dist.locate_file(file)
            if not path.is_file(): continue
            with path.open('rb') as stream:
                fcntl.fcntl(stream.fileno(), 48, 1)
                artifacts[name + ':' + str(file)] = hashlib.file_digest(stream,'sha256').hexdigest()
print(json.dumps({'python':sys.version,'versions':versions,'artifacts':artifacts}))'''
    return json.loads(subprocess.check_output([str(PYTHON), '-c', code], text=True, timeout=90))


def source_pins():
    prepared = json.loads((ROOT / 'bench/results/20261010-next-tests/mlx/preparation.json').read_text())
    pins = {name: sha256(SOURCE / name) for name in prepared['source_files']}
    revision = subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip()
    if pins != prepared['source_files'] or revision != prepared['revision']:
        raise ValueError('Prepared MLX source changed')
    if subprocess.check_output(['git', '-C', str(SOURCE), 'status', '--porcelain'], text=True).strip():
        raise ValueError('MLX checkout must stay clean')
    native = verify_engine('m5-small-stack')
    vocab = json.loads((PREVIOUS / 'vocab-build.json').read_text())
    if (vocab['engine'] != native or sha256(vocab['binary']) != vocab['binary_sha256']
            or sha256(PREVIOUS / 'vocab.cpp') != vocab['source_sha256']):
        raise ValueError('Vocabulary-only helper changed')
    return dict(revision=revision, source_files=pins, native=native, vocab=vocab,
                dependencies=dependency_pins(), offline_sources=fingerprint())


def freeze():
    require_pass()
    if (RESULTS / 'frozen.json').exists():
        raise ValueError('Frozen campaign exists; never overwrite or silently retry')
    for name in ('mlx-device', 'mlx-load', 'mlx-reply'):
        receipt = ROOT / 'bench/results/20261010-next-tests-v2' / name / 'receipt.json'
        if json.loads(receipt.read_text())['status'] != 'passed':
            raise ValueError('Prior F32 feasibility prerequisite failed')
    assert_no_model_server()
    plan = json.loads(CONFIG.read_text())
    pins = source_pins()
    models = verify_models(['flash'])
    inputs = {}
    for name, prompt in plan['prompts'].items():
        text = plan['render_prefix'] + prompt + plan['render_suffix']
        data = subprocess.check_output([pins['vocab']['binary'], str(model_path('flash'))],
                                       input=json.dumps({'text': text}), text=True, timeout=30)
        item = json.loads(data)
        if (item.get('vocabulary_only') is not True or item.get('weights_loaded') is not False
                or item['text'] != text or not item['tokens']
                or len(item['tokens']) + plan['output_limit'] > plan['max_context_tokens']):
            raise ValueError('Vocabulary-only exact prompt preflight failed')
        inputs[name] = item
    assert_unchanged(models)
    archive = {}
    for name in pins['offline_sources']:
        dest = RESULTS / 'source' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, dest)
        archive[name] = sha256(dest)
        if archive[name] != pins['offline_sources'][name]:
            raise ValueError('Source archive differs from validated inputs')
    record = dict(status='prepared-not-run', created_utc=datetime.now(timezone.utc).isoformat(),
                  plan=plan, inputs=inputs, schedule=schedule(plan), sources=pins, models=models,
                  archive=archive, benchmark_run=False, adoption=False)
    write(RESULTS / 'frozen.json', record)
    print('Frozen English comparison:', RESULTS, flush=True)


def unchanged(frozen):
    require_pass()
    if source_pins() != frozen['sources'] or json.loads(CONFIG.read_text()) != frozen['plan']:
        raise ValueError('Frozen source/dependencies/config changed')
    assert_unchanged(frozen['models'])
    for name, digest in frozen['archive'].items():
        if sha256(RESULTS / 'source' / name) != digest:
            raise ValueError('Frozen archive changed')


def watch_pressure(process, path, done, state):
    try:
        with path.open('w') as stream:
            while not done.is_set():
                level = int(subprocess.check_output(['sysctl', '-n', 'kern.memorystatus_vm_pressure_level'], text=True, timeout=3))
                stream.write(json.dumps({'time_utc': datetime.now(timezone.utc).isoformat(), 'pressure_level': level}) + '\n')
                stream.flush()
                state['samples'] += 1
                if level != 1:
                    raise RuntimeError(f'Memory pressure became {level}')
                done.wait(0.5)
    except BaseException as error:
        state['error'] = f'{type(error).__name__}: {error}'
        if process.poll() is None:
            process.terminate()


def execute(index, frozen):
    budget = frozen['plan']['budgets_decimal_GB'][index]
    folder = RESULTS / f'{index:02d}-{budget}GB'
    if folder.exists():
        raise ValueError('Existing launch cannot be overwritten/retried')
    folder.mkdir()
    process = monitor = pressure_thread = None
    pressure_done = threading.Event()
    pressure = dict(samples=0, error=None)
    record = dict(status='preflight', index=index, budget_decimal_GB=budget, adoption=False)
    try:
        unchanged(frozen)
        before = preflight(small=True)
        if before['memory']['available'] < frozen['plan']['admission_gib'] * 2**30:
            raise ValueError('MLX requires 28 GiB available; no automatic cleanup or retry')
        record.update(preflight=before, host_before=host_snapshot())
        env = dict(os.environ, PYTHONPATH=str(SOURCE), PYTHONNOUSERSITE='1')
        for key in list(env):
            if key.startswith('MTL_DEBUG_LAYER'):
                del env[key]
        worker = RESULTS / 'source/scripts/mlx_cache_worker.py'
        command = [str(PYTHON), str(worker), str(RESULTS / 'frozen.json'),
                   str(model_path('flash')), frozen['sources']['vocab']['binary'], str(budget)]
        record.update(status='running', command=command)
        write(folder / 'result.json', record)
        with (folder / 'native.log').open('w') as log:
            baseline = Monitor.baseline()
            # Recheck the exact launch baseline, after all provenance/host reads.
            if baseline['available_bytes'] < frozen['plan']['admission_gib'] * 2**30:
                raise ValueError('Final 28 GiB admission failed')
            if int(subprocess.check_output(['sysctl', '-n', 'kern.memorystatus_vm_pressure_level'], text=True)) != 1:
                raise ValueError('Final pressure admission failed')
            process = subprocess.Popen(command, stdout=log, stderr=log, env=env, start_new_session=True)
            monitor = Monitor(process, folder / 'memory.jsonl', 0,
                              frozen['plan']['availability_floor_gib'] * 2**30, baseline=baseline)
            monitor.thread.start()
            pressure_thread = threading.Thread(target=watch_pressure, args=(process, folder / 'pressure.jsonl', pressure_done, pressure), daemon=True)
            pressure_thread.start()
            code = process.wait(timeout=frozen['plan']['child_timeout_s'])
        pressure_done.set()
        pressure_thread.join(timeout=5)
        if pressure_thread.is_alive():
            raise ValueError('Pressure watcher failed to stop')
        record.update(returncode=code, memory=monitor.finish(), pressure=pressure)
        if (code or record['memory']['guard'] or record['memory']['swap_growth_bytes']
                or not record['memory']['monitor_healthy'] or not record['memory']['child_exited']
                or pressure['error'] or not pressure['samples']):
            raise ValueError('MLX execution or resource monitor failed')
        events = [json.loads(line) for line in (folder / 'native.log').read_text().splitlines() if line.startswith('{')]
        rows = validate_launch(events[-1], frozen['plan'], frozen['inputs'], budget)
        unchanged(frozen)
        record.update(status='passed', output=events[-1], cases=rows, host_after=host_snapshot())
        print(json.dumps({'launch': index, 'budget_GB': budget, 'status': record['status'],
                          'minimum_available_gib': record['memory']['minimum_available_bytes']/2**30,
                          'swap_growth_bytes': record['memory']['swap_growth_bytes']}), flush=True)
        return rows
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
                process.wait(timeout=5)
        pressure_done.set()
        if pressure_thread:
            pressure_thread.join(timeout=5)
        if monitor and 'memory' not in record:
            record['memory'] = monitor.finish()
        record['pressure'] = pressure
        write(folder / 'result.json', record)


def run():
    destination = RESULTS / 'comparison.json'
    if destination.exists() or any(RESULTS.glob('[0-9][0-9]-*GB')):
        raise ValueError('Campaign already attempted; no retry or partial resume')
    frozen = json.loads((RESULTS / 'frozen.json').read_text())
    record = dict(status='running', scope=frozen['plan']['timing_scope'], launches=[], adoption=False)
    try:
        with (ROOT / 'bench/.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            unchanged(frozen)
            groups = []
            for index in range(4):
                print(f'Starting sequential launch {index+1}/4: {frozen["plan"]["budgets_decimal_GB"][index]} GB cache', flush=True)
                groups.append(execute(index, frozen))
                record['launches'].append(index)
                write(destination, record)
            record.update(status='passed', summary=summarize(groups, frozen['plan']))
    except BaseException as error:
        record.update(status='failed', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        write(destination, record)
    print(json.dumps(record['summary'], indent=2), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument('--freeze', action='store_true')
    choice.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    if args.freeze:
        with (ROOT / 'bench/.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            freeze()
    elif args.run:
        run()
    else:
        print('Preparation only: validate offline, --freeze, then --run when authorized. No models loaded.')


if __name__ == '__main__':
    main()
