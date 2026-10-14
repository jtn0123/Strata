"""Owned-process readiness and memory guards shared by app and trial launches."""

import json
from pathlib import Path
import subprocess
import threading
import time
from typing import NotRequired, Protocol, TypedDict

import psutil
from lab import request


class OwnedProcess(Protocol):
    pid: int
    returncode: int | None

    def poll(self) -> int | None: ...
    def terminate(self) -> None: ...
    def kill(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...


class MemoryInfo(Protocol):
    @property
    def rss(self) -> int: ...
    @property
    def vms(self) -> int: ...


class MemoryBaseline(TypedDict):
    swap_used_bytes: int
    available_bytes: int


class MemorySample(TypedDict):
    elapsed_s: float
    rss_bytes: int
    vms_bytes: int
    available_bytes: int
    swap_used_bytes: int
    system_disk_read_bytes: int | None
    system_disk_write_bytes: int | None
    pressure_level: NotRequired[int]


class MemorySummary(TypedDict):
    guard: str | None
    monitor_healthy: bool
    monitor_error: str | None
    samples: int
    live_samples: int
    baseline_before_launch: bool
    child_exited: bool
    launch_baseline: MemoryBaseline
    peak_rss_bytes: int
    minimum_available_bytes: int
    peak_swap_bytes: int
    swap_growth_bytes: int
    normal_pressure_required: bool
    pressure_samples: int
    pressure_live_samples: int
    peak_pressure_level: int | None
    normal_pressure_observed: bool | None
    system_disk_read_bytes: int | None
    sampling_interval_s: float
    note: str


class Monitor:
    @staticmethod
    def read_pressure_level() -> int:
        level = int(
            subprocess.check_output(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"], text=True, timeout=2)
        )
        if level not in (1, 2, 4):
            raise ValueError("Invalid macOS pressure level")
        return level

    @staticmethod
    def baseline() -> MemoryBaseline:
        return {"swap_used_bytes": psutil.swap_memory().used, "available_bytes": psutil.virtual_memory().available}

    def __init__(
        self,
        process: OwnedProcess,
        path: Path,
        swap_guard_bytes: int = 2 * 1024**3,
        minimum_available_bytes: int = 384 * 1024**2,
        *,
        baseline: MemoryBaseline | None = None,
        require_normal_pressure: bool = False,
    ) -> None:
        self.process, self.path = process, path
        self.swap_guard_bytes = swap_guard_bytes
        self.minimum_available_bytes = minimum_available_bytes
        self.require_normal_pressure = require_normal_pressure
        self.pressure_samples, self.pressure_live_samples = 0, 0
        self.peak_pressure_level: int | None = None
        self.done = threading.Event()
        self.baseline_before_launch = baseline is not None
        self.launch_baseline = baseline if baseline is not None else self.baseline()
        self.initial_swap = self.launch_baseline["swap_used_bytes"]
        self.first_sample: MemorySample | None = None
        self.latest_sample: MemorySample | None = None
        self.guard: str | None = None
        self.peak_rss, self.minimum_available, self.peak_swap = (
            0,
            self.launch_baseline["available_bytes"],
            self.initial_swap,
        )
        self.sample_count, self.live_samples = 0, 0
        self.monitor_error: str | None = None
        self.start = time.monotonic()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def stop_owned_child(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)

    def fail(self, error: Exception) -> None:
        self.monitor_error = f"{type(error).__name__}: {error}"
        self.guard = self.guard or "Monitoring failed: " + self.monitor_error
        try:
            self.stop_owned_child()
        except Exception as stop_error:
            self.monitor_error += f"; child stop failed: {stop_error}"

    def sample(self, mem: MemoryInfo | None = None) -> MemorySample:
        vm, swap, io = psutil.virtual_memory(), psutil.swap_memory(), psutil.disk_io_counters()
        sample: MemorySample = {
            "elapsed_s": round(time.monotonic() - self.start, 3),
            "rss_bytes": mem.rss if mem else 0,
            "vms_bytes": mem.vms if mem else 0,
            "available_bytes": vm.available,
            "swap_used_bytes": swap.used,
            "system_disk_read_bytes": io.read_bytes if io else None,
            "system_disk_write_bytes": io.write_bytes if io else None,
        }
        if self.require_normal_pressure:
            level = self.read_pressure_level()
            sample["pressure_level"] = level
            self.pressure_samples += 1
            self.pressure_live_samples += int(mem is not None)
            self.peak_pressure_level = max(self.peak_pressure_level or level, level)
        self.first_sample = self.first_sample or sample
        self.latest_sample = sample
        self.sample_count += 1
        self.live_samples += int(mem is not None)
        self.peak_rss = max(self.peak_rss, sample["rss_bytes"])
        self.minimum_available = min(self.minimum_available, vm.available)
        self.peak_swap = max(self.peak_swap, swap.used)
        return sample

    def pressure_guard(self, sample: MemorySample) -> bool:
        if self.require_normal_pressure and sample["pressure_level"] != 1:
            self.guard = self.guard or f"Stopped: macOS pressure level {sample['pressure_level']} is not normal"
            self.stop_owned_child()
            return True
        return False

    def swap_guard(self, sample: MemorySample) -> bool:
        if sample["swap_used_bytes"] - self.initial_swap > self.swap_guard_bytes:
            self.guard = self.guard or f"Stopped: swap grew by over {self.swap_guard_bytes / 1024**2:.0f} MiB"
            self.stop_owned_child()
            return True
        return False

    def run(self) -> None:
        low_since = None
        try:
            proc = psutil.Process(self.process.pid)
            with self.path.open("w") as stream:
                while not self.done.is_set():
                    try:
                        mem = proc.memory_info()
                    except psutil.NoSuchProcess:
                        mem = None
                    sample = self.sample(mem)
                    stream.write(json.dumps(sample) + "\n")
                    stream.flush()
                    if self.pressure_guard(sample):
                        return
                    if self.swap_guard(sample):
                        return
                    if sample["available_bytes"] < self.minimum_available_bytes:
                        low_since = low_since or time.monotonic()
                    else:
                        low_since = None
                    if low_since and time.monotonic() - low_since > 4:
                        self.guard = f"Stopped: available memory stayed below {self.minimum_available_bytes / 1024**2:.0f} MiB for 4 seconds"
                        self.stop_owned_child()
                        return
                    if mem is None or self.process.poll() is not None:
                        return
                    self.done.wait(0.25)
        except Exception as error:
            self.fail(error)

    def finish(self) -> MemorySummary:
        if self.process.poll() is None:
            self.fail(RuntimeError("Monitoring finished before the owned child exited"))
        self.done.set()
        if self.thread.ident is not None:
            self.thread.join(timeout=2)
        if self.thread.is_alive():
            self.fail(RuntimeError("Monitoring thread did not stop"))
        else:
            self._record_exit_sample()
        if not self.live_samples:
            self.guard = self.guard or "No live child samples; monitoring coverage is incomplete"
        if not self.baseline_before_launch:
            self.guard = self.guard or "No prelaunch memory baseline; update this launch path"
        return self._summary()

    def _record_exit_sample(self) -> None:
        try:
            sample = self.sample()
            self.pressure_guard(sample)
            self.swap_guard(sample)
            with self.path.open("a") as stream:
                stream.write(json.dumps({**sample, "after_child_exit": self.process.poll() is not None}) + "\n")
        except Exception as error:
            self.fail(error)

    def _summary(self) -> MemorySummary:
        first_read = self.first_sample.get("system_disk_read_bytes") if self.first_sample else None
        latest_read = self.latest_sample.get("system_disk_read_bytes") if self.latest_sample else None
        return {
            "guard": self.guard,
            "monitor_healthy": not self.monitor_error
            and bool(self.live_samples)
            and self.baseline_before_launch
            and not self.thread.is_alive(),
            "monitor_error": self.monitor_error,
            "samples": self.sample_count,
            "live_samples": self.live_samples,
            "baseline_before_launch": self.baseline_before_launch,
            "child_exited": self.process.poll() is not None,
            "launch_baseline": self.launch_baseline,
            "peak_rss_bytes": self.peak_rss,
            "minimum_available_bytes": self.minimum_available,
            "peak_swap_bytes": self.peak_swap,
            "swap_growth_bytes": max(0, self.peak_swap - self.initial_swap),
            "normal_pressure_required": self.require_normal_pressure,
            "pressure_samples": self.pressure_samples,
            "pressure_live_samples": self.pressure_live_samples,
            "peak_pressure_level": self.peak_pressure_level,
            "normal_pressure_observed": (
                bool(self.pressure_live_samples) and self.peak_pressure_level == 1 and not self.monitor_error
            )
            if self.require_normal_pressure
            else None,
            "system_disk_read_bytes": latest_read - first_read
            if first_read is not None and latest_read is not None
            else None,
            "sampling_interval_s": 0.25,
            "note": "RSS is not total Metal memory. Disk counters include all system activity. See native allocation log and vm_stat.",
        }


def wait_ready(process: OwnedProcess, base: str, timeout: float = 600) -> float:
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        if process.poll() is not None:
            raise RuntimeError(f"Server exited during load with code {process.returncode}; see server.log")
        try:
            if request(base, "/health", timeout=2).get("status") == "ok":
                return time.monotonic() - started
        except (OSError, RuntimeError):
            pass
        time.sleep(0.25)
    raise TimeoutError("Server did not become ready within 600 seconds")
