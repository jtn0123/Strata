#!/usr/bin/env python3
"""One user-authorized cache purge, with before/after resource evidence."""
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import re
import subprocess
import time

import psutil

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
OUT = HERE / ('purge-trial-' + STAMP)


def snapshot(phase):
    vm = psutil.virtual_memory()
    raw = subprocess.check_output(['vm_stat'], text=True)
    page_size = int(re.search(r'page size of (\d+) bytes', raw).group(1))
    counts = {}
    for line in raw.splitlines()[1:]:
        match = re.match(r'([^:]+):\s+(\d+)\.', line)
        if match:
            counts[match[1].strip('"')] = int(match[2])
    pressure = int(subprocess.check_output(
        ['sysctl', '-n', 'kern.memorystatus_vm_pressure_level'], text=True).strip())
    return dict(time_utc=datetime.now(timezone.utc).isoformat(), phase=phase,
                available_gib=vm.available / 2**30, free_gib=vm.free / 2**30,
                wired_gib=vm.wired / 2**30, swap_used_bytes=psutil.swap_memory().used,
                pressure_level=pressure, page_size=page_size, vm_counts=counts)


def main():
    OUT.mkdir()
    command = ['osascript', '-e', 'with timeout of 180 seconds', '-e',
               'do shell script "/usr/sbin/purge" with administrator privileges',
               '-e', 'end timeout']
    samples = []
    record = dict(status='prepared', command=command, permission='user authorized cache purge',
                  model_benchmark_launched=False, samples=samples)
    def save():
        (OUT / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
    def capture(phase):
        sample = snapshot(phase)
        samples.append(sample)
        save()
        return sample
    print('Evidence:', OUT, flush=True)
    with (ROOT / 'bench/.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = capture('before')
        record['before'] = before
        record['status'] = 'awaiting macOS authentication / purge completion'
        save()
        print(f"Before: available={before['available_gib']:.3f} GiB; "
              f"swap={before['swap_used_bytes']} bytes; pressure={before['pressure_level']}", flush=True)
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        while proc.poll() is None:
            capture('authentication-or-purge')
            time.sleep(2)
        stdout, stderr = proc.communicate()
        record.update(purge_returncode=proc.returncode, purge_stdout=stdout, purge_stderr=stderr)
        immediate = capture('immediate-after')
        record['immediate_after'] = immediate
        print(f"Purge return={proc.returncode}; available={immediate['available_gib']:.3f} GiB; "
              f"swap={immediate['swap_used_bytes']} bytes", flush=True)
        if proc.returncode:
            record['status'] = 'purge not confirmed; no benchmark launched'
            save()
            print(stderr.strip(), flush=True)
            return
        record['status'] = 'purge completed; measuring 60-second quiet settle'
        save()
        for index in range(30):
            time.sleep(2)
            current = capture('quiet-settle')
            if index % 5 == 4:
                print(f"Settle {(index+1)*2}s: available={current['available_gib']:.3f} GiB; "
                      f"swap={current['swap_used_bytes']} bytes", flush=True)
        settled = [s for s in samples if s['phase'] == 'quiet-settle']
        growth = max(0, max(s['swap_used_bytes'] for s in samples) - before['swap_used_bytes'])
        eligible = (min(s['available_gib'] for s in settled) >= 34
                    and all(s['pressure_level'] == 1 for s in settled) and growth == 0)
        record.update(status='measured; eligible for canonical preflight' if eligible else
                      'measured; existing benchmark gate not met', after=settled[-1],
                      available_gain_gib=settled[-1]['available_gib']-before['available_gib'],
                      settled_min_available_gib=min(s['available_gib'] for s in settled),
                      settled_max_available_gib=max(s['available_gib'] for s in settled),
                      swap_growth_bytes=growth, eligible_for_canonical_preflight=eligible,
                      gate='all settle samples >=34 GiB, pressure normal, zero new swap',
                      source_sha256=__import__('hashlib').sha256(Path(__file__).read_bytes()).hexdigest())
        save()
        print(json.dumps({k:record[k] for k in ['status','available_gain_gib',
              'settled_min_available_gib','settled_max_available_gib','swap_growth_bytes',
              'eligible_for_canonical_preflight']}, indent=2), flush=True)


if __name__ == '__main__':
    main()
