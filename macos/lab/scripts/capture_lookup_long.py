#!/usr/bin/env python3
"""Screen long English lookup costs without treating tracing as a speed result."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess

from benchmark import stream_completion, wait_ready
from benchmark_editing import clean_memory, power
from benchmark_m5_next import wait_for_headroom
from capture_m5_native import markers, monotonic_us, parse_lookup
from check_memory import assert_no_model_server
from engines import verify_engine
from lab import ROOT, request, server_command
from metal_environment import configure
from model_provenance import assert_unchanged, verify_models
from profile_m5_routes import preflight
from runtime_memory import admit_model, app_monitor
from validate_offline import fingerprint, require_pass

ENGINE = 'm5-lookup'
MAX_OUTPUT = 256
ORDER = ('trace', 'control')


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def workloads():
    # Synthetic English records: no user files, repeated filler or language detour.
    services = ('catalog', 'ledger', 'search', 'queue', 'billing', 'archive', 'gateway', 'worker')
    regions = ('north', 'south', 'east', 'west')
    owners = ('Amber', 'Birch', 'Cedar', 'Dawn', 'Elm', 'Fern', 'Grove', 'Hazel')
    tasks = ('restart after a timeout', 'check the input schema', 'rotate an expired key',
             'verify the stored checksum', 'inspect the retry limit', 'compare the daily totals',
             'reduce the batch size', 'confirm the backup receipt')
    cases = []
    for cohort in range(2):
        rows = []
        for i in range(36):
            k = i + cohort * 36
            rows.append(f"Record {k + 1}: the {services[k % 8]} service in the {regions[(k // 8) % 4]} "
                        f"region belongs to team {owners[(k // 4) % 8]}. Its review interval is {7 + k % 19} "
                        f"days, its timeout is {12 + k % 29} seconds, and its retry limit is {1 + k % 5}. "
                        f"The next action is to {tasks[(k // 3) % 8]}. The owner must record the outcome "
                        'before approving another change.')
        cases.append(dict(name=f'operations-{cohort + 1}', content=(
            'Read these fictional service review notes. Reply with exactly one English sentence, '
            'under twenty words, describing the common responsibility of the owners. '
            'Do not enumerate the records or explain your reasoning.\n\n' + '\n'.join(rows))))
    return cases


def validate_response(response, prompt_tokens):
    final = response['final']
    timings = final['timings']
    ids = response['generated_token_ids']
    if (not final.get('stop') or final.get('stop_type') != 'eos' or not ids
            or any(type(t) is not int or t < 0 for t in ids)
            or len(ids) >= MAX_OUTPUT or timings['predicted_n'] != len(ids)
            or timings['prompt_n'] != prompt_tokens or not response['text'].strip()):
        raise ValueError('Complete normal-EOS output and exact fresh prompt/token counts required')


def signature(record):
    return [(r['workload'], r['repeat'], r['prompt_sha256'], r['prompt_tokens'],
             r['response']['text'], r['response']['generated_token_ids']) for r in record['requests']]


def assess(text, requests):
    result = parse_lookup(text, requests)
    ops = markers(text, 'M5_LOOKUP_OP')
    for req, summary in zip(requests, result['requests']):
        first = req['begin_us'] + round(req['response']['ttft_s'] * 1e6)
        if not req['begin_us'] < first <= req['end_us']:
            raise ValueError('Invalid observed first-text interval')
        before = [o for o in ops if req['begin_us'] <= o['begin_us'] and o['end_us'] <= first]
        crossing = [o for o in ops if o['begin_us'] < first < o['end_us']]
        total = sum(o['envelope_us'] for o in before)
        summary.update(repeat=req['repeat'], first_exposure=req['repeat'] == 0,
                       observed_first_text_us=first - req['begin_us'],
                       lookup_before_first_text_us=total,
                       lookup_before_first_text_percent=100 * total / (first - req['begin_us']),
                       operations_crossing_first_text=len(crossing))
    result.update(cache_state='unknown; no purge, eviction, wiring or preload performed',
                  phase_limitation='First-text split uses client stream observation, not an internal prompt-phase callback. '
                                   'The earlier envelope can include initial generation. Tracing adds metadata work.',
                  eligible_tensor='lazy host-backed per_layer_token_embd.weight, verified by native mapping and loader log',
                  speed_gain_measured=False)
    result['prefetch_worth_investigating'] = any(
        max(r['upper_bound_percent'], r['lookup_before_first_text_percent']) >= 2
        for r in result['requests'] if r['first_exposure'])
    return result


def closure():
    return dict(sources=fingerprint(), engine=verify_engine(ENGINE))


def assert_frozen(frozen):
    require_pass()
    if closure() != frozen['closure']:
        raise RuntimeError('Source or diagnostic engine changed; use a new campaign')
    assert_unchanged(frozen['models'])


def launch(folder, role, frozen):
    folder.mkdir()
    record = dict(schema=1, status='running', role=role, requests=[], cleanup_errors=[],
                  models_loaded=False, timings_excluded_from_speed_results=True, normal_fusion=True)
    child = monitor = None
    try:
        assert_frozen(frozen)
        record['settle'] = wait_for_headroom()
        record['preflight'] = preflight(False)
        record['power'] = power()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env, flags = configure(os.environ, ENGINE, 'on', 'conv-direct')
        if role == 'trace':
            env['GGML_M5_LAB_LOOKUP_TRACE'] = '1'
            flags['variables']['GGML_M5_LAB_LOOKUP_TRACE'] = '1'
        record['environment'] = flags
        command = server_command('flash', port, 4096, 512, 512, 'draft-mtp', 3,
                                 draft_placement='mixed', draft_model='mtp_shared_packed_q3',
                                 engine=ENGINE, draft_threads=8, draft_p_min=0.0)
        record['command'] = command
        assert_unchanged(frozen['models'])
        policy = admit_model('flash')
        record['memory_policy'] = policy
        write(folder / 'capture.json', record)
        with (folder / 'native.log').open('w') as log:
            child = subprocess.Popen(command, env=env, stdout=log, stderr=log)
            record['models_loaded'] = True
            write(folder / 'capture.json', record)
            monitor = app_monitor(child, folder / 'memory.jsonl', policy)
            monitor.thread.start()
            base = f'http://127.0.0.1:{port}'
            record['ready_s'] = wait_ready(child, base)
            for case in workloads():
                rendered = request(base, '/apply-template', dict(messages=[dict(role='user', content=case['content'])],
                                   chat_template_kwargs={'enable_thinking': False}))['prompt']
                tokens = request(base, '/tokenize', dict(content=rendered, add_special=False, parse_special=True))['tokens']
                if not 2048 <= len(tokens) <= 3584:
                    raise RuntimeError(f'Long prompt outside frozen 2048–3584 token scope: {len(tokens)}')
                for repeat in range(2):
                    begin = monotonic_us()
                    response = stream_completion(base, dict(prompt=tokens, n_predict=MAX_OUTPUT, ignore_eos=False,
                        temperature=0, seed=1234, cache_prompt=False, return_tokens=True, stream=True))
                    end = monotonic_us()
                    validate_response(response, len(tokens))
                    record['requests'].append(dict(workload=case['name'], repeat=repeat, warmup=False,
                        begin_us=begin, end_us=end, prompt_tokens=len(tokens),
                        prompt_sha256=hashlib.sha256(json.dumps(tokens).encode()).hexdigest(), response=response))
                    write(folder / 'capture.json', record)
                    print(f"{role}: {case['name']} repeat{repeat}, {len(tokens)} input tokens, normal EOS", flush=True)
        record['status'] = 'completed'
    except BaseException as error:
        record.update(status='failed', error=f'{type(error).__name__}: {error}')
    finally:
        try:
            if child and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
            if monitor:
                record['memory'] = monitor.finish()
            assert_no_model_server()
            if record['status'] == 'completed':
                if not clean_memory(record['memory']):
                    raise RuntimeError('Continuous normal pressure, zero new swap and owned-child cleanup required')
                assert_frozen(frozen)
                text = (folder / 'native.log').read_text()
                if "enabling prefetch for 'per_layer_token_embd.weight'" not in text:
                    raise RuntimeError('Native loader did not confirm prefetch eligibility')
                if role == 'trace':
                    record['lookup'] = assess(text, record['requests'])
                elif markers(text, 'M5_LOOKUP_OP') or markers(text, 'M5_LOOKUP_MAPPING'):
                    raise RuntimeError('Control unexpectedly enabled tracing')
                record['status'] = 'passed'
        except BaseException as error:
            record.update(status='failed', error=f'{type(error).__name__}: {error}')
            record['cleanup_errors'].append(str(error))
        write(folder / 'capture.json', record)
    if record['status'] != 'passed':
        raise RuntimeError(record.get('error', 'Capture failed'))
    return record


def campaign(folder):
    folder.mkdir(parents=True, exist_ok=False)
    frozen = dict(closure=closure(), models=verify_models(['flash', 'mtp_shared_packed_q3']))
    result = dict(schema=1, status='running', frozen=frozen, order=ORDER, arms=[],
                  request_policy=dict(normal_eos=True, output_cap=MAX_OUTPUT, temperature=0, seed=1234,
                                      cache_prompt=False, warmups=0),
                  scope='Long English lookup diagnostic over m5-copy plus tracing; P07 is absent. '
                        'Not a speed comparison with the maintained small-reduce runtime.',
                  cache_state='unknown', models_loaded=False, speed_gain_measured=False)
    write(folder / 'campaign.json', result)
    for relative in frozen['closure']['sources']:
        dest = folder / 'source' / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((ROOT / relative).read_bytes())
    try:
        for role in ORDER:
            result['arms'].append(launch(folder / role, role, frozen))
            result['models_loaded'] = True
            write(folder / 'campaign.json', result)
        if signature(result['arms'][0]) != signature(result['arms'][1]):
            raise RuntimeError('Trace/control complete text, tokens or prompt identity differs')
        result.update(status='passed', exact_output_parity=True, lookup=result['arms'][0]['lookup'])
    except BaseException as error:
        result.update(status='failed', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        result['launches'] = [json.loads((folder / role / 'capture.json').read_text())
                             for role in ORDER if (folder / role / 'capture.json').is_file()]
        result['models_loaded'] = any(r['models_loaded'] for r in result['launches'])
        write(folder / 'campaign.json', result)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path)
    ap.add_argument('--run', action='store_true')
    args = ap.parse_args()
    if not args.run:
        print('Prepared: two long English files, first exposure and exact replay, native trace then parity control. '
              'Cache unknown; no warmup or purge; normal EOS; 34 GiB admission, normal pressure, zero new swap. No model loaded.')
        return
    require_pass()
    output = args.output or ROOT / 'bench/features' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-lookup-long')
    with (ROOT / 'bench/.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = campaign(output)
    print(json.dumps(dict(status=result['status'], lookup=result['lookup']), indent=2), flush=True)


if __name__ == '__main__':
    main()
