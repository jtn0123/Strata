#!/usr/bin/env python3
"""Independent encoder model brackets, with actual callback/count and reply-drift gates."""
import argparse
import fcntl
import json
import re
from pathlib import Path

from benchmark_m5 import execute
from benchmark_m5_next import finish, wait_for_headroom
from benchmark_m5_encoders import read_record, verify
from engines import ROOT
from validate_offline import require_pass


def validate_startup(text, expected):
    def markers(name):
        records = []
        for line in text.splitlines():
            if name not in line: continue
            match = re.fullmatch(r'(?:[0-9]+\.[0-9]{2}\.[0-9]{3}\.[0-9]{3} I )?'+re.escape(name)+r' (.+)',line)
            if not match: raise ValueError('Malformed or unknown-prefix native marker')
            records.append(json.loads(match.group(1)))
        return records
    init, abort = markers('M5_ENCODER_INIT'), markers('M5_ENCODER_ABORT')
    if len(init) != 2:
        raise ValueError('Expected one target and one helper backend initialization')
    if any(x not in [dict(path=p, requested_n_cb=expected, effective_n_cb=expected, stats=False)
                     for p in ('public', 'device')]
           or type(x['requested_n_cb']) is not int or type(x['effective_n_cb']) is not int
           or x['stats'] is not False for x in init):
        raise ValueError('Wrong actual encoding count or active fusion statistics')
    if any(x != dict(has_abort_callback=False, effective_n_cb=expected)
           or x['has_abort_callback'] is not False or type(x['effective_n_cb']) is not int for x in abort):
        raise ValueError('Encoder experiment requires a null abort callback')
    # The pinned context is calloc-initialized; every subsequent callback assignment
    # emits the unconditional setter marker. No setter events is the normal server path.
    return dict(initializations=len(init), abort_setters=len(abort), effective_n_cb=expected,
                stats=False, has_abort_callback=False,
                initial_callback_proof='Pinned zero-initialized context and instrumented setter; absent events means no installation')



def adoption(summary, candidate):
    winning = []
    for row in summary:
        if row['cached'] or row['workload'] not in ('code', 'prose', 'chinese'):
            continue
        gain, drift = row['vs_control'][candidate], row['control_drift']
        if (gain['generation_increase_percent'] >= 1 and gain['total_time_reduction_percent'] >= 1
                and gain['generation_increase_percent'] > abs(drift['generation_increase_percent'])
                and gain['total_time_reduction_percent'] > abs(drift['total_time_reduction_percent'])):
            winning.append(row['workload'])
    return dict(measured_speed_candidate=len(winning) >= 2, winning_real_workloads=winning,
                rule='At least1% TPS and whole-reply gain on two real workloads, each above its own absolute control drift; exact outputs, null callbacks, effective count, zero new swap.')


def prerequisites():
    checks = json.loads((ROOT/'bench/runtime/m5-encoders/checks.json').read_text())
    if checks['status'] != 'passed' or checks['probe'] != verify() or len(checks['runs']) != 26:
        raise ValueError('Current complete encoder correctness suite required')
    buffers = None
    for path in checks['runs'].values():
        record = read_record(ROOT/path)
        if buffers is None: buffers = record['buffers']
        if record['buffers'] != buffers: raise ValueError('Encoder correctness output bits differ')
    return checks


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--candidate', choices=('encoders0','encoders2'), required=True)
    ap.add_argument('--repeats', type=int, default=3)
    ap.add_argument('--resume', type=Path)
    ap.add_argument('--run', action='store_true')
    args = ap.parse_args()
    if args.repeats < 2: ap.error('At least two repeats required')
    spec = dict(id=args.candidate, engine='m5-encoders', depth=3, axis='m5_tuning',
                control='conv-direct', candidates=[args.candidate], predict=256)
    if not args.run:
        print('Preparation only:', spec); return
    require_pass()
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        proof = prerequisites()
        folder = execute(spec, args.repeats, resume=args.resume, before_pass=wait_for_headroom)
        # Validate the actual target/helper path before labeling the suite accepted.
        startup = []
        record = json.loads((folder/'comparison.json').read_text())
        try:
            for run in record['runs']:
                expected = int(run['value'][-1]) if run['value'].startswith('encoders') else 1
                startup.append(dict(run_id=run['run_id'], **validate_startup(
                    (ROOT/'bench/results'/run['run_id']/'server.log').read_text(), expected)))
            record = finish(folder)
            record['encoder_prerequisites'] = proof
            record['actual_encoder_startup'] = startup
            record['decision'] = adoption(record['summary'], args.candidate)
            (folder/'comparison.json').write_text(json.dumps(record,indent=2)+'\n')
            with (folder/'REPORT.md').open('a') as out:
                out.write('\nEffective count and null callback verified for every target/helper initialization.\n')
                out.write('Stricter acceptance including reply-time drift: '+str(record['decision']['measured_speed_candidate'])+'.\n')
        except BaseException as error:
            record.update(status='failed',error=str(error),actual_encoder_startup=startup)
            (folder/'comparison.json').write_text(json.dumps(record,indent=2)+'\n'); raise
        print('Encoder suite:',folder,record['decision'],flush=True)


if __name__=='__main__': main()
