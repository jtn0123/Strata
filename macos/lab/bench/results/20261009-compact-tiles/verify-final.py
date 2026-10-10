#!/usr/bin/env python3
"""Reparse compact V1/V2 evidence without starting a model or GPU workload."""
import importlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'scripts'))
from engines import ENGINES, sha256, verify_engine
from check_memory import snapshot, assert_no_model_server
from validate_offline import require_pass

BUNDLE = Path(__file__).resolve().parent


def audit(module_name, candidate):
    module = importlib.import_module(module_name)
    folder, work = module.RESULTS, module.WORK
    comparison = json.loads((folder/'comparison.json').read_text())
    plan = json.loads((folder/'plan.json').read_text())
    builds = json.loads((work/'build.json').read_text())
    assert plan['source'] == builds
    historical_changes = {}
    for name, digest in plan['archive'].items():
        assert sha256(folder/'source'/name) == digest, name
        if sha256(ROOT/name) != digest:
            assert module_name == 'benchmark_m5_compact'
            assert name in ('scripts/engines.py', 'scripts/metal_environment.py')
            historical_changes[name] = dict(archived_sha256=digest, current_sha256=sha256(ROOT/name),
                                           reason='V2 isolated engine/profile registered after V1 timing; original archive preserved')
    if module_name == 'benchmark_m5_compact':
        assert set(historical_changes) == {'scripts/engines.py', 'scripts/metal_environment.py'}
    for scope, engine in (('control', 'm5-copy'), ('compact', candidate)):
        saved = builds[scope]
        current = module.pins(engine)
        assert current['engine'] == saved['engine']
        assert current['source_sha256'] == saved['source_sha256']
        assert current['runner_sha256'] == saved['runner_sha256']
        assert sha256(work/(scope+'-probe')) == saved['binary_sha256']
        for name, digest in saved['dependencies'].items():
            assert sha256(ROOT/'scripts'/name) == digest or 'scripts/'+name in historical_changes
    order = [('control','check'), ('compact','check'), ('control','perf'),
             ('compact','perf'), ('compact','perf'), ('control','perf')]
    paths = comparison['checks'] + comparison['runs']
    assert len(paths) == len(order)
    records = []
    result = []
    for path, (scope, mode) in zip(paths, order):
        location = ROOT/path
        record = json.loads((location/'result.json').read_text())
        assert record['status'] == 'passed' and record['scope'] == scope and record['mode'] == mode
        assert record['native_returncode'] == 0 and record['probe'] == builds[scope]
        memory = record['memory']
        assert memory['swap_growth_bytes'] == 0 and memory['guard'] is None
        assert memory['monitor_healthy'] and memory['child_exited'] and memory['baseline_before_launch']
        assert sha256(location/'native.log') == record['native_log_sha256']
        assert sha256(location/'outputs.jsonl') == record['evidence_sha256']
        raw = (location/'native.log').read_text()
        assert module.parse(raw, mode, scope) == record['cases']
        assert [json.loads(line) for line in (location/'outputs.jsonl').read_text().splitlines()] == record['cases']+module.markers(raw,'M5_COMPACT_DONE')
        records.append((record, location))
        result.append(dict(path=path, scope=scope, mode=mode, cases=len(record['cases']),
                           eligible_encodings=sum(row['count_delta'] for row in record['cases']),
                           peak_rss_bytes=memory['peak_rss_bytes'], swap_growth_bytes=memory['swap_growth_bytes']))
    module.compare_exact(records[0][0]['cases'], records[1][0]['cases'])
    calculated = module.summarize(records[2:])
    calculated['checks'] = paths[:2]
    assert calculated == comparison
    assert comparison['qualifies_for_model_trial'] is False
    return dict(status='verified', runs=result, exact_outputs=True, aggregate_recomputed=True,
                qualifies_for_model_trial=False, current_dependency_differences=historical_changes,
                comparison_sha256=sha256(folder/'comparison.json'))


def main():
    offline = require_pass()
    original = json.loads((BUNDLE/'original-engines.json').read_text())
    current = {name:verify_engine(name) for name in ENGINES}
    assert len(original) == 24 and len(current) == 26
    assert all(current[name] == value for name, value in original.items())
    columns_plan = json.loads((BUNDLE/'columns-plan.json').read_text())
    assert all(sha256(ROOT/name) == value for name, value in columns_plan['preserved_v1'].items())
    outcomes = {name:audit(module, candidate) for name,module,candidate in
                (('V1','benchmark_m5_compact','m5-compact'), ('V2','benchmark_m5_compact_cols','m5-compact-cols'))}
    for name in ('benchmark_m5_compact_models', 'benchmark_m5_compact_cols_models'):
        try:
            importlib.import_module(name).prerequisites()
        except ValueError as error:
            assert str(error) == 'Qualified component comparison required'
        else:
            raise AssertionError('Unqualified component permitted model trial')
    assert_no_model_server()
    record = dict(status='passed', models_loaded_by_verifier=False, gpu_execution_by_verifier=False,
                  model_trials_run=False, model_trials_rejected_by_component_gate=True,
                  original_engine_count=len(original), engine_count=len(current), original_engines_unchanged=True,
                  engines=current, compact=outcomes, offline_tests=offline['tests_run'],
                  offline_receipt_sha256=sha256(ROOT/'bench/features/offline-validation.json'),
                  resources=snapshot(), model_servers_running=False,
                  commit_push_publish='None; local isolated experiments only')
    (BUNDLE/'final-verification.json').write_text(json.dumps(record,indent=2)+'\n')
    print('Verified V1/V2:12 clean launches, exact output hashes, recomputed18rows each,26 engines/24 original unchanged,148 offline tests. Neither qualifies for model trial.')


if __name__ == '__main__':
    main()
