#!/usr/bin/env python3
"""Qualify complete English file edits, then compare isolated drafting policies."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re
import socket
import subprocess
import time

from benchmark import Monitor, stream_completion, wait_ready
from benchmark_metrics import case_metrics, completion_counts, metrics
from benchmark_signals import cleanup_on_termination, defer_termination
from benchmark_m5_small_gains import feature_receipts, launch_row
from benchmark_m5_next import wait_for_headroom
from check_memory import assert_no_model_server
from engines import sha256, verify_engine
from lab import ROOT, request, server_command
from metal_environment import configure
from model_provenance import assert_unchanged, verify_models
from profile_m5_routes import preflight
from runtime_memory import admit_model, app_monitor
from validate_offline import fingerprint, require_pass

FIXTURES = ROOT / 'tests/fixtures/editing-workloads.json'
ENGINE = 'm5-small-stack'
ORDER = ('control', 'candidate', 'candidate', 'control')
EXPERIMENTS = {'editing': ('balanced', 'code-edit'),
               'prompt-local': ('code-edit', 'prompt-local'),
               'prompt-map': ('code-edit', 'prompt-map')}
LANGUAGES = {'python', 'javascript', 'json'}
REPEATS = 3
MAX_OUTPUT = 1536


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def fixtures(path=FIXTURES):
    spec = json.loads(path.read_text())
    cases = spec['cases']
    if spec.get('schema') != 1 or len(cases) != 6 or len({c['name'] for c in cases}) != 6:
        raise ValueError('Six unique, bounded synthetic files required')
    for cohort in ('screen', 'confirm'):
        selected = [c for c in cases if c['cohort'] == cohort]
        if len(selected) != 3 or {c['language'] for c in selected} != LANGUAGES:
            raise ValueError('Each cohort requires separate Python, JavaScript and JSON files')
    for case in cases:
        if (not all(isinstance(case[k], str) and case[k] for k in ('source', 'old', 'new'))
                or not 100 <= len(case['source']) <= 8192
                or case['source'].count(case['old']) != 1
                or case['old'] == case['new']):
            raise ValueError('Every file needs precisely one explicit replacement')
    return cases


def prompt(case):
    return (f"Make exactly one change to this {case['language']} file: replace "
            f"{case['old']!r} with {case['new']!r}. Return the entire updated file "
            'verbatim, including all unchanged code, spacing and blank lines. '
            'Do not add Markdown fences, explanations or any other changes.\n\n' + case['source'])


def trial_command(command, profile):
    if profile not in {'balanced', 'code-edit', 'prompt-local', 'prompt-map'}:
        raise ValueError('Unknown drafting trial')
    if profile == 'prompt-local':
        raise ValueError('E02: native ngram-simple cannot draft width3 with match12; use the qualified prompt-map mechanism')
    command = list(command)
    if command[command.index('--spec-type') + 1] != 'draft-mtp' or command[command.index('--spec-draft-n-max') + 1] != '3':
        raise ValueError('Preserve the qualified MTP configuration and maximum width three')
    if profile == 'balanced':
        return command
    command[command.index('--spec-type') + 1] = ('ngram-mod,draft-mtp' if profile == 'code-edit'
                                                else 'ngram-map-k,ngram-mod,draft-mtp')
    command += ['--spec-ngram-mod-n-match', '16', '--spec-ngram-mod-n-min', '1', '--spec-ngram-mod-n-max', '3']
    if profile == 'prompt-map':
        # size-m participates in native allocation sizing; never use the default 48.
        command += ['--spec-ngram-map-k-size-n', '12', '--spec-ngram-map-k-size-m', '3',
                    '--spec-ngram-map-k-min-hits', '1']
    return command


def validate_response(response, case=None):
    final = response['final']
    if not final.get('stop') or final.get('stop_type') != 'eos':
        raise ValueError('Complete normal-EOS response required; capped output is ineligible')
    ids = response['generated_token_ids']
    if not ids or any(type(t) is not int or t < 0 for t in ids):
        raise ValueError('Actual output token IDs required')
    if case is not None:
        expected = case['source'].replace(case['old'], case['new'])
        if response['text'].strip() != expected.strip():
            raise ValueError(f"Complete verbatim edit failed: {case['name']}")
    timings = final['timings']
    completion_counts(timings, ids, max_new=MAX_OUTPUT)
    result = dict(ttft_s=response['ttft_s'], wall_s=response['wall_s'],
                  generation_tok_s=timings['predicted_per_second'], prompt_tok_s=timings['prompt_per_second'],
                  output_tokens=timings['predicted_n'], response=response)
    case_metrics(result)
    return result


def signature(case):
    response = case['response']
    return dict(text=hashlib.sha256(response['text'].encode()).hexdigest(),
                tokens=hashlib.sha256(json.dumps(response['generated_token_ids']).encode()).hexdigest(),
                prompt=case['prompt_sha256'], output_tokens=case['output_tokens'])


def closure():
    return dict(sources=fingerprint(), fixture_sha256=sha256(FIXTURES), engine=verify_engine(ENGINE),
                native_probe_sha256=sha256(ROOT / 'native/ngram_short_probe.cpp'))


def matcher_proof():
    folder = ROOT / 'bench/features/20261013-ngram-short-mechanism'
    proof = json.loads((folder / 'proof.json').read_text())
    obj = ROOT / 'vendor/llama-m5-small-stack/build/common/CMakeFiles/llama-common.dir/ngram-map.cpp.o'
    if (proof['status'] != 'passed' or proof['cases'] != 18 or proof['models_loaded'] is not False
            or proof['gpu_tests'] is not False or proof['map_maximum_width'] != 3
            or proof['engine'] != verify_engine(ENGINE)
            or proof['source_sha256'] != sha256(ROOT / 'native/ngram_short_probe.cpp')
            or proof['native_object_sha256'] != sha256(obj)
            or proof['binary_sha256'] != sha256(folder / 'probe')):
        raise RuntimeError('A current, bounded native CPU matcher proof is required')
    return sha256(folder / 'proof.json')


def assert_frozen(frozen):
    require_pass()
    if closure() != frozen['closure']:
        raise RuntimeError('Experiment source, fixtures or engine changed; start a new campaign')
    assert_unchanged(frozen['models'])
    if frozen.get('matcher_proof_sha256') and matcher_proof() != frozen['matcher_proof_sha256']:
        raise RuntimeError('Native CPU matcher proof changed')


def clean_memory(memory):
    return (memory.get('monitor_healthy') is True and memory.get('child_exited') is True
            and memory.get('normal_pressure_required') is True
            and memory.get('normal_pressure_observed') is True
            and memory.get('pressure_live_samples', 0) > 0 and not memory.get('guard')
            and memory.get('swap_growth_bytes') == 0)


def drafting_receipts(text, profile):
    """Normal trace verbosity emits cumulative statistics, not per-draft debug lines."""
    receipts = {}
    for kind in ('ngram-mod', 'ngram-simple', 'ngram-map-k'):
        enabled = (kind == 'ngram-mod' and profile != 'balanced'
                   or kind == 'ngram-simple' and profile == 'prompt-local'
                   or kind == 'ngram-map-k' and profile == 'prompt-map')
        if (f"adding speculative implementation '{kind}'" in text) != enabled:
            raise ValueError(f'Unexpected or missing {kind} initialization')
        pattern = (rf'statistics\s+{re.escape(kind)}:.*?#gen drafts\s*=\s*(\d+),'
                   r'.*?#acc drafts\s*=\s*(\d+),.*?#gen tokens\s*=\s*(\d+),'
                   r'.*?#acc tokens\s*=\s*(\d+)')
        counters = [tuple(map(int, values)) for values in re.findall(pattern, text)]
        if not enabled:
            if counters: raise ValueError(f'Unexpected {kind} statistics')
            continue
        required_active = kind != 'ngram-mod' or profile == 'code-edit'
        if not counters or required_active and not any(g > 0 and a > 0 and t > 0 and at > 0 for g, a, t, at in counters):
            raise ValueError(f'{kind} produced no accepted drafts')
        if any(a > g or at > t or t > 3*g for g, a, t, at in counters):
            raise ValueError(f'Invalid or unbounded {kind} draft counters')
        g, a, t, at = counters[-1]
        receipts[kind] = dict(generated_drafts=g, accepted_drafts=a, proposed_tokens=t, accepted_tokens=at)
    return receipts


def compare(arms):
    if (len(arms) != 4 or any(a['status'] != 'passed' or not clean_memory(a['memory']) for a in arms)
            or [a['role'] for a in arms] != list(ORDER)):
        raise ValueError('Four complete, guarded A/B/B/A launches required')
    cohort = arms[0]['cohort']
    if cohort not in ('screen', 'confirm') or any(a['cohort'] != cohort for a in arms):
        raise ValueError('A bracket cannot mix fixture cohorts')
    names = {c['name'] for c in fixtures() if c['cohort'] == cohort} | {'prose-control'}
    expected = {(name, repeat) for name in names for repeat in range(REPEATS + 1)}
    if any(len(a['cases']) != len(expected) or {(c['name'], c['repeat']) for c in a['cases']} != expected for a in arms):
        raise ValueError('The full frozen file/repetition inventory is required')
    reference = {(c['name'], c['repeat']): signature(c) for c in arms[0]['cases']}
    if any({(c['name'], c['repeat']): signature(c) for c in a['cases']} != reference for a in arms[1:]):
        raise ValueError('Complete text, token IDs or prompt identity changed across policies')
    rss = [a['memory']['peak_rss_bytes'] for a in arms]
    extra = (rss[1] + rss[2] - rss[0] - rss[3]) / 2
    memory_clean = extra <= max(128 * 1024**2, 2 * abs(rss[3] - rss[0]))
    rows = []
    for name in sorted({c['name'] for c in arms[0]['cases']}):
        for cohort in ('first-exposure', 'warmed'):
            groups = [[c for c in a['cases'] if c['name'] == name
                       and (c['repeat'] == 0 if cohort == 'first-exposure' else c['repeat'] > 0)] for a in arms]
            if any(len(g) != (1 if cohort == 'first-exposure' else REPEATS) for g in groups):
                raise ValueError('Missing/duplicate first exposure or warmed repetition')
            row = launch_row([metrics(g) for g in groups])
            row.update(name=name, language=groups[0][0]['language'], cohort=cohort)
            values = row['launch_medians']
            row['worst_ttft_cost_ms'] = 1000 * max(values[b]['ttft_s'] - values[a]['ttft_s']
                                                 for b in (1, 2) for a in (0, 3))
            # Editing can trade <=100 ms first-token delay for a faster complete reply.
            safe = memory_clean and row['worst_ttft_cost_ms'] <= 100 and not any(
                x in row['regressions'] for x in ('generation_increase_percent', 'total_time_reduction_percent'))
            q = row['qualifying_metrics']
            row['qualified_scopes'] = (['reply'] + (['generation'] if q['generation_increase_percent'] else [])) if safe and q['total_time_reduction_percent'] else []
            rows.append(row)
    eligible = sorted({r['language'] for r in rows if r['language'] in LANGUAGES
                       and r['cohort'] == 'first-exposure' and r['qualified_scopes']})
    return dict(rows=rows, eligible_languages=eligible, memory_clean=memory_clean,
                candidate_extra_rss_bytes=extra, exact_output_parity=True)


def power():
    battery = subprocess.check_output(['pmset', '-g', 'batt'], text=True)
    ac = subprocess.check_output(['pmset', '-g', 'custom'], text=True).split('AC Power:', 1)[1]
    mode = int(next(line.split()[1] for line in ac.splitlines() if line.strip().startswith('powermode ')))
    if 'AC Power' not in battery or mode != 0:
        raise RuntimeError('This campaign requires AC power and unchanged Automatic mode')
    return dict(on_ac=True, mode=mode)


def lifecycle(base):
    import urllib.request
    payload = dict(prompt='Write a detailed guide to fair benchmarks.', n_predict=1536, stream=True,
                   cache_prompt=False, temperature=0, seed=1234, ignore_eos=True)
    req = urllib.request.Request(base + '/completion', data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as response:
        for line in response:
            if line.startswith(b'data: ') and json.loads(line[6:]).get('content'):
                break
        else:
            raise RuntimeError('No first text before disconnect')
    response = request(base, '/v1/chat/completions', dict(model='flash', messages=[dict(role='user', content=
        'What is 17 multiplied by 23? Reply with only the number.')], temperature=0, seed=1234,
        max_tokens=32, chat_template_kwargs=dict(enable_thinking=False)), timeout=60)
    if response['choices'][0]['message']['content'].strip() != '391' or response['choices'][0]['finish_reason'] != 'stop':
        raise RuntimeError('Disconnect/reuse answer failed')
    return dict(disconnect_after_first_text=True, reuse_answer='391', passed=True)


def arm(folder, profile, role, cohort, frozen):
    folder.mkdir()
    record = dict(status='attempting', profile=profile, role=role, cohort=cohort, cases=[])
    path = folder / 'result.json'
    write(path, record)
    process = monitor = None
    try:
        assert_frozen(frozen)
        assert_no_model_server()
        record['power_before'] = power()
        record['headroom_settle'] = wait_for_headroom()
        record['preflight'] = preflight()
        policy = admit_model('flash')
        record['memory_policy'] = policy
        env, metal = configure(__import__('os').environ, ENGINE, 'on', 'small-reduce')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        command = trial_command(server_command('flash', port, 4096, 512, 512, 'draft-mtp', 3, 'f16', 8,
            'mixed', 'mtp_shared_packed_q3', engine=ENGINE, draft_threads=8, draft_p_min=0.0), profile)
        record.update(command=command, metal_environment=metal)
        write(path, record)
        with (folder / 'server.log').open('w') as log:
            with defer_termination():
                process = subprocess.Popen(command, stdout=log, stderr=log, env=env)
                monitor = app_monitor(process, folder / 'memory.jsonl', policy)
                monitor.thread.start()
            record['ready_s'] = wait_ready(process, base, timeout=180)
            tasks = [dict(c, content=prompt(c)) for c in fixtures() if c['cohort'] == cohort]
            tasks.append(dict(name='prose-control', language='prose', content=
                'Explain a fair computer speed comparison in exactly four short sentences. Mention warmup, repeated trials, background activity and memory. No headings.'))
            for task in tasks:
                rendered = request(base, '/apply-template', dict(messages=[dict(role='user', content=task['content'])],
                    chat_template_kwargs=dict(enable_thinking=False)))['prompt']
                ids = request(base, '/tokenize', dict(content=rendered, add_special=False, parse_special=True))['tokens']
                if len(ids) + MAX_OUTPUT + 8 > 4096:
                    raise ValueError('Complete edit budget does not fit the maintained context')
                prompt_sha = hashlib.sha256(json.dumps(ids).encode()).hexdigest()
                for repeat in range(REPEATS + 1):
                    response = stream_completion(base, dict(prompt=ids, n_predict=MAX_OUTPUT, stream=True,
                        cache_prompt=False, temperature=0.6, seed=1234, return_tokens=True))
                    result = validate_response(response, task if task['language'] in LANGUAGES else None)
                    result.update(name=task['name'], language=task['language'], repeat=repeat,
                                  prompt_sha256=prompt_sha, input_tokens=len(ids))
                    record['cases'].append(result); write(path, record)
                    print(f"{profile} {task['name']} {'first' if repeat == 0 else 'warm'+str(repeat)}: "
                          f"{result['generation_tok_s']:.2f} TPS, full reply {result['wall_s']:.3f}s", flush=True)
                    if response['final']['timings']['prompt_n'] != len(ids) or response['final']['timings'].get('cache_n', 0):
                        raise ValueError('Fresh prompt unexpectedly reused native prefix state')
            record['lifecycle'] = lifecycle(base)
        record['power_after'] = power()
        assert_frozen(frozen)
        record['status'] = 'passed'
    except BaseException as error:
        record.update(status='failed', error=f'{type(error).__name__}: {error}')
        print(f'{profile}: {record["error"]}', flush=True)
    finally:
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=3)
        if monitor:
            record['memory'] = monitor.finish()
            if not clean_memory(record['memory']):
                record.update(status='failed', resource_failure=True)
        if process:
            record['exit_code'] = process.returncode
            text = (folder / 'server.log').read_text()
            try:
                record['activation'] = feature_receipts(text, ['reduce'])
                if 'borrowing target embeddings/output; draft KV remains separate' not in text:
                    raise ValueError('Shared helper activation missing')
                record['drafting_receipts'] = drafting_receipts(text, profile)
            except ValueError as error:
                record.update(status='failed', activation_error=str(error))
        assert_no_model_server()
        write(path, record)
    return record


def bracket(folder, profiles, cohort, frozen):
    folder.mkdir()
    arms = []
    for index, role in enumerate(ORDER):
        if index:
            time.sleep(15)
        record = arm(folder / f'arm-{index+1}', profiles[0 if role == 'control' else 1], role, cohort, frozen)
        arms.append(record)
        if record['status'] != 'passed':
            result = dict(status='failed', failed_arm=index+1, eligible_languages=[],
                          error=record.get('error') or record.get('activation_error') or 'Resource gate failed',
                          partial_results_not_scored=True)
            write(folder / 'comparison.json', result)
            return result
        if index and {(c['name'], c['repeat']): signature(c) for c in record['cases']} != {
                (c['name'], c['repeat']): signature(c) for c in arms[0]['cases']}:
            result = dict(status='failed', failed_arm=index+1, eligible_languages=[],
                          error='Cross-policy exact output parity failed', partial_results_not_scored=True)
            write(folder / 'comparison.json', result)
            return result
    result = dict(status='completed', **compare(arms))
    write(folder / 'comparison.json', result)
    return result


@cleanup_on_termination()
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--experiment', choices=EXPERIMENTS, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--run', action='store_true')
    args = ap.parse_args(argv)
    cases = fixtures()
    plan = dict(schema=1, experiment=args.experiment, profiles=EXPERIMENTS[args.experiment], order=ORDER,
        files=[{k:c[k] for k in ('name', 'language', 'cohort')} for c in cases], repeats=REPEATS,
        temperature=0.6, seed=1234, normal_eos=True, maximum_output_tokens=MAX_OUTPUT,
        first_exposure='First encounter with each disjoint file; first file is also the first request after load. OS cache is uncontrolled.',
        warmed='Three subsequent repeats are separate from first exposure; global lookup pool may remember the same file.',
        confirm='Independent A/B/B/A on three held-out files; same language scope must qualify in screen and confirmation.',
        acceptance='No minimum percentage: both candidate launches beat both controls, gain above twice control drift, faster complete reply, no material TPS regression, <=100ms extra first-token latency; exact text/token parity, guards and activation required.',
        resources='34GiB entry, 1GiB ongoing floor, continuous normal pressure, zero new swap, AC Automatic, quiet preflight, no cleanup during brackets.',
        stop='One attempt per arm; no partial scoring, overwrites or unchanged retries. No automatic launcher changes.')
    print(json.dumps(plan, indent=2), flush=True)
    if not args.run:
        return
    if args.experiment == 'prompt-local':
        raise RuntimeError('E02 is parked: this native matcher produces zero guesses under width3. No model loaded.')
    cpu_proof = matcher_proof() if args.experiment == 'prompt-map' else None
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    with (ROOT / 'bench/.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require_pass(); assert_no_model_server(); power()
        write(folder / 'plan.json', plan)
        frozen = dict(created_utc=datetime.now(timezone.utc).isoformat(), closure=closure(),
                      models=verify_models(['flash', 'mtp_shared_packed_q3']), matcher_proof_sha256=cpu_proof)
        write(folder / 'frozen.json', frozen)
        record = dict(status='running', experiment=args.experiment, confirmed_languages=[])
        write(folder / 'campaign.json', record)
        record['screen'] = bracket(folder / 'screen', EXPERIMENTS[args.experiment], 'screen', frozen)
        if record['screen']['eligible_languages']:
            record['confirm'] = bracket(folder / 'confirm', EXPERIMENTS[args.experiment], 'confirm', frozen)
            record['confirmed_languages'] = sorted(set(record['screen']['eligible_languages']) &
                                                   set(record['confirm']['eligible_languages']))
            record['confirmed_scopes'] = {}
            for language in record['confirmed_languages']:
                scopes = [{s for r in record[phase]['rows'] if r['language'] == language
                           and r['cohort'] == 'first-exposure' for s in r['qualified_scopes']}
                          for phase in ('screen', 'confirm')]
                record['confirmed_scopes'][language] = sorted(scopes[0] & scopes[1])
        record['status'] = ('failed' if any(record[p]['status'] == 'failed' for p in ('screen', 'confirm') if p in record)
                            else 'confirmed' if record['confirmed_languages'] else 'no confirmed gain')
        write(folder / 'campaign.json', record)
        print(f"Campaign: {record['status']}; independently confirmed languages: {record['confirmed_languages']}", flush=True)
        if record['status'] == 'failed':
            raise SystemExit(1)


if __name__ == '__main__':
    main()
