#!/usr/bin/env python3
"""Freeze or execute the first native/MLX English greedy-output screen."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import threading

from benchmark import Monitor, host_snapshot, stream_completion, wait_ready
from benchmark_mlx_cache import source_pins, watch_pressure
from check_memory import assert_no_model_server
from engines import sha256
from lab import ROOT, server_command
from metal_environment import configure
from mlx_cache_protocol import validate_launch, summarize
from model_provenance import assert_unchanged, verify_models
from profile_m5_routes import preflight
from validate_offline import fingerprint, require_pass

CONFIG = ROOT / 'config/native_mlx_greedy.json'
RESULTS = ROOT / 'bench/results/20261010-native-mlx-greedy-v1'


def write(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, allow_nan=False) + '\n')


def reference(plan):
    folder = ROOT / plan['reference']
    old = json.loads((folder / 'frozen.json').read_text())
    pins = {}
    for name, digest in old['archive'].items():
        if sha256(folder / 'source' / name) != digest:
            raise ValueError('Original MLX source archive changed')
    groups = []
    for i, budget in enumerate(old['plan']['budgets_decimal_GB']):
        path = folder / f'{i:02}-{budget}GB/result.json'
        result = json.loads(path.read_text())
        if result['status'] != 'passed' or result['memory']['swap_growth_bytes']:
            raise ValueError('MLX reference is not a clean completed launch')
        groups.append(validate_launch(result['output'], old['plan'], old['inputs'], budget))
        pins[str(path.relative_to(ROOT))] = sha256(path)
    if summarize(groups, old['plan']) != json.loads((folder / 'comparison.json').read_text())['summary']:
        raise ValueError('Original MLX comparison no longer recomputes')
    for name in ('frozen.json', 'comparison.json', 'post-run-verification.json'):
        pins[str((folder / name).relative_to(ROOT))] = sha256(folder / name)
    current = source_pins()
    if any(current[key] != old['sources'][key] for key in current if key != 'offline_sources'):
        raise ValueError('Reference runtime, dependencies or native helper changed')
    answers = {r['workload']: dict(input_ids=r['input_ids'], output_ids=r['output_ids'],
                                  finish_reason=r['finish_reason']) for r in groups[0]}
    if set(answers) != {'code', 'prose'} or any(len(r['output_ids']) != plan['output_limit']
                                               or r['finish_reason'] != 'length' for r in answers.values()):
        raise ValueError('This screen requires the original capped English reference')
    return dict(pins=pins, answers=answers, sources=current)


def evaluate(response, expected, plan):
    ids = response.get('generated_token_ids', [])
    final = response.get('final', {})
    timings = final.get('timings', {})
    settings = final.get('generation_settings', {})
    if (not ids or any(type(t) is not int or t < 0 for t in ids)
            or len(ids) > plan['output_limit'] or final.get('stop') is not True
            or final.get('tokens_predicted') != len(ids)
            or timings.get('predicted_n') != len(ids)
            or timings.get('prompt_n') != len(expected['input_ids'])
            or timings.get('draft_n', 0) != 0 or timings.get('draft_n_accepted', 0) != 0
            or settings.get('temperature') != 0 or settings.get('seed') != 1234
            or settings.get('ignore_eos') is not False
            or settings.get('samplers') != ['temperature']):
        raise ValueError('Native answer inventory, sampler, input count or helper scope changed')
    mismatch = next((i for i, (a, b) in enumerate(zip(expected['output_ids'], ids)) if a != b), None)
    if mismatch is None and len(ids) != len(expected['output_ids']):
        mismatch = min(len(ids), len(expected['output_ids']))
    finish = final.get('stop_type')
    passed = mismatch is None and finish == 'limit'
    return dict(exact_output=passed, first_mismatch_zero_based=mismatch,
                expected_token=expected['output_ids'][mismatch] if mismatch is not None and mismatch < len(expected['output_ids']) else None,
                actual_token=ids[mismatch] if mismatch is not None and mismatch < len(ids) else None,
                native_stop_type=finish, output_tokens=len(ids),
                tensor_state_equivalence=False, numerical_equivalence=False, adoption=False)


def freeze():
    require_pass()
    if RESULTS.exists():
        raise ValueError('Campaign already exists; never overwrite')
    plan = json.loads(CONFIG.read_text())
    ref = reference(plan)
    models = verify_models(['flash'])
    files = fingerprint()
    archive = {}
    for name, digest in files.items():
        path = RESULTS / 'source' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, path)
        archive[name] = sha256(path)
        if archive[name] != digest:
            raise ValueError('Source archive changed during freeze')
    assert_unchanged(models)
    write(RESULTS / 'frozen.json', dict(status='prepared-not-run', created_utc=datetime.now(timezone.utc).isoformat(),
                                       plan=plan, reference=ref, models=models, archive=archive,
                                       adoption=False, timings_excluded_from_speed_results=True))
    print('Frozen first greedy-output screen:', RESULTS, flush=True)


def unchanged(frozen):
    require_pass()
    if json.loads(CONFIG.read_text()) != frozen['plan'] or fingerprint() != frozen['archive']:
        raise ValueError('Screen source/config changed')
    if reference(frozen['plan']) != frozen['reference']:
        raise ValueError('Native/MLX reference pins changed')
    for name, digest in frozen['archive'].items():
        if sha256(RESULTS / 'source' / name) != digest:
            raise ValueError('Screen source archive changed')
    assert_unchanged(frozen['models'])


def run():
    destination = RESULTS / 'result.json'
    if destination.exists():
        raise ValueError('Screen already attempted; no automatic retry or partial resume')
    frozen = json.loads((RESULTS / 'frozen.json').read_text())
    plan = frozen['plan']
    process = monitor = pressure_thread = timer = None
    done = threading.Event()
    pressure = dict(samples=0, error=None)
    record = dict(status='preflight', cases=[], adoption=False, timings_excluded_from_speed_results=True,
                  scope=plan['scope'])
    try:
        with (ROOT / 'bench/.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            unchanged(frozen)
            record['preflight'] = preflight(False)
            record['host_before'] = host_snapshot()
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            env, flags = configure(os.environ, plan['engine'], plan['tensor_api'], plan['tuning'])
            command = server_command('flash', port, plan['context'], plan['batch'], plan['batch'],
                                     spec='none', draft=0, cache_type=plan['kv_type'],
                                     threads=plan['threads'], engine=plan['engine'])
            record.update(command=command, metal_environment=flags, status='running')
            write(destination, record)
            baseline = Monitor.baseline()
            if baseline['available_bytes'] < plan['admission_gib'] * 2**30:
                raise ValueError('Final native 34 GiB admission failed; no child launched')
            if int(subprocess.check_output(['sysctl', '-n', 'kern.memorystatus_vm_pressure_level'], text=True)) != 1:
                raise ValueError('Final pressure admission failed; no child launched')
            with (RESULTS / 'native.log').open('w') as log:
                process = subprocess.Popen(command, env=env, stdout=log, stderr=log, start_new_session=True)
                monitor = Monitor(process, RESULTS / 'memory.jsonl', 0,
                                  plan['availability_floor_gib'] * 2**30, baseline=baseline)
                monitor.thread.start()
                pressure_thread = threading.Thread(target=watch_pressure,
                    args=(process, RESULTS / 'pressure.jsonl', done, pressure), daemon=True)
                pressure_thread.start()
                timer = threading.Timer(plan['timeout_s'], lambda: process.terminate() if process.poll() is None else None)
                timer.start()
                base = f'http://127.0.0.1:{port}'
                record['ready_s'] = wait_ready(process, base)
                for repeat in range(plan['repeats']):
                    for name in ('code', 'prose'):
                        expected = frozen['reference']['answers'][name]
                        payload = dict(plan['payload'], prompt=expected['input_ids'])
                        response = stream_completion(base, payload)
                        row = dict(workload=name, repeat=repeat, input_ids=expected['input_ids'],
                                   request=payload, response=response)
                        record['cases'].append(row)
                        write(destination, record)
                        row['comparison'] = evaluate(response, expected, plan)
                        write(destination, record)
                        print(json.dumps({'workload':name, 'repeat':repeat, **row['comparison']}), flush=True)
                record['status'] = 'completed'
    except BaseException as error:
        record.update(status='failed', error=f'{type(error).__name__}: {error}')
    finally:
        if timer:
            timer.cancel()
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        done.set()
        if pressure_thread:
            pressure_thread.join(timeout=5)
        if monitor:
            record['memory'] = monitor.finish()
        record['pressure'] = pressure
        record['host_after'] = host_snapshot()
        try:
            assert_no_model_server()
            if record['status'] == 'completed':
                memory = record['memory']
                if (memory['guard'] or memory['swap_growth_bytes'] or not memory['monitor_healthy']
                        or not memory['child_exited'] or pressure['error'] or not pressure['samples']
                        or pressure_thread.is_alive()):
                    raise ValueError('Native screen resource monitor/cleanup failed')
                unchanged(frozen)
                record.update(status='passed-output-screen' if all(r['comparison']['exact_output'] for r in record['cases'])
                              else 'completed-output-divergence', native_state_qualified=False,
                              numerical_qualified=False, speed_gain_claimed=False)
        except BaseException as error:
            record.update(status='failed', postcheck_error=f'{type(error).__name__}: {error}')
        write(destination, record)
        print('Native/MLX screen:', record['status'], flush=True)
    if record['status'] == 'failed':
        raise RuntimeError(record.get('error', record.get('postcheck_error')))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument('--freeze', action='store_true')
    choice.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    if args.freeze:
        freeze()
    elif args.run:
        run()
    else:
        print('Prepared first English greedy-output screen; no model load. Use --freeze then --run.')


if __name__ == '__main__':
    main()
