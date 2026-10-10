#!/usr/bin/env python3
"""Untimed, normal-scheduler embedding-order diagnostic; no callback or speed claim."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark import Monitor, stream_completion, wait_ready
from capture_m5_native import PROMPTS, normalized_command
from check_memory import assert_no_model_server
from engines import sha256, verify_engine
from lab import request, server_command
from metal_environment import configure
from model_provenance import assert_unchanged, verify_models
from profile_m5_routes import preflight
from validate_offline import require_pass


def capture(engine, folder, proof):
    folder.mkdir()
    source = sha256(__file__)
    (folder / 'runner.py').write_bytes(Path(__file__).read_bytes())
    pin = verify_engine(engine)
    env, flags = configure(os.environ, engine, 'on', 'conv-direct')
    env['GGML_SCHED_DEBUG'] = '2'
    flags['variables']['GGML_SCHED_DEBUG'] = '2'
    record = dict(schema=1, status='running', engine=pin, model_proof=proof,
                  runner_sha256=source, metal_environment=flags, requests=[],
                  timings_excluded_from_speed_results=True, evaluation_callback=False,
                  request_policy=dict(temperature=0, seed=1234, predict=32, ignore_eos=True))
    save = lambda: (folder / 'capture.json').write_text(json.dumps(record, indent=2, allow_nan=False)+'\n')
    process = monitor = None
    stop_log_guard = threading.Event()
    log_guard = None
    try:
        require_pass(); assert_no_model_server(); assert_unchanged(proof)
        record['preflight'] = preflight(False)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        command = server_command('flash', port, 4096, 512, 512, 'draft-mtp', 3,
            draft_placement='mixed', draft_model='mtp_shared_packed_q3', engine=engine,
            draft_threads=8, draft_p_min=0.0)
        command[command.index('--verbosity')+1] = '5'
        record['command'] = command
        save()
        log_path = folder / 'native.log'
        with log_path.open('w') as log:
            baseline = Monitor.baseline()
            process = subprocess.Popen(command, env=env, stdout=log, stderr=log)
            monitor = Monitor(process, folder / 'memory.jsonl', 0, 1024**3, baseline=baseline)
            monitor.thread.start()
            def guard_log():
                while not stop_log_guard.wait(0.25):
                    if log_path.stat().st_size > 128*1024**2:
                        record['log_guard'] = '128 MiB diagnostic log cap exceeded'
                        monitor.stop_owned_child(); return
            log_guard = threading.Thread(target=guard_log, daemon=True); log_guard.start()
            base = f'http://127.0.0.1:{port}'
            record['ready_s'] = wait_ready(process, base)
            time.sleep(0.3)
            record['startup_log_end'] = log_path.stat().st_size
            print('Ready', engine, record['ready_s'], flush=True)
            def encode(text):
                return request(base, '/tokenize', dict(content=text, add_special=False, parse_special=True))['tokens']
            def render(text):
                return request(base, '/apply-template', dict(messages=[dict(role='user', content=text)],
                    chat_template_kwargs={'enable_thinking':False}))['prompt']
            def complete(name, tokens, cached=False):
                time.sleep(0.2)
                begin = log_path.stat().st_size
                response = stream_completion(base, dict(prompt=tokens, n_predict=32, ignore_eos=True,
                    temperature=0, seed=1234, cache_prompt=cached, return_tokens=True, stream=True))
                time.sleep(0.2)
                end = log_path.stat().st_size
                timings = response['final']['timings']
                if timings['predicted_n'] != 32 or len(response['generated_token_ids']) != 32:
                    raise RuntimeError('Output token count mismatch')
                if not cached and timings['prompt_n'] != len(tokens):
                    raise RuntimeError('Fresh prompt token count mismatch')
                if cached and not 0 <= timings['prompt_n'] < len(tokens):
                    raise RuntimeError('Cached request did not reuse prefix')
                record['requests'].append(dict(workload=name, cache_prompt=cached, prompt=tokens,
                    prompt_sha256=hashlib.sha256(json.dumps(tokens).encode()).hexdigest(),
                    log_begin=begin, log_end=end, response=response))
                save(); print(engine, name, 'ok', flush=True)
            for name, content in PROMPTS.items(): complete(name, encode(render(content)))
            filler = 'The lab machine has 48 GB of memory. Its SSD stores model lookup rows. We compare repeatable inference runs, preserve the baseline, and record speed and memory. ' * 600
            tokens = encode(render(filler+'Explain a repeatable benchmark in plain language.'))
            prompt = tokens[:512-48]+tokens[-48:]
            complete('synthetic512', prompt)
            followup = prompt + encode('\nNow give a concrete example of the same experiment.\n')
            complete('cached-followup', followup, True)
            complete('fresh-followup', followup)
            cached, fresh = record['requests'][-2:]
            if any(cached['response'][k] != fresh['response'][k] for k in ('text','generated_token_ids')):
                raise RuntimeError('Cached/fresh continuation parity failed')
            record['status'] = 'completed'
    except BaseException as error:
        record.update(status='failed', error=f'{type(error).__name__}: {error}')
    finally:
        stop_log_guard.set()
        if log_guard: log_guard.join(timeout=2)
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        if monitor: record['memory'] = monitor.finish()
        try:
            assert_no_model_server()
            if record['status'] == 'completed':
                memory = record['memory']
                if record.get('log_guard') or memory['guard'] or memory['swap_growth_bytes'] or not memory['monitor_healthy'] or not memory['child_exited']:
                    raise RuntimeError('Diagnostic resource/cleanup gate failed')
                if verify_engine(engine) != pin or sha256(__file__) != source:
                    raise RuntimeError('Diagnostic provenance changed')
                assert_unchanged(proof); require_pass()
                text = (folder/'native.log').read_text()
                if 'borrowing target embeddings/output; draft KV remains separate' not in text:
                    raise RuntimeError('Shared helper did not activate')
                actual = (folder/'native.log').read_bytes()[record['startup_log_end']:].decode()
                if '## SPLIT #0:' not in actual:
                    raise RuntimeError('No actual-request scheduler graph evidence')
                record['status'] = 'passed'
        except BaseException as error:
            record.update(status='failed', error=f'{type(error).__name__}: {error}')
        save(); print(engine, record['status'], folder, flush=True)
    if record['status'] != 'passed': raise RuntimeError(record.get('error','capture failed'))
    return record


def main():
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        require_pass(); assert_no_model_server()
        proof = verify_models(['flash','mtp_shared_packed_q3'])
        folder = ROOT/'bench/features'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-m5-embedding-topology')
        folder.mkdir(); print(folder, flush=True)
        records = []
        for engine in ('m5-copy','m5-embedding'):
            if records:
                print('Waiting 10 seconds for previous model resources to settle', flush=True)
                time.sleep(10)
            records.append(capture(engine, folder/engine, proof))
        signature = lambda r: [(x['workload'],x['cache_prompt'],x['prompt_sha256'],x['response']['generated_token_ids'],x['response']['text']) for x in r['requests']]
        if signature(records[0]) != signature(records[1]) or normalized_command(records[0]['command']) != normalized_command(records[1]['command']):
            raise RuntimeError('Engine comparison outputs or settings differ')
        parity = dict(status='passed', requests_identical=len(records[0]['requests']),
            output_tokens_identical=sum(len(r['response']['generated_token_ids']) for r in records[0]['requests']),
            cached_fresh_checks=2, speed_gain_measured=False)
        (folder/'parity.json').write_text(json.dumps(parity,indent=2)+'\n')
        print('Parity', parity, flush=True)


if __name__ == '__main__': main()
