#!/usr/bin/env python3
"""Compare synthetic Q2 GPU operations with CPU reference math; no model or perf mode."""
from collections.abc import Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import time
from typing import TypedDict

import psutil
from engines import verify_engine
from lab import ROOT
from memory_monitor import Monitor, OwnedProcess

RSS_LIMIT_BYTES = 1536 * 1024**2
SWAP_LIMIT_BYTES = 256 * 1024**2
LIMIT_GUARD = "Small feature check exceeded 1.5 GiB RSS or 256 MiB system swap growth"


class FinalObservation(TypedDict, total=False):
    swap_used_bytes: int
    pressure_level: int


class CheckResult(TypedDict):
    name: str
    command: list[str]
    passed: bool
    counts: list[tuple[int, int]]
    exit_code: int | None
    peak_rss_bytes: int
    system_swap_growth_bytes: int
    guard: str | None
    live_samples: int
    final_observation: FinalObservation | None
    monitor_error: str | None


class Usage:
    """Live child RSS and system swap, closed by one bounded observation after reaping.

    A tiny check can exit between polls and swap can grow after the last live
    sample, so acceptance needs a live sample and the post-exit swap/pressure reading.
    """

    def __init__(self) -> None:
        self.initial_swap = psutil.swap_memory().used
        self.peak_rss, self.peak_swap, self.live_samples = 0, self.initial_swap, 0
        self.final: FinalObservation | None = None
        self.guard: str | None = None
        self.monitor_error: str | None = None

    def limit(self) -> None:
        if self.peak_rss > RSS_LIMIT_BYTES or self.peak_swap - self.initial_swap > SWAP_LIMIT_BYTES:
            self.guard = self.guard or LIMIT_GUARD

    def watch(self, process: OwnedProcess) -> None:
        """Sample until the child exits, a limit is crossed or a reading fails; the caller stops it."""
        try:
            proc = psutil.Process(process.pid)
            while process.poll() is None:
                rss = proc.memory_info().rss
                self.peak_rss = max(self.peak_rss, rss)
                self.peak_swap = max(self.peak_swap, psutil.swap_memory().used)
                self.live_samples += 1
                self.limit()
                if self.guard:
                    return
                time.sleep(0.1)
        except psutil.NoSuchProcess:
            return  # Exited before or during a sample; finish() decides coverage.
        except Exception as error:
            self.monitor_error = f"{type(error).__name__}: {error}"

    def finish(self) -> None:
        """Take the final swap/pressure reading after reaping; sysctl is bounded by its timeout."""
        final: FinalObservation = {}
        self.final = final
        try:
            final["swap_used_bytes"] = psutil.swap_memory().used
            self.peak_swap = max(self.peak_swap, final["swap_used_bytes"])
            self.limit()
            final["pressure_level"] = Monitor.read_pressure_level()
        except Exception as error:
            self.monitor_error = self.monitor_error or f"Final observation failed: {type(error).__name__}: {error}"
        if self.monitor_error:
            self.guard = self.guard or "Monitoring failed: " + self.monitor_error
        if final.get("pressure_level", 1) != 1:
            self.guard = self.guard or f"macOS memory pressure level {final['pressure_level']} is not normal"
        if not self.live_samples:
            self.guard = self.guard or "No live child sample; RSS coverage is incomplete"


def reap(process: OwnedProcess) -> int:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    return process.wait()


def evidence(name: str, command: list[str], exit_code: int | None, usage: Usage, log_path: Path) -> CheckResult:
    text = log_path.read_text(errors="replace") if log_path.is_file() else ""
    counts = [(int(passed), int(total)) for passed, total in re.findall(r"(\d+)/(\d+) tests passed", text)]
    passed = exit_code == 0 and len(counts) == 1 and counts[0][0] == counts[0][1] > 0 and usage.guard is None
    return {"name": name, "command": command, "passed": passed, "counts": counts,
            "exit_code": exit_code, "peak_rss_bytes": usage.peak_rss,
            "system_swap_growth_bytes": max(0, usage.peak_swap - usage.initial_swap), "guard": usage.guard,
            "live_samples": usage.live_samples, "final_observation": usage.final,
            "monitor_error": usage.monitor_error}


def check_case(binary: Path, folder: Path, name: str, params: str, env: Mapping[str, str] | None = None,
               operations: str = "MUL_MAT,MUL_MAT_ID") -> CheckResult:
    command = [str(binary), "test", "-b", "MTL0", "-o", operations, "-p", params, "-j", "1"]
    log_path = folder / f"{name}.log"
    usage = Usage()
    exit_code: int | None = None
    try:
        with log_path.open("w") as log:
            process = subprocess.Popen(command, stdout=log, stderr=log, env=env)
            try:
                usage.watch(process)
            finally:
                exit_code = reap(process)
                usage.finish()
    finally:
        # Publish the evidence beside the log, including guard, monitor and interrupted outcomes.
        result = evidence(name, command, exit_code, usage, log_path)
        (folder / f"{name}.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"{name}: {'PASS' if result['passed'] else 'FAIL'} {result['counts']}; "
          f"peak RSS {result['peak_rss_bytes']/1024**2:.1f} MiB", flush=True)
    return result


def main():
    engine = verify_engine("q2-masked")
    binary = ROOT / engine["directory"] / "build/bin/test-backend-ops"
    folder = ROOT / "bench/features" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-q2-metal")
    folder.mkdir(parents=True)
    record = {"schema": 1, "kind": "synthetic-correctness", "engine": engine,
              "models_loaded": False, "benchmarks_run": False, "checks": [], "status": "running",
              "method": "Native test-backend-ops test mode on MTL0 against CPU reference. No performance mode, model weights, inference requests or TPS measurements."}
    try:
        for name, params in [("q2-matvec-and-experts", "type_a=q2_0,"),
                             ("q4-control", r"type_a=q4_0,type_b=f32,m=16,n=(1|8),k=4096,")]:
            record["checks"].append(check_case(binary, folder, name, params))
            if not record["checks"][-1]["passed"]:
                raise RuntimeError(f"Feature check failed: {name}")
        record["status"] = "passed"
    except BaseException as error:
        record["status"] = "failed"
        record["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        (folder / "checks.json").write_text(json.dumps(record, indent=2) + "\n")
        print(f"Saved {folder / 'checks.json'}")


if __name__ == "__main__":
    main()
