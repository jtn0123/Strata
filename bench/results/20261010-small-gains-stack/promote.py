#!/usr/bin/env python3
"""Install only the campaign's qualified profile, retaining the original launcher."""
import json
from pathlib import Path
import shlex
import shutil
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from engines import sha256
from check_memory import assert_no_model_server
from validate_offline import fingerprint, require_pass


def main():
    state=json.loads((HERE/'tracking.json').read_text())
    frozen=json.loads((HERE/'frozen.json').read_text())
    if state['status']!='completed' or not state['promotion_eligible']:
        raise ValueError('Campaign has no safety-qualified winner')
    require_pass(); assert_no_model_server()
    if fingerprint()!=frozen['source_pins']:
        raise ValueError('Validated source closure changed')
    launcher=ROOT/'Start Strata.command'
    if sha256(launcher)!=frozen['original_launcher_sha256']:
        raise ValueError('Original launcher changed; preserve unrelated changes')
    profile=state['winner_profile']
    if profile not in ('small-reduce','small-reduce-top10'):
        raise ValueError('Winner outside the predefined profile choices')
    command=['.venv/bin/python','scripts/run.py','flash','--engine','m5-small-stack',
             '--m5-tuning',profile,'--tensor-api','on','--context','4096','--ubatch','512',
             '--cache-type','f16','--spec','draft-mtp','--draft-model','mtp_shared_packed_q3',
             '--draft','3','--draft-placement','mixed','--draft-threads','8','--draft-p-min','0.0']
    backup=ROOT/'Start Strata - Original Baseline.command'
    if backup.exists(): raise ValueError('Rollback launcher exists; refuse to overwrite')
    shutil.copy2(launcher, backup)
    text='#!/bin/zsh\ncd "${0:A:h}"\n'
    text+='# Explicit CLI arguments retain the original generic launcher behavior, including the small model.\n'
    text+='if (( $# )); then\n  exec .venv/bin/python scripts/run.py "$@"\nfi\n'
    text+='exec '+shlex.join(command)+'\n'
    launcher.write_text(text);launcher.chmod(0o755)
    record=dict(status='installed; application verification pending', profile=profile, features=state['winner'],
                evidence=str((HERE/'tracking.json').relative_to(ROOT)), command=command,
                launcher_sha256=sha256(launcher), rollback_path=str(backup.relative_to(ROOT)),
                rollback_sha256=sha256(backup), source_pins_unchanged=fingerprint()==frozen['source_pins'],
                cli_explicit_arguments_preserved=True, application_server_left_running=False)
    (HERE/'promotion.json').write_text(json.dumps(record,indent=2)+'\n')
    print('Installed qualified profile:',profile,'; rollback:',backup,flush=True)


if __name__=='__main__':main()
