#!/usr/bin/env python3
"""Start Strata's Mac web app over the pinned native Metal engine. Ctrl-C stops both."""
import argparse
from datetime import datetime, timezone
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model", choices=["small", "flash"], nargs="?", default="flash")
    ap.add_argument("--port", type=int, default=8095)
    ap.add_argument("--native-port", type=int, default=8096)
    ap.add_argument("--context", type=int, default=4096)
    ap.add_argument("--ubatch", type=int, default=512)
    ap.add_argument("--cache-type", default="f16", choices=["f16", "q8_0", "q4_0"])
    ap.add_argument("--spec", default="none", choices=["none", "draft-mtp"])
    ap.add_argument("--draft", type=int, default=3)
    ap.add_argument("--draft-placement", choices=["gpu", "cpu"], default="cpu")
    args = ap.parse_args()
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGHUP, interrupted)
    for port in (args.port, args.native_port):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))
    folder = ROOT / "bench/runtime" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder.mkdir(parents=True)
    active_path = ROOT / "bench/runtime/active.json"
    active_path.write_text(json.dumps({"pid": os.getpid(), "create_time": psutil.Process().create_time(),
                           "model": args.model, "port": args.port, "native_port": args.native_port,
                           "log_directory": str(folder)}, indent=2) + "\n")
    config = {"native_url": f"http://127.0.0.1:{args.native_port}", "model_name": args.model,
              "host": "127.0.0.1", "fit_max_tokens": True}
    config_path = folder / "strata.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    native, app, monitor = None, None, None
    with (folder / "native.log").open("w") as log:
        try:
            command = server_command(args.model, args.native_port, args.context, ubatch=args.ubatch,
                                     cache_type=args.cache_type, spec=args.spec, draft=args.draft,
                                     draft_placement=args.draft_placement)
            (folder / "command.json").write_text(json.dumps(command, indent=2) + "\n")
            native = subprocess.Popen(command, stdout=log, stderr=log)
            monitor = Monitor(native, folder / "memory.jsonl")
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
