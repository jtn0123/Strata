#!/usr/bin/env python3
"""Isolated, guarded same-model comparison with the parent's native Mac engine."""
import argparse
import ast
import fcntl
import hashlib
import json
import os
from pathlib import Path
import queue
import socket
import statistics
import subprocess
import sys
import threading
import time

import psutil
from benchmark import stream_completion, wait_ready
from benchmark_editing import clean_memory, fixtures, power, prompt as edit_prompt, trial_command
from benchmark_m5_next import wait_for_headroom
from benchmark_m5_small_gains import launch_row
from benchmark_signals import cleanup_on_termination, defer_termination
from capture_lookup_long import workloads as long_workloads
from engines import sha256, verify_engine
from lab import ROOT, model_path, request, server_command
from metal_environment import configure
from model_provenance import assert_unchanged, identity, verify_models
from profile_m5_routes import preflight
from runtime_memory import admit_model, app_monitor
from validate_offline import fingerprint, require_pass

PARENT = ROOT / 'vendor/strata-parent-metal-20261013'
PRIVATE = ROOT / 'bench/private/parent-metal-20261013'
REVISION = 'ed4773eb7c8f1f1531ba2bc70e0e1987de2661af'
MAX_OUTPUT = 1536
REPEATS = 2
ORDER = ('current', 'parent', 'parent', 'current')


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def no_engines():
    names = ('strata', 'llama-server')
    active = [p.pid for p in psutil.process_iter(['name'])
              if any((p.info['name'] or '').startswith(n) for n in names)]
    if active:
        raise RuntimeError(f'Another inference engine is running: {active}')


def release_owned_expert_cache():
    """Startup-only cleanup for the private generated copy, never an active benchmark."""
    no_engines()
    proof = json.loads((PRIVATE / 'prepare-expert-copy.json').read_text())
    if proof['status'] != 'passed': raise RuntimeError('Verified private expert copy required')
    source = json.loads((PRIVATE / 'prepare-pack.json').read_text())['model_proof']
    assert_unchanged(source)
    path = PRIVATE / 'models' / (Path(source['models']['flash']['files'][0]['path']).name + '.experts')
    before = identity(path)
    with path.open('rb') as file:
        if file.read(4) != b'STRX': raise ValueError('Unexpected private expert-copy format')
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_longlong]
    libc.mmap.restype = ctypes.c_void_p
    libc.msync.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
    libc.msync.restype = ctypes.c_int
    libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    libc.munmap.restype = ctypes.c_int
    from benchmark import Monitor
    baseline = Monitor.baseline()
    fd = os.open(path, os.O_RDONLY)
    base = None
    try:
        base = libc.mmap(None, before['size'], 1, 1, fd, 0)  # PROT_READ, MAP_SHARED: no payload allocation/write
        if base == ctypes.c_void_p(-1).value: raise OSError(ctypes.get_errno(), 'read-only mmap')
        if libc.msync(base, before['size'], 0x10 | 0x2):  # MS_SYNC | MS_INVALIDATE
            raise OSError(ctypes.get_errno(), 'owned clean-cache invalidate')
    finally:
        if base is not None and base != ctypes.c_void_p(-1).value: libc.munmap(base, before['size'])
        os.close(fd)
    if identity(path) != before: raise RuntimeError('Private expert file changed')
    assert_unchanged(source)
    after = Monitor.baseline()
    if after['swap_used_bytes'] > baseline['swap_used_bytes'] or Monitor.read_pressure_level() != 1:
        raise RuntimeError('Cache cleanup did not retain normal pressure/zero new swap')
    record = dict(before=baseline, after=after, file_identity_unchanged=True,
                  scope='Only the private generated expert file; no model payload read or anonymous allocation. Cache state unknown.')
    write(PRIVATE / 'last-owned-cache-release.json', record)
    return record


def parent_pin():
    revision = subprocess.check_output(['git', '-C', str(PARENT), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != REVISION or subprocess.check_output(['git', '-C', str(PARENT), 'diff', 'HEAD']):
        raise RuntimeError('Parent checkout is not the pinned unchanged source')
    paths = [PARENT / 'build-metal/strata', PARENT / 'third_party/ggml/ggml-common.h',
             PARENT / 'data/expert-profile.bin']
    paths += sorted((PARENT / 'metal').rglob('*.metal'))
    # All dynamic shader inputs, native executable and original-source identity.
    return dict(revision=revision, files={str(p.relative_to(PARENT)): sha256(p) for p in paths},
                build=json.loads((PARENT / 'build-metal/trial-build.json').read_text()))


def prepare_cases():
    sys.path.insert(0, str(PARENT))
    sys.path.insert(0, str(PARENT / 'tools'))
    from strata_tokenizer import Tokenizer
    from serve.frontend import ChatTemplate
    tokenizer = Tokenizer.from_gguf(model_path('flash'))
    template = ChatTemplate(PRIVATE / 'pack/tokenizer/chat_template.jinja')
    cases = [dict(name='prose', kind='prose', content=(
        'In about 180 words, explain why local AI benchmark results vary. '
        'Cover model size, input length, draft tokens, warmup, and memory. Use clear English.')),
        dict(name='code', kind='code', content=(
        'Return only Python code, without Markdown. Write a function compare_reports(before, after) '
        'that reads positive finite generation_tps and reply_seconds from two dictionaries, rejects '
        'missing or invalid values with ValueError, and returns a dictionary with tps_gain_percent '
        'and reply_faster_percent. Include the required standard-library import. Keep it concise.'))]
    for f in fixtures():
        if f['cohort'] == 'screen':
            cases.append(dict(name=f['name'], kind='editing', content=edit_prompt(f),
                              expected=f['source'].replace(f['old'], f['new'])))
    notes = long_workloads()[0]['content'].split('\n\n', 1)[1]
    cases.append(dict(name='long-retrieval', kind='retrieval', content=(
        'Read the fictional notes below. Return only a JSON object for Record 27, with keys owner, '
        'timeout_seconds and retry_limit. Do not explain.\n\n' + notes),
        expected_json=dict(owner='Grove', timeout_seconds=38, retry_limit=2)))
    for case in cases:
        rendered = template.render([dict(role='user', content=case['content'])], enable_thinking=False)
        tokens = tokenizer.encode(rendered, parse_special=True)
        if len(tokens) + MAX_OUTPUT > 4096:
            raise ValueError('Frozen request exceeds 4K context')
        case.update(rendered=rendered, tokens=tokens, prompt_tokens=len(tokens),
                    prompt_sha256=hashlib.sha256(json.dumps(tokens).encode()).hexdigest())
    return cases, tokenizer


def parse_done(line, emitted, prompt_tokens):
    f = line.split()
    if len(f) < 16 or f[0] != 'DONE':
        raise ValueError('Complete native DONE counters required')
    generated, count = int(f[1]), int(f[2])
    prompt_ms, decode_ms = float(f[3]), float(f[4])
    accepted, proposed, reused, read = int(f[6]), int(f[7]), int(f[8]), int(f[14])
    if (f[5] != 'stop' or generated != len(emitted) or not 0 < generated < MAX_OUTPUT
            or count != prompt_tokens or reused != 0 or read != prompt_tokens
            or not 0 <= accepted <= proposed or min(prompt_ms, decode_ms) <= 0
            or not all(__import__('math').isfinite(n) for n in (prompt_ms, decode_ms))):
        raise ValueError('Normal stop, complete fresh input/output and valid native timings required')
    return dict(generation_tok_s=1000 * generated / decode_ms,
                prompt_tok_s=1000 * read / prompt_ms, output_tokens=generated,
                native=dict(generated=generated, prompt_tokens=count, prompt_ms=prompt_ms,
                            decode_ms=decode_ms, accepted=accepted, proposed=proposed, reused=reused,
                            ram_blobs=int(f[11]), file_blobs=int(f[12]), file_mb=float(f[13])))


def quality(case, text):
    stripped = text.strip()
    if case['kind'] == 'editing':
        return dict(passed=stripped == case['expected'].strip(), scope='complete verbatim file')
    if case['kind'] == 'retrieval':
        try:
            result = json.loads(stripped)
        except ValueError:
            result = None
        return dict(passed=result == case['expected_json'], scope='exact long-document facts')
    if case['kind'] == 'code':
        try:
            tree = ast.parse(stripped)
            valid = any(isinstance(n, ast.FunctionDef) and n.name == 'compare_reports' for n in tree.body)
        except SyntaxError:
            valid = False
        return dict(passed=valid, scope='syntax and required function only; not functional equivalence')
    return dict(passed=bool(stripped) and '<think>' not in stripped,
                scope='nonempty English request output; no independent prose quality grading')


class Lines:
    def __init__(self, child, path):
        self.child, self.queue = child, queue.Queue()
        def pump():
            try:
                with path.open('w') as log:
                    for line in child.stdout:
                        now = time.monotonic()
                        log.write(json.dumps(dict(time=now, line=line.strip())) + '\n')
                        log.flush()
                        self.queue.put((now, line.strip()))
            except BaseException as error:
                self.queue.put((time.monotonic(), error))
            finally:
                self.queue.put((time.monotonic(), None))
        self.thread = threading.Thread(target=pump, daemon=True)
        self.thread.start()

    def until(self, prefix, timeout=600):
        deadline = time.monotonic() + timeout
        rows = []
        while time.monotonic() < deadline:
            try:
                stamp, line = self.queue.get(timeout=min(1, max(0.001, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if isinstance(line, BaseException):
                raise RuntimeError(f'Native protocol reader failed: {line}') from line
            if line is None or line.startswith(('ERR', 'FATAL')):
                raise RuntimeError(f'Native engine stopped or refused request: {line}')
            rows.append((stamp, line))
            if line.startswith(prefix):
                return rows
        raise TimeoutError(f'Native protocol did not reach {prefix}')

    def complete(self, case):
        begin = time.monotonic()
        self.child.stdin.write(f"GEN {MAX_OUTPUT} temperature=0 seed=1234 {','.join(map(str, case['tokens']))}\n")
        self.child.stdin.flush()
        rows = self.until('DONE ')
        output = [(stamp, int(line[2:])) for stamp, line in rows if line.startswith('T ')]
        ids = [t for _, t in output]
        result = parse_done(rows[-1][1], ids, len(case['tokens']))
        result.update(generated_token_ids=ids, ttft_s=output[0][0] - begin,
                      wall_s=rows[-1][0] - begin, transport='native line protocol')
        return result


def frozen_state():
    return dict(sources=fingerprint(), current_engine=verify_engine('m5-small-stack'), parent=parent_pin(),
                preparation={p.name: sha256(p) for p in PRIVATE.glob('prepare-*.json')},
                pack=verified_pack(),
                experts=identity(next((PRIVATE / 'models').glob('*.experts'))))


def verified_pack(folder=None, receipt=None):
    """Same identity-bound hash policy as model provenance; avoid repeated dense-pack scans."""
    folder = folder or PRIVATE / 'pack'
    receipt = receipt or PRIVATE / 'pack-verification.json'
    cached = json.loads(receipt.read_text()) if receipt.exists() else {}
    hashes = {}
    updated = {}
    for path in sorted(folder.glob('*')):
        if not path.is_file(): continue
        before = identity(path)
        old = cached.get(path.name)
        digest = old['sha256'] if old and old['identity'] == before else sha256(path)
        if identity(path) != before: raise RuntimeError('Pack changed during hash verification')
        hashes[path.name] = digest
        updated[path.name] = dict(identity=before, sha256=digest)
    write(receipt, updated)
    return hashes


def launch(folder, role, cases, tokenizer, frozen, hc, editing=False, smoke=False, arena_gb=None):
    folder.mkdir()
    result = dict(status='running', role=role, hc=hc if role == 'parent' else 'original-model',
                  arena_gb=arena_gb if role == 'parent' else None, editing_profile=editing, cases=[], models_loaded=False)
    child = monitor = lines = None
    try:
        no_engines(); require_pass()
        if frozen_state() != frozen['state']:
            raise RuntimeError('Source, binaries, pack or expert-copy identity changed')
        assert_unchanged(frozen['models'])
        result['settle'] = wait_for_headroom()
        result['preflight'] = preflight(False)
        result['power'] = power()
        env, flags = configure(os.environ, 'm5-small-stack', 'on', 'small-reduce')
        env = {k: v for k, v in env.items() if not k.startswith('STRATA_')}
        if role == 'parent':
            env = {k: v for k, v in env.items() if not k.startswith(('GGML_', 'METAL_CAPTURE_'))}
            env.update(STRATA_METAL_STREAM='1', STRATA_HC_Q8='1' if hc == 'q8' else '0')
            if arena_gb is not None:
                env['STRATA_METAL_ARENA_GB'] = str(arena_gb)
            shards = sorted((PRIVATE / 'models').glob('*.gguf'))
            command = [str(PARENT / 'build-metal/strata'), '--serve', '--pack', str(PRIVATE / 'pack'),
                '--native', str(shards[0]), '--ple-gguf', str(shards[1]), '--expert-profile',
                str(PARENT / 'data/expert-profile.bin'), '--expert-cache', '64', '--prefill', 'auto',
                '--spec', '2', '--suffix-draft', '0', '--max-context', '4096', '--mmap-experts', '--prompt-cache', '0']
            result['settings'] = dict(streaming=True, mtp=False, hc=hc, arena_gb=arena_gb, prompt_cache=False)
        else:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
            command = server_command('flash', port, 4096, 512, 512, 'draft-mtp', 3,
                draft_placement='mixed', draft_model='mtp_shared_packed_q3', engine='m5-small-stack',
                draft_threads=8, draft_p_min=0.0)
            command = trial_command(command, 'code-edit' if editing else 'balanced')
            result['settings'] = dict(metal=flags, mtp=True, draft_depth=3, prompt_cache=False)
        result['command'] = command
        policy = admit_model('flash'); result['memory_policy'] = policy
        write(folder / 'result.json', result)
        with (folder / 'native.log').open('w') as log:
            start = time.monotonic()
            with defer_termination():
                child = subprocess.Popen(command, env=env, stdout=subprocess.PIPE if role == 'parent' else log,
                    stdin=subprocess.PIPE if role == 'parent' else None, stderr=log,
                    text=role == 'parent', bufsize=1)
                result['models_loaded'] = True
                monitor = app_monitor(child, folder / 'memory.jsonl', policy); monitor.thread.start()
                if role == 'parent':
                    lines = Lines(child, folder / 'protocol.jsonl')
            if role == 'parent':
                lines.until('READY ')
            else:
                base = f'http://127.0.0.1:{port}'; wait_ready(child, base)
            result['load_ready_s'] = time.monotonic() - start
            for case in cases:
                if role == 'current':
                    check = request(base, '/tokenize', dict(content=case['rendered'], add_special=False, parse_special=True))['tokens']
                    if check != case['tokens']:
                        raise RuntimeError('Tokenizer IDs differ across engines; timing comparison is invalid')
                for repeat in range(1 if smoke else REPEATS):
                    if role == 'parent':
                        row = lines.complete(case)
                        text = tokenizer.decode([t for t in row['generated_token_ids'] if t not in (248044, 248046)])
                    else:
                        response = stream_completion(base, dict(prompt=case['tokens'], n_predict=MAX_OUTPUT,
                            temperature=0, seed=1234, cache_prompt=False, ignore_eos=False, return_tokens=True, stream=True))
                        final = response['final']; timings = final['timings']
                        if not final.get('stop') or final.get('stop_type') != 'eos':
                            raise ValueError('Normal-EOS completion required')
                        row = dict(generation_tok_s=timings['predicted_per_second'], prompt_tok_s=timings['prompt_per_second'],
                                   ttft_s=response['ttft_s'], wall_s=response['wall_s'], output_tokens=timings['predicted_n'],
                                   generated_token_ids=response['generated_token_ids'], native=timings, transport='native HTTP SSE')
                        text = response['text']
                    row.update(name=case['name'], kind=case['kind'], repeat=repeat, prompt_tokens=case['prompt_tokens'],
                               prompt_sha256=case['prompt_sha256'], text=text, quality=quality(case, text))
                    result['cases'].append(row); write(folder / 'result.json', result)
                    print(f"{role}/{result['hc']}: {case['name']} repeat{repeat}: {row['generation_tok_s']:.2f} TPS, "
                          f"first {row['ttft_s']:.3f}s, full {row['wall_s']:.3f}s, check={row['quality']['passed']}", flush=True)
        result['status'] = 'completed'
    except BaseException as error:
        result.update(status='failed', error=f'{type(error).__name__}: {error}')
    finally:
        if child and child.poll() is None:
            child.terminate()
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=5)
        if monitor: result['memory'] = monitor.finish()
        if lines: lines.thread.join(timeout=2)
        try:
            no_engines(); assert_unchanged(frozen['models']); require_pass()
            if frozen_state() != frozen['state']: raise RuntimeError('Frozen source/artifact changed')
            if result['status'] == 'completed':
                if not clean_memory(result['memory']): raise RuntimeError('RAM, swap, monitor or cleanup gate failed')
                result['status'] = 'passed'
        except BaseException as error:
            result.update(status='failed', error=f'{type(error).__name__}: {error}')
        write(folder / 'result.json', result)
    if result['status'] != 'passed': raise RuntimeError(result.get('error', 'Launch failed'))
    return result


def compare(arms, cases):
    if len(arms) != 4 or [a['role'] for a in arms] != list(ORDER) or any(a['status'] != 'passed' for a in arms):
        raise ValueError('Four complete current/parent/parent/current launches required')
    rows = []
    for case in cases:
        groups = [[r for r in a['cases'] if r['name'] == case['name']] for a in arms]
        if any(len(g) != REPEATS or {r['repeat'] for r in g} != set(range(REPEATS)) for g in groups):
            raise ValueError('Full request inventory required')
        if any(r['prompt_sha256'] != case['prompt_sha256'] for g in groups for r in g):
            raise ValueError('Prompt identity changed')
        medians = [{k: statistics.median(r[k] for r in g) for k in
                   ('generation_tok_s', 'prompt_tok_s', 'ttft_s', 'wall_s')} for g in groups]
        row = launch_row(medians)
        row.update(name=case['name'], kind=case['kind'], all_quality_checks_pass=all(r['quality']['passed'] for g in groups for r in g),
                   exact_output_parity=len({tuple(r['generated_token_ids']) for g in groups for r in g}) == 1,
                   output_tokens_by_launch=[statistics.median(r['output_tokens'] for r in g) for g in groups],
                   limitation='Different backend/settings; output lengths can differ. Native timing definitions and transports differ. '
                              'Quality scopes are explicit; this is an engine trial, not an exact optimization keeper.')
        rows.append(row)
    return dict(rows=rows, keeper_enabled=False, whole_model_outputs_may_differ=True)


@cleanup_on_termination()
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--mode', choices=['parent-smoke', 'current-smoke', 'comparison', 'editing'], default='parent-smoke')
    ap.add_argument('--hc', choices=['q8', 'bf16'], default='q8')
    ap.add_argument('--arena-gb', type=float, help='Reduced parent-only expert cache; decimal GB, at most20 for this48GiB trial')
    ap.add_argument('--run', action='store_true'); args = ap.parse_args()
    if args.arena_gb is not None and not 1 <= args.arena_gb <= 20:
        ap.error('Explicit trial arena must be within1–20 decimal GB; no raised memory cap')
    if not args.run:
        print('Prepared isolated parent/current trial; native Q2, 4K, complete English outputs, normal pressure/zero new swap. No model loaded.'); return
    no_engines(); require_pass()
    args.output.mkdir(parents=True, exist_ok=False)
    cases, tokenizer = prepare_cases()
    if args.mode == 'editing': cases = [c for c in cases if c['kind'] == 'editing']
    frozen = dict(state=frozen_state(), models=verify_models(['flash', 'mtp_shared_packed_q3']))
    record = dict(status='running', mode=args.mode, hc=args.hc, arena_gb=args.arena_gb, frozen=frozen, cases=cases, arms=[],
                  cache_state='OS cache unknown; fresh process, no prompt cache; replay shares expert/file/kernel caches',
                  new_engine_adopted=False)
    write(args.output / 'campaign.json', record)
    try:
        with (ROOT / 'bench/.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            order = ORDER if args.mode == 'comparison' else ('current',) if args.mode in ('current-smoke', 'editing') else ('parent',)
            for i, role in enumerate(order):
                record['arms'].append(launch(args.output / f'arm-{i+1}-{role}', role, cases, tokenizer, frozen, args.hc,
                    editing=args.mode == 'editing', smoke=args.mode.endswith('smoke'), arena_gb=args.arena_gb))
                write(args.output / 'campaign.json', record)
            if args.mode == 'comparison': record['comparison'] = compare(record['arms'], cases)
            record['status'] = 'passed'
    except BaseException as error:
        record.update(status='failed', error=f'{type(error).__name__}: {error}'); raise
    finally: write(args.output / 'campaign.json', record)
    print('Trial', record['status'], args.output, flush=True)


if __name__ == '__main__': main()
