#!/usr/bin/env python3
"""Start Strata's Mac web app over the pinned native Metal engine. Ctrl-C stops both."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import fcntl
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import psutil
from collections.abc import Sequence
from typing import NotRequired, Protocol, TypedDict

from memory_monitor import Monitor, wait_ready
from lab import ROOT, server_command
from engines import ENGINES, verify_engine
from draft_vocab import experiment_environment
from check_memory import assert_no_model_server
from metal_environment import TUNING, configure
from runtime_profiles import lookup_command
from runtime_memory import MemoryPolicy, admit_model, app_monitor
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


class AppConfig(TypedDict):
    native_url: str
    model_name: str
    host: str
    fit_max_tokens: bool
    prompt_cache: bool
    performance: NotRequired[dict[str, object]]


@dataclass(frozen=True)
class LaunchContext:
    folder: Path
    active_path: Path
    config_path: Path
    config: AppConfig
    batch: int
    app_port: int
    native_port: int
    native_env: dict[str, str]
    receipts: dict[str, object]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n")


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
    ap.add_argument("--draft-placement", choices=["gpu", "cpu", "output", "mixed"], default="cpu")
    ap.add_argument("--draft-model", default="mtp")
    ap.add_argument("--draft-threads", type=int, help="CPU workers for the prediction helper only")
    ap.add_argument("--draft-p-min", type=float)
    ap.add_argument("--tensor-api", choices=["auto", "on", "off"], default="auto")
    ap.add_argument("--m5-tuning", choices=TUNING, default="stock")
    ap.add_argument("--prompt-cache", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--lookup-profile", choices=["off", "code-edit"], default="off")
    args = ap.parse_args(argv)
    if args.draft_vocab != "off" and args.spec != "draft-mtp":
        ap.error("The draft vocabulary requires --spec draft-mtp")
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        execute(args)


def prepare_launch(args: RunArguments) -> LaunchContext:
    batch: int = getattr(args, "batch", 512)
    if not 0 < args.ubatch <= batch <= args.context:
        raise ValueError("Prompt chunks must satisfy 0 < ubatch <= batch <= context; refusing silent clamping")
    # Reject unsupported lookup settings before any native process can launch.
    lookup_command(["--spec-type", args.spec], args)
    app_port, native_port = validated_ports(args)
    native_env, vocab_info = experiment_environment(args.engine, args.draft_vocab)
    native_env, metal_info = configure(native_env, args.engine, args.tensor_api, args.m5_tuning)
    assert_no_model_server()
    engine_info = verify_engine(args.engine)
    model_ids = [args.model] + ([args.draft_model] if args.spec == "draft-mtp" else [])
    model_info = verify_models(model_ids)
    assert_ports_available((app_port, native_port))
    folder = ROOT / "bench/runtime" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    folder.mkdir(parents=True)
    active_path = ROOT / "bench/runtime/active.json"
    write_json(
        active_path,
        {
            "pid": os.getpid(),
            "create_time": psutil.Process().create_time(),
            "model": args.model,
            "engine": args.engine,
            "port": app_port,
            "native_port": native_port,
            "log_directory": str(folder),
        },
    )
    config: AppConfig = {
        "native_url": f"http://127.0.0.1:{native_port}",
        "model_name": args.model,
        "host": "127.0.0.1",
        "fit_max_tokens": True,
        "prompt_cache": args.prompt_cache,
    }
    config_path = folder / "strata.json"
    write_json(config_path, config)
    receipts: dict[str, object] = {
        "engine": engine_info,
        "draft-vocabulary": vocab_info,
        "metal-environment": metal_info,
        "models": model_info,
    }
    return LaunchContext(folder, active_path, config_path, config, batch, app_port, native_port, native_env, receipts)


def prepare_native(args: RunArguments, launch: LaunchContext) -> tuple[list[str], MemoryPolicy]:
    command = server_command(
        args.model,
        launch.native_port,
        args.context,
        batch=launch.batch,
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
    write_json(launch.folder / "command.json", command)
    for name, receipt in launch.receipts.items():
        write_json(launch.folder / f"{name}.json", receipt)
    write_json(launch.folder / "settings.json", vars(args))
    policy = admit_model(args.model)
    write_json(launch.folder / "memory-policy.json", policy)
    performance: dict[str, object] = {
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
    performance.update(
        monitor_file=str(launch.folder / "memory.jsonl"),
        batch=launch.batch,
        initial_swap_bytes=policy["baseline"]["swap_used_bytes"],
    )
    launch.config["performance"] = performance
    write_json(launch.config_path, launch.config)
    return command, policy


def wait_for_exit(
    native: subprocess.Popen[bytes], app: subprocess.Popen[bytes], monitor: Monitor, launch: LaunchContext
) -> None:
    print(f"Strata: http://127.0.0.1:{launch.app_port} | native API: {launch.config['native_url']}/v1", flush=True)
    print(f"Logs: {launch.folder} | Ctrl-C stops both processes", flush=True)
    while native.poll() is None and app.poll() is None:
        time.sleep(0.25)
    if monitor.guard:
        raise RuntimeError(monitor.guard)
    if native.poll() is not None or app.returncode:
        raise RuntimeError(f"Server exited; native={native.poll()}, Strata={app.poll()}. See {launch.folder}")


@cleanup_on_termination()
def execute(args: RunArguments) -> None:
    launch = prepare_launch(args)
    native: subprocess.Popen[bytes] | None = None
    app: subprocess.Popen[bytes] | None = None
    monitor = None
    with (launch.folder / "native.log").open("w") as log:
        try:
            command, policy = prepare_native(args, launch)
            with defer_termination():
                native = subprocess.Popen(command, stdout=log, stderr=log, env=launch.native_env)
                monitor = app_monitor(native, launch.folder / "memory.jsonl", policy)
                monitor.thread.start()
            wait_ready(native, launch.config["native_url"])
            with defer_termination():
                app = subprocess.Popen(
                    [
                        sys.executable,
                        str(ROOT / "scripts/strata_server.py"),
                        "--engine",
                        "metal-native",
                        "--config",
                        str(launch.config_path),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(launch.app_port),
                    ]
                )
            wait_for_exit(native, app, monitor, launch)
        except KeyboardInterrupt:
            pass
        finally:
            stop_owned_processes((app, native))
            if monitor:
                write_json(launch.folder / "memory-summary.json", monitor.finish())
            if launch.active_path.exists() and json.loads(launch.active_path.read_text()).get("pid") == os.getpid():
                launch.active_path.unlink()


if __name__ == "__main__":
    main()
