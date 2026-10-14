#!/usr/bin/env python3
"""N00: prompt-chunk dispatch inventory and command-buffer GPU time on the kept engine; no load without --run.

An inventory launch logs every encoded Metal dispatch with its tensor types and shapes, plus launch-wide fusion
counts. That needs debug verbosity and single-thread encoding, so its timings are discarded. A timing launch keeps
only command-buffer GPU timestamps. Neither changes kernels, fusion rules, weights or arithmetic. Each request reads
a fresh prompt and samples one token, so the results describe prompt reading only and are not a speed estimate.
"""

import argparse
from collections.abc import Sequence
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time
from typing import cast

from benchmark import JSONDict, wait_ready
from benchmark_m5_next import wait_for_headroom
from benchmark_prompt_chunks import (
    Frozen,
    PromptCase,
    cases,
    check_frozen,
    chunk_receipt,
    closure,
)
from benchmark_signals import cleanup_on_termination, defer_termination
from check_memory import assert_no_model_server
from lab import ROOT, request
from metal_environment import configure
from model_provenance import verify_models
from profile_m5_routes import preflight
from prompt_ops import (
    ChunkTime,
    chunk_sizes,
    command_buffers,
    dispatch_graphs,
    fusion_counts,
    graph_times,
    inventory,
    label_graphs,
    median_by_size,
    request_graphs,
)
from runtime_memory import admit_model, app_monitor
from trial_support import (
    ENGINE,
    OwnedServer,
    clean_memory,
    free_port,
    kept_server,
    power,
    prompt_tokens,
    stop_owned,
    write,
)
from validate_offline import require_pass

PROFILES = {"512": (512, 512), "1536": (1536, 1536)}
REPEATS = {"inventory": 1, "timing": 3}
# The pinned common init warms up with BOS and EOS before the server accepts requests.
WARMUP_TOKENS = 2
# Graph and fusion debug output; fusion statistics also force single-thread, single-buffer encoding.
INVENTORY_ENV = {"GGML_METAL_GRAPH_DEBUG": "2", "GGML_METAL_FUSION_DEBUG": "1"}
LIMITATION = (
    "Inventory launches log at debug verbosity with single-thread encoding, so their timings are not used. "
    "Command-buffer intervals cover node ranges, not single kernels; this GPU timestamps only stage boundaries. "
    "Requests sample one token after a fresh prompt, so these are prompt-reading costs, not reply speed."
)


def launch_command(port: int, profile: str, mode: str) -> list[str]:
    batch, ubatch = PROFILES[profile]
    command = list(kept_server(port, batch, ubatch))
    if mode == "inventory":
        command[command.index("--verbosity") + 1] = "5"
    return command


def launch_env(mode: str) -> tuple[dict[str, str], JSONDict]:
    env, flags = configure(os.environ, ENGINE, "on", "small-reduce", profile=True)
    extra = INVENTORY_ENV if mode == "inventory" else {}
    env.update(extra)
    return env, {"metal": flags, "diagnostic_env": extra}


def measure(base: str, case: PromptCase, tokens: list[int], repeat: int) -> JSONDict:
    payload = {
        "prompt": tokens,
        "n_predict": 1,
        "temperature": 0,
        "seed": 1234,
        "cache_prompt": False,
    }
    begin = time.monotonic()
    response = request(base, "/completion", payload, timeout=900)
    end = time.monotonic()
    timings = cast(JSONDict, response["timings"])
    if timings["prompt_n"] != len(tokens):
        raise ValueError("The whole fresh prompt must be read")
    return {
        "name": case["name"],
        "repeat": repeat,
        "prompt_tokens": len(tokens),
        "begin_monotonic_s": begin,
        "end_monotonic_s": end,
        "prompt_ms": timings["prompt_ms"],
        "prompt_tok_s": timings["prompt_per_second"],
    }


def run_requests(folder: Path, result: JSONDict, base: str) -> None:
    for case in cases("balanced"):
        tokens = prompt_tokens(base, case["content"])
        if not tokens or len(tokens) + 1 > 4096:
            raise ValueError("Request exceeds frozen 4K context")
        for repeat in range(REPEATS[result["mode"]]):
            row = measure(base, case, tokens, repeat)
            result["requests"].append(row)
            write(folder / "result.json", result)
            print(
                f"{result['mode']}/{result['profile']}: {case['name']} r{repeat}: {len(tokens)} tokens, "
                f"prompt {row['prompt_tok_s']:.1f} tok/s",
                flush=True,
            )


def run_launch(folder: Path, result: JSONDict, owned: OwnedServer, frozen: Frozen) -> None:
    assert_no_model_server()
    check_frozen(frozen)
    result["settle"] = wait_for_headroom()
    result["preflight"] = preflight(False)
    result["power"] = power()
    port = free_port()
    command = launch_command(port, result["profile"], result["mode"])
    env, settings = launch_env(result["mode"])
    policy = admit_model("flash")
    result.update(command=command, settings=settings, memory_policy=policy)
    write(folder / "result.json", result)
    with (folder / "native.log").open("w") as log:
        with defer_termination():
            owned.process = subprocess.Popen(command, env=env, stdout=log, stderr=log)
            result["models_loaded"] = True
            owned.monitor = app_monitor(owned.process, folder / "memory.jsonl", policy)
            owned.monitor.thread.start()
        write(folder / "result.json", result)
        base = f"http://127.0.0.1:{port}"
        result["ready_s"] = wait_ready(owned.process, base)
        run_requests(folder, result, base)


def schedule(result: JSONDict) -> list[int]:
    """Warm-up, then every request's prompt batches in order."""
    batch, ubatch = PROFILES[result["profile"]]
    chunks = [size for row in result["requests"] for size in chunk_sizes(row["prompt_tokens"], batch, ubatch)]
    return [WARMUP_TOKENS, *chunks]


def timing(lines: list[str], result: JSONDict) -> JSONDict:
    graphs = graph_times(command_buffers(lines))
    batch, ubatch = PROFILES[result["profile"]]
    rows: list[ChunkTime] = []
    for row in result["requests"]:
        window = request_graphs(
            graphs,
            row["begin_monotonic_s"],
            row["end_monotonic_s"],
            row["prompt_tokens"],
            batch,
            ubatch,
        )
        row["gpu"] = window
        rows.extend(window["chunks"])
    warm = [chunk for row in result["requests"] if row["repeat"] > 0 for chunk in row["gpu"]["chunks"]]
    return {
        "all_requests": median_by_size(rows),
        "repeats_after_first": median_by_size(warm),
    }


def analyze(folder: Path, result: JSONDict) -> None:
    lines = (folder / "native.log").read_text(errors="replace").splitlines()
    result["actual_chunks"] = chunk_receipt("\n".join(lines), result["profile"])
    if result["mode"] == "timing":
        result["timing"] = timing(lines, result)
        return
    graphs = dispatch_graphs(lines)
    labels = label_graphs(graphs, schedule(result))
    result["fusion"] = {
        "launch_patterns": fusion_counts(lines),
        "fused_nodes": sum(d["fused"] for graph in graphs for d in graph["dispatches"]),
        "unencoded_nodes": sum(graph["unencoded"] for graph in graphs),
    }
    write(folder / "inventory.json", inventory(graphs, labels))


def finish_launch(folder: Path, result: JSONDict, owned: OwnedServer, frozen: Frozen) -> None:
    stop_owned(owned.process, 5, 5)
    if owned.monitor:
        result["memory"] = owned.monitor.finish()
    try:
        assert_no_model_server()
        check_frozen(frozen)
        if result["status"] == "completed":
            if not clean_memory(result["memory"]):
                raise RuntimeError("RAM/swap/cleanup gate failed")
            analyze(folder, result)
            result["status"] = "passed"
    except BaseException as error:
        result.update(status="failed", error=f"{type(error).__name__}: {error}")
    write(folder / "result.json", result)


def launch(folder: Path, mode: str, profile: str, frozen: Frozen) -> JSONDict:
    folder.mkdir()
    result: JSONDict = {
        "status": "running",
        "mode": mode,
        "profile": profile,
        "requests": [],
        "models_loaded": False,
    }
    result["limitation"] = LIMITATION
    owned = OwnedServer()
    try:
        run_launch(folder, result, owned, frozen)
        result["status"] = "completed"
    except BaseException as error:
        result.update(status="failed", error=f"{type(error).__name__}: {error}")
    finally:
        finish_launch(folder, result, owned, frozen)
    if result["status"] != "passed":
        raise RuntimeError(result.get("error", "Launch failed"))
    return result


@cleanup_on_termination()
def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=tuple(REPEATS), required=True)
    ap.add_argument("--profile", action="append", choices=tuple(PROFILES), required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args(argv)
    print(
        f"Plan: {args.mode} launches {'/'.join(args.profile)}; kept engine, 4K/F16/MTP3, four prompt cases, "
        f"{REPEATS[args.mode]} fresh one-token request(s) each.",
        flush=True,
    )
    if not args.run:
        return
    assert_no_model_server()
    require_pass()
    args.output.mkdir(parents=True, exist_ok=False)
    frozen: Frozen = {
        "closure": closure(),
        "models": verify_models(["flash", "mtp_shared_packed_q3"]),
    }
    summary: JSONDict = {
        "schema": 1,
        "mode": args.mode,
        "order": args.profile,
        "frozen": frozen,
        "launches": [],
    }
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for i, profile in enumerate(args.profile):
            folder = args.output / f"launch-{i + 1}-{args.mode}-{profile}"
            summary["launches"].append(launch(folder, args.mode, profile, frozen)["status"])
            write(args.output / "summary.json", summary)
    print("N00 launches passed:", json.dumps(summary["launches"]), flush=True)


if __name__ == "__main__":
    main()
