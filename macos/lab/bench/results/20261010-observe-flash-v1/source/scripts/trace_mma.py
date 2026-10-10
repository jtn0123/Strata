#!/usr/bin/env python3
"""Record real-model Metal pipeline selection; debug timings are excluded from benchmarks."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import re
import socket
import subprocess

from benchmark import Monitor, wait_ready
from check_memory import assert_no_model_server
from draft_vocab import experiment_environment
from engines import verify_engine
from lab import ROOT, request, server_command


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--engine", choices=["mtp-shared", "mtp-mma"], default="mtp-mma")
    ap.add_argument("--depth", type=int, choices=[1, 3, 4], default=3)
    args = ap.parse_args()
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert_no_model_server()
        engine = verify_engine(args.engine)
        folder = ROOT / "bench/features" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-mma-trace-{args.engine}-{args.depth}")
        folder.mkdir()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        command = server_command("flash", port, 4096, 512, 512, "draft-mtp", args.depth,
                                 draft_placement="mixed", draft_model="mtp_shared_packed_q3",
                                 engine=args.engine, draft_threads=8)
        command[command.index("--verbosity") + 1] = "5"
        env, _ = experiment_environment(args.engine)
        env["GGML_METAL_GRAPH_DEBUG"] = "2"
        record = {"kind": "real-model-pipeline-proof", "engine": engine, "depth": args.depth,
                  "command": command, "status": "running",
                  "note": "Verbose native diagnostics only. Pipeline compilation shows dispatch activation, not GPU operation timing. Exclude these timings from speed results."}
        process, monitor = None, None
        log_path = folder / "native.log"
        try:
            with log_path.open("w") as log:
                launch_baseline = Monitor.baseline()
                process = subprocess.Popen(command, stdout=log, stderr=log, env=env)
                monitor = Monitor(process, folder / "memory.jsonl", baseline=launch_baseline)
                monitor.thread.start()
                base = f"http://127.0.0.1:{port}"
                record["ready_s"] = wait_ready(process, base)
                rendered = request(base, "/apply-template", {"messages": [{"role": "user", "content": "Write a Python function that calculates the average of a list of numbers. Include a short example."}], "chat_template_kwargs": {"enable_thinking": False}})["prompt"]
                record["response"] = request(base, "/completion", {"prompt": rendered,
                    "n_predict": 16, "ignore_eos": True, "cache_prompt": False,
                    "temperature": 0, "seed": 1234, "return_tokens": True})
            text = log_path.read_text()
            record["mma_pipelines"] = sorted(set(re.findall(r"compiling pipeline: base = '(kernel_mul_mv_mma_[^']+)'", text)))
            new_types = ("bf16", "q2_0", "q3_K", "iq4_nl", "iq4_xs")
            record["new_format_pipelines"] = [p for p in record["mma_pipelines"] if any(f"mma_{t}_" in p for t in new_types)]
            if args.engine == "mtp-mma" and not record["new_format_pipelines"]:
                raise RuntimeError("No affected-format few-row pipeline observed; inspect native log")
            if args.engine == "mtp-shared" and record["new_format_pipelines"]:
                raise RuntimeError("Control unexpectedly used the new pipelines")
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
            record["servers_stopped"] = True
            (folder / "trace.json").write_text(json.dumps(record, indent=2) + "\n")
            print(f"Saved {folder}", flush=True)


if __name__ == "__main__":
    main()
