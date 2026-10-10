#!/usr/bin/env python3
"""Start Strata's Mac web app over the pinned native Metal engine. Ctrl-C stops both."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
import signal
import socket
import subprocess
import sys
import time
import psutil

from benchmark import Monitor, wait_ready
from lab import ROOT, server_command
from engines import ENGINES, verify_engine
from draft_vocab import experiment_environment
from check_memory import assert_no_model_server
from metal_environment import TUNING, configure


def assert_ports_available(ports):
    for port in ports:
        with socket.socket() as sock:
            if os.name != "nt":
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("model", choices=["small", "flash"], nargs="?", default="flash")
    ap.add_argument("--engine", choices=ENGINES, default="baseline")
    ap.add_argument("--draft-vocab", choices=["off", "106k"], default="off")
    ap.add_argument("--port", type=int, default=8095)
    ap.add_argument("--native-port", type=int, default=8096)
    ap.add_argument("--context", type=int, default=4096)
    ap.add_argument("--ubatch", type=int, default=512)
    ap.add_argument("--cache-type", default="f16", choices=["f16", "q8_0", "q4_0"])
    ap.add_argument("--spec", default="none", choices=["none", "draft-mtp"])
    ap.add_argument("--draft", type=int, default=3)
    ap.add_argument("--draft-placement", choices=["gpu", "cpu", "output", "mixed"], default="cpu")
    ap.add_argument("--draft-model", default="mtp")
    ap.add_argument("--draft-threads", type=int, help="CPU workers for the prediction helper only")
    ap.add_argument("--draft-p-min", type=float)
    ap.add_argument("--tensor-api", choices=["auto", "on", "off"], default="auto")
    ap.add_argument("--m5-tuning", choices=TUNING, default="stock")
    ap.add_argument("--prompt-cache", action=argparse.BooleanOptionalAction, default=True)
    args = ap.parse_args(argv)
    if args.draft_vocab != "off" and args.spec != "draft-mtp":
        ap.error("The draft vocabulary requires --spec draft-mtp")
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        execute(args)


def execute(args):
    native_env, vocab_info = experiment_environment(args.engine, args.draft_vocab)
    native_env, metal_info = configure(native_env, args.engine, args.tensor_api, args.m5_tuning)
    assert_no_model_server()
    engine_info = verify_engine(args.engine)
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGHUP, interrupted)
    assert_ports_available((args.port, args.native_port))
    folder = ROOT / "bench/runtime" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder.mkdir(parents=True)
    active_path = ROOT / "bench/runtime/active.json"
    active_path.write_text(json.dumps({"pid": os.getpid(), "create_time": psutil.Process().create_time(),
                           "model": args.model, "engine": args.engine, "port": args.port, "native_port": args.native_port,
                           "log_directory": str(folder)}, indent=2) + "\n")
    config = {"native_url": f"http://127.0.0.1:{args.native_port}", "model_name": args.model,
              "host": "127.0.0.1", "fit_max_tokens": True, "prompt_cache": args.prompt_cache}
    config_path = folder / "strata.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    native, app, monitor = None, None, None
    with (folder / "native.log").open("w") as log:
        try:
            command = server_command(args.model, args.native_port, args.context, ubatch=args.ubatch,
                                     cache_type=args.cache_type, spec=args.spec, draft=args.draft,
                                     draft_placement=args.draft_placement, draft_model=args.draft_model,
                                     engine=args.engine, draft_threads=args.draft_threads,
                                     draft_p_min=args.draft_p_min)
            (folder / "command.json").write_text(json.dumps(command, indent=2) + "\n")
            (folder / "engine.json").write_text(json.dumps(engine_info, indent=2) + "\n")
            (folder / "draft-vocabulary.json").write_text(json.dumps(vocab_info, indent=2) + "\n")
            (folder / "metal-environment.json").write_text(json.dumps(metal_info, indent=2) + "\n")
            launch_baseline = Monitor.baseline()
            native = subprocess.Popen(command, stdout=log, stderr=log, env=native_env)
            monitor = Monitor(native, folder / "memory.jsonl", baseline=launch_baseline)
            monitor.thread.start()
            wait_ready(native, config["native_url"])
            app = subprocess.Popen([sys.executable, str(ROOT / "scripts/strata_server.py"),
                                    "--engine", "metal-native", "--config", str(config_path),
                                    "--host", "127.0.0.1", "--port", str(args.port)])
            print(f"Strata: http://127.0.0.1:{args.port} | native API: {config['native_url']}/v1", flush=True)
            print(f"Logs: {folder} | Ctrl-C stops both processes", flush=True)
            while native.poll() is None and app.poll() is None:
                time.sleep(0.25)
            if monitor.guard:
                raise RuntimeError(monitor.guard)
            if native.poll() is not None or app.returncode:
                raise RuntimeError(f"Server exited; native={native.poll()}, Strata={app.poll()}. See {folder}")
        except KeyboardInterrupt:
            pass
        finally:
            for process in (app, native):
                if process and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            if monitor:
                (folder / "memory-summary.json").write_text(json.dumps(monitor.finish(), indent=2) + "\n")
            if active_path.exists() and json.loads(active_path.read_text()).get("pid") == os.getpid():
                active_path.unlink()


if __name__ == "__main__":
    main()
