#!/usr/bin/env python3
"""N15 qualification: the helper overlap as an app setting, in three A/B/B/A brackets; no load without --run.

Each bracket runs the prompt-chunk protocol (benchmark_prompt_chunks.py) with the kept engine and switches as the
control and m5-overlap with the overlap-reduce switches as the candidate, at an unchanged chunk size:
- default: the default app, balanced drafting at 512-token chunks;
- code-edit: the Code Editing app, code-edit drafting at 512;
- long-documents: the Long Documents app, balanced drafting at 1,536.

After its timed requests, every launch runs the lifecycle checks described in qualify_ops.py: conversations with
regenerate and edit, a request cancelled while the server reads its prompt, its resume, and a fresh repeat. The
decision rule is fixed in qualify_ops.py before the run.
"""

import argparse
from collections.abc import Sequence
import http.client
import json
from pathlib import Path
import select
import socket
import time
from typing import cast
from urllib.parse import urlsplit

from benchmark import JSONDict
from benchmark_prompt_chunks import (
    MAX_OUTPUT,
    REPEATS,
    Frozen,
    PromptCase,
    campaign,
    cases,
    closure,
    measure_repeat,
    quality,
)
from benchmark_signals import cleanup_on_termination
from check_memory import assert_no_model_server
from lab import ROOT, request
from model_provenance import verify_models
from profile_mtpstate import EDIT, FOLLOW_UP, chat
from qualify_ops import (
    RULE,
    Bracket,
    Cancel,
    LaunchMemory,
    Lifecycle,
    Resume,
    Turn,
    decision,
    lifecycle_bracket,
    memory,
)
from trial_support import prompt_tokens, write
from validate_offline import require_pass

CANDIDATE = "overlap"
# App bracket: (draft profile, chunk size).
BRACKETS = {"default": ("balanced", "512"), "code-edit": ("code-edit", "512"), "long-documents": ("balanced", "1536")}
# The server checks for a closed connection once a second; at 0.5 s the stop lands within the first one or two
# chunks of a 2,332-token prompt (N15 read it in about 4 s at both chunk sizes).
CANCEL_AFTER_S = 0.5
CONVERSATION_TOKENS = 256
STOP = "stop processing: n_tokens = "
RESTORED = "restored context checkpoint"
# Run folders stay under bench/features, where raw measurements are ignored.
FEATURES = ROOT / "bench/features"
SUMMARY = "summary.json"


def output_folder(path: Path) -> Path:
    """A run folder inside bench/features, resolved before anything is read or written there."""
    folder = path.resolve()
    features = FEATURES.resolve()
    if folder == features or not folder.is_relative_to(features):
        raise ValueError("The output folder must be inside bench/features")
    return folder


def log_size(folder: Path) -> int:
    return (folder / "native.log").stat().st_size


def log_since(folder: Path, offset: int) -> str:
    with (folder / "native.log").open("rb") as log:
        log.seek(offset)
        return log.read().decode(errors="replace")


def stops(text: str) -> list[int]:
    """Cached tokens of each request the server stopped, in order."""
    return [int(line.split(STOP, 1)[1].split(",", 1)[0]) for line in text.splitlines() if STOP in line]


def wait_stop(folder: Path, offset: int, timeout_s: float = 60) -> int:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        found = stops(log_since(folder, offset))
        if found:
            return found[0]
        time.sleep(0.1)
    raise RuntimeError("The cancelled request did not stop")


def abort(base: str, tokens: list[int], after_s: float) -> bool:
    """Stream a request, close the connection after after_s, and say whether reply data had arrived by then."""
    connection = http.client.HTTPConnection(urlsplit(base).netloc, timeout=60)
    payload = {
        "prompt": tokens,
        "n_predict": MAX_OUTPUT,
        "temperature": 0,
        "seed": 1234,
        "cache_prompt": True,
        "stream": True,
    }
    connection.request("POST", "/completion", json.dumps(payload), {"Content-Type": "application/json"})
    time.sleep(after_s)
    sock = connection.sock
    received = b""
    while select.select([sock], [], [], 0)[0] and (chunk := sock.recv(65536)):
        received += chunk
    sock.shutdown(socket.SHUT_RDWR)
    connection.close()
    # The server sends its headers when it starts reading a streamed prompt; reply text comes as "data:" events.
    return b"data:" in received


def resume(base: str, case: PromptCase, tokens: list[int], fresh: str) -> Resume:
    payload = {
        "prompt": tokens,
        "n_predict": MAX_OUTPUT,
        "temperature": 0,
        "seed": 1234,
        "cache_prompt": True,
        "return_tokens": True,
    }
    response = request(base, "/completion", payload, timeout=900)
    timings = cast(JSONDict, response["timings"])
    text = cast(str, response["content"])
    return {
        "prompt_n": timings["prompt_n"],
        "cache_n": timings["cache_n"],
        "drafted": timings.get("draft_n", 0),
        "accepted": timings.get("draft_n_accepted", 0),
        "quality_passed": quality(case, text),
        "matches_fresh": text == fresh,
    }


def conversation(base: str, draft_profile: str) -> list[JSONDict]:
    turns = []
    for case in cases(draft_profile):
        opening = [{"role": "user", "content": case["content"]}]
        first = chat(base, {"name": case["name"], "kind": "first"}, opening, CONVERSATION_TOKENS)
        turns.append(first)
        turns.append(chat(base, {"name": case["name"], "kind": "regenerate"}, opening, CONVERSATION_TOKENS))
        reply = {"role": "assistant", "content": cast(str, first["content"])}
        for kind, text in (("follow-up", FOLLOW_UP), ("edit", EDIT)):
            messages = [*opening, reply, {"role": "user", "content": text}]
            turns.append(chat(base, {"name": case["name"], "kind": kind}, messages, CONVERSATION_TOKENS))
    return turns


def lifecycle(folder: Path, result: JSONDict, base: str) -> None:
    """The launch's lifecycle checks, after its timed requests."""
    offset = log_size(folder)
    turns = conversation(base, result["draft_profile"])
    restores = log_since(folder, offset).count(RESTORED)
    long, *_, short = cases(result["draft_profile"])
    tokens = prompt_tokens(base, long["content"])
    offset = log_size(folder)
    started = abort(base, tokens, CANCEL_AFTER_S)
    cancelled: Cancel = {
        "after_s": CANCEL_AFTER_S,
        "reply_started": started,
        "prompt_tokens": len(tokens),
        "stopped_tokens": wait_stop(folder, offset),
    }
    earlier = {r["name"]: r for r in result["cases"] if r["repeat"] == 0}
    resumed = resume(base, long, tokens, earlier[long["name"]]["response"]["text"])
    row = measure_repeat(base, short, prompt_tokens(base, short["content"]), REPEATS, False)
    answer = (row["response"]["text"], row["response"]["generated_token_ids"])
    repeat_matches = all(
        (r["response"]["text"], r["response"]["generated_token_ids"]) == answer
        for r in result["cases"]
        if r["name"] == short["name"]
    )
    checks: Lifecycle = {
        "cancel": cancelled,
        "resume": resumed,
        "repeat_matches": repeat_matches,
        "conversation": cast(list[Turn], turns),
        "restores": restores,
    }
    result["lifecycle"] = checks
    write(folder / "result.json", result)
    print(
        f"{result['role']}: {len(turns)} conversation turns, {restores} restores; cancel stopped at "
        f"{cancelled['stopped_tokens']} of {len(tokens)} tokens, resume reused {resumed['cache_n']}, "
        f"quality={resumed['quality_passed']}; repeat matches={repeat_matches}",
        flush=True,
    )


def analyze(folder: Path) -> Bracket:
    bracket = json.loads((folder / "campaign.json").read_text())
    comparison = bracket["comparison"]
    launches = bracket["arms"]
    return {
        "rows": comparison["rows"],
        "exact_output_parity": comparison["exact_output_parity"],
        "all_quality_checks_pass": comparison["all_quality_checks_pass"],
        "lifecycle": lifecycle_bracket([cast(Lifecycle, a["lifecycle"]) for a in launches]),
        "memory": memory([cast(LaunchMemory, a["memory"]) for a in launches]),
    }


def run(output: Path) -> JSONDict:
    assert_no_model_server()
    require_pass()
    output.mkdir(parents=True, exist_ok=False)
    frozen: Frozen = {"closure": closure("m5-overlap"), "models": verify_models(["flash", "mtp_shared_packed_q3"])}
    brackets: dict[str, Bracket] = {}
    summary: JSONDict = {"schema": 1, "status": "running", "plan": BRACKETS, "rule": RULE, "brackets": brackets}
    try:
        for name, (draft_profile, chunks) in BRACKETS.items():
            folder = output / name
            folder.mkdir()
            campaign(folder, CANDIDATE, draft_profile, frozen, chunks, lifecycle)
            brackets[name] = analyze(folder)
            write(output / SUMMARY, summary)
        summary["decision"] = decision(brackets)
        summary["status"] = "passed"
    except BaseException as error:
        summary.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        write(output / SUMMARY, summary)
    return summary


def reanalyze(output: Path) -> JSONDict:
    """Recompute every bracket and the decision from the saved launches; their measurements are unchanged."""
    summary: JSONDict = json.loads((output / SUMMARY).read_text())
    summary.setdefault("recorded_decision", summary["decision"])
    brackets = {name: analyze(output / name) for name in BRACKETS}
    summary.update(brackets=brackets, decision=decision(brackets), recomputed=True)
    write(output / SUMMARY, summary)
    return summary


@cleanup_on_termination()
def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyze", action="store_true", help="Recompute the summary of a finished run; no model")
    args = ap.parse_args(argv)
    for name, (draft_profile, chunks) in BRACKETS.items():
        print(
            f"Plan {name}: kept/overlap/overlap/kept at {chunks}, {draft_profile} drafting, 4K/F16/MTP3; the standard "
            f"cases, then conversations, a cancel at {CANCEL_AFTER_S} s, its resume and a fresh repeat.",
            flush=True,
        )
    print("Rule:", RULE, flush=True)
    if args.analyze:
        summary = reanalyze(output_folder(args.output))
    elif args.run:
        summary = run(output_folder(args.output))
    else:
        return
    print("N15 qualification:", json.dumps(summary["decision"], indent=2), flush=True)


if __name__ == "__main__":
    main()
