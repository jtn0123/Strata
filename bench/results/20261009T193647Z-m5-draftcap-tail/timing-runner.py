#!/usr/bin/env python3
"""Guarded max3-allocation ABBA after independent exact-output qualification."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from benchmark_m5 import execute
from benchmark_m5_next import finish, wait_for_headroom
from benchmark_m5_encoder_models import adoption
from capture import markers, compare
from engines import sha256, verify_engine
from model_provenance import assert_unchanged
from validate_offline import require_pass


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--candidate',choices=['tail','two'],required=True)
    ap.add_argument('--control-record',type=Path,required=True)
    ap.add_argument('--candidate-record',type=Path,required=True)
    args=ap.parse_args()
    expected=('off','tail') if args.candidate=='tail' else ('tail','two')
    records=[json.loads(p.read_text()) for p in (args.control_record,args.candidate_record)]
    if tuple(r['mode'] for r in records)!=expected: raise ValueError('Wrong qualification pair')
    for r in records:
        if r['engine']!=verify_engine('m5-draftcap'): raise ValueError('Qualified engine changed')
        assert_unchanged(r['model_proof'])
    qualification=compare(*records,require_rows=args.candidate=='tail')
    if qualification['status']!='passed': raise ValueError('Exact-output qualification failed')
    # Avoid any inherited diagnostic perturbation. configure() also strips all GGML traces.
    removed={k:os.environ.pop(k) for k in
        ('LLAMA_TRACE','LLAMA_SERVER_SLOTS_DEBUG','LLAMA_SERVER_SLOTS_N_DIFF') if k in os.environ}
    spec=dict(id='draftcap-'+args.candidate,engine='m5-draftcap',depth=3,axis='m5_tuning',
        control='conv-direct' if args.candidate=='tail' else 'draftcap3',
        candidates=['draftcap-tail' if args.candidate=='tail' else 'draftcap2'],predict=256)
    source=sha256(__file__); require_pass()
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        folder=execute(spec,3,before_pass=wait_for_headroom)
        (folder/'timing-runner.py').write_bytes(Path(__file__).read_bytes())
        path=folder/'comparison.json'; r=json.loads(path.read_text())
        try:
            startup=[]; allocations=[]
            for run in r['runs']:
                text=(ROOT/'bench/results'/run['run_id']/'server.log').read_text()
                early=run['value']!='conv-direct'
                if markers(text,'M5_DRAFT_INIT')!=[dict(configured=3,early_stop=early,trace=False)]:
                    raise ValueError('Actual helper configuration or trace selection differs')
                if (any(name in text for name in ('M5_DRAFT_NATIVE','M5_DRAFT_OFFER','M5_DRAFT_VERIFY','M5_DRAFT_TARGET')) or
                    re.search(r'accepted\s+\d+/\s*\d+ draft tokens',text)):
                    raise ValueError('Timing run contains diagnostic native trace')
                result=json.loads((ROOT/'bench/results'/run['run_id']/'result.json').read_text())
                command=result['command']
                for flag,value in (('--spec-draft-n-max','3'),('--spec-draft-n-min','0'),('--spec-draft-sampling','greedy')):
                    if command[command.index(flag)+1]!=value: raise ValueError('MTP scope changed')
                startup.append(dict(run_id=run['run_id'],configured=3,early_stop=early,trace=False))
                lines=[line.split(' I ',1)[-1] for line in text.splitlines()
                    if 'buffer size =' in line or 'RS buffer size' in line]
                allocations.append(dict(run_id=run['run_id'],allocation_lines=lines))
            if any(x['allocation_lines']!=allocations[0]['allocation_lines'] for x in allocations):
                raise ValueError('Actual target/helper allocation changed')
            r=finish(folder); r['decision']=adoption(r['summary'],spec['candidates'][0])
            r['decision']['rule']='At least1% TPS and whole-reply gain on two real workloads, each above its own absolute control drift; exact outputs, same actual allocation and max3, helper greedy/n_min0, diagnostics off, zero new swap.'
            r.update(draftcap_qualification=dict(**qualification,
                records={str(p.relative_to(ROOT)):sha256(p) for p in (args.control_record,args.candidate_record)}),
                actual_mtp_startup=startup,actual_allocations=allocations,
                timing_runner_sha256=source,removed_inherited_diagnostics=sorted(removed),
                finalized_utc=datetime.now(timezone.utc).isoformat())
            if sha256(__file__)!=source: raise ValueError('Timing runner changed')
            require_pass()
            with (folder/'REPORT.md').open('a') as out:
                out.write('\nSame actual target/helper allocation and configured max3; greedy helper and n_min0. All diagnostic traces off.\n')
                out.write('Stricter reply-time drift acceptance: '+str(r['decision']['measured_speed_candidate'])+'.\n')
        except BaseException as error:
            r.update(status='failed',error=f'{type(error).__name__}: {error}'); raise
        finally: path.write_text(json.dumps(r,indent=2)+'\n')
        print('Draftcap timing:',folder,r['decision'],flush=True)


if __name__=='__main__': main()
