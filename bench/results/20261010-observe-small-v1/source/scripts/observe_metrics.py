"""Validate native diagnostic records and separate overlapping wall intervals."""
from collections import Counter, defaultdict
import json
import math
import re
import statistics

from profile_m5_phases import parse as phase_parse, union_ms

STAGES = {'memory_apply', 'reset', 'build', 'allocate', 'inputs', 'reuse_sync'}
REASONS = {'reuse', 'arena-switch', 'topology', 'disabled'}


def integer(value):
    if type(value) is not int or value < 0:
        raise ValueError('Expected nonnegative integer timestamp/counter')
    return value


def interval(row, low=None, high=None):
    a, b = integer(row['begin_us']), integer(row['end_us'])
    if b < a or (low is not None and a < low) or (high is not None and b > high):
        raise ValueError('Invalid or out-of-bound CPU span')
    return a, b


def outside_ms(spans, occupied):
    """Union of spans outside the occupied union; no double counting."""
    return union_ms(spans + occupied) - union_ms(occupied)


def markers(text, name):
    return [json.loads(line.split(name + ' ', 1)[1]) for line in text.splitlines() if name + ' ' in line]


def allocation_entries(text):
    # Preserve every reservation, including separate attention/indexer KV rows.
    role, loads, rows = 'target', 0, []
    for line_no, line in enumerate(text.splitlines(), 1):
        if 'load_tensors: loading model tensors' in line:
            loads += 1
            role = 'target' if loads == 1 else 'helper'
        match = re.search(r'(\S+)\s+(model|KV|RS|compute|output) buffer size\s*=\s*([0-9.]+)\s*MiB', line)
        if match:
            backend, kind, size = match.groups()
            rows.append(dict(line=line_no, role=role, backend=backend, kind=kind,
                             bytes=round(float(size) * 2**20)))
    return dict(entries=rows, unique_physical_total_bytes=None,
                note='Every logged reservation retained. Mapped/repacked/shared ranges can overlap; rows are not a physical-memory total or peak.')


def parse(text, expected_requests, *, max_clock_spread_us=100, max_anchor_width_us=50):
    phases = phase_parse(text, expected_requests)
    calls, shapes = markers(text, 'M5_CPU_CALL'), markers(text, 'M5_SHAPES')
    shape_map = {s['call']: s for s in shapes}
    if not calls or len(calls) != len({c['call'] for c in calls}) or {c['call'] for c in calls} != set(shape_map):
        raise ValueError('Every shape call needs one unique CPU record')
    offsets, widths = [], []
    for c in calls:
        integer(c['call']); integer(c['tokens']); integer(c['seqs']); integer(c['outputs'])
        if c['reason'] not in REASONS or any(c[k] != shape_map[c['call']][k] for k in ('role', 'tokens')):
            raise ValueError('Unknown reuse reason or mismatched CPU/GPU call metadata')
        if c['role'] not in ('target', 'helper'):
            raise ValueError('Unknown native role')
        low, high = interval(c)
        clock_low, clock_high = integer(c['clock_low_us']), integer(c['clock_high_us'])
        mach = c['mach_us']
        if isinstance(mach, bool) or not isinstance(mach, (int, float)) or not math.isfinite(mach) or mach <= 0:
            raise ValueError('Invalid mach clock anchor')
        width = clock_high - clock_low
        if width < 0 or width > max_anchor_width_us or clock_high > low:
            raise ValueError('Clock anchor is too wide or misplaced')
        offsets.append(mach - (clock_low + clock_high) / 2)
        widths.append(width)
        previous, seen = low, set()
        for s in c['spans']:
            a, b = interval(s, low, high)
            if s['stage'] not in STAGES or s['stage'] in seen or a < previous:
                raise ValueError('Missing/duplicate/unknown or overlapping setup stages')
            seen.add(s['stage']); previous = b
        required = {'memory_apply', 'inputs'} | ({'reset', 'build', 'allocate'} if c['reason'] != 'reuse' else set())
        if not required <= seen or (c['reason'] == 'reuse' and seen & {'reset', 'build', 'allocate'}):
            raise ValueError('Setup stage coverage disagrees with reuse decision')
    spread = max(offsets) - min(offsets)
    if spread > max_clock_spread_us:
        raise ValueError('CPU/mach clock mapping changed; cross-clock attribution refused')
    offset = statistics.median(offsets)
    gpu_rows = [b for b in markers(text, 'M5_PROFILE') if b['valid']]
    occupied = [((b['gpu_start_s'] * 1e6 - offset) / 1e6,
                 (b['gpu_end_s'] * 1e6 - offset) / 1e6) for b in gpu_rows]
    for b, (start, _) in zip(gpu_rows, occupied):
        if start * 1e6 < b['submit_cpu_us'] - max_clock_spread_us:
            raise ValueError('GPU execution precedes labelled submission after clock mapping')
    events, ends = markers(text, 'M5_PHASE'), markers(text, 'M5_REQUEST_END')
    checkpoint_rows = markers(text, 'M5_CHECKPOINT')
    accepts = markers(text, 'M5_ACCEPT')
    for a in accepts:
        integer(a['cpu_us']); integer(a['seq']); integer(a['accepted_drafts'])
    output = []
    for request in phases['requests']:
        task = request['task']; e = [x for x in events if x['task'] == task]
        first = min(x['cpu_us'] for x in e)
        generation = min(x['cpu_us'] for x in e if x['phase'] == 'generation')
        end = next(x['cpu_us'] for x in ends if x['task'] == task)
        requested_calls={s['call'] for s in shapes if first <= s['cpu_us'] < end}
        for b, (start, finish) in zip(gpu_rows, occupied):
            if b['call'] in requested_calls and (start*1e6<first-max_clock_spread_us or finish*1e6>end+max_clock_spread_us):
                raise ValueError('Mapped GPU interval crosses its completed request')
        request_out = dict(task=task, phases={})
        for phase, low, high in (('prompt', first, generation), ('generation', generation, end)):
            selected = [c for c in calls if low <= shape_map[c['call']]['cpu_us'] < high]
            stages, counters, role_rows = defaultdict(list), defaultdict(Counter), defaultdict(Counter)
            for c in selected:
                interval(c, low, high)
                counters[c['role']][c['reason']] += 1
                role_rows[c['role']]['token_rows'] += c['tokens']
                if c['role'] == 'helper':
                    role_rows['helper']['catchup_rows' if not c['outputs'] else 'draft_rows'] += c['tokens']
                for span in c['spans']:
                    stages[c['role'] + '/' + span['stage']].append(tuple(v / 1e6 for v in interval(span)))
            checkpoint = [x for x in checkpoint_rows if x['task'] == task and low <= x['begin_us'] < high]
            for row in checkpoint:
                if row['slot'] != 0 or row['operation'] != 'create':
                    raise ValueError('Unknown checkpoint operation/slot')
                interval(row, low, high); integer(row['bytes'])
            checkpoint_spans = [tuple(v / 1e6 for v in interval(c)) for c in checkpoint]
            accepted = [a for a in accepts if low <= a['cpu_us'] < high]
            values = {name: dict(calls=len(spans), wall_union_ms=union_ms(spans),
                                outside_recorded_model_gpu_ms=max(0, outside_ms(spans, occupied)))
                      for name, spans in stages.items()}
            planning = [s for name, spans in stages.items() if name.split('/')[1] in {'reset', 'build', 'allocate'} for s in spans]
            request_out['phases'][phase] = dict(**request['phases'][phase], cpu_stages=values,
                graph_calls={r:dict(v) for r,v in counters.items()}, token_rows={r:dict(v) for r,v in role_rows.items()},
                planning_wall_union_ms=union_ms(planning),
                planning_outside_recorded_gpu_ms=max(0, outside_ms(planning, occupied)),
                checkpoint_create_calls=len(checkpoint), checkpoint_create_wall_ms=union_ms(checkpoint_spans),
                checkpoint_payload_bytes=sum(c['bytes'] for c in checkpoint),
                accepted_draft_histogram=dict(Counter(a['accepted_drafts'] for a in accepted)))
        output.append(request_out)
    return dict(requests=output, allocations=allocation_entries(text),
                clock=dict(mach_minus_ggml_us=offset, spread_us=spread, widest_anchor_us=max(widths)),
                startup_calls=len(calls)-sum(sum(sum(v.values()) for v in p['graph_calls'].values()) for r in output for p in r['phases'].values()),
                note='CPU setup and GPU elapsed intervals overlap. Outside recorded model GPU is a diagnostic bound, not proof of removable time, GPU utilization, SSD wait or hardware accelerator occupancy. Helper wall includes synchronization; do not sum it with GPU or setup totals.')
