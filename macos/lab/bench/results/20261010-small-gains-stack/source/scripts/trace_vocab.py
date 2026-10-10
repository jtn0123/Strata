#!/usr/bin/env python3
"""Record backend placement for the vocabulary head; debug timings are not benchmarks."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import socket
import subprocess

from benchmark import Monitor, wait_ready
from check_memory import assert_no_model_server
from draft_vocab import experiment_environment
from engines import verify_engine
from lab import ROOT, request, server_command


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--label", required=True)
    args = ap.parse_args()
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert_no_model_server()
        engine = verify_engine("draft-vocab")
        folder = ROOT / "bench/features" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + args.label)
        folder.mkdir()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        command = server_command("flash", port, 4096, 512, 512, "draft-mtp", 2,
                                 draft_placement="output", draft_model="mtp_q3", engine="draft-vocab")
        command[command.index("--verbosity") + 1] = "5"
        env, vocabulary = experiment_environment("draft-vocab", "106k")
        env["GGML_SCHED_DEBUG"] = "2"
        record = {"engine": engine, "command": command, "vocabulary": vocabulary, "status": "running",
                  "note": "Verbose scheduler diagnostics only. Do not use timings as performance results."}
        process, monitor = None, None
        with (folder / "scheduler.log").open("w") as log:
            try:
                launch_baseline = Monitor.baseline()
                process = subprocess.Popen(command, stdout=log, stderr=log, env=env)
                monitor = Monitor(process, folder / "memory.jsonl", baseline=launch_baseline)
                monitor.thread.start()
                base = f"http://127.0.0.1:{port}"
                record["ready_s"] = wait_ready(process, base)
                record["response"] = request(base, "/completion", {"prompt": "Write a short hello message.",
                    "n_predict": 8, "ignore_eos": True, "cache_prompt": False,
                    "temperature": 0, "seed": 1234, "return_tokens": True})
                record["status"] = "passed"
            except BaseException as error:
                record.update(status="failed", error=f"{type(error).__name__}: {error}")
                raise
            finally:
                if process and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                if monitor:
                    record["memory"] = monitor.finish()
                (folder / "trace.json").write_text(json.dumps(record, indent=2) + "\n")
                print(f"Saved {folder}", flush=True)


if __name__ == "__main__":
    main()
