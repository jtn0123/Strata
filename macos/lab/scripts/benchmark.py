#!/usr/bin/env python3
"""Run fixed workloads, preserve raw results, and monitor Mac memory pressure."""

import argparse
import csv
from datetime import UTC, datetime
import fcntl
import json
import platform
import socket
import statistics
import subprocess
import time
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

import psutil
from lab import ROOT, request, server_command
from engines import ENGINES, verify_engine
from draft_vocab import experiment_environment
from check_memory import assert_no_model_server
from metal_environment import TUNING, configure
from benchmark_metrics import case_metrics, completion_counts
from benchmark_signals import cleanup_on_termination, defer_termination
from model_provenance import ModelVerification, assert_unchanged, verify_models
from memory_monitor import Monitor as Monitor, OwnedProcess, wait_ready as wait_ready
from trial_workloads import TrialWorkloads, measure_workloads


JSONDict = dict[str, Any]


def command_output(command: Sequence[str]) -> str:
    return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()


def host_snapshot() -> JSONDict:
    return {
        "os": platform.platform(),
        "machine": platform.machine(),
        "chip": command_output(["sysctl", "-n", "machdep.cpu.brand_string"]),
        "ram_bytes": psutil.virtual_memory().total,
        "cpu_count": psutil.cpu_count(),
        "power": command_output(["pmset", "-g", "batt"]),
        "power_settings": command_output(["pmset", "-g", "custom"]),
        "thermal_status": command_output(["pmset", "-g", "therm"]),
        "gpu_wired_limit": command_output(["sysctl", "iogpu.wired_limit_mb"]),
        "vm_stat": command_output(["vm_stat"]),
        "swap": psutil.swap_memory()._asdict(),
        "available_bytes": psutil.virtual_memory().available,
    }


class _Receipt:
    def __init__(self, path: Path, record: JSONDict) -> None:
        self.path, self.record = path, record

    def save(self) -> None:
        self.path.write_text(json.dumps(self.record, indent=2) + "\n")


class _PreparedTrial(NamedTuple):
    base: str
    command: list[str]
    environment: dict[str, str]
    model_proof: ModelVerification
    engine_info: Mapping[str, Any]


def stream_completion(
    base: str, payload: JSONDict, observer: Callable[[JSONDict, float], None] | None = None
) -> JSONDict:
    started, first, final = time.monotonic(), None, None
    text, ids = [], []
    req = urllib.request.Request(
        base + "/completion", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=600) as response:
        for line in response:
            if not line.startswith(b"data: "):
                continue
            item = json.loads(line[6:])
            if observer is not None:
                observer(item, time.monotonic() - started)
            if first is None and (item.get("tokens") or item.get("content")):
                first = time.monotonic()
            text.append(item.get("content", ""))
            ids.extend(item.get("tokens", []))
            if item.get("stop"):
                final = item
    elapsed = time.monotonic() - started
    if final is None or first is None:
        raise RuntimeError("Streaming response has no first token or final timing record")
    prompt = payload.get("prompt")
    completion_counts(
        final["timings"],
        ids,
        len(prompt) if isinstance(prompt, list) else None,
        cached=bool(payload.get("cache_prompt")),
        max_new=payload.get("n_predict"),
    )
    return {
        "ttft_s": first - started,
        "wall_s": elapsed,
        "text": "".join(text),
        "generated_token_ids": ids,
        "final": final,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("model", choices=["small", "flash"])
    ap.add_argument("--label", required=True)
    ap.add_argument("--engine", choices=ENGINES, default="baseline")
    ap.add_argument("--draft-vocab", choices=["off", "106k"], default="off")
    ap.add_argument("--real-workloads", action="store_true")
    ap.add_argument("--cached-workloads", action="store_true")
    ap.add_argument("--context", type=int, default=4096)
    ap.add_argument("--batch", type=int, default=512)
    ap.add_argument("--ubatch", type=int, default=128)
    ap.add_argument("--cache-type", default="f16", choices=["f16", "q8_0", "q4_0"])
    ap.add_argument("--spec", default="none", choices=["none", "draft-mtp"])
    ap.add_argument("--draft", type=int, default=3)
    ap.add_argument("--draft-placement", choices=["gpu", "cpu", "output", "mixed"], default="gpu")
    ap.add_argument("--draft-model", default="mtp")
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--draft-threads", type=int)
    ap.add_argument("--draft-p-min", type=float)
    ap.add_argument("--tensor-api", choices=["auto", "on", "off"], default="auto")
    ap.add_argument("--m5-tuning", choices=TUNING, default="stock")
    ap.add_argument("--temperature", type=float, default=0)
    ap.add_argument("--extended-checks", action="store_true")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--warmups", type=int, default=0)
    ap.add_argument("--predict", type=int, default=128)
    ap.add_argument("--prompts", type=int, nargs="+", default=[512, 2048])
    args = ap.parse_args()
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert_no_model_server()
        record = run(args)
        if record["status"] != "passed":
            raise SystemExit(1)


def _source_receipts(record: JSONDict) -> None:
    record["actual_sources"] = {}
    for name, directory in [("llama_cpp", "llama.cpp"), ("strata_macos", "Strata-macOS")]:
        path = ROOT / "vendor" / directory
        revision = command_output(["git", "-C", str(path), "rev-parse", "HEAD"])
        dirty = command_output(["git", "-C", str(path), "status", "--porcelain"])
        record["actual_sources"][name] = {"revision": revision, "dirty": dirty}
        if revision != record["runtime"][name]["revision"] or dirty:
            raise RuntimeError(f"Unpinned or modified source checkout: {directory}")


def _prepare_trial(args: argparse.Namespace, run_id: str, engine: str, receipt: _Receipt) -> _PreparedTrial:
    engine_info = verify_engine(engine)
    vocab_mode = getattr(args, "draft_vocab", "off")
    if vocab_mode != "off" and args.spec != "draft-mtp":
        raise ValueError("A draft vocabulary can only be used with prediction enabled")
    env, vocab_info = experiment_environment(engine, vocab_mode)
    env, metal_info = configure(env, engine, getattr(args, "tensor_api", "auto"), getattr(args, "m5_tuning", "stock"))
    model_ids = [args.model] + ([args.draft_model] if args.spec == "draft-mtp" else [])
    model_proof = verify_models(model_ids, ROOT)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    command = server_command(
        args.model,
        port,
        args.context,
        args.batch,
        args.ubatch,
        args.spec,
        args.draft,
        args.cache_type,
        args.threads,
        args.draft_placement,
        args.draft_model,
        engine=engine,
        draft_threads=getattr(args, "draft_threads", None),
        draft_p_min=getattr(args, "draft_p_min", None),
    )
    receipt.record = {
        "schema": 1,
        "run_id": run_id,
        "status": "running",
        "settings": vars(args),
        "command": command,
        "runtime": json.loads((ROOT / "config/runtime.json").read_text()),
        "model": json.loads((ROOT / "config/models.json").read_text())[args.model],
        "host_before": host_snapshot(),
        "cases": [],
        "warmups": [],
        "checks": [],
        "selected_engine": engine_info,
        "model_provenance": model_proof,
        "draft_vocabulary": vocab_info,
        "metal_environment": metal_info,
        "method": "Single slot, full Metal offload, fixed seed 1234; sampling temperature is recorded in settings. Exact synthetic chat prompt sizes and fixed output count from settings; no prompt reuse; ignore EOS for timing only. No model downloads during a run. Warm OS file cache is uncontrolled. TTFT includes HTTP and prompt evaluation. Correctness checks use normal EOS handling.",
    }
    record = receipt.record
    _source_receipts(record)
    record["binary_version"] = command_output([command[0], "--version"])
    if args.spec == "draft-mtp":
        record["draft_model"] = json.loads((ROOT / "config/models.json").read_text())[args.draft_model]
    receipt.save()
    return _PreparedTrial(base, command, env, model_proof, engine_info)


def _stop_trial(process: OwnedProcess | None, monitor: Monitor | None, record: JSONDict) -> None:
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    if monitor:
        record["memory"] = monitor.finish()
        if record["memory"]["guard"] or not record["memory"]["monitor_healthy"]:
            record["status"] = "failed"
            record.setdefault("error", record["memory"]["guard"] or "Memory monitoring was incomplete")


def _summarize_cases(record: JSONDict) -> None:
    if record["cases"]:
        record["summary"] = [
            {
                "workload": name,
                "prompt_tokens": n,
                **{
                    "median_" + metric: statistics.median(
                        c[metric] for c in record["cases"] if c["prompt_tokens"] == n and c["workload"] == name
                    )
                    for metric in ("generation_tok_s", "ttft_s", "prompt_tok_s")
                },
            }
            for name, n in sorted({(c["workload"], c["prompt_tokens"]) for c in record["cases"]})
        ]


def _publish_cases(folder: Path, receipt: _Receipt) -> None:
    record = receipt.record
    save = receipt.save
    save()
    with (folder / "cases.csv").open("w", newline="") as output:
        keys = [
            "workload",
            "prompt_tokens",
            "repeat",
            "ttft_s",
            "wall_s",
            "prompt_tok_s",
            "generation_tok_s",
            "output_tokens",
        ]
        writer = csv.DictWriter(output, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(record["cases"])
    print(f"Saved {receipt.path}", flush=True)


def _finish_trial(
    engine: str,
    prepared: _PreparedTrial,
    process: OwnedProcess | None,
    monitor: Monitor | None,
    folder: Path,
    receipt: _Receipt,
) -> None:
    record = receipt.record
    try:
        _stop_trial(process, monitor, record)
        assert_unchanged(prepared.model_proof, ROOT)
        if verify_engine(engine) != prepared.engine_info:
            raise RuntimeError("Native engine changed during benchmark")
        record["host_after"] = host_snapshot()
        _summarize_cases(record)
        _publish_cases(folder, receipt)
    except BaseException as error:
        record.update(status="failed", cleanup_error=f"{type(error).__name__}: {error}")
        record.setdefault("error", record["cleanup_error"])
    finally:
        receipt.save()


@cleanup_on_termination()
def run(args: argparse.Namespace) -> JSONDict:
    engine = getattr(args, "engine", "baseline")
    warmups = getattr(args, "warmups", 0)
    if args.repeats < 1 or warmups < 0:
        raise ValueError("Use at least one measured repeat and nonnegative warmups")
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + args.label
    folder = ROOT / "bench/results" / run_id
    folder.mkdir()
    receipt = _Receipt(
        folder / "result.json", {"schema": 1, "run_id": run_id, "status": "running", "settings": vars(args)}
    )
    receipt.save()
    try:
        prepared = _prepare_trial(args, run_id, engine, receipt)
    except BaseException as error:
        receipt.record.update(status="failed", error=f"{type(error).__name__}: {error}", preparation_failed=True)
        receipt.save()
        raise
    process, monitor = None, None
    with (folder / "server.log").open("w") as log:
        try:
            started = time.monotonic()
            if getattr(args, "require_quiet_host", False):
                from profile_m5_routes import preflight

                receipt.record["launch_preflight"] = preflight(small=args.model != "flash")
                receipt.save()
            launch_baseline = Monitor.baseline()
            with defer_termination():
                process = subprocess.Popen(prepared.command, stdout=log, stderr=log, env=prepared.environment)
                monitor = Monitor(
                    process,
                    folder / "memory.jsonl",
                    getattr(args, "swap_guard_bytes", 2 * 1024**3),
                    getattr(args, "minimum_available_bytes", 384 * 1024**2),
                    baseline=launch_baseline,
                )
                monitor.thread.start()
            record = receipt.record
            record["ready_s"] = wait_ready(process, prepared.base)
            record["props"] = request(prepared.base, "/props")
            print(f"{run_id}: ready in {record['ready_s']:.2f}s", flush=True)
            measure_workloads(
                TrialWorkloads(
                    args=args,
                    base=prepared.base,
                    folder=folder,
                    record=record,
                    save=receipt.save,
                    warmups=warmups,
                    root=ROOT,
                    request=request,
                    stream_completion=stream_completion,
                    case_metrics=case_metrics,
                    disk_io_counters=psutil.disk_io_counters,
                    swap_used=lambda: psutil.swap_memory().used,
                )
            )
            record["run_wall_s"] = time.monotonic() - started
            record["status"] = (
                "passed" if all(case["passed"] for case in record["checks"]) else "completed-check-failure"
            )
        except BaseException as error:
            receipt.record["status"], receipt.record["error"] = "failed", f"{type(error).__name__}: {error}"
            raise
        finally:
            _finish_trial(engine, prepared, process, monitor, folder, receipt)
    return receipt.record


if __name__ == "__main__":
    main()
