#!/usr/bin/env python3
"""Recover a complete tail suite rejected only while formatting relative report paths."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
from benchmark_m5 import compare as compare_speed
from benchmark_m5_next import finish
from benchmark_m5_encoder_models import adoption
from capture import markers,compare
from engines import sha256,verify_engine
from model_provenance import assert_unchanged
from validate_offline import require_pass


def main():
    folder=(ROOT/'bench/results/20261009T193647Z-m5-draftcap-tail')
    original=folder/'comparison-postcheck-original.json'; before=json.loads(original.read_text())
    if (before['status']!='failed' or not before.get('error','').startswith("ValueError: 'bench/features/")
        or 'is not in the subpath' not in before['error']):
        raise ValueError('Only known report-path formatting failure can be recovered')
    source=sha256(__file__); pin=verify_engine('m5-draftcap'); require_pass()
    paths=[ROOT/p for p in (
        'bench/features/20261009T193100376954Z-m5-draftcap-qualification/off/reanalysis.json',
        'bench/features/20261009T193412937896Z-m5-draftcap-qualification/tail/capture.json')]
    records=[json.loads(p.read_text()) for p in paths]
    for r in records:
        if r['engine']!=pin: raise ValueError('Qualified engine changed')
        assert_unchanged(r['model_proof'])
    qualification=compare(*records,require_rows=True)
    if qualification['status']!='passed': raise ValueError('Qualification failed')
    runs=[json.loads((ROOT/'bench/results'/entry['run_id']/'result.json').read_text()) for entry in before['runs']]
    if len(runs)!=4 or any(r['selected_engine']!=pin for r in runs): raise ValueError('Timed engine differs')
    summary=compare_speed(runs,before['experiment'],before['repeats'])
    if summary!=before['summary']: raise ValueError('Recomputed timed summary differs')
    startup=[];allocations=[]
    for run,result in zip(before['runs'],runs):
        text=(ROOT/'bench/results'/run['run_id']/'server.log').read_text(); early=run['value']!='conv-direct'
        if markers(text,'M5_DRAFT_INIT')!=[dict(configured=3,early_stop=early,trace=False)]: raise ValueError('Actual selection differs')
        if (any(n in text for n in ('M5_DRAFT_NATIVE','M5_DRAFT_OFFER','M5_DRAFT_VERIFY','M5_DRAFT_TARGET')) or
            re.search(r'accepted\s+\d+/\s*\d+ draft tokens',text)): raise ValueError('Active diagnostic traces')
        command=result['command']
        for flag,value in (('--spec-draft-n-max','3'),('--spec-draft-n-min','0'),('--spec-draft-sampling','greedy')):
            if command.count(flag)!=1 or command[command.index(flag)+1]!=value: raise ValueError('MTP scope changed')
        startup.append(dict(run_id=run['run_id'],configured=3,early_stop=early,trace=False))
        lines=[s.split(' I ',1)[-1] for s in text.splitlines() if 'buffer size =' in s or 'RS buffer size' in s]
        if not lines: raise ValueError('No actual allocation proof')
        allocations.append(dict(run_id=run['run_id'],allocation_lines=lines))
    if any(x['allocation_lines']!=allocations[0]['allocation_lines'] for x in allocations): raise ValueError('Allocation changed')
    for path in before['math_checks']:
        r=json.loads((ROOT/path).read_text())
        if r['status']!='passed' or r['engine']!=pin: raise ValueError('Math prerequisites changed')
    repaired=dict(before,status='passed',original_error=before['error']); repaired.pop('error')
    path=folder/'comparison.json'; path.write_text(json.dumps(repaired,indent=2)+'\n')
    r=finish(folder); r['decision']=adoption(r['summary'],'draftcap-tail')
    r['decision']['rule']='At least1% TPS and whole-reply gain on two real workloads, each above its own absolute control drift; exact outputs, same actual allocation and max3, helper greedy/n_min0, diagnostics off, zero new swap.'
    r.update(draftcap_qualification=dict(**qualification,records={str(p.relative_to(ROOT)):sha256(p) for p in paths}),
        actual_mtp_startup=startup,actual_allocations=allocations,
        timing_runner_sha256=sha256(folder/'timing-runner.py'),
        reanalysis=dict(original_record_sha256=sha256(original),analyzer_sha256=source,
            raw_runs={x['run_id']:sha256(ROOT/'bench/results'/x['run_id']/'result.json') for x in before['runs']},
            performance_rerun=False,reason='Relative report-path formatting only; outputs/math/actual allocation/traces/memory/provenance reverified'),
        finalized_utc=datetime.now(timezone.utc).isoformat())
    if verify_engine('m5-draftcap')!=pin or sha256(__file__)!=source: raise ValueError('Reanalysis provenance changed')
    for record in records: assert_unchanged(record['model_proof'])
    require_pass(); path.write_text(json.dumps(r,indent=2)+'\n')
    (folder/'reanalysis-runner.py').write_bytes(Path(__file__).read_bytes())
    with (folder/'REPORT.md').open('a') as out:
        out.write('\nSame actual allocation/max3 and no diagnostic trace; report-path correction analyzes unchanged saved runs. Original rejection retained.\n')
    print(r['status'],r['decision'],flush=True)


if __name__=='__main__': main()
