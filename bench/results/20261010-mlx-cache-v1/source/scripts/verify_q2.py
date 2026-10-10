#!/usr/bin/env python3
"""Compare synthetic Q2 GPU operations with CPU reference math; no model or perf mode."""
from datetime import datetime, timezone
import json
import re
import subprocess
import time

import psutil
from engines import verify_engine
from lab import ROOT


def check_case(binary, folder, name, params, env=None, operations="MUL_MAT,MUL_MAT_ID"):
    command = [str(binary), "test", "-b", "MTL0", "-o", operations, "-p", params, "-j", "1"]
    log_path = folder / f"{name}.log"
    initial_swap = psutil.swap_memory().used
    peak_rss, peak_swap, guard = 0, initial_swap, None
    with log_path.open("w") as log:
        process = subprocess.Popen(command, stdout=log, stderr=log, env=env)
        try:
            proc = psutil.Process(process.pid)
            while process.poll() is None:
                try:
                    peak_rss = max(peak_rss, proc.memory_info().rss)
                    peak_swap = max(peak_swap, psutil.swap_memory().used)
                    if peak_rss > 1536 * 1024**2 or peak_swap - initial_swap > 256 * 1024**2:
                        guard = "Small feature check exceeded 1.5 GiB RSS or 256 MiB system swap growth"
                        raise RuntimeError(guard)
                except psutil.NoSuchProcess:
                    break
                time.sleep(0.1)
            process.wait()
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    matches = re.findall(r"(\d+)/(\d+) tests passed", log_path.read_text())
    counts = [(int(passed), int(total)) for passed, total in matches]
    passed = process.returncode == 0 and len(counts) == 1 and counts[0][0] == counts[0][1] > 0 and guard is None
    result = {"name": name, "command": command, "passed": passed, "counts": counts,
              "exit_code": process.returncode, "peak_rss_bytes": peak_rss,
              "system_swap_growth_bytes": max(0, peak_swap - initial_swap), "guard": guard}
    print(f"{name}: {'PASS' if passed else 'FAIL'} {counts}; peak RSS {peak_rss/1024**2:.1f} MiB", flush=True)
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
