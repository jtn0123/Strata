#!/usr/bin/env python3
"""Start Strata's Mac web app over the pinned native Metal engine. Ctrl-C stops both."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
import socket
import subprocess
import sys
import time
import psutil
from collections.abc import Sequence
from typing import Any, Protocol

from benchmark import wait_ready
from lab import ROOT, server_command
from engines import ENGINES, verify_engine
from draft_vocab import experiment_environment
from check_memory import assert_no_model_server
from metal_environment import TUNING, configure
from runtime_profiles import lookup_command
from runtime_memory import admit_model, app_monitor
from model_provenance import verify_models
from benchmark_signals import cleanup_on_termination, defer_termination


class RunArguments(Protocol):
    model: str
    engine: str
    draft_vocab: str
    port: int
    native_port: int
    context: int
    batch: int
    ubatch: int
    cache_type: str
    spec: str
    draft: int
    draft_placement: str
    draft_model: str
    draft_threads: int | None
    draft_p_min: float | None
    tensor_api: str
    m5_tuning: str
    prompt_cache: bool
    lookup_profile: str


def assert_ports_available(ports: Sequence[int]) -> None:
    for port in ports:
        with socket.socket() as sock:
            if os.name != "nt":
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))


def validated_ports(args: RunArguments) -> tuple[int, int]:
    """Keep CLI values numeric before resource checks or child argument assembly."""
    for value in (args.port, args.native_port):
        if type(value) is not int or not 1 <= value <= 65535:
            raise ValueError("Ports must be integers from 1 to 65535")
    if args.port == args.native_port:
        raise ValueError("API and native ports must differ")
    return int(args.port), int(args.native_port)


def stop_owned_processes(processes: Sequence[subprocess.Popen[bytes] | None]) -> None:
    for process in processes:
        if process is None or process.poll() is not None:
            continue
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("model", choices=["small", "flash"], nargs="?", default="flash")
    ap.add_argument("--engine", choices=ENGINES, default="baseline")
    ap.add_argument("--draft-vocab", choices=["off", "106k"], default="off")
    ap.add_argument("--port", type=int, default=8095)
    ap.add_argument("--native-port", type=int, default=8096)
    ap.add_argument("--context", type=int, default=4096)
    ap.add_argument("--batch", type=int, default=512)
    ap.add_argument("--ubatch", type=int, default=512)
    ap.add_argument("--cache-type", default="f16", choices=["f16", "q8_0", "q4_0"])
    ap.add_argument("--spec", default="none", choices=["none", "draft-mtp"])
    ap.add_argument("--draft", type=int, default=3)
    ap.add_argument(
        "--draft-placement", choices=["gpu", "cpu", "output", "mixed"], default="cpu"
    )
    ap.add_argument("--draft-model", default="mtp")
    ap.add_argument(
        "--draft-threads", type=int, help="CPU workers for the prediction helper only"
    )
    ap.add_argument("--draft-p-min", type=float)
    ap.add_argument("--tensor-api", choices=["auto", "on", "off"], default="auto")
    ap.add_argument("--m5-tuning", choices=TUNING, default="stock")
    ap.add_argument(
        "--prompt-cache", action=argparse.BooleanOptionalAction, default=True
    )
    ap.add_argument("--lookup-profile", choices=["off", "code-edit"], default="off")
    args = ap.parse_args(argv)
    if args.draft_vocab != "off" and args.spec != "draft-mtp":
        ap.error("The draft vocabulary requires --spec draft-mtp")
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        execute(args)


@cleanup_on_termination()
def execute(args: RunArguments) -> None:
    batch: int = getattr(args, "batch", 512)
    if not 0 < args.ubatch <= batch <= args.context:
        raise ValueError(
            "Prompt chunks must satisfy 0 < ubatch <= batch <= context; refusing silent clamping"
        )
    # Reject unsupported lookup settings before any native process can launch.
    lookup_command(["--spec-type", args.spec], args)
    app_port, native_port = validated_ports(args)
    native_env, vocab_info = experiment_environment(args.engine, args.draft_vocab)
    native_env, metal_info = configure(
        native_env, args.engine, args.tensor_api, args.m5_tuning
    )
    assert_no_model_server()
    engine_info = verify_engine(args.engine)
    model_ids = [args.model] + ([args.draft_model] if args.spec == "draft-mtp" else [])
    model_info = verify_models(model_ids)
    assert_ports_available((app_port, native_port))
    folder = (
        ROOT / "bench/runtime" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    folder.mkdir(parents=True)
    active_path = ROOT / "bench/runtime/active.json"
    active_path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "create_time": psutil.Process().create_time(),
                "model": args.model,
                "engine": args.engine,
                "port": app_port,
                "native_port": native_port,
                "log_directory": str(folder),
            },
            indent=2,
        )
        + "\n"
    )
    config: dict[str, Any] = {
        "native_url": f"http://127.0.0.1:{native_port}",
        "model_name": args.model,
        "host": "127.0.0.1",
        "fit_max_tokens": True,
        "prompt_cache": args.prompt_cache,
    }
    config_path = folder / "strata.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    native: subprocess.Popen[bytes] | None = None
    app: subprocess.Popen[bytes] | None = None
    monitor = None
    with (folder / "native.log").open("w") as log:
        try:
            command = server_command(
                args.model,
                native_port,
                args.context,
                batch=batch,
                ubatch=args.ubatch,
                cache_type=args.cache_type,
                spec=args.spec,
                draft=args.draft,
                draft_placement=args.draft_placement,
                draft_model=args.draft_model,
                engine=args.engine,
                draft_threads=args.draft_threads,
                draft_p_min=args.draft_p_min,
            )
            command = lookup_command(command, args)
            (folder / "command.json").write_text(json.dumps(command, indent=2) + "\n")
            (folder / "engine.json").write_text(
                json.dumps(engine_info, indent=2) + "\n"
            )
            (folder / "draft-vocabulary.json").write_text(
                json.dumps(vocab_info, indent=2) + "\n"
            )
            (folder / "metal-environment.json").write_text(
                json.dumps(metal_info, indent=2) + "\n"
            )
            (folder / "models.json").write_text(json.dumps(model_info, indent=2) + "\n")
            (folder / "settings.json").write_text(
                json.dumps(vars(args), indent=2) + "\n"
            )
            policy = admit_model(args.model)
            (folder / "memory-policy.json").write_text(
                json.dumps(policy, indent=2) + "\n"
            )
            config["performance"] = {
                key: getattr(args, key)
                for key in (
                    "model",
                    "engine",
                    "context",
                    "cache_type",
                    "spec",
                    "draft",
                    "draft_model",
                    "lookup_profile",
                    "tensor_api",
                    "m5_tuning",
                    "ubatch",
                    "draft_threads",
                    "draft_placement",
                    "draft_p_min",
                )
            }
            config["performance"].update(
                monitor_file=str(folder / "memory.jsonl"),
                batch=batch,
                initial_swap_bytes=policy["baseline"]["swap_used_bytes"],
            )
            config_path.write_text(json.dumps(config, indent=2) + "\n")
            with defer_termination():
                native = subprocess.Popen(
                    command, stdout=log, stderr=log, env=native_env
                )
                monitor = app_monitor(native, folder / "memory.jsonl", policy)
                monitor.thread.start()
            wait_ready(native, config["native_url"])
            with defer_termination():
                app = subprocess.Popen(
                    [
                        sys.executable,
                        str(ROOT / "scripts/strata_server.py"),
                        "--engine",
                        "metal-native",
                        "--config",
                        str(config_path),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(app_port),
                    ]
                )
            print(
                f"Strata: http://127.0.0.1:{app_port} | native API: {config['native_url']}/v1",
                flush=True,
            )
            print(f"Logs: {folder} | Ctrl-C stops both processes", flush=True)
            while native.poll() is None and app.poll() is None:
                time.sleep(0.25)
            if monitor.guard:
                raise RuntimeError(monitor.guard)
            if native.poll() is not None or app.returncode:
                raise RuntimeError(
                    f"Server exited; native={native.poll()}, Strata={app.poll()}. See {folder}"
                )
        except KeyboardInterrupt:
            pass
        finally:
            stop_owned_processes((app, native))
            if monitor:
                (folder / "memory-summary.json").write_text(
                    json.dumps(monitor.finish(), indent=2) + "\n"
                )
            if (
                active_path.exists()
                and json.loads(active_path.read_text()).get("pid") == os.getpid()
            ):
                active_path.unlink()


if __name__ == "__main__":
    main()
