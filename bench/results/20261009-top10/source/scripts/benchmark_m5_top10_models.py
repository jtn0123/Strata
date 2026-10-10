#!/usr/bin/env python3
"""Matched original-engine control for the exact helper top10 experiment."""
import argparse
import fcntl
import json
from pathlib import Path

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
                      decision=adoption(record['summary'], 'top10'))
        (folder/'comparison.json').write_text(json.dumps(record, indent=2)+'\n')
        with (folder/'REPORT.md').open('a') as report:
            report.write('\nOriginal m5-copy control; eligible variant entry confirmed on candidate launches.\n')
            report.write('Stricter TPS and reply drift acceptance: '+str(record['decision']['measured_speed_candidate'])+'.\n')
        print('Matched model bracket:', folder, record['decision'], flush=True)


if __name__ == '__main__':
    main()
