#!/usr/bin/env python3
"""N02: Apple advisory reads for the lazy lookup-table rows, on the isolated m5-advise engine; no load without --run.

Three launch modes on the same engine, each with the advice trace on: no advice (the pinned behaviour), MADV_WILLNEED
(madvise) and F_RDADVISE (rdadvise). Each runs twice, in rotated order, with the default 512-token prompt chunks.

Every launch reads eight documents, or the --documents count, that no earlier request in the run has read: excerpts
of the pinned llama.cpp checkout's Markdown files, cut to the same token count. Each is answered twice in a row with
a short reply, first exposure and then an exact replay whose lookup rows are resident. Then the four standard prompt
cases, already read by earlier runs, are answered twice with a 128-token reply to compare warm reply speed and text
between modes. One warm-up request comes first in every launch and is not compared.

A check run (--check) makes one short launch per advice mode with the trace's second level, which also counts the
pages still not resident when the advice returns; its timings are not compared. It also lists any excerpt shorter
than the token count. A full run given earlier runs' folders (--exclude, repeatable) leaves out every excerpt those
runs were dealt, read or not, and the short ones, so a rerun after a stopped launch still reads unseen excerpts.
"""

import argparse
from collections.abc import Sequence
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import time
from typing import TypedDict, cast

import psutil

from advise_ops import MODES, Launch, compare, parse, request_advice
from benchmark import JSONDict
from benchmark_prompt_chunks import Frozen, cases, chunk_receipt, closure
from benchmark_signals import cleanup_on_termination
from check_memory import assert_no_model_server
from engines import verify_engine
from lab import ROOT, request
from metal_environment import configure
from model_provenance import verify_models
import profile_prompt_ops as guarded
from prompt_ops import chunk_sizes
from trial_support import kept_server, prompt_tokens, write
from validate_offline import require_pass

ENGINE = "m5-advise"
PROFILE = "512"
DOCUMENTS = 8
CHECK_DOCUMENTS = 2
DOCUMENT_TOKENS = 2048
WINDOW_CHARS = 10000
FIRST_TOKENS = 32
WARM_REPLIES = 2
REPLY_TOKENS = 128
SEED = 20261014
SOURCE = "vendor/llama.cpp"
INSTRUCTION = (
    "Read this excerpt from a software project's documentation. Reply with one plain English sentence, "
    "under twenty-five words, saying what it explains.\n\n"
)
ADVICE = {"no-advice": None, "madvise": "madvise", "rdadvise": "rdadvise"}
CHECKS = {"madvise-check": "madvise", "rdadvise-check": "rdadvise"}
ELIGIBLE = "enabling prefetch for 'per_layer_token_embd.weight'"
LIMITATION = (
    "Documents differ between launches, so first-exposure figures are compared through each document's own replay "
    "and the trace's count of pages that were not resident. The trace's residency checks run in every mode and are "
    "reported. Page-cache contents before a launch are not controlled; nothing is purged or preloaded."
)


class Document(TypedDict):
    name: str
    sha256: str
    text: str


# Documents for each launch folder, set by main before the launch starts.
ASSIGNED: dict[Path, list[Document]] = {}


def monotonic_us() -> int:
    """The engine's clock: ggml_time_us reads CLOCK_MONOTONIC."""
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC) // 1000


def windows(root: Path = ROOT) -> list[Document]:
    """Consecutive paragraph runs of at least WINDOW_CHARS characters from each tracked Markdown file."""
    source = root / SOURCE
    names = subprocess.check_output(["git", "-C", str(source), "ls-files", "*.md"], text=True).split()
    found: list[Document] = []
    for name in sorted(names):
        paragraphs = (source / name).read_text(errors="replace").split("\n\n")
        current: list[str] = []
        for paragraph in paragraphs:
            current.append(paragraph)
            text = "\n\n".join(current)
            if len(text) >= WINDOW_CHARS:
                found.append(
                    {"name": f"{name}#{len(found)}", "sha256": hashlib.sha256(text.encode()).hexdigest(), "text": text}
                )
                current = []
    return found


def assign(
    count: int, per_launch: int, offset: int = 0, root: Path = ROOT, exclude: frozenset[str] = frozenset()
) -> list[list[Document]]:
    """A fixed shuffle of every window, less the excluded ones, dealt out so no window is used twice."""
    found = windows(root)
    random.Random(SEED).shuffle(found)
    found = [d for d in found if d["name"] not in exclude]
    needed = offset + count * per_launch
    if len(found) < needed:
        raise ValueError(f"Only {len(found)} documents for {needed}")
    return [found[offset + i * per_launch : offset + (i + 1) * per_launch] for i in range(count)]


def launch_plan(check: bool = False) -> list[str]:
    if check:
        return list(CHECKS)
    # Each mode twice; the second round reverses the first so every mode has the same mean position.
    return [*MODES, *MODES[::-1]]


def advice_env(mode: str) -> tuple[dict[str, str], JSONDict]:
    env, flags = configure(os.environ, ENGINE, "on", "small-reduce")
    extra = {"GGML_M5_LAB_ADVISE_TRACE": "2" if mode in CHECKS else "1"}
    advice = CHECKS.get(mode) or ADVICE[mode]
    if advice:
        extra["GGML_M5_LAB_ADVISE"] = advice
    env.update(extra)
    return env, {"metal": flags, "diagnostic_env": extra}


def advice_command(port: int, profile: str, mode: str) -> list[str]:
    verify_engine(ENGINE)
    batch, ubatch = guarded.PROFILES[profile]
    return list(kept_server(port, batch, ubatch, ENGINE))


def ask(base: str, row: JSONDict, tokens: list[int], n_predict: int) -> JSONDict:
    payload: JSONDict = {
        "prompt": tokens,
        "n_predict": n_predict,
        "temperature": 0,
        "seed": 1234,
        "cache_prompt": False,
    }
    before = psutil.disk_io_counters()
    begin = monotonic_us()
    response = request(base, "/completion", payload, timeout=900)
    end = monotonic_us()
    after = psutil.disk_io_counters()
    timings = cast(JSONDict, response["timings"])
    if timings["prompt_n"] != len(tokens):
        raise ValueError("The whole fresh prompt must be read")
    return {
        **row,
        "prompt_tokens": len(tokens),
        "begin_us": begin,
        "end_us": end,
        "prompt_ms": timings["prompt_ms"],
        "predicted_n": timings["predicted_n"],
        "tok_s": timings["predicted_per_second"],
        "drafted": timings.get("draft_n", 0),
        "accepted": timings.get("draft_n_accepted", 0),
        "content": response["content"],
        "disk_read_bytes": after.read_bytes - before.read_bytes if before and after else None,
    }


def text_tokens(base: str, text: str) -> list[int]:
    return cast(list[int], request(base, "/tokenize", {"content": text, "add_special": False})["tokens"])


def document_tokens(base: str, document: Document) -> list[int]:
    """The excerpt cut to DOCUMENT_TOKENS tokens, behind the instruction, as one user turn."""
    tokens = text_tokens(base, document["text"])
    if len(tokens) < DOCUMENT_TOKENS:
        raise ValueError(f"{document['name']} has only {len(tokens)} tokens")
    text = cast(str, request(base, "/detokenize", {"tokens": tokens[:DOCUMENT_TOKENS]})["content"])
    return prompt_tokens(base, INSTRUCTION + text)


def record(folder: Path, result: JSONDict, row: JSONDict) -> None:
    result["requests"].append(row)
    write(folder / "result.json", result)
    print(
        f"{result['mode']}: {row['name']} {row['kind']}: {row['prompt_tokens']} tokens, prompt {row['prompt_ms']:.0f} ms, "
        f"{row['predicted_n']} tokens at {row['tok_s']:.2f} tok/s",
        flush=True,
    )


def advice_requests(folder: Path, result: JSONDict, base: str) -> None:
    result["documents"] = [{"name": d["name"], "sha256": d["sha256"]} for d in ASSIGNED[folder]]
    warmup = cases("balanced")[-1]
    record(
        folder, result, ask(base, {"name": warmup["name"], "kind": "warmup"}, prompt_tokens(base, warmup["content"]), 1)
    )
    for document in ASSIGNED[folder]:
        tokens = document_tokens(base, document)
        for kind in ("first", "replay"):
            record(folder, result, ask(base, {"name": document["name"], "kind": kind}, tokens, FIRST_TOKENS))
    if result["mode"] in CHECKS:
        # Proves before the full run that every excerpt is long enough.
        lengths = {d["name"]: len(text_tokens(base, d["text"])) for d in windows()}
        result["short_documents"] = sorted(name for name, n in lengths.items() if n < DOCUMENT_TOKENS)
        return
    for case in cases("balanced"):
        tokens = prompt_tokens(base, case["content"])
        for repeat in range(WARM_REPLIES):
            row = ask(base, {"name": case["name"], "kind": "warm", "repeat": repeat}, tokens, REPLY_TOKENS)
            record(folder, result, row)


def advice_analyze(folder: Path, result: JSONDict) -> None:
    lines = (folder / "native.log").read_text(errors="replace").splitlines()
    result["actual_chunks"] = chunk_receipt("\n".join(lines), result["profile"])
    advice = CHECKS.get(result["mode"]) or ADVICE[result["mode"]] or "off"
    level = 2 if result["mode"] in CHECKS else 1
    for marker in (ELIGIBLE, f"lab: lazy-row advice {advice}, trace level {level}"):
        if not any(marker in line for line in lines):
            raise ValueError(f"Missing engine marker: {marker}")
    calls = parse(lines)
    if {call["mode"] for call in calls} != {advice}:
        raise ValueError("The advice setting did not reach the engine")
    batch, ubatch = guarded.PROFILES[result["profile"]]
    for row in result["requests"]:
        chunks = chunk_sizes(row["prompt_tokens"], batch, ubatch)
        row["advice"] = request_advice(calls, row["begin_us"], row["end_us"], chunks)
    if result["mode"] in CHECKS:
        result["check"] = [
            {key: call[key] for key in ("rows", "pages", "cold_before", "cold_after", "advice_us", "check_us")}
            for call in calls
            if call["rows"] >= batch
        ]


STEPS = guarded.Steps(advice_command, advice_env, advice_requests, advice_analyze, LIMITATION)
guarded.OTHER_TRIALS.update(dict.fromkeys((*MODES, *CHECKS), STEPS))


def dealt(folder: Path) -> frozenset[str]:
    """Excerpts an earlier run's launches were dealt, and those a check run found too short."""
    names: set[str] = set()
    for path in folder.glob("launch-*/result.json"):
        result = json.loads(path.read_text())
        names.update(d["name"] for d in result["documents"])
        names.update(result.get("short_documents", []))
    return frozenset(names)


@cleanup_on_termination()
def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--exclude", type=Path, action="append", default=[])
    ap.add_argument("--documents", type=int, default=DOCUMENTS)
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args(argv)
    plan = launch_plan(args.check)
    per_launch = CHECK_DOCUMENTS if args.check else args.documents
    # Check launches take documents after every document the full run uses.
    offset = len(launch_plan()) * DOCUMENTS if args.check else 0
    print(
        f"Plan: {'/'.join(plan)} on {ENGINE}, 4K/F16/MTP3 at {PROFILE}; {per_launch} unseen documents per launch, "
        f"each read twice with a {FIRST_TOKENS}-token reply"
        f"{'' if args.check else f', then four warm cases with {WARM_REPLIES} {REPLY_TOKENS}-token replies'}.",
        flush=True,
    )
    if not args.run:
        return
    assert_no_model_server()
    require_pass()
    excluded = frozenset[str]().union(*map(dealt, args.exclude))
    documents = assign(len(plan), per_launch, offset, exclude=excluded)
    args.output.mkdir(parents=True, exist_ok=False)
    frozen: Frozen = {"closure": closure(), "models": verify_models(["flash", "mtp_shared_packed_q3"])}
    summary: JSONDict = {
        "schema": 1,
        "plan": plan,
        "frozen": frozen,
        "engine": verify_engine(ENGINE),
        "documents_per_launch": per_launch,
        "excluded": sorted(excluded),
        "launches": [],
    }
    results: list[JSONDict] = []
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for i, mode in enumerate(plan):
            folder = args.output / f"launch-{i + 1}-{mode}"
            ASSIGNED[folder] = documents[i]
            results.append(guarded.launch(folder, mode, PROFILE, frozen))
            summary["launches"].append(results[-1]["status"])
            write(args.output / "summary.json", summary)
    if not args.check:
        summary["analysis"] = compare(cast(list[Launch], results))
        write(args.output / "summary.json", summary)
    print("N02 launches passed:", json.dumps(summary["launches"]), flush=True)


if __name__ == "__main__":
    main()
