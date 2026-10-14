"""Numeric local telemetry; never retains prompts, replies, file paths or API keys."""
from collections import deque
import json
import math
from pathlib import Path
import time

import psutil
from lab import ROOT


def number(value, minimum=0):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= minimum else None


def measured_history(record, status, last, kind):
    row = dict(record)
    start, first = number(status.get('started')), number(status.get('first_token'))
    native = last.get('native_timings') or {}
    if not isinstance(native, dict): native = {}
    proposed, accepted = number(native.get('draft_n')), number(native.get('draft_n_accepted'))
    row.update(measurement_kind=kind,
               server_first_token_ms=1000*(first-start) if start is not None and first is not None and first >= start else None,
               server_duration_ms=number(1000*(time.time()-start)) if start is not None else None,
               generation_tps=number(native.get('predicted_per_second')),
               prompt_tps=number(native.get('prompt_per_second')),
               draft_acceptance_percent=100*(accepted/proposed) if proposed and accepted is not None and accepted <= proposed else None)
    if row['generation_tps'] is None:
        row['generation_tps'] = number(record.get('decode_tok_s'))
        row['generation_source'] = 'server-derived' if row['generation_tps'] else 'unreported'
    else:
        row['generation_source'] = 'native' if row['generation_tps'] else 'unreported'
    return row


def guard_sample(path, now=None, runtime_root=None):
    """Read at most 16 KiB from the existing owned guard; no extra pressure subprocess."""
    if not path:
        return None
    root = (runtime_root or ROOT/'bench/runtime').resolve()
    source = Path(path).resolve()
    if not source.is_relative_to(root) or source.name != 'memory.jsonl':
        return None
    try:
        age = (time.time() if now is None else now)-source.stat().st_mtime
        if age < 0 or age > 3:
            return None
        with source.open('rb') as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell()-16384))
            data = stream.read(16384)
        # A writer can be midway through its final line. Use the last complete sample.
        lines = data.split(b'\n')[:-1]
        for line in reversed(lines):
            try:
                sample = json.loads(line)
                if isinstance(sample, dict):
                    return sample
            except (ValueError, UnicodeDecodeError):
                continue
    except OSError:
        pass
    return None


def resources(config):
    vm, swap = psutil.virtual_memory(), psutil.swap_memory()
    sample = guard_sample(config.get('monitor_file')) or {}
    initial = number(config.get('initial_swap_bytes'))
    return dict(available_bytes=vm.available, total_bytes=vm.total, swap_used_bytes=swap.used,
                new_swap_bytes=max(0, swap.used-initial) if initial is not None else None,
                model_rss_bytes=number(sample.get('rss_bytes')),
                pressure_level=sample.get('pressure_level') if sample.get('pressure_level') in (1, 2, 4) else None)


def tracked_service(original, mock_type, config=None):
    config = dict(config or {})
    allowed = ('model', 'engine', 'context', 'cache_type', 'spec', 'draft', 'draft_model', 'lookup_profile', 'tensor_api', 'm5_tuning', 'batch', 'ubatch', 'draft_threads', 'draft_placement', 'draft_p_min')

    class TrackedService(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            service = self

            class History(deque):
                def append(self, row):
                    # The pinned shell calls append while holding status_lock, immediately
                    # after copying engine.last. Preserve its deque and lifecycle semantics.
                    last = dict(getattr(service.engine, 'last', {}) or {})
                    super().append(measured_history(row, service.status, last, service.kind()))

            self.history = History(self.history, maxlen=self.history.maxlen)

        def kind(self):
            return 'mock' if isinstance(self.engine, mock_type) else 'model' if (getattr(self.engine, 'info', {}) or {}).get('backend') == 'metal-native-http' else 'unverified'

        def metrics(self):
            result = super().metrics()
            try: memory = resources(config)
            except (OSError, ValueError, psutil.Error): memory = {}
            result['performance'] = dict(schema=1, measurement_kind=self.kind(),
                settings={key: config[key] for key in allowed if key in config}, resources=memory,
                scope='Server timings start after queue admission; browser and engine timings have different scopes.')
            return result

    return TrackedService
