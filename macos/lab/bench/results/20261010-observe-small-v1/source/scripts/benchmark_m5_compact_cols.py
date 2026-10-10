#!/usr/bin/env python3
"""Exact two-block MoE screen for column-first compact tile scheduling."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import math
import os
import shutil
import subprocess

from benchmark import Monitor
from check_memory import assert_no_model_server
from engines import ROOT, sha256, verify_engine
from metal_environment import configure
from validate_offline import require_pass

SOURCE = ROOT/'native/m5_compact_probe.cpp'
WORK = ROOT/'bench/runtime/m5-compact-cols'
RESULTS = ROOT/'bench/results/20261009-compact-tiles/columns'
EXACT_ORACLE = 'original-engine full F32 byte digests'
COUNTER_SEMANTICS = 'each eligible encoded compact MM_ID; elapsed complete graph measured separately'
GATE = ('Strictly more than 10% complete two-dependent-block time reduction above twice absolute '
        'control drift for BOTH T508/T512 uniform synthetic routes; exact terminal F32 bytes and '
        'diagnostic projection bytes, complete per-MM activation/fallback, immutable inputs/weights, '
        'no new swap. Scheduling tile counts are not elapsed gains or model TPS.')


def inventory(mode):
    if mode not in ('check', 'perf'):
        raise ValueError('Unknown compact mode')
    fixtures = []
    def add(rows, route='mixed', stride=2048, layout='plain', precision='default', terminal_only=True):
        fixtures.append(dict(rows=rows, route=route, id_stride_bytes=stride, layout=layout,
                             precision=precision, terminal_only=terminal_only))
    for rows in ((32, 33, 64, 127, 508, 512) if mode == 'perf' else (31, 32, 33, 64, 127, 508, 512, 513)):
        for route in ('uniform', 'shared', 'mixed'):
            for stride in ((2048,) if mode == 'perf' else (40, 2048)):
                add(rows, route, stride)
    if mode == 'check':
        for rows in (33, 512):
            add(rows, terminal_only=False)
            for precision in ('all-f32', 'gate-f32-up-default', 'gate-default-up-f32'):
                add(rows, precision=precision)
            for layout in ('different-input', 'different-ids', 'intervening-gate-scale', 'activation-unfused',
                           'unsupported-shape', 'unsupported-k', 'activation-f16', 'precision-f16'):
                add(rows, layout=layout, precision='all-f16' if layout == 'precision-f16' else 'default')
        add(1, 'shared', 40)
        for rows in (33, 64, 127, 508, 512):
            for stride in (40, 2048):
                add(rows, 'skewed', stride)
        for rows in (508, 512):
            for stride in (40, 2048):
                for route in ('capacity', 'capacity-permuted'):
                    add(rows, route, stride)
    return [dict(fixture, round=n) for fixture in fixtures for n in (range(3) if mode == 'check' else range(1))]


def eligible_projections(fixture):
    if not 32 <= fixture['rows'] <= 512 or fixture['layout'] in ('unsupported-shape', 'precision-f16'):
        return [False]*6
    per_block = [False, False, True] if fixture['layout'] in ('unsupported-k', 'activation-f16') else [True]*3
    return per_block*2


def expected_id(fixture):
    return (f"t{fixture['rows']}-{fixture['route']}-stride{fixture['id_stride_bytes']}-"
            f"{fixture['layout']}-precision-{fixture['precision']}" +
            ('-terminal-only' if fixture['terminal_only'] else ''))


def route_counts(fixture, block, phase, offset=0):
    """Independent validation of synthetic top10 degree and tile-capacity receipts."""
    count = [0]*512
    rows, route = fixture['rows'], fixture['route']
    shift = (block*61 + phase*37 + offset) % 512
    capacity = []
    if route in ('capacity', 'capacity-permuted'):
        extra = (10*rows - 512)//32
        remaining = [33]*extra + [1]*(512-extra)
        remaining[extra] += (10*rows - 512) % 32
        for _ in range(rows):
            selected = sorted(range(512), key=lambda expert: (-remaining[expert], expert))[:10]
            if any(remaining[expert] <= 0 for expert in selected):
                raise ValueError('Invalid capacity degree sequence')
            for expert in selected:
                remaining[expert] -= 1
            capacity.append(selected)
        if any(remaining):
            raise ValueError('Incomplete capacity degree sequence')
    for row in range(rows):
        if route == 'uniform':
            selected = [(10*row + lane) % 512 for lane in range(10)]
        elif route == 'shared':
            selected = list(range(10))
        elif route == 'mixed':
            selected = list(range(5)) + [5 + ((5*row + lane) % 507) for lane in range(5)]
        elif route == 'skewed':
            selected = [0] + [expert for expert, limit in ((1, 1), (2, 31), (3, 32), (4, 33)) if row < limit]
            selected += [5 + ((10*row + lane) % 506) for lane in range(10-len(selected))]
        elif route in ('capacity', 'capacity-permuted'):
            selected = capacity[row]
            if route == 'capacity-permuted':
                selected = [(73*selected[(3*lane+7) % 10]+19) % 512 for lane in range(10)]
        else:
            raise ValueError('Unknown route fixture')
        selected = [(expert+shift) % 512 for expert in selected]
        if len(set(selected)) != 10:
            raise ValueError('Synthetic IDs are not distinct top10')
        for expert in selected:
            count[expert] += 1
    return count


def pins(engine):
    return dict(engine=verify_engine(engine), source_sha256=sha256(SOURCE), runner_sha256=sha256(__file__),
                dependencies={name: sha256(ROOT/'scripts'/name) for name in
                              ('benchmark.py', 'engines.py', 'metal_environment.py', 'check_memory.py', 'validate_offline.py')})


def markers(text, name):
    return [json.loads(line[len(name)+1:]) for line in text.splitlines() if line.startswith(name+' ')]


def validate_projections(row, fixture):
    wanted = eligible_projections(fixture)
    actual = row['projections']
    if len(actual) != 6:
        raise ValueError('Per-MM predicate coverage missing')
    precision = fixture['precision']
    precs = {'default': [0, 0, 0], 'all-f32': [10, 10, 10], 'gate-f32-up-default': [10, 0, 10],
             'gate-default-up-f32': [0, 10, 10], 'all-f16': [20, 20, 20]}[precision]
    k = 2496 if fixture['layout'] == 'unsupported-k' else 2560
    hidden = 576 if fixture['layout'] == 'unsupported-shape' else 640
    for index, projection in enumerate(actual):
        lane = index % 3
        weight = [hidden, 2560, 512, 1] if lane == 2 else [k, hidden, 512, 1]
        activation = [hidden, 10, fixture['rows'], 1] if lane == 2 else [k, 1, fixture['rows'], 1]
        activation_type = 'f16' if lane != 2 and fixture['layout'] == 'activation-f16' else 'f32'
        # The shape/K fallback fixtures retain stock strided quantized views;
        # their shape and contiguity guards are exercised jointly.
        weight_contiguous = not (fixture['layout'] == 'unsupported-shape' or
                                 (fixture['layout'] == 'unsupported-k' and lane != 2))
        expected = dict(name=f"block{index//3}."+('gate', 'up', 'down')[lane], eligible=wanted[index],
                        weight_shape=weight, activation_shape=activation, activation_type=activation_type,
                        weight_type='q2_0', source_precision=precs[lane], id_stride_bytes=fixture['id_stride_bytes'],
                        weight_contiguous=weight_contiguous, activation_contiguous=True, output_contiguous=True)
        if projection != expected:
            raise ValueError('Actual MM tensor predicate changed')
    return sum(wanted)


def parse(text, mode, scope):
    if scope not in ('control', 'compact'):
        raise ValueError('Unknown compact scope')
    rows, done = markers(text, 'M5_COMPACT_CASE'), markers(text, 'M5_COMPACT_DONE')
    wanted = inventory(mode)
    if 'M5_COMPACT_ERROR' in text or len(done) != 1 or len(rows) != len(wanted):
        raise ValueError('Incomplete compact probe')
    end = done[0]
    if (end['mode'] != mode or end['scope'] != scope or end['cases'] != len(wanted)
            or end['fixtures']* (3 if mode == 'check' else 1) != len(wanted)
            or end['models_loaded'] is not False or end['weights_preserved'] is not True
            or end['route_source'] != 'synthetic' or (scope == 'compact' and end['counter_available'] is not True)):
        raise ValueError('Compact completion or preservation changed')
    for row, expected in zip(rows, wanted):
        if any(row[key] != value for key, value in expected.items()) or row['mode'] != mode or row['scope'] != scope:
            raise ValueError('Compact fixture coverage changed')
        if row['id'] != expected_id(expected) or row['exact_oracle'] != EXACT_ORACLE or row['route_source'] != 'synthetic':
            raise ValueError('Complete graph identity or original-engine oracle changed')
        eligible = validate_projections(row, expected)
        integer_fields = ('count_delta', 'executions', 'triplets_per_graph', 'eligible_mm_per_graph', 'mm_ids_per_graph')
        if (any(type(row[key]) is not int for key in integer_fields) or row['executions'] < 1
                or row['eligible'] is not bool(eligible) or row['eligible_mm_per_graph'] != eligible
                or row['mm_ids_per_graph'] != 6 or row['triplets_per_graph'] != 2
                or row['counter_semantics'] != COUNTER_SEMANTICS):
            raise ValueError('Invalid execution/counter metadata')
        target = row['executions']*eligible if scope == 'compact' else 0
        if row['count_delta'] != target or (scope == 'compact' and row['counter_available'] is not True):
            raise ValueError('Complete eligible compact/fallback coverage missing')
        names = ([f'block{block}.{name}' for block in range(2) for name in ('gate', 'up', 'activated', 'down')]
                 if not expected['terminal_only'] else []) + ['block1.residual']
        if (not all(row[key] is True for key in ('inputs_preserved', 'ids_preserved', 'all_nodes_metal'))
                or row['scheduler_splits'] != 1 or row['cpu_compute_nodes'] != 0 or row['evaluation_callbacks'] is not False
                or [output['name'] for output in row['outputs']] != names
                or row['allocation_estimate_bytes'] >= 3*1024**3):
            raise ValueError('Placement, preservation or allocation checks failed')
        for output in row['outputs']:
            multiplier = 2560 if output['name'].endswith('.residual') else (2560*10 if output['name'].endswith('.down') else 640*10)
            if (output['finite'] is not True or output['elements'] != multiplier*expected['rows']
                    or output['bytes'] != 4*output['elements'] or not valid_digest(output['sha256'])):
                raise ValueError('Complete finite F32 output bytes missing')
        if row['output_sha256'] != row['outputs'][-1]['sha256']:
            raise ValueError('Terminal result hash disagrees with full output')
        phase = 1 if expected['round'] == 1 else 0
        if row['input_version'] != phase or row['same_graph_mutation'] is not (mode == 'check'):
            raise ValueError('A/B/A execution version changed')
        positions = [(block, offset) for block in range(2) for offset in ((0, 7) if expected['layout'] == 'different-ids' else (0,))]
        if len(row['routes']) != len(positions) or len(row['ids_sha256']) != len(positions):
            raise ValueError('ID route receipt coverage missing')
        for receipt, (block, offset) in zip(row['routes'], positions):
            counts = route_counts(expected, block, phase, offset)
            tiles, bound = sum((count+31)//32 for count in counts), (10*expected['rows']+31*512)//32
            if receipt != dict(expert_counts=counts, memberships=10*expected['rows'], nonempty_tiles32=tiles,
                               static_tile_capacity=bound, distinct_top10_per_token=True) or tiles > bound:
                raise ValueError('Synthetic top10 or static tile capacity changed')
        if (any(not valid_digest(value) for value in [row['input_sha256'], row['coefficients_sha256'], *row['ids_sha256']])
                or len(row['weights']) != 3 or row['weights'] != end['weights']):
            raise ValueError('Immutable input/weight receipts missing')
        if mode == 'perf':
            samples = row['ns_samples']
            if (len(samples) != 7 or any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0 for value in samples)
                    or row['median_ns'] != sorted(samples)[3] or type(row['warmup_ns']) is not int or row['warmup_ns'] < 500000000
                    or type(row['warmup_iterations']) is not int or row['warmup_iterations'] < 1 or row['pipeline_primed'] is not True
                    or len(row['block_iterations']) != 7 or len(row['block_ns']) != 7
                    or any(type(value) is not int or value < 8 for value in row['block_iterations'])
                    or any(type(value) is not int or value < 100000000 for value in row['block_ns'])
                    or row['executions'] != 1+row['warmup_iterations']+sum(row['block_iterations'])
                    or any(value != ns/iterations for value, ns, iterations in zip(samples, row['block_ns'], row['block_iterations']))
                    or row['ns_per_triplet'] != [value/2 for value in samples]):
                raise ValueError('Sustained complete-block timings missing')
    if mode == 'check':
        for index in range(0, len(rows), 3):
            first, changed, restored = rows[index:index+3]
            if first['outputs'] != restored['outputs'] or first['input_sha256'] != restored['input_sha256'] or first['ids_sha256'] != restored['ids_sha256']:
                raise ValueError('A/B/A terminal result restoration changed')
            if first['input_sha256'] == changed['input_sha256'] or first['ids_sha256'] == changed['ids_sha256']:
                raise ValueError('A/B/A data did not change')
    return rows


def valid_digest(value):
    return isinstance(value, str) and len(value) == 64 and all(char in '0123456789abcdef' for char in value)


def comparable(row):
    return {key: row[key] for key in ('id', 'round', 'outputs', 'output_sha256', 'input_sha256', 'ids_sha256',
                                     'coefficients_sha256', 'weights', 'routes', 'triplets_per_graph', 'terminal_only')}


def compare_exact(control, candidate):
    if len(control) != len(candidate) or [comparable(row) for row in control] != [comparable(row) for row in candidate]:
        raise ValueError('Complete original-engine terminal/projection F32 bytes changed')


def execute(scope, mode, receipt):
    assert_no_model_server()
    folder = RESULTS/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+mode+'-'+scope)
    folder.mkdir()
    engine = 'm5-compact-cols' if scope == 'compact' else 'm5-copy'
    binary = WORK/(scope+'-probe')
    process = monitor = None
    record = dict(status='running', scope=scope, mode=mode, probe=receipt)
    try:
        before = pins(engine)
        if before != {key: receipt[key] for key in before} or sha256(binary) != receipt['binary_sha256']:
            raise ValueError('Probe closure changed')
        env, flags = configure(dict(os.environ), engine, 'on', 'compact-cols' if scope == 'compact' else 'conv-direct')
        record['metal_environment'] = flags
        with (folder/'native.log').open('w') as log:
            baseline = Monitor.baseline()
            process = subprocess.Popen([str(binary), mode, str(folder/'outputs.jsonl'), scope], stdout=log, stderr=log, env=env)
            monitor = Monitor(process, folder/'memory.jsonl', 0, 1024**3, baseline=baseline)
            monitor.thread.start()
            code = process.wait(timeout=900)
        record['memory'] = monitor.finish()
        memory = record['memory']
        record['native_returncode'] = code
        if code or memory['swap_growth_bytes'] or memory['guard'] or not memory['monitor_healthy'] or not memory['child_exited']:
            raise ValueError('Probe or resource guard failed')
        text = (folder/'native.log').read_text()
        rows = parse(text, mode, scope)
        evidence = [json.loads(line) for line in (folder/'outputs.jsonl').read_text().splitlines()]
        if evidence != rows+markers(text, 'M5_COMPACT_DONE'):
            raise ValueError('Native log/evidence disagree')
        record.update(status='passed', cases=rows, native_log_sha256=sha256(folder/'native.log'), evidence_sha256=sha256(folder/'outputs.jsonl'))
        after = pins(engine)
        if after != before or sha256(binary) != receipt['binary_sha256']:
            raise ValueError('Source or binary changed during probe')
    except BaseException as error:
        record.update(status='failed', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)
        if monitor and 'memory' not in record:
            record['memory'] = monitor.finish()
        (folder/'result.json').write_text(json.dumps(record, indent=2)+'\n')
        print(scope, mode, record['status'], folder, flush=True)
    return record, folder


def summarize(timed):
    if len(timed) != 4:
        raise ValueError('Matched control/candidate/candidate/control runs missing')
    for record, _ in timed:
        if record['status'] != 'passed':
            raise ValueError('Failed component run cannot qualify')
        compare_exact(timed[0][0]['cases'], record['cases'])
    rows = []
    for index, first in enumerate(timed[0][0]['cases']):
        values = [record['cases'][index] for record, _ in timed]
        control = (values[0]['median_ns']+values[3]['median_ns'])/2
        candidate = (values[1]['median_ns']+values[2]['median_ns'])/2
        gain = 100*(1-candidate/control)
        drift = 100*abs(values[3]['median_ns']/values[0]['median_ns']-1)
        rows.append(dict(id=first['id'], tokens=first['rows'], route=first['route'], triplets_per_graph=2,
                         control_ms=control/1e6, candidate_ms=candidate/1e6, time_reduction_percent=gain,
                         control_drift_percent=drift, qualifies=gain > 10 and gain > 2*drift))
    required = [row for row in rows if row['tokens'] in (508, 512) and row['route'] == 'uniform']
    return dict(status='passed', runs=[str(path.relative_to(ROOT)) for _, path in timed], rows=rows,
                qualifies_for_model_trial=len(required) == 2 and all(row['qualifies'] for row in required),
                models_loaded=False, route_source='synthetic', gate=GATE)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if not args.run:
        print('Prepared exact full prompt-block screen; no GPU execution or models loaded.')
        return
    require_pass()
    RESULTS.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert_no_model_server()
        receipts = {}
        for scope, engine in (('control', 'm5-copy'), ('compact', 'm5-compact-cols')):
            before = pins(engine)
            native = ROOT/before['engine']['directory']
            binary = WORK/(scope+'-probe')
            command = ['/usr/bin/c++', '-O3', '-ffp-contract=off', '-std=gnu++17', '-arch', 'arm64',
                       '-I'+str(native/'ggml/include'), '-I'+str(native/'vendor'), str(SOURCE), '-o', str(binary),
                       '-Wl,-rpath,'+str(native/'build/bin'), *[str(native/'build/bin'/name) for name in
                                                             ('libggml.0.26.0.dylib', 'libggml-base.0.26.0.dylib')]]
            with (WORK/(scope+'-build.log')).open('w') as log:
                subprocess.run(command, stdout=log, stderr=log, check=True)
            after = pins(engine)
            if after != before:
                raise ValueError('Source closure changed during compilation')
            receipts[scope] = dict(**before, binary_sha256=sha256(binary), command=command)
        archive = RESULTS/'source'
        archive.mkdir()
        closure = [SOURCE, ROOT/'scripts/benchmark_m5_compact_cols.py', ROOT/'tests/test_m5_compact.py',
                   *[ROOT/'scripts'/name for name in receipts['control']['dependencies']],
                   ROOT/'config/m5_compact_cols_experiment.json', ROOT/'patches/mtp-m5-compact-cols.patch',
                   ROOT/'config/m5_compact_experiment.json', ROOT/'patches/mtp-m5-compact.patch',
                   ROOT/'scripts/benchmark_m5_compact.py',
                   ROOT/'config/m5_copy_experiment.json', ROOT/'patches/mtp-m5-copy.patch']
        archived = {}
        for path in closure:
            destination = archive/path.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            archived[str(path.relative_to(ROOT))] = sha256(destination)
            if sha256(path) != archived[str(path.relative_to(ROOT))]:
                raise ValueError('Archived source closure differs')
        (WORK/'build.json').write_text(json.dumps(receipts, indent=2)+'\n')
        (RESULTS/'plan.json').write_text(json.dumps(dict(status='preregistered_before_gpu', source=receipts,
                                                       archive=archived, check_inventory=inventory('check'),
                                                       perf_inventory=inventory('perf'), gate=GATE), indent=2)+'\n')
        checked = [execute(scope, 'check', receipts[scope]) for scope in ('control', 'compact')]
        compare_exact(checked[0][0]['cases'], checked[1][0]['cases'])
        timed = [execute(scope, 'perf', receipts[scope]) for scope in ('control', 'compact', 'compact', 'control')]
        # Reparse native text, JSONL and saved JSON before accepting the aggregate.
        for record, folder in checked+timed:
            text = (folder/'native.log').read_text()
            if parse(text, record['mode'], record['scope']) != record['cases']:
                raise ValueError('Reparsed native evidence changed')
            evidence = [json.loads(line) for line in (folder/'outputs.jsonl').read_text().splitlines()]
            if evidence != record['cases']+markers(text, 'M5_COMPACT_DONE') or json.loads((folder/'result.json').read_text()) != record:
                raise ValueError('Saved artifact differs from raw evidence')
        result = summarize(timed)
        result['checks'] = [str(path.relative_to(ROOT)) for _, path in checked]
        (RESULTS/'comparison.json').write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps(result['rows'], indent=2), flush=True)


if __name__ == '__main__':
    main()
