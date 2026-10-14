#!/usr/bin/env python3
"""N00: prompt-chunk dispatch inventory and command-buffer GPU time on the kept engine; no load without --run.

An inventory launch logs every encoded Metal dispatch with its tensor types and shapes, plus launch-wide fusion
counts. That needs debug verbosity and single-thread encoding, so its timings are discarded. A timing launch keeps
only command-buffer GPU timestamps. Neither changes kernels, fusion rules, weights or arithmetic. Each request reads
a fresh prompt and samples one token, so the results describe prompt reading only and are not a speed estimate.

Segments mode (N00b) uses the isolated m5-segments engine. Each profile runs twice in alternating order: once with
the segment timer, which gives every part of a chunk its own command buffer, and once without it as a control on the
same engine. Both record the sampled token's probabilities; the comparison reports whether every launch matched bit
for bit.

Overlap mode (N15) uses the isolated m5-overlap engine. Overlap launches give each model context its own Metal queue
and hold the helper's work on a prompt chunk until the target's next chunk is queued; serial launches leave both off.
Each profile runs both twice, in mirrored order. Each prompt is read three times as above and then answered three
times with a 128-token reply, so reply speed, drafts and text can be compared between the two.
"""

import argparse
from collections.abc import Callable, Sequence
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time
from typing import NamedTuple, cast

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
from overlap_ops import Launch, request_busy
from overlap_ops import compare as overlap_compare
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
    target_context,
)
from runtime_memory import admit_model, app_monitor
from segment_ops import (
    ChunkParts,
    by_graph,
    control_medians,
    fit,
    fit_parts,
    median_parts,
    output_parity,
    overhead,
    request_parts,
    segments,
)
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
REPEATS = {"inventory": 1, "timing": 3, "segments": 3, "control": 3, "overlap": 3, "serial": 3}
SEGMENT_MODES = ("segments", "control")
SEGMENT_ENGINE = "m5-segments"
SEGMENT_ENV = {"GGML_M5_LAB_SEGMENTS": "1"}
SEGMENT_MARKER = "use m5 segments    = true"
OVERLAP_MODES = ("overlap", "serial")
OVERLAP_ENGINE = "m5-overlap"
OVERLAP_ENV = {"GGML_M5_LAB_CONTEXT_QUEUE": "1", "GGML_M5_LAB_HELPER_OVERLAP": "1"}
OVERLAP_MARKERS = ("using a separate command queue for this context", "lab: deferring prompt-chunk helper decodes")
# Modes whose launches pair two variants on one engine; overlap mode runs each pair a second time in reverse.
PAIRED = {"segments": SEGMENT_MODES, "overlap": OVERLAP_MODES}
ROUNDS = {"segments": 1, "overlap": 2}
PARITY_MODES = (*SEGMENT_MODES, *OVERLAP_MODES)
ENGINES = {**dict.fromkeys(SEGMENT_MODES, SEGMENT_ENGINE), **dict.fromkeys(OVERLAP_MODES, OVERLAP_ENGINE)}
REPLIES = 3
REPLY_TOKENS = 128
# Probabilities for the sampled token's top candidates; computed on the CPU after the prompt's last chunk.
PROBABILITIES = 8
# The pinned common init warms up with BOS and EOS before the server accepts requests.
WARMUP_TOKENS = 2
# Graph and fusion debug output; fusion statistics also force single-thread, single-buffer encoding.
INVENTORY_ENV = {"GGML_METAL_GRAPH_DEBUG": "2", "GGML_METAL_FUSION_DEBUG": "1"}
LIMITATION = (
    "Inventory launches log at debug verbosity with single-thread encoding, so their timings are not used. "
    "Command-buffer intervals cover node ranges, not single kernels; this GPU timestamps only stage boundaries. "
    "Requests sample one token after a fresh prompt, so these are prompt-reading costs, not reply speed."
)
OVERLAP_LIMITATION = (
    "Overlap launches also answer each prompt three times with a 128-token reply at temperature 0; reply speed comes "
    "from those replies only and is compared between overlap and serial launches of the same profile."
)


class Steps(NamedTuple):
    """The parts of a guarded launch that differ between trials: server command, environment, requests, analysis."""

    command: Callable[[int, str, str], list[str]]
    env: Callable[[str], tuple[dict[str, str], JSONDict]]
    requests: Callable[[Path, JSONDict, str], None]
    analyze: Callable[[Path, JSONDict], None]
    limitation: str


# Trials in other modules that reuse this guarded launch register their own modes here.
OTHER_TRIALS: dict[str, Steps] = {}


def steps(mode: str) -> Steps:
    """A registered trial's steps, or this module's, looked up when the launch needs them."""
    if mode in OTHER_TRIALS:
        return OTHER_TRIALS[mode]
    limitation = LIMITATION if mode not in OVERLAP_MODES else f"{LIMITATION} {OVERLAP_LIMITATION}"
    return Steps(launch_command, launch_env, run_requests, analyze, limitation)


def launch_engine(mode: str) -> str:
    return ENGINES.get(mode, ENGINE)


def launch_command(port: int, profile: str, mode: str) -> list[str]:
    batch, ubatch = PROFILES[profile]
    command = list(kept_server(port, batch, ubatch, launch_engine(mode)))
    if mode == "inventory":
        command[command.index("--verbosity") + 1] = "5"
    return command


def launch_env(mode: str) -> tuple[dict[str, str], JSONDict]:
    env, flags = configure(os.environ, launch_engine(mode), "on", "small-reduce", profile=True)
    extra = {"inventory": INVENTORY_ENV, "segments": SEGMENT_ENV, "overlap": OVERLAP_ENV}.get(mode, {})
    env.update(extra)
    return env, {"metal": flags, "diagnostic_env": extra}


def measure(base: str, case: PromptCase, tokens: list[int], repeat: int, mode: str = "timing") -> JSONDict:
    payload: JSONDict = {
        "prompt": tokens,
        "n_predict": 1,
        "temperature": 0,
        "seed": 1234,
        "cache_prompt": False,
    }
    if mode in PARITY_MODES:
        payload["n_probs"] = PROBABILITIES
    begin = time.monotonic()
    response = request(base, "/completion", payload, timeout=900)
    end = time.monotonic()
    timings = cast(JSONDict, response["timings"])
    if timings["prompt_n"] != len(tokens):
        raise ValueError("The whole fresh prompt must be read")
    row: JSONDict = {
        "name": case["name"],
        "repeat": repeat,
        "prompt_tokens": len(tokens),
        "begin_monotonic_s": begin,
        "end_monotonic_s": end,
        "prompt_ms": timings["prompt_ms"],
        "prompt_tok_s": timings["prompt_per_second"],
    }
    if mode in PARITY_MODES:
        row["output"] = {"content": response["content"], "probabilities": response["completion_probabilities"]}
    return row


def reply(base: str, case: PromptCase, tokens: list[int], repeat: int) -> JSONDict:
    """One fresh prompt answered with up to REPLY_TOKENS tokens; speed, drafts and text for the comparison."""
    payload: JSONDict = {
        "prompt": tokens,
        "n_predict": REPLY_TOKENS,
        "temperature": 0,
        "seed": 1234,
        "cache_prompt": False,
    }
    response = request(base, "/completion", payload, timeout=900)
    timings = cast(JSONDict, response["timings"])
    if timings["prompt_n"] != len(tokens):
        raise ValueError("The whole fresh prompt must be read")
    return {
        "name": case["name"],
        "repeat": repeat,
        "prompt_ms": timings["prompt_ms"],
        "predicted_n": timings["predicted_n"],
        "tok_s": timings["predicted_per_second"],
        # The server leaves both counts out when nothing was drafted.
        "drafted": timings.get("draft_n", 0),
        "accepted": timings.get("draft_n_accepted", 0),
        "content": response["content"],
    }


def run_requests(folder: Path, result: JSONDict, base: str) -> None:
    for case in cases("balanced"):
        tokens = prompt_tokens(base, case["content"])
        if not tokens or len(tokens) + 1 > 4096:
            raise ValueError("Request exceeds frozen 4K context")
        for repeat in range(REPEATS[result["mode"]]):
            row = measure(base, case, tokens, repeat, result["mode"])
            result["requests"].append(row)
            write(folder / "result.json", result)
            print(
                f"{result['mode']}/{result['profile']}: {case['name']} r{repeat}: {len(tokens)} tokens, "
                f"prompt {row['prompt_tok_s']:.1f} tok/s",
                flush=True,
            )
        for repeat in range(REPLIES if result["mode"] in OVERLAP_MODES else 0):
            row = reply(base, case, tokens, repeat)
            result.setdefault("generations", []).append(row)
            write(folder / "result.json", result)
            print(
                f"{result['mode']}/{result['profile']}: {case['name']} reply {repeat}: {row['predicted_n']} tokens, "
                f"{row['tok_s']:.2f} tok/s, drafted {row['drafted']}, accepted {row['accepted']}",
                flush=True,
            )


def run_launch(folder: Path, result: JSONDict, owned: OwnedServer, frozen: Frozen) -> None:
    assert_no_model_server()
    check_frozen(frozen)
    result["settle"] = wait_for_headroom()
    result["preflight"] = preflight(False)
    result["power"] = power()
    port = free_port()
    trial = steps(result["mode"])
    command = trial.command(port, result["profile"], result["mode"])
    env, settings = trial.env(result["mode"])
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
        trial.requests(folder, result, base)


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


def segment_timing(lines: list[str], result: JSONDict) -> JSONDict:
    graphs = graph_times(command_buffers(lines))
    split = by_graph(segments(lines))
    rows: list[ChunkParts] = []
    for row in result["requests"]:
        window = (row["begin_monotonic_s"], row["end_monotonic_s"])
        row["parts"] = request_parts(graphs, split, window, row["prompt_tokens"], PROFILES[result["profile"]])
        rows.extend(row["parts"])
    return {"medians": median_parts(rows)}


def overlap_timing(lines: list[str], result: JSONDict) -> None:
    buffers = command_buffers(lines)
    target = target_context(graph_times(buffers))
    for row in result["requests"]:
        row["busy"] = request_busy(buffers, target, row["begin_monotonic_s"], row["end_monotonic_s"])


def check_markers(lines: list[str], mode: str) -> None:
    """The diagnostic switches reached the engine exactly in the launches that set them."""
    if mode in SEGMENT_MODES and any(SEGMENT_MARKER in line for line in lines) != (mode == "segments"):
        raise ValueError("The segment timer setting did not reach the engine")
    if mode in OVERLAP_MODES:
        for marker in OVERLAP_MARKERS:
            if any(marker in line for line in lines) != (mode == "overlap"):
                raise ValueError("The helper overlap settings did not reach the engine")


def analyze(folder: Path, result: JSONDict) -> None:
    lines = (folder / "native.log").read_text(errors="replace").splitlines()
    result["actual_chunks"] = chunk_receipt("\n".join(lines), result["profile"])
    check_markers(lines, result["mode"])
    if result["mode"] in ("timing", *PARITY_MODES):
        result["timing"] = timing(lines, result)
        if result["mode"] == "segments":
            result["segments"] = segment_timing(lines, result)
        if result["mode"] in OVERLAP_MODES:
            overlap_timing(lines, result)
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
            steps(result["mode"]).analyze(folder, result)
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
    result["limitation"] = steps(mode).limitation
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


def compare(results: Sequence[JSONDict]) -> JSONDict:
    """Part times and fits from segmented launches, unsegmented controls on the same engine, and output parity."""
    parts = [
        chunk
        for result in results
        if result["mode"] == "segments"
        for row in result["requests"]
        for chunk in row["parts"]
    ]
    medians = median_parts(parts)
    control = control_medians(
        row["gpu"]["chunks"] for result in results if result["mode"] == "control" for row in result["requests"]
    )
    points = [
        (cast(int, row["tokens"]), cast(int, row["position"]), cast(float, row["gpu_ms"])) for row in control.values()
    ]
    return {
        "segments": medians,
        "fits": fit_parts(medians),
        "control": control,
        "control_fit": fit(points),
        "segment_overhead_pct": overhead(medians, control),
        "parity": output_parity((row["name"], row["output"]) for result in results for row in result["requests"]),
    }


def launch_plan(mode: str, profiles: Sequence[str]) -> list[tuple[str, str]]:
    """(launch mode, profile) in order; paired modes alternate which variant of each pair runs first."""
    if mode not in PAIRED:
        return [(mode, profile) for profile in profiles]
    plan: list[tuple[str, str]] = []
    for i, profile in enumerate(profiles):
        for round_ in range(ROUNDS[mode]):
            pair = PAIRED[mode] if (i + round_) % 2 == 0 else PAIRED[mode][::-1]
            plan += [(variant, profile) for variant in pair]
    return plan


@cleanup_on_termination()
def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=("inventory", "timing", *PAIRED), required=True)
    ap.add_argument("--profile", action="append", choices=tuple(PROFILES), required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args(argv)
    plan = launch_plan(args.mode, args.profile)
    print(
        f"Plan: {args.mode} launches {'/'.join(f'{m}-{p}' if args.mode in PAIRED else p for m, p in plan)}; "
        f"{launch_engine(plan[0][0])} engine, "
        f"4K/F16/MTP3, four prompt cases, {REPEATS[args.mode]} fresh one-token request(s) each"
        f"{f', then {REPLIES} {REPLY_TOKENS}-token replies' if args.mode == 'overlap' else ''}.",
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
    results: list[JSONDict] = []
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for i, (mode, profile) in enumerate(plan):
            folder = args.output / f"launch-{i + 1}-{mode}-{profile}"
            results.append(launch(folder, mode, profile, frozen))
            summary["launches"].append(results[-1]["status"])
            write(args.output / "summary.json", summary)
    if args.mode == "segments":
        summary["analysis"] = compare(results)
        write(args.output / "summary.json", summary)
    if args.mode == "overlap":
        summary["analysis"] = overlap_compare(cast(list[Launch], results))
        write(args.output / "summary.json", summary)
    print("N00 launches passed:", json.dumps(summary["launches"]), flush=True)


if __name__ == "__main__":
    main()
