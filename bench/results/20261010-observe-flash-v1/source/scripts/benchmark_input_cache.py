#!/usr/bin/env python3
"""Held 4B Service comparison of cold, identical and unique whole-input tokenization."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
import socket
import statistics
import subprocess
import threading
import time

from benchmark import Monitor, host_snapshot, wait_ready
from benchmark_m5_small_gains import launch_row
from benchmark_streaming import RecordingEngine, TASKS
from check_memory import assert_no_model_server
from engines import ROOT, sha256, verify_engine
from input_token_cache import InputCacheTokenizer
from lab import request, server_command
from model_provenance import assert_unchanged, verify_models
from native_backend import NativeEngine, NativeTemplate
from profile_m5_routes import preflight
from validate_offline import fingerprint, require_pass
from metal_environment import configure
from serve.server import Service

RESULTS = ROOT / 'bench/results/20261010-next-tests-v2/input-cache'
NATIVE = 'm5-small-stack'
ORDER = (False, True, True, False)
MODES = ('cold', 'identical', 'unique')
RULE = ('Independent fresh native launches A/B/B/A on pinned Qwen3.5-4B Q4_K_M; same instrumented '
        'Service path and P07-capable engine, prompt_cache=false, no MTP or piece cache. English code/prose, '
        'cold/identical/unique inputs, one excluded warmup and three measured repeats. Exact input IDs, '
        'output IDs, parser events and finish parity. Native generation acceleration attribution is zero. '
        'Positive identical-input first-content AND reply gain above 2x own control drift; both B launches '
        'beat both A; cold/unique/native TPS may not materially regress beyond max(1 percent,2x drift). '
        'Healthy monitoring and zero new swap. Independent confirmation and full-model app exposure are '
        'required before any default change. Service timings omit browser rendering and incoming HTTP overhead.')


def write(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, allow_nan=False) + '\n')


def pins():
    return dict(sources=fingerprint(), engine=verify_engine(NATIVE),
                vendor={name: sha256(ROOT / name) for name in
                        ('vendor/Strata-macOS/serve/server.py',)})


def freeze():
    require_pass(); assert_no_model_server()
    if (RESULTS / 'frozen.json').exists(): raise ValueError('Do not overwrite a frozen campaign')
    write(RESULTS / 'frozen.json', dict(status='prepared-not-run', pins=pins(), rule=RULE,
          tasks=TASKS, launch_order=list(ORDER), modes=list(MODES), output_limit=128,
          models_loaded=False, gpu_tests_run=False, benchmarks_run=False,
          created_utc=datetime.now(timezone.utc).isoformat()))


def unchanged(frozen):
    if frozen['pins'] != pins() or frozen['rule'] != RULE or frozen['tasks'] != TASKS:
        raise ValueError('Frozen comparison inputs changed')


def measure(base, props, tok, text):
    engine = RecordingEngine(NativeEngine(base, props, 'small', prompt_cache=False))
    service = Service(engine, tok, None)
    before = dict(tok.encode_stats)
    started = time.monotonic()
    rendered = NativeTemplate(base).render([dict(role='user', content=text)], enable_thinking=False)
    ids = tok.encode(rendered, parse_special=True)
    encoded = time.monotonic()
    events, first, done = [], None, None
    for kind, item in service.run(ids, False, [], 128, dict(temperature=.6, seed=1234), threading.Event()):
        if kind == 'event':
            events.append(asdict(item))
            if item.text and first is None: first = time.monotonic()
        elif kind == 'done': done = item
    wall = time.monotonic() - started
    timing = engine.last.get('native_timings')
    if (not timing or timing.get('predicted_n') != 128 or timing.get('cache_n') != 0 or
            len(engine.tokens) != 128 or first is None or done is None):
        raise ValueError('Incomplete fixed output or hidden prompt reuse')
    return dict(wall_s=wall, ttft_s=first-started, encode_render_s=encoded-started,
                generation_tok_s=timing['predicted_per_second'], prompt_tok_s=timing['prompt_per_second'],
                input_tokens=ids, tokens=engine.tokens, events=events, done=done, native_timings=timing,
                encode_stats={key:tok.encode_stats[key]-before[key] for key in before},
                cache_entries=len(tok.entries), cache_accounted_bytes=tok.accounted_bytes,
                text_sha256=hashlib.sha256(text.encode()).hexdigest())


def summarize(records):
    if len(records) != 4 or [r['enabled'] for r in records] != list(ORDER):
        raise ValueError('Independent ABBA launches missing')
    if any(r.get('status') != 'passed' for r in records): raise ValueError('Failed launch cannot qualify')
    reference = None
    for record in records:
        if not record.get('engine') or not record.get('models'):
            raise ValueError('Verified engine/model provenance missing')
        memory = record.get('memory', {})
        if (memory.get('swap_growth_bytes') != 0 or memory.get('guard') or
                memory.get('monitor_healthy') is not True or memory.get('child_exited') is not True):
            raise ValueError('Resource evidence missing or failed')
        if (record.get('engine') != records[0].get('engine') or
                record.get('models') != records[0].get('models')):
            raise ValueError('Engine or verified model changed between launches')
        signatures = [(c['task'], c['mode'], c['repeat'], c['text_sha256'], c['input_tokens'],
                       c['tokens'], c['events'], c['done']) for c in record['cases']]
        if reference is None: reference = signatures
        if signatures != reference: raise ValueError('Complete Service parity changed')
        if len(record['cases']) != len(TASKS)*len(MODES)*4:
            raise ValueError('Incomplete cold/identical/unique coverage')
        expected = {(task, mode, n) for task in TASKS for mode in MODES for n in range(4)}
        actual = [(c['task'], c['mode'], c['repeat']) for c in record['cases']]
        if len(actual) != len(set(actual)) or set(actual) != expected:
            raise ValueError('Missing or duplicated planned input case')
        for case in record['cases']:
            if case['warmup'] is not (case['repeat'] == 0): raise ValueError('Warmup scope changed')
            expected_hit = int(record['enabled'] and case['mode'] == 'identical' and case['repeat'] > 0)
            if (case['encode_stats']['hits'] != expected_hit or
                    case['encode_stats']['requests'] != 1-expected_hit or
                    case['encode_stats']['errors'] or case['cache_accounted_bytes'] > 2*1024**2):
                raise ValueError('Input-cache activation or bounds failed')
    rows = []
    for task in TASKS:
        for mode in MODES:
            groups = [[c for c in r['cases'] if c['task']==task and c['mode']==mode and c['repeat']>0]
                      for r in records]
            if any(len(g) != 3 for g in groups): raise ValueError('Three measured repeats missing')
            medians = [{key:statistics.median(c[key] for c in g) for key in
                        ('generation_tok_s','prompt_tok_s','ttft_s','wall_s')} for g in groups]
            row = launch_row(medians); row.update(task=task, mode=mode); rows.append(row)
    repeated = [r for r in rows if r['mode']=='identical']
    useful = len(repeated)==2 and all(r['qualifying_metrics']['ttft_reduction_percent'] and
             r['qualifying_metrics']['total_time_reduction_percent'] for r in repeated)
    return dict(rows=rows, eligible_for_confirmation=useful and all(not r['regressions'] for r in rows),
                adoption=False, attributed_native_TPS_gain=0, rule=RULE)


def execute(index, enabled, frozen, models):
    unchanged(frozen); assert_no_model_server(); assert_unchanged(models)
    folder = RESULTS / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + str(index))
    folder.mkdir(parents=True)
    record = dict(status='running', enabled=enabled, launch_index=index, cases=[], models=models,
                  engine=frozen['pins']['engine'], host_before=host_snapshot())
    process = monitor = None
    def save(): write(folder / 'result.json', record)
    save()
    try:
        record['preflight'] = preflight(small=True)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        command = server_command('small', port, 4096, batch=512, ubatch=512, engine=NATIVE)
        env, flags = configure(dict(os.environ), NATIVE, 'on', 'small-reduce')
        record.update(command=command, environment=flags)
        with (folder / 'native.log').open('w') as log:
            baseline = Monitor.baseline()
            process = subprocess.Popen(command, stdout=log, stderr=log, env=env)
            monitor = Monitor(process, folder / 'memory.jsonl', 0, 1024**3, baseline=baseline)
            monitor.thread.start(); record['ready_s'] = wait_ready(process, base)
            props = request(base, '/props'); record['props'] = props
            tok = InputCacheTokenizer(base, enabled=enabled)
            for task, text in TASKS.items():
                for mode in MODES:
                    tok.clear_input_cache()
                    for repetition in range(4):
                        if monitor.guard: raise ValueError('Resource guard fired')
                        if mode == 'cold': tok.clear_input_cache()
                        prompt = text if mode != 'unique' else f'Example version {repetition}.\n' + text
                        result = measure(base, props, tok, prompt)
                        record['cases'].append(dict(task=task, mode=mode, repeat=repetition,
                                                    warmup=repetition==0, **result)); save()
            unchanged(frozen); assert_unchanged(models)
            record['status'] = 'passed'
    except BaseException as error:
        record.update(status='failed', error=f'{type(error).__name__}: {error}'); raise
    finally:
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=10)
        if monitor:
            memory = monitor.finish(); record['memory'] = memory
            if (memory['guard'] or memory['swap_growth_bytes'] or not memory['monitor_healthy'] or
                    not memory['child_exited']): record.update(status='failed', error='Resource/monitor gate failed')
        save()
    if record['status'] != 'passed': raise ValueError(record.get('error', 'Failed launch'))
    return record


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--freeze', action='store_true'); mode.add_argument('--run', action='store_true')
    args = ap.parse_args(argv)
    if not (args.freeze or args.run):
        print('Prepared 4B cold/identical/unique English Service test. --freeze records; --run loads the model.')
        return
    with (ROOT / 'bench/.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.freeze: freeze(); return
        require_pass(); frozen = json.loads((RESULTS / 'frozen.json').read_text())
        unchanged(frozen); assert_no_model_server()
        state_path = RESULTS / 'tracking.json'
        if state_path.exists(): raise ValueError('No automatic retry or partial resume')
        state = dict(status='running', adoption=False, frozen_sha256=sha256(RESULTS/'frozen.json'), runs=[])
        write(state_path, state)
        try:
            models = verify_models(['small']); records=[]
            for index, enabled in enumerate(ORDER):
                records.append(execute(index, enabled, frozen, models)); state['runs'].append(index); write(state_path,state)
            state.update(status='passed', comparison=summarize(records))
        except BaseException as error:
            state.update(status='failed', error=f'{type(error).__name__}: {error}'); raise
        finally: write(state_path, state)


if __name__ == '__main__': main()
