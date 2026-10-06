#!/usr/bin/env python3
"""Check real Strata APIs for helper settings; exclude these timings from speed results."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import shutil
import signal
import subprocess
import sys

from benchmark import wait_ready
from check_memory import assert_no_model_server
from engines import verify_engine
from lab import ROOT


def check(depth, threads, engine="mtp-shared"):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prefix = "tuning" if engine == "mtp-shared" else "mma"
    folder = ROOT / "bench/features" / f"{stamp}-{prefix}-app-{depth}-{threads}"
    folder.mkdir()
    before = set((ROOT / "bench/results").glob("*-flash-integration.json"))
    command = [sys.executable, "scripts/run.py", "flash", "--engine", engine,
               "--spec", "draft-mtp", "--draft-model", "mtp_shared_packed_q3", "--draft", str(depth),
               "--draft-placement", "mixed", "--draft-threads", str(threads)]
    models = json.loads((ROOT / "config/models.json").read_text())
    record = {"kind": "helper-tuning-app-proof" if engine == "mtp-shared" else "metal-few-row-app-proof", "status": "running", "depth": depth,
              "draft_threads": threads, "launch_command": command, "engine": verify_engine(engine),
              "models": {k: models[k] for k in ("flash", "mtp_shared_packed_q3")},
              "note": "Functional API tests only; these timings are excluded from speed comparisons."}
    process = None
    runtime = None
    try:
        assert_no_model_server()
        with (folder / "launcher.log").open("w") as log:
            process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=log)
            wait_ready(process, "http://127.0.0.1:8095", timeout=120)
            active = json.loads((ROOT / "bench/runtime/active.json").read_text())
            if active["pid"] != process.pid:
                raise RuntimeError("Active app does not match this test launcher")
            runtime = ROOT / active["log_directory"]
            result = subprocess.run([sys.executable, "scripts/verify_integration.py", "--model", "flash"],
                                    cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            (folder / "integration.log").write_text(result.stdout)
            print(result.stdout, end="", flush=True)
            added = set((ROOT / "bench/results").glob("*-flash-integration.json")) - before
            if result.returncode or len(added) != 1:
                raise RuntimeError("Real app integration checks failed")
            path = added.pop()
            integration = json.loads(path.read_text())
            record.update(integration=str(path.relative_to(ROOT)), checks_total=len(integration["checks"]),
                          checks_passed=sum(c["passed"] for c in integration["checks"]), status="passed")
    except BaseException as error:
        record.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        if process and process.poll() is None:
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=30)
        if runtime:
            shutil.copytree(runtime, folder / "runtime")
            record["command"] = json.loads((runtime / "command.json").read_text())
            record["memory"] = json.loads((runtime / "memory-summary.json").read_text())
            if record["memory"].get("guard"):
                record.update(status="failed", error=record["memory"]["guard"])
        assert_no_model_server()
        record.update(servers_stopped=True, artifacts=str(folder.relative_to(ROOT)))
        output = ROOT / "bench/results" / f"{stamp}-{prefix}-app-{depth}-{threads}.json"
        output.write_text(json.dumps(record, indent=2) + "\n")
        print(f"Saved {output}", flush=True)
    if record["status"] != "passed":
        raise RuntimeError("App or memory checks failed")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--depths", type=int, nargs="+", default=[1, 3, 4])
    ap.add_argument("--draft-threads", type=int, default=8)
    ap.add_argument("--engine", choices=["mtp-shared", "mtp-mma"], default="mtp-shared")
    args = ap.parse_args()
    if not args.depths or min(args.depths) < 1 or max(args.depths) > 4 or not 1 <= args.draft_threads <= 18:
        ap.error("Use depths 1-4 and helper thread counts 1-18")
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for depth in args.depths:
            check(depth, args.draft_threads, args.engine)


if __name__ == "__main__":
    main()
