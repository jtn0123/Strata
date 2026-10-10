#!/usr/bin/env python3
"""Load-free recheck of this baseline, archived pins and native receipts."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from baseline_m5_observe import unchanged, summarize, signature
from check_memory import assert_no_model_server, snapshot
from engines import verify_engine, ENGINES
from observe_metrics import parse
from validate_offline import require_pass


def main():
    full = HERE.parent/'20261010-observe-flash-v1'
    gate = require_pass()
    for folder in (HERE, full):
        unchanged(folder, json.loads((folder/'frozen.json').read_text()))
    paths = [HERE/name for name in ('00-control', '01-observer-off', '02-observer-on', '03-control')]
    records = [json.loads((p/'result.json').read_text()) for p in paths]
    result = json.loads((HERE/'result.json').read_text())
    assert result['summary'] == summarize(records)
    # JSON object keys are strings; the parser's accepted-draft Counter uses integers.
    recomputed = json.loads(json.dumps(parse((paths[2]/'native.log').read_text(), 8), allow_nan=False))
    assert records[2]['diagnostics'] == recomputed
    assert all(signature(r) == signature(records[0]) for r in records)
    assert all(r['memory']['guard'] is None and r['memory']['swap_growth_bytes']==0 and
               r['memory']['monitor_healthy'] and r['memory']['child_exited'] and
               r['pressure']['error'] is None for r in records)
    proof = {name:verify_engine(name) for name in ENGINES}
    launcher = 'Start Strata.command'
    previous = subprocess.check_output(['git', '-C', str(ROOT), 'show', 'HEAD:'+launcher])
    assert (ROOT/launcher).read_bytes() == previous
    assert_no_model_server()
    full_result = json.loads((full/'00-control/result.json').read_text())
    assert not full_result['model_process_launched'] and not full_result['cases']
    data = dict(status='passed', time_utc=datetime.now(timezone.utc).isoformat(),
        offline_tests=gate['tests_run'], frozen_source_and_native_and_model_pins_unchanged=True,
        raw_small_summary_and_monitoring_recompute_exactly=True, exact_answers=32,
        measured_answers=24, small_zero_new_swap=True,
        full_status=json.loads((full/'result.json').read_text())['status'],
        full_model_launched=False, engine_receipts=proof,
        ordinary_launcher_sha256=hashlib.sha256(previous).hexdigest(),
        ordinary_launcher_matches_prior_commit=True, current_resources=snapshot(),
        pressure_level=int(subprocess.check_output(['sysctl','-n','kern.memorystatus_vm_pressure_level'],text=True)),
        no_model_server=True, adoption=False, speed_gain_claimed=False,
        new_gpu_math_suite_run=False, runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    output = HERE/'post-run-verification.json'
    if output.exists():
        raise RuntimeError('Post-run verification receipt already exists; preserve it')
    output.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    print(f"Verified {len(proof)} native receipts; {gate['tests_run']} offline tests; archived pins; 32 exact outputs; raw monitoring recomputes; launcher unchanged; no model server.")


if __name__=='__main__':
    main()
