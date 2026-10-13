#!/usr/bin/env python3
"""Guarded prompt-chunk trials on the kept engine; no load without --run."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import statistics
import subprocess

from benchmark import stream_completion, wait_ready
from benchmark_editing import (FIXTURES, clean_memory, drafting_receipts, fixtures, power,
                               prompt, trial_command, validate_response)
from benchmark_m5_next import wait_for_headroom
from benchmark_m5_small_gains import feature_receipts, launch_row
from benchmark_metrics import METRICS
from capture_lookup_long import workloads as documents
from check_memory import assert_no_model_server
from engines import sha256, verify_engine
from lab import ROOT, request, server_command
from metal_environment import configure
from model_provenance import assert_unchanged, verify_models
from profile_m5_routes import preflight
from runtime_memory import admit_model, app_monitor
from validate_offline import fingerprint, require_pass

ENGINE = 'm5-small-stack'
MAX_OUTPUT = 768
REPEATS = 3
ORDER = ('control', 'candidate', 'candidate', 'control')
PROFILES = {'512': (512, 512), '1024': (1024, 1024), '1536': (1536, 1536), '256': (512, 256)}


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def cases(draft_profile='balanced'):
    if draft_profile not in ('balanced', 'code-edit'): raise ValueError('Unknown draft profile')
    edits = ([f for f in fixtures() if f['cohort'] == 'confirm'] if draft_profile == 'code-edit' else
             [f for f in fixtures() if f['name'] == 'python-client'])
    notes = documents()[0]['content'].split('\n\n', 1)[1]
    return [dict(name='long-retrieval', kind='retrieval', content=(
        'Read the fictional notes below. Return only a JSON object for Record 27, with keys owner, '
        'timeout_seconds and retry_limit. Do not explain.\n\n' + notes)),
        dict(name='long-prose', kind='prose', content=documents()[1]['content'])] + [
        dict(name=f['name'], kind='editing', content=prompt(f), fixture=f) for f in edits] + [
        dict(name='short-prose', kind='prose', content=(
            'In about 180 words, explain why local AI benchmark results vary. '
            'Cover model size, input length, draft tokens, warmup, and memory. Use clear English.'))]


def quality(case, text):
    if case['kind'] == 'editing':
        f = case['fixture']
        return text.strip() == f['source'].replace(f['old'], f['new']).strip()
    if case['kind'] == 'retrieval':
        try:
            value = json.loads(text)
        except ValueError:
            return False
        return (isinstance(value, dict) and set(value) == {'owner', 'timeout_seconds', 'retry_limit'}
                and value['owner'] in ('Grove', 'team Grove')
                and value['timeout_seconds'] == 38 and value['retry_limit'] == 2)
    # Exact token parity is the optimization gate; this is not an independent prose grade.
    return bool(text.strip()) and '<think>' not in text


def signature(rows):
    return [(r['name'], r['repeat'], r['prompt_sha256'], r['prompt_tokens'],
             r['response']['text'], r['response']['generated_token_ids']) for r in rows]


def chunk_receipt(text, profile):
    """Reject silent batch clamping in either target or shared helper context."""
    batch, ubatch = PROFILES[profile]
    values = {key: list(map(int, re.findall(r'\bllama_context: ' + key + r'\s*=\s*(\d+)', text)))
              for key in ('n_batch', 'n_ubatch')}
    if values != {'n_batch': [batch, batch], 'n_ubatch': [ubatch, ubatch]}:
        raise ValueError('Native target/helper batch sizes differ from the declared recipe')
    return values


def compare(arms, draft_profile='balanced'):
    if (len(arms) != 4 or [a['role'] for a in arms] != list(ORDER)
            or any(a['status'] != 'passed' for a in arms)):
        raise ValueError('Only a complete healthy A/B/B/A bracket can be scored')
    names = [c['name'] for c in cases(draft_profile)]
    expected = {(n, r) for n in names for r in range(REPEATS)}
    for arm in arms:
        keys = [(r['name'], r['repeat']) for r in arm['cases']]
        if len(keys) != len(expected) or set(keys) != expected:
            raise ValueError('Missing, duplicate or unexpected request')
    parity = all(signature(a['cases']) == signature(arms[0]['cases']) for a in arms[1:])
    good = all(r['quality_passed'] for a in arms for r in a['cases'])
    rows = []
    for name in names:
        for phase in ('first-exposure', 'replay'):
            groups = [[r for r in a['cases'] if r['name'] == name and
                       (r['repeat'] == 0 if phase == 'first-exposure' else r['repeat'] > 0)] for a in arms]
            row = launch_row([{k: statistics.median(r[k] for r in g) for k in METRICS} for g in groups])
            row.update(name=name, phase=phase, exact_output_parity=parity, quality_passed=good)
            row['eligible_prompt_scope'] = (parity and good and not row['regressions']
                and row['qualifying_metrics']['ttft_reduction_percent']
                and row['qualifying_metrics']['total_time_reduction_percent'])
            rows.append(row)
    return dict(rows=rows, exact_output_parity=parity, all_quality_checks_pass=good,
                default_changed=False, confirmation_required=True,
                limitation='First exposure is a process-local observation, not controlled cold SSD. '
                           'Replay has fresh prompt computation but shares OS/model/kernel caches. '
                           'Two launches per arm; small gains need a new independent confirmation.')


def closure():
    return dict(sources=fingerprint(), fixture_sha256=sha256(FIXTURES), engine=verify_engine(ENGINE))


def check_frozen(frozen):
    require_pass()
    if closure() != frozen['closure']:
        raise RuntimeError('Frozen source or engine changed; start a new campaign')
    assert_unchanged(frozen['models'])


def launch(folder, role, profile, frozen, draft_profile='balanced'):
    folder.mkdir()
    result = dict(status='running', role=role, profile=profile, draft_profile=draft_profile,
                  cases=[], models_loaded=False)
    child = monitor = None
    try:
        assert_no_model_server(); check_frozen(frozen)
        result['settle'] = wait_for_headroom()
        result['preflight'] = preflight(False)
        result['power'] = power()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        batch, ubatch = PROFILES[profile]
        command = server_command('flash', port, 4096, batch, ubatch, 'draft-mtp', 3,
            draft_placement='mixed', draft_model='mtp_shared_packed_q3', engine=ENGINE,
            draft_threads=8, draft_p_min=0.0)
        command = trial_command(command, draft_profile)
        env, flags = configure(os.environ, ENGINE, 'on', 'small-reduce')
        result.update(command=command, settings=dict(batch=batch, ubatch=ubatch, metal=flags),
                      memory_policy=admit_model('flash'))
        write(folder / 'result.json', result)
        with (folder / 'native.log').open('w') as log:
            child = subprocess.Popen(command, env=env, stdout=log, stderr=log)
            result['models_loaded'] = True
            write(folder / 'result.json', result)
            monitor = app_monitor(child, folder / 'memory.jsonl', result['memory_policy'])
            monitor.thread.start()
            base = f'http://127.0.0.1:{port}'
            result['ready_s'] = wait_ready(child, base)
            for case in cases(draft_profile):
                rendered = request(base, '/apply-template', dict(messages=[dict(role='user', content=case['content'])],
                    chat_template_kwargs={'enable_thinking': False}))['prompt']
                tokens = request(base, '/tokenize', dict(content=rendered, add_special=False, parse_special=True))['tokens']
                if not tokens or len(tokens) + MAX_OUTPUT > 4096:
                    raise ValueError('Request exceeds frozen 4K context')
                if case['name'].startswith('long-') and not 2048 <= len(tokens) <= 3000:
                    raise ValueError('Long prompt is outside the predeclared scope')
                for repeat in range(REPEATS):
                    response = stream_completion(base, dict(prompt=tokens, n_predict=MAX_OUTPUT,
                        temperature=0, seed=1234, cache_prompt=False, ignore_eos=False, return_tokens=True, stream=True))
                    row = validate_response(response)
                    timings = response['final']['timings']
                    if timings['prompt_n'] != len(tokens) or row['output_tokens'] != len(response['generated_token_ids']):
                        raise ValueError('Complete fresh prompt and exact output token counts required')
                    row.update(name=case['name'], repeat=repeat, prompt_tokens=len(tokens),
                        prompt_sha256=hashlib.sha256(json.dumps(tokens).encode()).hexdigest(),
                        quality_passed=quality(case, response['text']))
                    result['cases'].append(row); write(folder / 'result.json', result)
                    print(f"{role}/{profile}: {case['name']} r{repeat}: prompt {row['prompt_tok_s']:.2f}, "
                          f"generation {row['generation_tok_s']:.2f} TPS, first {row['ttft_s']:.3f}s, "
                          f"reply {row['wall_s']:.3f}s, quality={row['quality_passed']}", flush=True)
        result['status'] = 'completed'
    except BaseException as error:
        result.update(status='failed', error=f'{type(error).__name__}: {error}')
    finally:
        if child and child.poll() is None:
            child.terminate()
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=5)
        if monitor: result['memory'] = monitor.finish()
        try:
            assert_no_model_server(); check_frozen(frozen)
            if result['status'] == 'completed':
                if not clean_memory(result['memory']): raise RuntimeError('RAM/swap/cleanup gate failed')
                result['activation'] = feature_receipts((folder / 'native.log').read_text(), ['reduce'])
                result['drafting'] = drafting_receipts((folder / 'native.log').read_text(), draft_profile)
                result['actual_chunks'] = chunk_receipt((folder / 'native.log').read_text(), profile)
                result['status'] = 'passed'
        except BaseException as error:
            result.update(status='failed', error=f'{type(error).__name__}: {error}')
        write(folder / 'result.json', result)
    if result['status'] != 'passed': raise RuntimeError(result.get('error', 'Launch failed'))
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--candidate', choices=('1024', '1536', '256'), required=True)
    ap.add_argument('--draft-profile', choices=('balanced', 'code-edit'), default='balanced')
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--run', action='store_true'); args = ap.parse_args()
    print(f'Plan: 512/{args.candidate}/{args.candidate}/512; {args.draft_profile}, kept engine, 4K/F16/MTP3, '
          'two long English inputs, short edit/prose, three normal-EOS responses each.', flush=True)
    if not args.run: return
    assert_no_model_server(); require_pass()
    args.output.mkdir(parents=True, exist_ok=False)
    frozen = dict(closure=closure(), models=verify_models(['flash', 'mtp_shared_packed_q3']))
    result = dict(schema=1, status='running', candidate=args.candidate, draft_profile=args.draft_profile,
                  order=ORDER, arms=[], frozen=frozen,
                  prompt_cache=False, normal_eos=True, output_cap=MAX_OUTPUT, default_changed=False,
                  cache_state='unknown; no purge, forced eviction, preload or intervention inside bracket')
    for relative in frozen['closure']['sources']:
        dest = args.output / 'source' / relative
        dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes((ROOT / relative).read_bytes())
    write(args.output / 'campaign.json', result)
    try:
        with (ROOT / 'bench/.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for i, role in enumerate(ORDER):
                profile = '512' if role == 'control' else args.candidate
                result['arms'].append(launch(args.output / f'arm-{i+1}-{role}', role, profile, frozen, args.draft_profile))
                write(args.output / 'campaign.json', result)
            result['comparison'] = compare(result['arms'], args.draft_profile)
            result['status'] = 'passed'
    except BaseException as error:
        result.update(status='failed', error=f'{type(error).__name__}: {error}'); raise
    finally:
        result['launches'] = [json.loads(p.read_text()) for p in sorted(args.output.glob('arm-*/result.json'))]
        write(args.output / 'campaign.json', result)
    print('Trial passed:', args.output, flush=True)


if __name__ == '__main__': main()
