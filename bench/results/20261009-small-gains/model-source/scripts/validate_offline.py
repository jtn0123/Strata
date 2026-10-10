#!/usr/bin/env python3
"""Run the maintained load-free test inventory; deny sockets and native subprocesses."""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch
import urllib.request

from lab import ROOT

INVENTORY = ROOT / 'config/offline_tests.json'
RECEIPT = ROOT / 'bench/features/offline-validation.json'
_POPEN = subprocess.Popen


def inventory(root=ROOT):
    spec = json.loads((root / 'config/offline_tests.json').read_text())
    listed = spec['included'] + list(spec['excluded'])
    actual = {p.name for p in (root / 'tests').glob('test_*.py')}
    if len(listed) != len(set(listed)) or set(listed) != actual:
        raise RuntimeError(f'Unclassified/missing/duplicate tests: {sorted(actual ^ set(listed))}')
    if not all(spec['excluded'].values()): raise RuntimeError('Excluded tests need a reason')
    return spec


def fingerprint(root=ROOT):
    paths = sorted([*(root / 'scripts').glob('*.py'), *(root / 'tests').glob('test_*.py'),
                    *(root / 'config').glob('*.json')])
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def require_pass(root=ROOT):
    inventory(root)
    receipt = json.loads((root / 'bench/features/offline-validation.json').read_text())
    if receipt.get('status') != 'passed' or receipt.get('sources') != fingerprint(root):
        raise RuntimeError('Offline validation is missing, failed or stale; run scripts/validate_offline.py first')
    return receipt


def deny(*args, **kwargs):
    raise RuntimeError('Offline gate forbids network, sockets and native execution')


def git_fixture_only(command, *args, **kwargs):
    # The existing source-provenance tests initialize and inspect temporary Git fixtures.
    if not isinstance(command, (list, tuple)) or not command or Path(str(command[0])).name != 'git' or kwargs.get('shell'):
        return deny()
    tail = list(map(str, command[1:]))
    while tail and tail[0] in ('-C', '-c'):
        tail = tail[2:]
    if not tail or tail[0] not in ('init', 'add', 'commit', 'diff', 'status', 'rev-parse'):
        return deny()
    env = dict(__import__('os').environ, **kwargs.pop('env', {}))
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_TERMINAL_PROMPT='0')
    return _POPEN(command, *args, env=env, **kwargs)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--log', type=Path, default=ROOT / 'bench/features/offline-validation.log')
    args = ap.parse_args(argv)
    spec = inventory()
    sys.path.insert(0, str(ROOT / 'tests'))
    args.log.parent.mkdir(parents=True, exist_ok=True)
    sources = fingerprint()
    record = {'schema': 1, 'status': 'failed', 'sources': sources, 'inventory': spec,
              'time_utc': datetime.now(timezone.utc).isoformat(), 'log': str(args.log),
              'models_loaded': False, 'gpu_tests_run': False, 'builds_run': False,
              'native_cpu_self_tests_run': False, 'real_sockets_opened': False,
              'allowed_subprocesses': 'Local temporary Git provenance fixtures only'}
    try:
        with ExitStack() as stack, args.log.open('w') as stream:
            stack.enter_context(patch.object(socket, 'socket', deny))
            stack.enter_context(patch.object(urllib.request, 'urlopen', deny))
            stack.enter_context(patch.object(subprocess, 'Popen', git_fixture_only))
            suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(Path(p).stem) for p in spec['included'])
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
            record.update(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                          status='passed' if result.wasSuccessful() else 'failed')
        if fingerprint() != sources:
            record.update(status='failed', error='Gate sources changed during validation')
    except BaseException as error:
        record['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        RECEIPT.parent.mkdir(parents=True, exist_ok=True)
        RECEIPT.write_text(json.dumps(record, indent=2, allow_nan=False) + '\n')
    print(f"Offline gate: {record['status']}; {record['tests_run']} tests. Log: {args.log}")
    if record['status'] != 'passed': raise SystemExit(1)


if __name__ == '__main__': main()
