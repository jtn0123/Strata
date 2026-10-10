"""Audit-only pure/mocked probes. Never call a model, backend, socket or native tool."""
import copy
import hashlib
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
from unittest.mock import patch
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import benchmark_m5 as m5
import benchmark_context as context
import benchmark_metrics as bm
import benchmark_cache
import profile_m5_routes as routes
import memory_budget
import verify_q2
import benchmark_m5_decision_baseline as baseline
from test_m5_preparation import M5Tests
from test_context_preparation import ContextTests

results = []
def probe(name, callback):
    try:
        value = callback()
        result = {'name': name, 'accepted': True, 'detail': value}
    except Exception as error:
        result = {'name': name, 'accepted': False, 'detail': f'{type(error).__name__}: {error}'}
    results.append(result)

def fresh_m5():
    records, spec = M5Tests().records()
    # Complete expected fresh workload set, retaining the test's other mocked evidence.
    for record in records:
        template = record['cases'][0]
        for name, count in [('code', 48), ('prose', 53), ('chinese', 56)]:
            record['cases'].append(dict(copy.deepcopy(template), workload=name,
                                        prompt_tokens=count, prompt_sha256=name))
    return records, spec

def compare_mutation(mutate, use_context=False):
    if use_context:
        records = ContextTests().records()
        mutate(records)
        rows = context.compare(records, 1)
    else:
        records, spec = fresh_m5()
        mutate(records)
        rows = m5.compare(records, spec, 1)
    return {'summary_rows': len(rows)}

def remove_real(records):
    for record in records:
        record['cases'] = [case for case in record['cases'] if case['workload'] == 'synthetic']

def remove_2048(records):
    for record in records:
        record['cases'] = [case for case in record['cases'] if case['prompt_tokens'] != 2048]

def bad_counters(records):
    for record in records:
        for case in record['cached_cases']:
            case['native_timings'].update(prompt_n=513, cache_n=-1, predicted_n=0)
            case.update(prompt_tokens=512, token_ids=[])
        for case in record['cases']:
            case['response']['final']['timings'].update(prompt_n=-10, predicted_n=0)

def no_quiet(records):
    for record in records:
        record.pop('launch_preflight', None)
        record['resource_samples'] = [{'unrelated_cpu_percent': 1200}]

def truthful_string(records):
    records[1]['checks'] = [{'passed': 'false'}]

def uneven_repeats():
    records, spec = fresh_m5()
    for index, record in enumerate(records):
        record['settings'] = vars(m5.settings(spec, m5.plan(spec)[index], str(index), 2))
        # Both candidate launches have each workload but 1 and 3 samples, not 2 each.
        count = 1 if index == 1 else 3 if index == 2 else 2
        for key in ('cases', 'cached_cases'):
            record[key] = [dict(copy.deepcopy(case), repeat=1) for case in record[key] for _ in range(count)]
    return {'summary_rows': len(m5.compare(records, spec, 2)), 'candidate_samples_per_workload': [1, 3]}

def drift():
    records, spec = fresh_m5()
    for case in records[-1]['cases']:
        case['generation_tok_s'] *= 10
    rows = m5.compare(records, spec, 1)
    return {'accepted_control_drift_percent': rows[0]['control_drift']['generation_increase_percent']}

def bad_cache_measure():
    class Engine:
        last = {'native_timings': {'prompt_n': 513, 'cache_n': -1, 'predicted_n': 0}}
        def generate(self, *args):
            yield 7
    class Tokenizer:
        def decode(self, tokens): return 'one token'
    measured = benchmark_cache.measure(Engine(), Tokenizer(), [1] * 512)
    return measured['native_timings']

def stale_preflight():
    # Headroom changes during the 3-second CPU sampling window, before launch baseline.
    stale = {'memory': {'available': 40 * 1024**3}}
    with patch.object(routes, 'assert_no_model_server'), patch.object(routes, 'snapshot', return_value=stale), \
         patch.object(routes.subprocess, 'check_output', return_value='1'), \
         patch.object(routes.psutil, 'cpu_percent', return_value=0), \
         patch.object(routes.psutil, 'virtual_memory', return_value=type('VM', (), {'available': 10*1024**3})()) as live:
        record = routes.preflight()
    return {'accepted_available_gib': record['memory']['available']/1024**3,
            'live_available_gib': 10, 'live_headroom_reads': live.call_count}

def filter_cases():
    source = (ROOT/'vendor/llama-m5-correctness/tests/test-backend-ops.cpp').read_text()
    block = source[source.index('// few src1 rows (speculative verify)'):]
    generated = [int(x.strip()) for x in re.search(r'for \(int64_t n : \{([^}]+)\}', block).group(1).split(',')]
    pattern = r'n=(1|2|3|4|5|8|32),.*mode=mm2\+mm'
    selected = [n for n in generated if re.search(pattern, f'type_a=q4_0,m=1000,n={n},k=1024,mode=mm2+mm')]
    return {'generated_rows': generated, 'selected_rows': selected,
            'selected_cases': len(selected)*4, 'available_cases': len(generated)*4,
            'unmatched_requested_rows': sorted({1,2,3,4,5,8,32}-set(generated))}

def saved_memory_accounting():
    log = (ROOT/'bench/results/20261007T052606Z-m5-decision-baseline-1/server.log').read_text()
    observed = memory_budget.allocations(log)
    kv = [entry for entry in observed['entries'] if entry['kind'] == 'KV']
    actual_mib = [float(size) for size in re.findall(r'MTL0 KV buffer size\s*=\s*([0-9.]+) MiB', log)]
    parsed = sum(entry['bytes'] for entry in kv)
    return {'distinct_KV_allocations_MiB': actual_mib, 'retained_KV_MiB': parsed/1024**2,
            'missing_bytes': round(sum(actual_mib)*1024**2)-parsed,
            'private_total_current_MiB': observed['known_private_buffer_bytes']/1024**2}

def skipped_correctness_cases():
    class Completed:
        pid = 999999
        returncode = 0
        def poll(self): return 0
        def wait(self): return 0
    def fake_popen(*args, **kwargs):
        kwargs['stdout'].write('1/1 tests passed\n')
        kwargs['stdout'].flush()
        return Completed()
    folder = Path(__file__).parent
    with patch.object(verify_q2.subprocess, 'Popen', fake_popen), \
         patch.object(verify_q2.psutil, 'Process'), \
         patch.object(verify_q2.psutil, 'swap_memory', return_value=type('Swap', (), {'used': 0})()):
        result = verify_q2.check_case(Path('NEVER_EXECUTED'), folder, 'mock-coverage',
                                    r'n=(1|2|3|4|5|8|32),.*mode=mm2\+mm', operations='MUL_MAT_ADD')
    return {'passed': result['passed'], 'accepted_counts': result['counts'], 'selected_expected_cases': 16}

def baseline_missing_checks():
    args = baseline.settings(baseline.SPEC, 'mtp-mma', 'audit', 2)
    record = {'status': 'passed', 'settings': vars(args), 'selected_engine': {},
              'memory': {'guard': None, 'swap_growth_bytes': 0}}
    return {'rejection_reasons': baseline.acceptance_errors(record, args, {})}

def baseline_cleanup_receipt():
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
        root = Path(tmp)
        (root/'bench/features').mkdir(parents=True)
        with patch.object(baseline, 'ROOT', root), patch.object(baseline, 'verify_engine', return_value={}), \
             patch.object(baseline, 'snapshot', return_value={}), patch.object(baseline.threading, 'Thread'), \
             patch.object(baseline, 'assert_no_model_server', side_effect=[None, RuntimeError('postflight failure')]), \
             patch.object(baseline, 'run', side_effect=ValueError('primary launch failure')):
            try:
                baseline.execute()
            except Exception as error:
                return {'raised': str(error), 'original_error_preserved_as_cause': isinstance(error.__context__, ValueError),
                        'saved_batch_receipts': len(list(root.glob('bench/features/*/baseline.json')))}

def historical_baselines():
    from collections import Counter
    rows = []
    for stamp, suffix in [('20261007T052606Z', 1), ('20261007T052745Z', 2)]:
        path = ROOT/f'bench/results/{stamp}-m5-decision-baseline-{suffix}/result.json'
        record = json.loads(path.read_text())
        cases = record['cases']
        rows.append({'path': str(path.relative_to(ROOT)),
                     'workload_counts': {str(k): v for k, v in Counter((c['workload'], c['prompt_tokens']) for c in cases).items()},
                     'counter_mismatches': sum(c['response']['final']['timings']['prompt_n'] != c['prompt_tokens'] or
                                               c['response']['final']['timings']['predicted_n'] != c['output_tokens'] for c in cases),
                     'cached_measured': sum(not c['warmup'] for c in record['cached_cases']),
                     'cached_nonpositive_cache_counts': sum(c['native_timings']['cache_n'] <= 0 for c in record['cached_cases'] if not c['warmup']),
                     'quality_checks': len(record['checks']), 'all_quality_passed': all(c['passed'] for c in record['checks']),
                     'new_swap_bytes': record['memory']['swap_growth_bytes']})
    return rows

def denied(*args, **kwargs):
    raise AssertionError('AUDIT attempted forbidden native/network/socket operation')

with patch.object(subprocess, 'Popen', denied), patch.object(socket, 'socket', denied), \
     patch.object(urllib.request, 'urlopen', denied):
    probe('m5_complete_synthetic_record_control', lambda: compare_mutation(lambda records: None))
    probe('m5_omits_all_real_workloads', lambda: compare_mutation(remove_real))
    probe('m5_omits_2048_in_every_launch', lambda: compare_mutation(remove_2048))
    probe('context_omits_2048_in_every_launch', lambda: compare_mutation(remove_2048, True))
    probe('m5_invalid_native_counters', lambda: compare_mutation(bad_counters))
    probe('context_invalid_native_counters', lambda: compare_mutation(bad_counters, True))
    probe('m5_nonboolean_quality_pass', lambda: compare_mutation(truthful_string))
    probe('m5_no_preflight_and_explicit_contention', lambda: compare_mutation(no_quiet))
    probe('context_no_preflight_and_explicit_contention', lambda: compare_mutation(no_quiet, True))
    probe('m5_uneven_and_duplicate_repeats', uneven_repeats)
    probe('m5_extreme_control_drift', drift)
    probe('live_cache_measure_accepts_negative_cache_count', bad_cache_measure)
    probe('preflight_headroom_can_age_during_cpu_window', stale_preflight)
    probe('correctness_filter_inventory', filter_cases)
    probe('saved_memory_KV_accounting', saved_memory_accounting)
    probe('correctness_accepts_1_of_16_cases', skipped_correctness_cases)
    probe('baseline_missing_monitor_quality_cases', baseline_missing_checks)
    probe('baseline_cleanup_loses_receipt', baseline_cleanup_receipt)
    probe('historical_baseline_record_crosscheck', historical_baselines)
    probe('positive_NaN_rejected', lambda: bm.positive(float('nan'), 'audit'))
    probe('positive_bool_rejected', lambda: bm.positive(True, 'audit'))
    probe('draft_negative_counter_rejected', lambda: bm.counter(-1, 'audit'))

report = {'scope': 'pure/mocked; no model, backend, native executable, real socket, payload read or offline receipt rewrite',
          'probes': results, 'original_report_sha256': hashlib.sha256((ROOT/'.Codex/grade-report.md').read_bytes()).hexdigest()}
(Path(__file__).parent/'validation.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
print(json.dumps(report, indent=2, allow_nan=False))
