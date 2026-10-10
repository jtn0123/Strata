"""Read-only raw verification plus canonical report adjudication; no model runs."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'scripts'))
from benchmark_m5 import compare
from benchmark_m5_next import output_signatures
from benchmark_m5_top10_models import dispatch, model_adoption, render_report
from engines import sha256, verify_engine

HERE = Path(__file__).resolve().parent
FOLDER = ROOT/'bench/results/20261009T205909Z-m5-parallel-top10'


def warmup_signatures(record):
    out = {}
    for case in record['warmups']:
        key = ('fresh', case['workload'], case['prompt_sha256'], case['repeat'])
        if key in out:
            raise ValueError('Duplicate warmup')
        out[key] = (case['response']['generated_token_ids'], case['response']['text'])
    for case in record['cached_cases']:
        if not case['warmup']:
            continue
        key = ('cache', case['history_budget'], case['prompt_sha256'], case['repeat'])
        if key in out:
            raise ValueError('Duplicate cache warmup')
        out[key] = (case['token_ids'], case['text'])
    if len(out) != 6:
        raise ValueError('Missing warmup evidence')
    return out


def main():
    saved = FOLDER/'comparison-post-run-original.json'
    if not saved.exists():
        saved.write_bytes((FOLDER/'comparison.json').read_bytes())
        (FOLDER/'REPORT-post-run-original.md').write_bytes((FOLDER/'REPORT.md').read_bytes())
    record = json.loads(saved.read_text())
    if record['status'] != 'passed' or len(record['runs']) != 4:
        raise ValueError('Completed model ABBA required')
    plan = json.loads((HERE/'model-plan.json').read_text())
    supplemental = json.loads((HERE/'supplemental-provenance.json').read_text())
    archived = {**plan['sources'], **supplemental['files']}
    for path, expected in archived.items():
        if sha256(HERE/'source'/path) != expected:
            raise ValueError('Archived source digest mismatch: '+path)
    runs = [json.loads((ROOT/'bench/results'/r['run_id']/'result.json').read_text()) for r in record['runs']]
    summary = compare(runs, record['experiment'], 3)
    if summary != record['summary']:
        raise ValueError('Recomputed metrics changed')
    reference, warmups = output_signatures(runs[0]), warmup_signatures(runs[0])
    receipts = []
    for entry, run in zip(record['runs'], runs):
        if run['selected_engine'] != verify_engine(run['settings']['engine']):
            raise ValueError('Native receipt changed')
        if output_signatures(run) != reference or warmup_signatures(run) != warmups:
            raise ValueError('Measured or warmup outputs changed')
        if run['memory']['swap_growth_bytes'] or run['memory']['guard']:
            raise ValueError('Swap or monitor guard')
        receipt = dispatch((ROOT/'bench/results'/run['run_id']/'server.log').read_text(), entry['value'] == 'top10')
        receipts.append(dict(run_id=run['run_id'], **receipt))
    record.update(decision=model_adoption(summary), selector_dispatch=receipts,
                  warmup_output_parity=dict(passed=True, cases_per_run=len(warmups), runs=4),
                  final_adjudication=dict(timed_rerun=False, original_comparison_sha256=sha256(saved),
                    reason='Canonical strict verdict and experiment-specific rule; raw metrics and timings unchanged.',
                    reanalysis_source_sha256=sha256(__file__)))
    (FOLDER/'comparison.json').write_text(json.dumps(record, indent=2)+'\n')
    (FOLDER/'REPORT.md').write_text(render_report(record))
    verification = dict(status='passed', fresh_cache_output_comparisons=len(reference)*4,
                        warmup_output_comparisons=len(warmups)*4,
                        checks=sum(len(r['checks']) for r in runs), zero_new_swap=True,
                        peak_rss_bytes=max(r['memory']['peak_rss_bytes'] for r in runs),
                        minimum_available_bytes=min(r['memory']['minimum_available_bytes'] for r in runs),
                        original_saved_comparison_sha256=sha256(saved), final_comparison_sha256=sha256(FOLDER/'comparison.json'),
                        report_sha256=sha256(FOLDER/'REPORT.md'),
                        dependency_hashes={path:sha256(ROOT/path) for path in archived},
                        strict_report_renderer_sha256=sha256(ROOT/'scripts/benchmark_m5_top10_models.py'),
                        decision=record['decision'])
    (HERE/'model-final-verification.json').write_text(json.dumps(verification, indent=2)+'\n')
    print(json.dumps(verification, indent=2))


if __name__ == '__main__':
    main()
