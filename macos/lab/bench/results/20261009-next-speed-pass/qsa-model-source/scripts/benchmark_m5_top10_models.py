#!/usr/bin/env python3
"""Matched original-engine control for the exact helper top10 experiment."""
import argparse
import fcntl
import json

from benchmark_m5 import execute
from benchmark_m5_next import finish, output_signatures, wait_for_headroom
from benchmark_m5_encoder_models import adoption
from benchmark_m5_top10 import RESULTS, comparable, pins, summarize
from engines import ROOT, sha256
from validate_offline import require_pass


def prerequisites():
    comparison = json.loads((RESULTS/'comparison.json').read_text())
    if not comparison['qualifies_for_model_trial']:
        raise ValueError('Exact component must qualify before model launch')
    current = pins()
    rows = []
    for path in comparison['checks'] + comparison['runs']:
        record = json.loads((ROOT/path/'result.json').read_text())
        if record['status'] != 'passed' or any(record['probe'][k] != v for k, v in current.items()):
            raise ValueError('Component evidence stale or incomplete')
        if (sha256(ROOT/path/'native.log') != record['native_log_sha256'] or
                sha256(ROOT/path/'outputs.jsonl') != record['outputs_sha256'] or
                record['memory']['swap_growth_bytes']):
            raise ValueError('Component raw evidence changed')
        rows.append(record)
    if len(rows) != 6 or [comparable(x) for x in rows[0]['fixtures']] != [comparable(x) for x in rows[1]['fixtures']]:
        raise ValueError('Complete exactness bracket required')
    if not summarize(rows[2:])['qualifies_for_model_trial']:
        raise ValueError('Recomputed component screen failed')
    return comparison


def dispatch(text, candidate):
    lines = [line.split('M5_TOP10_DISPATCH ', 1)[1] for line in text.splitlines() if 'M5_TOP10_DISPATCH ' in line]
    expected = dict(ncols=248320, rows=1, k=10, device='M5 Pro', fallback='ties-exceptional-subnormal')
    if lines != ([json.dumps(expected, separators=(',', ':'))] if candidate else []):
        raise ValueError('Normal-path selector entry marker missing or unexpected')
    return dict(eligible_variant_entered=candidate, all_invocations_fast_proven=False)


def model_adoption(summary):
    decision = adoption(summary, 'top10')
    decision['rule'] = 'At least1% TPS and whole-reply gain on both English code/prose, each above its own absolute control drift; exact tested outputs and zero new swap.'
    return decision


def render_report(record):
    lines = ['# Exact parallel top10: matched model result', '',
             'Original m5-copy/conv-direct control versus isolated m5-top10/top10. Qwen3.8-Flash-Next Q2_0, packed shared Q3 helper, mixed placement, eight helper workers, depth3/confidence0, Tensor API on, F16/4K/batch512.', '',
             'Fresh ABBA,256 output tokens, excluded warmup plus three measured repetitions. Historical results are not pooled.', '',
             '| Workload / input | Control TPS | Candidate TPS | TPS gain | Reply quicker | TPS control drift | Reply control drift |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for row in record['summary']:
        a, b = row['profiles']['conv-direct'], row['profiles']['top10']
        delta, drift = row['vs_control']['top10'], row['control_drift']
        lines.append(f"| {row['workload']}/{row['input_budget']} | {a['generation_tok_s']:.3f} | {b['generation_tok_s']:.3f} | {delta['generation_increase_percent']:+.3f}% | {delta['total_time_reduction_percent']:+.3f}% | {drift['generation_increase_percent']:+.3f}% | {drift['total_time_reduction_percent']:+.3f}% |")
    decision = record['decision']
    lines += ['', 'Strict speed acceptance: '+str(decision['measured_speed_candidate'])+'. '+decision['rule'],
              'Only measured fresh English code/prose determine adoption. Cached replies and synthetic tasks are reported separately.', '',
              'Eligible variant entry confirmed on both candidate launches. This marker does not prove fast-branch frequency. Exact fresh/cache tokens and text match; accepted launches have zero new swap allocation, with existing system swap accounted separately.', '']
    for row in record['summary']:
        if row['workload'] in ('code', 'prose'):
            a, b = row['profiles']['conv-direct'], row['profiles']['top10']
            lines.append(f"{row['workload']} reply: {a['wall_s']:.6f} -> {b['wall_s']:.6f}s.")
    lines += ['', '| Fresh workload / input | First-token change | Prompt TPS change |',
              '| --- | ---: | ---: |']
    for row in record['summary']:
        if not row['cached']:
            delta = row['vs_control']['top10']
            lines.append(f"| {row['workload']}/{row['input_budget']} | {delta['ttft_reduction_percent']:+.3f}% quicker | {delta['prompt_increase_percent']:+.3f}% |")
    lines += ['', 'Default launchers remain unchanged.', '',
              '[Raw comparison](comparison.json). Development, component results and the excluded cold load are recorded in [the experiment report](../20261009-top10/REPORT.md).']
    return '\n'.join(lines)+'\n'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run', action='store_true')
    args = ap.parse_args()
    spec = dict(id='parallel-top10', engine='m5-top10', depth=3, axis='m5_tuning',
                control='conv-direct', candidates=['top10'], predict=256,
                engine_for_value={'conv-direct':'m5-copy', 'top10':'m5-top10'})
    if not args.run:
        print('Prepared matched English model bracket:', spec)
        return
    require_pass()
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        proof = prerequisites()
        reference = None
        receipts = []
        def check_pass(record, value):
            nonlocal reference
            signatures = output_signatures(record)
            if reference is None:
                reference = signatures
            if signatures != reference:
                raise ValueError('Fresh/cache output differs from original m5-copy control')
            receipt = dispatch((ROOT/'bench/results'/record['run_id']/'server.log').read_text(), value == 'top10')
            receipts.append(dict(run_id=record['run_id'], **receipt))
        folder = execute(spec, 3, before_pass=wait_for_headroom, after_pass=check_pass)
        record = finish(folder)
        record.update(component_prerequisites=proof, selector_dispatch=receipts,
                      decision=model_adoption(record['summary']))
        (folder/'comparison.json').write_text(json.dumps(record, indent=2)+'\n')
        (folder/'REPORT.md').write_text(render_report(record))
        print('Matched model bracket:', folder, record['decision'], flush=True)


if __name__ == '__main__':
    main()
