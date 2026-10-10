#!/usr/bin/env python3
"""Qualify and screen an exact parallel helper top10 selector."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import math
import os
from pathlib import Path
import subprocess

from benchmark import Monitor
from check_memory import assert_no_model_server, snapshot
from engines import ROOT, sha256, verify_engine
from metal_environment import configure
from validate_offline import require_pass

ENGINE = 'm5-top10'
SOURCE = ROOT / 'native/m5_top10_probe.cpp'
WORK = ROOT / 'bench/runtime/m5-top10'
BINARY = WORK / 'top10-probe'
RESULTS = ROOT / 'bench/results/20261009-top10'
DEPENDENCIES = ('benchmark.py', 'check_memory.py', 'engines.py', 'metal_environment.py', 'validate_offline.py')


def pins():
    return dict(engine=verify_engine(ENGINE), source_sha256=sha256(SOURCE), runner_sha256=sha256(__file__),
                dependencies={name: sha256(ROOT / 'scripts' / name) for name in DEPENDENCIES})


def markers(text, name):
    return [json.loads(line[len(name)+1:]) for line in text.splitlines() if line.startswith(name+' ')]


def parse(text, scope, mode):
    from benchmark_m5_head import inventory
    cases = markers(text, 'M5_TOP10_CASE')
    done = markers(text, 'M5_TOP10_DONE')
    wanted = inventory(mode)
    chain = 'head-top_k10-gather'
    if len(done) != 1 or len(cases) != len(wanted) or 'M5_TOP10_ERROR' in text:
        raise ValueError('Incomplete ceiling evidence')
    d = done[0]
    if (d['mode'] != mode or d['scope'] != scope or d['cases'] != len(wanted) or
            d['models_loaded'] or d['expanded_weight_cache'] or not d['weights_preserved'] or
            d['max_probe_bytes'] != 3*1024**3):
        raise ValueError('Invalid ceiling completion')
    for c, expected in zip(cases, wanted):
        if any(c[k] != v for k, v in expected.items()):
            raise ValueError('Ceiling fixture identity changed')
        if (c['elements'] != c['m']*c['rows'] or c['consumer_chain'] != chain or
                not c['inputs_preserved'] or not c['all_nodes_metal'] or c['scheduler_splits'] != 1 or
                c['cpu_compute_nodes'] != 0 or not 0 < c['allocation_bound_bytes'] < 3*1024**3):
            raise ValueError('Incomplete preservation or placement proof')
        if (len(c['consumers']) != c['rows'] or any(len(row['ids']) != 10 or
                len(set(row['ids'])) != 10 or not row['tie_safe'] for row in c['consumers'])):
            raise ValueError('Top10 consumer proof missing')
        for key in ('output_sha256', 'input_sha256', 'weight_sha256'):
            if len(c[key]) != 64 or any(x not in '0123456789abcdef' for x in c[key]):
                raise ValueError('Invalid fixture digest')
        if mode == 'perf':
            if (not c['pipeline_primed'] or c['warmup_us'] < 500000 or
                    any(len(c[k]) != 7 for k in ('block_us', 'block_iterations', 'block_us_per_iteration'))):
                raise ValueError('Insufficient performance blocks')
            for us, n, each in zip(c['block_us'], c['block_iterations'], c['block_us_per_iteration']):
                if not math.isfinite(us) or us < 100000 or n < 8 or each <= 0 or not math.isclose(each, us/n, rel_tol=1e-12):
                    raise ValueError('Invalid performance block')
            if c['median_us'] != sorted(c['block_us_per_iteration'])[3]:
                raise ValueError('Invalid median')
        elif c['cpu_reference_values'] != c['elements'] or c['block_us'] or c['median_us']:
            raise ValueError('Incomplete correctness reference')
    fixtures = markers(text, 'M5_TOP10_FIXTURE')
    if mode == 'check' and len(fixtures) != 30:
        raise ValueError('Missing adversarial selector fixtures')
    if mode == 'perf' and fixtures:
        raise ValueError('Unexpected fixtures in timing')
    return cases, d, fixtures


def comparable(row):
    return {k: v for k, v in row.items() if k != 'selector_status'}


def summarize(records):
    if [r['scope'] for r in records] != ['control', 'candidate', 'candidate', 'control']:
        raise ValueError('Require fresh A/B/B/A bracket')
    if any(r['status'] != 'passed' or r['mode'] != 'perf' for r in records):
        raise ValueError('Unqualified timing run')
    result = []
    for index, ref in enumerate(records[0]['cases']):
        rows = [r['cases'][index] for r in records]
        keys = ('id', 'rows', 'k', 'm', 'input_sha256', 'weight_sha256', 'output_sha256')
        if any(any(row[key] != ref[key] for key in keys) for row in rows):
            raise ValueError('Head math or fixture identity changed')
        if any([comparable(c) for c in row['consumers']] != [comparable(c) for c in ref['consumers']] for row in rows):
            raise ValueError('Top10 IDs or gathered logits changed')
        if any(c['selector_status'] != 1 for row in rows[1:3] for c in row['consumers']):
            raise ValueError('Candidate fast path did not activate')
        a = (rows[0]['median_us']+rows[3]['median_us'])/2
        b = (rows[1]['median_us']+rows[2]['median_us'])/2
        if not all(math.isfinite(x) and x > 0 for x in (a, b)):
            raise ValueError('Invalid bracket timing')
        gain = 100*(1-b/a)
        drift = 100*abs(rows[3]['median_us']/rows[0]['median_us']-1)
        result.append(dict(id=ref['id'], control_us=a, candidate_us=b, saved_us=a-b,
                           time_reduction_percent=gain, control_drift_percent=drift,
                           performance_gate_passed=gain >= 2 and gain > 2*drift))
    return dict(status='completed-component-screen', cases=result, tps_gain_measured=False,
                models_loaded=False, exact_top10_implemented=True,
                qualifies_for_model_trial=all(c['performance_gate_passed'] for c in result),
                note='Complete packed head+exact top10+gather component. Full-model TPS remains unmeasured.')


def build():
    require_pass(); assert_no_model_server()
    before = pins(); native = ROOT / before['engine']['directory']; WORK.mkdir(parents=True, exist_ok=True)
    command = ['/usr/bin/c++', '-O3', '-ffp-contract=off', '-std=gnu++17', '-arch', 'arm64',
               '-I'+str(native/'include'), '-I'+str(native/'ggml/include'), '-I'+str(native/'vendor'), str(SOURCE), '-o', str(BINARY),
               '-Wl,-rpath,'+str(native/'build/bin'),
               *[str(native/'build/bin'/name) for name in ('libllama.0.6.0.dylib', 'libggml.0.26.0.dylib', 'libggml-base.0.26.0.dylib')]]
    with (WORK/'build.log').open('w') as log:
        subprocess.run(command, stdout=log, stderr=log, check=True)
    if pins() != before:
        raise RuntimeError('Build inputs changed')
    record = dict(**before, binary_sha256=sha256(BINARY), command=command)
    (WORK/'build.json').write_text(json.dumps(record, indent=2)+'\n')
    return record


def execute(scope, mode, build_record):
    require_pass(); assert_no_model_server()
    if snapshot()['memory']['available'] < 4*1024**3:
        raise RuntimeError('At least4GiB available required for component screen')
    if pins() != {k: build_record[k] for k in pins()} or sha256(BINARY) != build_record['binary_sha256']:
        raise RuntimeError('Probe provenance changed')
    folder = RESULTS / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+mode+'-'+scope)
    folder.mkdir(parents=True)
    env, flags = configure(os.environ, ENGINE, 'on', 'top10' if scope == 'candidate' else 'conv-direct')
    record = dict(status='running', scope=scope, mode=mode, probe=build_record, metal_environment=flags)
    process = monitor = None
    try:
        with (folder/'native.log').open('w') as log:
            baseline = Monitor.baseline()
            process = subprocess.Popen([str(BINARY), mode, str(folder/'outputs.jsonl'), scope], env=env, stdout=log, stderr=log)
            monitor = Monitor(process, folder/'memory.jsonl', 0, 1024**3, baseline=baseline); monitor.thread.start()
            code = process.wait(timeout=1200)
        record['native_returncode'] = code; record['memory'] = monitor.finish(); m = record['memory']
        if code or m['guard'] or m['swap_growth_bytes'] or not m['monitor_healthy'] or not m['child_exited'] or m['peak_rss_bytes'] > 3*1024**3:
            raise RuntimeError('Native component or memory gate failed')
        record['cases'], record['done'], record['fixtures'] = parse((folder/'native.log').read_text(), scope, mode)
        evidence = [json.loads(line) for line in (folder/'outputs.jsonl').read_text().splitlines()]
        expected = [dict(id=c['id'], elements=c['elements'], sha256=c['output_sha256']) for c in record['cases']]
        expected += [c for c in record['fixtures'] if c['id'] != 'guard-stride']
        if evidence != expected:
            raise RuntimeError('Missing all-score evidence inventory')
        record.update(native_log_sha256=sha256(folder/'native.log'), outputs_sha256=sha256(folder/'outputs.jsonl'), status='passed')
        if pins() != {k: build_record[k] for k in pins()}:
            raise RuntimeError('Inputs changed during execution')
    except BaseException as error:
        record.update(status='failed', error=f'{type(error).__name__}: {error}'); raise
    finally:
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
        if monitor and 'memory' not in record:
            record['memory'] = monitor.finish()
        (folder/'result.json').write_text(json.dumps(record, indent=2, allow_nan=False)+'\n')
        print(mode, scope, record['status'], folder, flush=True)
    return record, folder


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--run', action='store_true'); args = ap.parse_args()
    if not args.run:
        print('Prepared exact top10 component. Use --run to qualify/time; no model loaded.'); return
    RESULTS.mkdir(exist_ok=True)
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        probe = build()
        checks = [execute(scope, 'check', probe) for scope in ('control', 'candidate')]
        a, b = [r for r, _ in checks]
        for x, y in zip(a['cases'], b['cases']):
            if any(x[k] != y[k] for k in ('id', 'input_sha256', 'weight_sha256', 'output_sha256')):
                raise RuntimeError('Selector changed complete head scores')
            if [comparable(c) for c in x['consumers']] != [comparable(c) for c in y['consumers']]:
                raise RuntimeError('Head consumer changed')
        if [comparable(c) for c in a['fixtures']] != [comparable(c) for c in b['fixtures']]:
            raise RuntimeError('Adversarial selector/CPU chain changed')
        rows = [execute(scope, 'perf', probe) for scope in ('control', 'candidate', 'candidate', 'control')]
        result = summarize([r for r, _ in rows])
        result.update(checks=[str(p.relative_to(ROOT)) for _, p in checks], runs=[str(p.relative_to(ROOT)) for _, p in rows])
        (RESULTS/'comparison.json').write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps(result['cases'], indent=2), flush=True)


if __name__ == '__main__':
    main()
