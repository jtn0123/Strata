#!/usr/bin/env python3
"""N06: MTP draft state across context checkpoint restores, on the isolated m5-mtpstate engine; no load without --run.

Two launch modes on the same engine, each with the state trace on: stale (the pinned behaviour, which pairs the
first token after a restore with the row the previous request left) and restore (the row saved with the checkpoint,
llama.cpp PR 30141). Each runs twice, in the order stale, restore, restore, stale, with the default 512-token prompt
chunks and the server's prompt cache on, as a chat client uses it.

Every launch holds one conversation per standard prompt case, through the chat endpoint with a 128-token reply
limit: the first reply, the same request again (regenerate), a follow-up turn after the first reply, and the same
follow-up edited. One warm-up request comes first in every launch and is not compared.
"""

import argparse
from collections.abc import Sequence
import fcntl
import json
import os
from pathlib import Path
import time
from typing import cast

from benchmark import JSONDict
from benchmark_prompt_chunks import Frozen, cases, chunk_receipt, closure
from benchmark_signals import cleanup_on_termination
from check_memory import assert_no_model_server
from engines import verify_engine
from lab import ROOT, request
from metal_environment import configure
from model_provenance import verify_models
from mtpstate_ops import MODES, Launch, compare, parse, request_state
import profile_prompt_ops as guarded
from trial_support import kept_server, write
from validate_offline import require_pass

ENGINE = "m5-mtpstate"
PROFILE = "512"
REPLY_TOKENS = 128
FOLLOW_UP = "Now say that again in one short sentence."
EDIT = "Now give the two most important points as a short bulleted list."
LIMITATION = (
    "Greedy replies through the chat endpoint with the prompt cache on. Restores happen where the server finds a "
    "usable checkpoint; the trace counts them per request. The reply limit caps most replies, so acceptance is "
    "compared over the same capped requests in both modes."
)


def monotonic_us() -> int:
    """The engine's clock: ggml_time_us reads CLOCK_MONOTONIC."""
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC) // 1000


def launch_plan() -> list[str]:
    # Each mode twice; the second round reverses the first so both modes have the same mean position.
    return [*MODES, *MODES[::-1]]


def state_env(mode: str) -> tuple[dict[str, str], JSONDict]:
    env, flags = configure(os.environ, ENGINE, "on", "small-reduce")
    extra = {"GGML_M5_LAB_MTP_STATE_TRACE": "1"}
    if mode == "restore":
        extra["GGML_M5_LAB_MTP_STATE"] = "restore"
    env.update(extra)
    return env, {"metal": flags, "diagnostic_env": extra}


def state_command(port: int, profile: str, mode: str) -> list[str]:
    verify_engine(ENGINE)
    batch, ubatch = guarded.PROFILES[profile]
    return list(kept_server(port, batch, ubatch, ENGINE))


def chat(base: str, row: JSONDict, messages: list[dict[str, str]], max_tokens: int) -> JSONDict:
    payload: JSONDict = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0,
        "seed": 1234,
        "cache_prompt": True,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    begin = monotonic_us()
    response = request(base, "/v1/chat/completions", payload, timeout=900)
    end = monotonic_us()
    timings = cast(JSONDict, response["timings"])
    choice = cast(list[JSONDict], response["choices"])[0]
    return {
        **row,
        "begin_us": begin,
        "end_us": end,
        "prompt_n": timings["prompt_n"],
        "cache_n": timings["cache_n"],
        "prompt_ms": timings["prompt_ms"],
        "predicted_n": timings["predicted_n"],
        "tok_s": timings["predicted_per_second"],
        "drafted": timings.get("draft_n", 0),
        "accepted": timings.get("draft_n_accepted", 0),
        "content": cast(JSONDict, choice["message"])["content"],
    }


def record(folder: Path, result: JSONDict, row: JSONDict) -> JSONDict:
    result["requests"].append(row)
    write(folder / "result.json", result)
    print(
        f"{result['mode']}: {row['name']} {row['kind']}: {row['prompt_n']} new and {row['cache_n']} cached tokens, "
        f"{row['predicted_n']} tokens at {row['tok_s']:.2f} tok/s, {row['accepted']}/{row['drafted']} drafts accepted",
        flush=True,
    )
    return row


def state_requests(folder: Path, result: JSONDict, base: str) -> None:
    warmup = cases("balanced")[-1]
    opening = [{"role": "user", "content": warmup["content"]}]
    record(folder, result, chat(base, {"name": warmup["name"], "kind": "warmup"}, opening, 1))
    for case in cases("balanced"):
        opening = [{"role": "user", "content": case["content"]}]
        first = record(folder, result, chat(base, {"name": case["name"], "kind": "first"}, opening, REPLY_TOKENS))
        record(folder, result, chat(base, {"name": case["name"], "kind": "regenerate"}, opening, REPLY_TOKENS))
        reply = {"role": "assistant", "content": cast(str, first["content"])}
        for kind, text in (("follow-up", FOLLOW_UP), ("edit", EDIT)):
            messages = [*opening, reply, {"role": "user", "content": text}]
            record(folder, result, chat(base, {"name": case["name"], "kind": kind}, messages, REPLY_TOKENS))


def state_analyze(folder: Path, result: JSONDict) -> None:
    lines = (folder / "native.log").read_text(errors="replace").splitlines()
    result["actual_chunks"] = chunk_receipt("\n".join(lines), result["profile"])
    restore = result["mode"] == "restore"
    marker = f"lab: MTP checkpoint state {'restore' if restore else 'stale'}, trace on"
    if not any(marker in line for line in lines):
        raise ValueError(f"Missing engine marker: {marker}")
    events = parse(lines)
    applied = [e["applied"] for e in events if e["event"] == "restore" and e["valid"]]
    if not applied or set(applied) != {restore}:
        raise ValueError("The state setting did not reach the engine, or no checkpoint was restored")
    for row in result["requests"]:
        row["state"] = request_state(events, row["begin_us"], row["end_us"])
    result["checkpoints_max"] = max(
        (
            int(line.split("created context checkpoint ", 1)[1].split()[0])
            for line in lines
            if "created context checkpoint " in line
        ),
        default=0,
    )


STEPS = guarded.Steps(state_command, state_env, state_requests, state_analyze, LIMITATION)
guarded.OTHER_TRIALS.update(dict.fromkeys(MODES, STEPS))


@cleanup_on_termination()
def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args(argv)
    plan = launch_plan()
    print(
        f"Plan: {'/'.join(plan)} on {ENGINE}, 4K/F16/MTP3 at {PROFILE}; one conversation per standard case, "
        f"first reply, regenerate, follow-up and edited follow-up, each up to {REPLY_TOKENS} tokens.",
        flush=True,
    )
    if not args.run:
        return
    assert_no_model_server()
    require_pass()
    args.output.mkdir(parents=True, exist_ok=False)
    frozen: Frozen = {"closure": closure(), "models": verify_models(["flash", "mtp_shared_packed_q3"])}
    summary: JSONDict = {"schema": 1, "plan": plan, "frozen": frozen, "engine": verify_engine(ENGINE), "launches": []}
    results: list[JSONDict] = []
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for i, mode in enumerate(plan):
            results.append(guarded.launch(args.output / f"launch-{i + 1}-{mode}", mode, PROFILE, frozen))
            summary["launches"].append(results[-1]["status"])
            write(args.output / "summary.json", summary)
    summary["analysis"] = compare(cast(list[Launch], results))
    write(args.output / "summary.json", summary)
    print("N06 launches passed:", json.dumps(summary["launches"]), flush=True)


if __name__ == "__main__":
    main()
