#!/usr/bin/env python3
"""Check every GDN snapshot and rollback; time complete single-op graphs including synchronization."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import math
import os
import re
import statistics
from pathlib import Path
import subprocess

from benchmark import Monitor
from check_memory import assert_no_model_server
from engines import ROOT, sha256, verify_engine
from metal_environment import configure

WORK = ROOT / 'bench/runtime/m5-gdn'
SOURCE = ROOT / 'native/m5_gdn_probe.cpp'
BINARY = WORK / 'gdn-probe'
TUNINGS = ('gdn-row4', 'gdn-row1', 'gdn-row2')


def inventory(mode):
    result = [dict(label='target', S=128, H=48, HQ=16, T=t, B=1, K=4, G=1,
                   fused=fused, layout=layout)
              for t in (1, 2, 3, 4, 5) for fused in (True, False)
              for layout in (('model', 'permuted') if mode == 'check' else ('model',))]
    if mode == 'check':
        for label, field, value in (('K1', 'K', 1), ('T6', 'T', 6), ('H32', 'H', 32),
                                    ('B2', 'B', 2), ('S64', 'S', 64), ('G128', 'G', 128)):
            for fused in (True, False):
                case = dict(label=label, S=128, H=48, HQ=16, T=4, B=1, K=4, G=1,
                            fused=fused, layout='model')
                case[field] = value
                result.append(case)
    return result


def buffer_elements(case):
    state = case['S']**2 * case['H'] * case['B']
    attention = case['S'] * case['H'] * case['T'] * case['B']
    # Attention, cache including guards and padded slots, complete GDN tail, SUM consumer.
    return 2*attention + 30 + (state + 37) * case['K'] + state * case['K'] + 1


def evidence_elements(case):
    count = buffer_elements(case)
    if case['label'] != 'target':
        return count
    for accepted in range(case['T'] + 1):
        if accepted and case['T'] - accepted >= case['K']:
            continue
        if accepted:
            count += buffer_elements({**case, 'T': accepted})
        count += 2 * buffer_elements({**case, 'T': 1})
    return count


def fixture_inventory(case):
    case_id = f"{case['label']}/T{case['T']}/{'fused' if case['fused'] else 'unfused'}/{case['layout']}"
    graphs = [(case_id+'/main', case)]
    if case['label'] == 'target':
        for accepted in range(case['T']+1):
            if accepted and case['T']-accepted >= case['K']:
                continue
            if accepted:
                graphs.append((case_id+f'/prefix/{accepted}', {**case, 'T': accepted}))
            graphs.extend((case_id+f'/{name}/{accepted}', {**case, 'T': 1})
                          for name in ('slot-next', 'prefix-next'))
    return graphs


def buffer_inventory(case):
    buffers = []
    for graph_id, shape in fixture_inventory(case):
        state = shape['S']**2*shape['H']*shape['B']
        attention = shape['S']*shape['H']*shape['T']*shape['B']
        for name, elements in (('attention', attention), ('cache', 30+(state+37)*shape['K']),
                               ('gdn_output', attention+state*shape['K']), ('consumer', 1)):
            buffers.append(dict(id=graph_id+'/'+name, bytes=elements*4))
    return buffers


def read_buffers(folder, mode):
    expected = [buffer for case in inventory(mode) for buffer in buffer_inventory(case)] if mode == 'check' else []
    values = [json.loads(line) for line in (Path(folder)/'outputs.jsonl').read_text().splitlines()]
    if len(values) != len(expected) or len({v['id'] for v in values}) != len(expected):
        raise ValueError('Missing or duplicated output-buffer digests')
    for value, wanted in zip(values, expected):
        if (set(value) != {'id', 'bytes', 'sha256'} or value['id'] != wanted['id']
                or type(value['bytes']) is not int or value['bytes'] != wanted['bytes']
                or not re.fullmatch('[0-9a-f]{64}', value['sha256'])):
            raise ValueError('Full-buffer digest inventory differs')
    return values


def trace_record(case, tuning):
    s, h, hq, t, b = (case[k] for k in ('S', 'H', 'HQ', 'T', 'B'))
    selected = int(tuning[-1]) if tuning in TUNINGS and case['label'] == 'target' else 0
    rows = selected or s // 32
    record = dict(rows=rows, variant_rows=selected, K=case['K'], fused=case['fused'],
                  slot_stride_floats=(s*s*h*b+37 if case['fused'] else 0))
    for side, (label, heads) in enumerate((('q', hq), ('k', hq), ('v', h))):
        hs, ts = s, s*heads
        bs = ts*t
        if case['layout'] == 'model' and side == 2:
            ts = s*(2*hq+h)
            bs = ts*t
        if case['layout'] == 'permuted':
            if side == 0:
                ts = s+8
                hs = ts*(t+1)
            elif side == 1:
                hs = s+12
                ts = hs*heads+20
            else:
                ts = s+16
                hs = ts*(t+2)
            bs = max(hs*heads, ts*t)+24
        record[label+'_ne'] = [s, heads, t, b]
        record[label+'_nb'] = [4, hs*4, ts*4, bs*4]
    for label, ne in (('g', [case['G'], h, t, b]), ('beta', [1, h, t, b]), ('state', [s, s, h, b])):
        stride = 4
        nb = []
        for n in ne:
            nb.append(stride)
            stride *= n
        record[label+'_ne'], record[label+'_nb'] = ne, nb
    record.update(threadgroups=[s//rows, h, b], threads=[32, rows, 1])
    return record


def build():
    pin = verify_engine('m5-gdn')
    native = ROOT / pin['directory']
    WORK.mkdir(parents=True, exist_ok=True)
    command = ['/usr/bin/c++', '-O3', '-ffp-contract=off', '-std=gnu++17', '-arch', 'arm64',
               '-I'+str(native/'ggml/include'), '-I'+str(native/'vendor'), str(SOURCE), '-o', str(BINARY),
               '-Wl,-rpath,'+str(native/'build/bin'),
               *[str(native/'build/bin'/name) for name in ('libggml.0.26.0.dylib', 'libggml-base.0.26.0.dylib')]]
    with (WORK/'probe-build.log').open('w') as log:
        subprocess.run(command, stdout=log, stderr=log, check=True)
    record = dict(engine=pin, source_sha256=sha256(SOURCE), runner_sha256=sha256(__file__),
                  binary_sha256=sha256(BINARY), command=command)
    (WORK/'probe-build.json').write_text(json.dumps(record, indent=2)+'\n')
    return record


def verify():
    record = json.loads((WORK/'probe-build.json').read_text())
    if (record['engine'] != verify_engine('m5-gdn') or record['source_sha256'] != sha256(SOURCE)
            or record['runner_sha256'] != sha256(__file__) or record['binary_sha256'] != sha256(BINARY)):
        raise RuntimeError('GDN probe provenance changed')
    return record



def fixture_geometry(case, mode):
    state = case['S']**2*case['H']*case['B']
    checking = mode == 'check'
    return dict(padded_cache=checking,
                qkv_view_offsets_bytes=[12, 16, 20] if checking else [0, 0, 2*case['S']*case['HQ']*4],
                cache_view_offset_bytes=44 if checking else state*4,
                cache_slot_stride_floats=state+(37 if checking else 0))


def parse(text, mode, tuning):
    def markers(name):
        return [json.loads(line[len(name)+1:]) for line in text.splitlines() if line.startswith(name+' ')]
    cases, done, traces = (markers(name) for name in ('M5_GDN_CASE', 'M5_GDN_DONE', 'M5_GDN_SHAPE'))
    expected = inventory(mode)
    if ('M5_GDN_ERROR' in text or len(done) != 1 or done[0] != dict(mode=mode, cases=len(expected),
            elements=sum(c.get('elements', -1) for c in cases), sync_included=True, callbacks_used=False,
            evidence_format='sha256-buffer-manifest-v1')):
        raise ValueError('Incomplete GDN completion evidence')
    if len(cases) != len(expected):
        raise ValueError('Incomplete GDN shape coverage')
    for actual, case in zip(cases, expected):
        if any(actual.get(key) != value for key, value in case.items()):
            raise ValueError('GDN shape coverage or order changed')
        wanted = [a for a in range(case['T']+1) if a == 0 or case['T']-a < case['K']]
        unavailable = [a for a in range(1, case['T']+1) if case['T']-a >= case['K']]
        if mode == 'perf' or case['label'] != 'target':
            wanted, unavailable = [], []
        shapes = [case]*4 if mode == 'perf' else [shape for _, shape in fixture_inventory(case)]
        attention_checked = sum(c['S']*c['H']*c['T']*c['B'] for c in shapes)
        state_checked = sum(c['S']**2*c['H']*c['B']*min(c['T'], c['K']) for c in shapes)
        if (actual['samples'] != (512 if mode == 'perf' else 1)
                or actual['distinct_state_buffers'] != (4 if mode == 'perf' else 1)
                or actual['geometry'] != fixture_geometry(case, mode)
                or actual['elements'] != (0 if mode == 'perf' else evidence_elements(case))
                or actual['attention_values_checked'] != attention_checked or actual['state_values_checked'] != state_checked
                or actual['continuation_pairs'] != len(wanted)
                or actual['rollback_prefixes'] != wanted or actual['unavailable_prefixes'] != unavailable
                or actual['scheduler_splits'] != 1 or actual['all_nodes_metal'] is not True
                or actual['inputs_preserved'] is not True or actual['unwritten_slots_preserved'] is not True):
            raise ValueError('Incomplete state, rollback, sentinel, or timing evidence')
        samples = actual['wall_samples_us_per_graph_sync']
        if (not isinstance(samples, list) or len(samples) != actual['samples']
                or any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0 for value in samples)
                or not math.isclose(actual['wall_us_per_graph_sync'], statistics.median(samples), rel_tol=1e-12, abs_tol=1e-9)
                or actual['warmup_minimum_ms'] != (500 if mode == 'perf' else 0)
                or not math.isfinite(actual['warmup_elapsed_ms'])
                or actual['warmup_elapsed_ms'] < actual['warmup_minimum_ms']
                or type(actual['warmup_graphs']) is not int
                or (mode == 'perf' and actual['warmup_graphs'] < 4)
                or (mode == 'check' and (actual['warmup_graphs'] != 0 or actual['warmup_elapsed_ms'] != 0))):
            raise ValueError('Incomplete positive timing samples, median, or sustained warmup evidence')
        for field in ('attention_nmse', 'state_nmse', 'max_absolute_error', 'wall_us_per_graph_sync'):
            if not math.isfinite(actual[field]) or actual[field] < 0:
                raise ValueError('Non-finite or negative GDN evidence')
        if (actual['attention_nmse'] >= 1e-10 or actual['state_nmse'] >= 1e-10
                or actual['max_absolute_error'] >= 2e-5 or actual['wall_us_per_graph_sync'] <= 0):
            raise ValueError('Strict GDN CPU-reference accuracy failed')
    canonical = lambda item: json.dumps(item, sort_keys=True)
    want = {canonical(trace_record(c, tuning)) for c in expected} if mode == 'check' else set()
    got = {canonical(trace) for trace in traces}
    if got != want:
        raise ValueError(f'Normal fusion/dispatch evidence differs: missing={len(want-got)} extra={len(got-want)}')
    return cases


def execute(mode, tuning):
    if mode not in ('check', 'perf') or tuning not in ('conv-direct', *TUNINGS):
        raise ValueError('Unknown GDN mode/tuning')
    assert_no_model_server()
    pin = verify()
    folder = ROOT/'bench/features'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-m5-gdn-'+mode+'-'+tuning)
    folder.mkdir()
    env, flags = configure(os.environ, 'm5-gdn', 'on', tuning)
    for key in ('GGML_SCHED_DEBUG', 'GGML_SCHED_DEBUG_REALLOC'):
        env.pop(key, None)
    if mode == 'check':
        env['GGML_M5_LAB_GDN_TRACE'] = '1'
        flags['variables']['GGML_M5_LAB_GDN_TRACE'] = '1'
    command = [str(BINARY), mode, str(folder/'outputs.jsonl')]
    record = dict(status='running', probe=pin, mode=mode, command=command, metal_environment=flags,
                  models_loaded=False, tps_measured=False,
                  cache_slot_stride_floats='S*S*H*B+37' if mode == 'check' else 'S*S*H*B',
                  scope='One complete GDN/cache-copy/consumer graph per submission plus synchronization. Metal scheduler with mandatory idle CPU fallback; all graph nodes pinned to Metal, one split. Explicitly retained fixture buffers. Four distinct input-state buffers rotate without overlap; performance cases have at least 500ms sustained compute warmup then 512 recorded synchronized samples. No callbacks; trace is check-only. Operator graph latency is not model TPS.')
    process = monitor = None
    try:
        with (folder/'native.log').open('w') as log:
            baseline = Monitor.baseline()
            process = subprocess.Popen(command, env=env, stdout=log, stderr=log)
            monitor = Monitor(process, folder/'memory.jsonl', 0, 2**30, baseline=baseline)
            monitor.thread.start()
            code = process.wait(timeout=1200)
        monitor.thread.join(timeout=5)
        record['memory'] = monitor.finish()
        memory = record['memory']
        if (code or memory['guard'] or memory['swap_growth_bytes'] != 0 or not memory['monitor_healthy']
                or not memory['child_exited'] or not memory['baseline_before_launch']):
            raise RuntimeError('GDN probe or memory check failed')
        record['cases'] = parse((folder/'native.log').read_text(), mode, tuning)
        buffers = read_buffers(folder, mode)
        if sum(b['bytes'] for b in buffers) != sum(c['elements'] for c in record['cases'])*4:
            raise RuntimeError('Wrong full-buffer evidence coverage')
        record['buffer_digest_count'] = len(buffers)
        record['evidence_format'] = 'sha256-buffer-manifest-v1'
        record['outputs_sha256'] = sha256(folder/'outputs.jsonl')
        record['native_log_sha256'] = sha256(folder/'native.log')
        if verify() != pin:
            raise RuntimeError('Engine or probe changed during execution')
        record['status'] = 'passed'
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
                process.wait()
        if monitor:
            monitor.thread.join(timeout=5)
            if 'memory' not in record:
                record['memory'] = monitor.finish()
        (folder/'probe.json').write_text(json.dumps(record, indent=2)+'\n')
        print(mode, tuning, record['status'], folder, flush=True)
    return folder


def read_record(folder):
    folder = Path(folder)
    record = json.loads((folder/'probe.json').read_text())
    memory = record.get('memory', {})
    if (record['status'] != 'passed' or record['probe'] != verify()
            or memory.get('swap_growth_bytes') != 0 or memory.get('guard')
            or not memory.get('monitor_healthy') or not memory.get('child_exited')
            or not memory.get('baseline_before_launch')
            or record['metal_environment']['tensor_api'] != 'on' or record['metal_environment']['profile']
            or record['outputs_sha256'] != sha256(folder/'outputs.jsonl')
            or record['native_log_sha256'] != sha256(folder/'native.log')):
        raise ValueError('Invalid or changed GDN evidence')
    parsed = parse((folder/'native.log').read_text(), record['mode'], record['metal_environment']['tuning'])
    buffers = read_buffers(folder, record['mode'])
    if (parsed != record['cases'] or len(buffers) != record['buffer_digest_count']
            or sum(b['bytes'] for b in buffers) != sum(c['elements'] for c in parsed)*4
            or record['evidence_format'] != 'sha256-buffer-manifest-v1'):
        raise ValueError('GDN case or output evidence changed')
    return record


def compare(control, candidate):
    control, candidate = Path(control), Path(candidate)
    try:
        a, b = (read_record(folder) for folder in (control, candidate))
        if (a['mode'] != 'check' or b['mode'] != 'check' or a['probe'] != b['probe']
                or a['metal_environment']['tuning'] != 'conv-direct' or b['metal_environment']['tuning'] not in TUNINGS):
            raise ValueError('Unmatched GDN check evidence')
        left, right = read_buffers(control, 'check'), read_buffers(candidate, 'check')
        if left != right:
            raise ValueError('GDN attention, full state, rollback, or sentinel buffer digests changed')
        result = dict(status='passed', control=str(control.relative_to(ROOT)), candidate=str(candidate.relative_to(ROOT)),
                      elements_with_identical_sha256=sum(c['elements'] for c in a['cases']),
                      buffers_with_identical_sha256=len(left), raw_values_stored=False,
                      every_snapshot_cpu_checked=True, rollback_continuations_bit_identical=True)
    except BaseException as error:
        result = dict(status='failed', error=f'{type(error).__name__}: {error}', control=str(control), candidate=str(candidate))
        (candidate/'comparison.json').write_text(json.dumps(result, indent=2)+'\n')
        raise
    (candidate/'comparison.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


def verify_checks():
    receipt = json.loads((WORK/'checks.json').read_text())
    if receipt['probe'] != verify() or receipt['status'] != 'passed' or set(receipt['candidates']) != set(TUNINGS):
        raise ValueError('GDN correctness gate is stale or incomplete')
    control = ROOT/receipt['control']
    for tuning, candidate in receipt['candidates'].items():
        compare(control, ROOT/candidate)
        if read_record(ROOT/candidate)['metal_environment']['tuning'] != tuning:
            raise ValueError('Wrong candidate in correctness gate')
    return receipt


def summarize_perf(before, after, candidates):
    controls = [read_record(before), read_record(after)]
    records = {tuning: [read_record(p) for p in paths] for tuning, paths in candidates.items()}
    if (any(r['mode'] != 'perf' or r['metal_environment']['tuning'] != 'conv-direct' for r in controls)
            or set(records) != set(TUNINGS) or any(len(rs) != 2 for rs in records.values())
            or any(r['mode'] != 'perf' or r['metal_environment']['tuning'] != tuning
                   for tuning, rs in records.items() for r in rs)):
        raise ValueError('Wrong performance bracket')
    rows = []
    for i, case in enumerate(inventory('perf')):
        c = [r['cases'][i]['wall_us_per_graph_sync'] for r in controls]
        negative_control = [r['cases'][i]['wall_us_per_graph_sync'] for r in records['gdn-row4']]
        envelope = c+negative_control
        drift = (max(envelope)-min(envelope))/min(envelope)
        for tuning, rs in records.items():
            values = [r['cases'][i]['wall_us_per_graph_sync'] for r in rs]
            improvement = 1-max(values)/min(envelope)
            rows.append({**case, 'tuning': tuning, 'control_us': c, 'negative_control_row4_us': negative_control,
                         'control_envelope_us': envelope, 'candidate_us': values,
                         'control_drift_percent': 100*drift, 'conservative_time_reduction_percent': 100*improvement,
                         'qualifies_for_model_trial': case['T'] == 4 and case['fused'] and tuning != 'gdn-row4'
                         and improvement >= 0.10 and improvement > drift})
    return dict(status='passed', controls=[str(Path(p).relative_to(ROOT)) for p in (before, after)],
                candidates={k: [str(Path(p).relative_to(ROOT)) for p in v] for k, v in candidates.items()},
                scope='Synchronized single-graph operator latency; no model TPS measured.', cases=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true')
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--mode', choices=('check', 'perf'), default='check')
    args = parser.parse_args()
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.build:
            build()
        if not args.run:
            return
        if args.mode == 'check':
            control = execute('check', 'conv-direct')
            candidates = {}
            for tuning in TUNINGS:
                candidate = execute('check', tuning)
                compare(control, candidate)
                candidates[tuning] = str(candidate.relative_to(ROOT))
            (WORK/'checks.json').write_text(json.dumps(dict(status='passed', probe=verify(),
                control=str(control.relative_to(ROOT)), candidates=candidates), indent=2)+'\n')
        else:
            verify_checks()
            before = execute('perf', 'conv-direct')
            candidates = {tuning: [execute('perf', tuning) for _ in range(2)] for tuning in TUNINGS}
            after = execute('perf', 'conv-direct')
            report = summarize_perf(before, after, candidates)
            (after/'bracket.json').write_text(json.dumps(report, indent=2)+'\n')
            print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
