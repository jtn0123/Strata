"""Optional owned, rootless macmon sampling for inference investigations."""
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import threading
import time

import psutil
from benchmark_signals import defer_termination


def number(value, low=0, high=float('inf')):
    return value if type(value) in (int, float) and math.isfinite(value) and low <= value <= high else None


def tool_pin():
    name = shutil.which('macmon')
    if not name: raise RuntimeError('Hardware investigation needs the installed macmon tool')
    path = Path(name).resolve()
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                version=subprocess.check_output([name, '--version'], text=True, timeout=5).strip())


def thermal_reader():
    # Public NSProcessInfo.thermalState through Objective-C; no private thermal selector.
    ctypes.CDLL('/System/Library/Frameworks/Foundation.framework/Foundation')
    objc = ctypes.CDLL('/usr/lib/libobjc.A.dylib')
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    send_pointer = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(('objc_msgSend', objc))
    send_integer = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p)(('objc_msgSend', objc))
    cls = objc.objc_getClass(b'NSProcessInfo')
    if not cls: raise RuntimeError('NSProcessInfo unavailable')
    obj = send_pointer(cls, objc.sel_registerName(b'processInfo'))
    if not obj: raise RuntimeError('NSProcessInfo singleton unavailable')
    selector = objc.sel_registerName(b'thermalState')
    return lambda: number(send_integer(obj, selector), high=3)


def normalize(raw, stamp, thermal=None):
    temp = raw.get('temp') if isinstance(raw.get('temp'), dict) else {}
    return dict(monotonic_s=stamp, sample_window_s=1, source='macmon',
                gpu_freq_mhz=number(raw.get('gpu_freq_mhz'), low=1, high=10000),
                gpu_active_ratio=number(raw.get('gpu_active_ratio'), high=1),
                gpu_temp_c=number(temp.get('gpu_temp_avg'), low=1, high=150),
                cpu_temp_c=number(temp.get('cpu_temp_avg'), low=1, high=150),
                thermal_state=number(thermal, high=3),
                fan_rpm=[value for fan in raw.get('fans', []) if isinstance(fan, dict)
                         and (value := number(fan.get('rpm'), high=20000)) is not None])


def summarize(rows):
    result = dict(samples=len(rows), source='macmon/IOReport and SMC; NSProcessInfo thermal state',
                  scope='Whole device, approximate one-second windows; no per-process GPU attribution.')
    for field in ('gpu_freq_mhz', 'gpu_temp_c', 'cpu_temp_c', 'other_cpu_percent', 'system_cpu_percent', 'model_cpu_percent'):
        values = [r[field] for r in rows if r.get(field) is not None]
        result[field] = dict(samples=len(values), minimum=min(values), median=statistics.median(values),
                             maximum=max(values)) if values else None
    active = [r for r in rows if (r.get('gpu_active_ratio') or 0) >= .05]
    values = [r['gpu_freq_mhz'] for r in active if r.get('gpu_freq_mhz') is not None]
    result['active_gpu_freq_mhz'] = dict(samples=len(values), minimum=min(values),
        median=statistics.median(values), maximum=max(values)) if values else None
    states = [r['thermal_state'] for r in rows if r.get('thermal_state') is not None]
    result['peak_thermal_state'] = max(states) if states else None
    for field in ('model_pfaults', 'model_pageins'):
        values = [r[field] for r in rows if r.get(field) is not None]
        result[field] = dict(samples=len(values), first=values[0], last=values[-1],
            change=values[-1]-values[0]) if len(values)>=2 and values[-1]>=values[0] else None
    return result


class Sampler:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.rows, self.error, self.child, self.thread = [], None, None, None
        self.model_pid = None
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.stopping = threading.Event()
        self.stderr = None

    def start(self, pin):
        self.pin = pin
        self.thermal = thermal_reader()
        self.stderr = (self.folder / 'hardware.stderr.log').open('w')
        with defer_termination():
            self.child = subprocess.Popen([pin['path'], 'pipe', '-i', '1000'],
                stdout=subprocess.PIPE, stderr=self.stderr, text=True, bufsize=1)
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()
        if not self.ready.wait(timeout=10) or self.error:
            self.stop()
            raise RuntimeError(self.error or 'Hardware sampler did not become ready')

    def run(self):
        try:
            primed = False
            psutil.cpu_percent(None)
            with (self.folder / 'hardware.jsonl').open('w') as log:
                for line in self.child.stdout:
                    if self.stopping.is_set():
                        break
                    row = normalize(json.loads(line), time.monotonic(), self.thermal())
                    # A power-gated idle GPU legitimately reports frequency0.
                    # Preserve it as unavailable; do not fail the sampling stream.
                    others = []
                    model_load = None
                    for proc in psutil.process_iter(['pid', 'name']):
                        try:
                            load = proc.cpu_percent(None)
                            if proc.pid == self.model_pid: model_load = load
                            if proc.pid not in (self.model_pid, self.child.pid, os.getpid()) and load > 0:
                                others.append(dict(pid=proc.pid, name=proc.info['name'], cpu_percent=load))
                        except (psutil.NoSuchProcess, psutil.AccessDenied): pass
                    model_memory = None
                    if self.model_pid:
                        try: model_memory = psutil.Process(self.model_pid).memory_info()
                        except (psutil.NoSuchProcess, psutil.AccessDenied): pass
                    row.update(model_cpu_percent=model_load if primed else None,
                               model_pfaults=number(getattr(model_memory,'pfaults',None)),
                               model_pageins=number(getattr(model_memory,'pageins',None)),
                               system_cpu_percent=psutil.cpu_percent(None) if primed else None,
                               other_cpu_percent=sum(p['cpu_percent'] for p in others) if primed else None,
                               other_cpu_processes=sorted(others, key=lambda p:p['cpu_percent'], reverse=True)[:5])
                    primed = True
                    with self.lock: self.rows.append(row)
                    log.write(json.dumps(row, allow_nan=False)+'\n'); log.flush()
                    self.ready.set()
            if not self.stopping.is_set():
                raise RuntimeError('Hardware sampler stream ended before requested stop')
        except BaseException as error:
            self.error = f'{type(error).__name__}: {error}'
            self.ready.set()

    def window(self, begin, end):
        # Each timestamp is the end of a device sampling interval, so select overlap.
        with self.lock:
            rows = [r for r in self.rows if r['monotonic_s'] >= begin and
                    r['monotonic_s'] - r['sample_window_s'] <= end]
        return summarize(rows)

    def stop(self):
        if not self.stopping.is_set() and self.child and self.child.poll() is not None:
            self.error = self.error or 'Hardware sampler exited before requested stop'
        self.stopping.set()
        if self.child and self.child.poll() is None:
            self.child.terminate()
            try: self.child.wait(timeout=5)
            except subprocess.TimeoutExpired: self.child.kill(); self.child.wait(timeout=5)
        if self.thread:
            self.thread.join(timeout=5)
            if self.thread.is_alive(): self.error = self.error or 'Hardware reader did not stop'
        if self.stderr: self.stderr.close()
        with self.lock: result = summarize(self.rows)
        result.update(error=self.error, healthy=bool(self.rows) and not self.error and
                      (not self.thread or not self.thread.is_alive()),
                      child_exited=self.child is not None and self.child.poll() is not None,
                      tool=getattr(self, 'pin', None))
        result['sensor_fields_observed'] = {key: any(r.get(key) is not None for r in self.rows)
            for key in ('gpu_freq_mhz','gpu_temp_c','thermal_state')}
        return result
