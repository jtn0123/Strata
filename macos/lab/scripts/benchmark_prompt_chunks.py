#!/usr/bin/env python3
"""Guarded prompt-chunk trials on the kept engine; no load without --run.

The same A/B/B/A protocol also compares an engine candidate (N15's helper overlap) against the kept engine at an
unchanged chunk size; qualify_overlap.py runs those brackets with extra lifecycle checks in every launch.
"""

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
import fcntl
import hashlib
from itertools import pairwise
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import time
from typing import NamedTuple, NotRequired, TypedDict

from benchmark import JSONDict, stream_completion, wait_ready
from benchmark_m5_next import wait_for_headroom
from benchmark_m5_small_gains import feature_receipts, launch_row
from benchmark_metrics import METRICS
from benchmark_signals import cleanup_on_termination, defer_termination
from capture_lookup_long import workloads as documents
from check_memory import assert_no_model_server
from engines import VerifiedEngine, sha256, verify_engine
from hardware_telemetry import Sampler, tool_pin
from lab import ROOT
from metal_environment import configure
from model_provenance import ModelVerification, assert_unchanged, verify_models
from overlap_ops import overlap_receipt
from profile_m5_routes import preflight
from runtime_memory import admit_model, app_monitor
from trial_support import (
    ENGINE,
    FIXTURES,
    EditFixture,
    OwnedServer,
    clean_memory,
    drafting_receipts,
    fixtures,
    free_port,
    kept_server,
    power,
    prompt,
    prompt_tokens,
    stop_owned,
    trial_command,
    validate_response,
    write,
)
from validate_offline import fingerprint, require_pass

MAX_OUTPUT = 768
REPEATS = 3
ORDER = ("control", "candidate", "candidate", "control")
PROFILES = {"512": (512, 512), "1024": (1024, 1024), "1536": (1536, 1536), "256": (512, 256)}
KEPT_TUNING = "small-reduce"
# Engine candidates keep the control's chunk size and change the engine and its switches instead.
ENGINE_CANDIDATES = {"overlap": ("m5-overlap", "overlap-reduce")}
RETRIEVAL = (
    "Read the fictional notes below. Return only a JSON object for Record 27, with keys owner, "
    "timeout_seconds and retry_limit. Do not explain.\n\n"
)
SHORT_PROSE = (
    "In about 180 words, explain why local AI benchmark results vary. "
    "Cover model size, input length, draft tokens, warmup, and memory. Use clear English."
)
GAP_NOTE = (
    "Client SSE inter-output gaps after first token; grouped tokens, transport/scheduling included. "
    "No GPU-kernel timing claim."
)
LIMITATION = (
    "First exposure is a process-local observation, not controlled cold SSD. "
    "Replay has fresh prompt computation but shares OS/model/kernel caches. "
    "Two launches per arm; small gains need a new independent confirmation."
)


class PromptCase(TypedDict):
    name: str
    kind: str
    content: str
    fixture: NotRequired[EditFixture]


class Closure(TypedDict):
    sources: dict[str, str]
    fixture_sha256: str
    engine: VerifiedEngine
    candidate_engine: NotRequired[VerifiedEngine]


class Frozen(TypedDict):
    closure: Closure
    models: ModelVerification
    hardware_tool: NotRequired[JSONDict]


# Requests a launch makes after its timed cases: (launch folder, result, server base URL).
Lifecycle = Callable[[Path, JSONDict, str], None]


class Arm(NamedTuple):
    """The engine and switches of one bracket arm, and the requests it makes after its timed cases."""

    engine: str = ENGINE
    tuning: str = KEPT_TUNING
    lifecycle: Lifecycle | None = None


@dataclass
class OwnedLaunch(OwnedServer):
    """Adds the optional owned hardware sampler to the published server references."""

    hardware: Sampler | None = None


def cases(draft_profile: str = "balanced") -> list[PromptCase]:
    if draft_profile not in ("balanced", "code-edit"):
        raise ValueError("Unknown draft profile")
    if draft_profile == "code-edit":
        edits = [f for f in fixtures() if f["cohort"] == "confirm"]
    else:
        edits = [f for f in fixtures() if f["name"] == "python-client"]
    long_documents = documents()
    notes = long_documents[0]["content"].split("\n\n", 1)[1]
    result: list[PromptCase] = [
        {"name": "long-retrieval", "kind": "retrieval", "content": RETRIEVAL + notes},
        {"name": "long-prose", "kind": "prose", "content": long_documents[1]["content"]},
    ]
    result += [{"name": f["name"], "kind": "editing", "content": prompt(f), "fixture": f} for f in edits]
    result.append({"name": "short-prose", "kind": "prose", "content": SHORT_PROSE})
    return result


def quality(case: PromptCase, text: str) -> bool:
    if case["kind"] == "editing":
        f = case["fixture"]
        return text.strip() == f["source"].replace(f["old"], f["new"]).strip()
    if case["kind"] == "retrieval":
        try:
            value = json.loads(text)
        except ValueError:
            return False
        return (
            isinstance(value, dict)
            and set(value) == {"owner", "timeout_seconds", "retry_limit"}
            and value["owner"] in ("Grove", "team Grove")
            and value["timeout_seconds"] == 38
            and value["retry_limit"] == 2
        )
    # Exact token parity is the optimization gate; this is not an independent prose grade.
    return bool(text.strip()) and "<think>" not in text


def signature(rows: Sequence[JSONDict]) -> list[tuple[object, ...]]:
    return [
        (
            r["name"],
            r["repeat"],
            r["prompt_sha256"],
            r["prompt_tokens"],
            r["response"]["text"],
            r["response"]["generated_token_ids"],
        )
        for r in rows
    ]


def chunk_receipt(text: str, profile: str) -> dict[str, list[int]]:
    """Reject silent batch clamping in either target or shared helper context."""
    batch, ubatch = PROFILES[profile]
    values = {
        key: list(map(int, re.findall(r"\bllama_context: " + key + r"\s*=\s*(\d+)", text)))
        for key in ("n_batch", "n_ubatch")
    }
    if values != {"n_batch": [batch, batch], "n_ubatch": [ubatch, ubatch]}:
        raise ValueError("Native target/helper batch sizes differ from the declared recipe")
    return values


def phase_row(arms: Sequence[JSONDict], name: str, phase: str, parity: bool, good: bool) -> JSONDict:
    groups = [
        [
            r
            for r in a["cases"]
            if r["name"] == name and (r["repeat"] == 0 if phase == "first-exposure" else r["repeat"] > 0)
        ]
        for a in arms
    ]
    row: JSONDict = launch_row([{k: statistics.median(r[k] for r in g) for k in METRICS} for g in groups])
    row.update(name=name, phase=phase, exact_output_parity=parity, quality_passed=good)
    gains = row["qualifying_metrics"]
    row["eligible_prompt_scope"] = (
        parity
        and good
        and not row["regressions"]
        and gains["ttft_reduction_percent"]
        and gains["total_time_reduction_percent"]
    )
    return row


def compare(arms: Sequence[JSONDict], draft_profile: str = "balanced") -> JSONDict:
    if len(arms) != 4 or [a["role"] for a in arms] != list(ORDER) or any(a["status"] != "passed" for a in arms):
        raise ValueError("Only a complete healthy A/B/B/A bracket can be scored")
    names = [c["name"] for c in cases(draft_profile)]
    expected = {(n, r) for n in names for r in range(REPEATS)}
    for arm in arms:
        keys = [(r["name"], r["repeat"]) for r in arm["cases"]]
        if len(keys) != len(expected) or set(keys) != expected:
            raise ValueError("Missing, duplicate or unexpected request")
    parity = all(signature(a["cases"]) == signature(arms[0]["cases"]) for a in arms[1:])
    good = all(r["quality_passed"] for a in arms for r in a["cases"])
    rows = [phase_row(arms, name, phase, parity, good) for name in names for phase in ("first-exposure", "replay")]
    return {
        "rows": rows,
        "exact_output_parity": parity,
        "all_quality_checks_pass": good,
        "default_changed": False,
        "confirmation_required": True,
        "limitation": LIMITATION,
    }


def closure(candidate_engine: str | None = None) -> Closure:
    result: Closure = {"sources": fingerprint(), "fixture_sha256": sha256(FIXTURES), "engine": verify_engine(ENGINE)}
    if candidate_engine is not None:
        result["candidate_engine"] = verify_engine(candidate_engine)
    return result


def check_frozen(frozen: Frozen) -> None:
    require_pass()
    candidate = frozen["closure"].get("candidate_engine")
    if closure(candidate["engine"] if candidate else None) != frozen["closure"]:
        raise RuntimeError("Frozen source or engine changed; start a new campaign")
    assert_unchanged(frozen["models"])
    if frozen.get("hardware_tool") and tool_pin() != frozen["hardware_tool"]:
        raise RuntimeError("Hardware sampler tool changed")


def stream_observer(events: list[JSONDict]) -> Callable[[JSONDict, float], None]:
    def observe(item: JSONDict, elapsed: float) -> None:
        events.append(
            {"elapsed_s": elapsed, "token_count": len(item.get("tokens", [])), "final": bool(item.get("stop"))}
        )

    return observe


def output_gaps(events: Sequence[JSONDict]) -> JSONDict:
    emitted = [e for e in events if e["token_count"] > 0]
    gaps = [b["elapsed_s"] - a["elapsed_s"] for a, b in pairwise(emitted)]
    return {
        "samples": len(gaps),
        "median_s": statistics.median(gaps) if gaps else None,
        "maximum_s": max(gaps) if gaps else None,
        "note": GAP_NOTE,
    }


def measure_repeat(base: str, case: PromptCase, tokens: list[int], repeat: int, hardware: bool) -> JSONDict:
    begin = time.monotonic()
    events: list[JSONDict] = []
    payload = {
        "prompt": tokens,
        "n_predict": MAX_OUTPUT,
        "temperature": 0,
        "seed": 1234,
        "cache_prompt": False,
        "ignore_eos": False,
        "return_tokens": True,
        "stream": True,
    }
    response = stream_completion(base, payload, observer=stream_observer(events) if hardware else None)
    end = time.monotonic()
    row = validate_response(response)
    timings = response["final"]["timings"]
    if timings["prompt_n"] != len(tokens) or row["output_tokens"] != len(response["generated_token_ids"]):
        raise ValueError("Complete fresh prompt and exact output token counts required")
    row.update(
        name=case["name"], repeat=repeat, prompt_tokens=len(tokens), begin_monotonic_s=begin, end_monotonic_s=end
    )
    row["prompt_sha256"] = hashlib.sha256(json.dumps(tokens).encode()).hexdigest()
    row["quality_passed"] = quality(case, response["text"])
    if hardware:
        row["stream_events"] = events
        row["observed_output_gaps"] = output_gaps(events)
    return row


def measure_case(folder: Path, result: JSONDict, owned: OwnedLaunch, base: str, case: PromptCase) -> None:
    tokens = prompt_tokens(base, case["content"])
    if not tokens or len(tokens) + MAX_OUTPUT > 4096:
        raise ValueError("Request exceeds frozen 4K context")
    if case["name"].startswith("long-") and not 2048 <= len(tokens) <= 3000:
        raise ValueError("Long prompt is outside the predeclared scope")
    for repeat in range(REPEATS):
        row = measure_repeat(base, case, tokens, repeat, owned.hardware is not None)
        result["cases"].append(row)
        write(folder / "result.json", result)
        print(
            f"{result['role']}/{result['profile']}: {case['name']} r{repeat}: prompt {row['prompt_tok_s']:.2f}, "
            f"generation {row['generation_tok_s']:.2f} TPS, first {row['ttft_s']:.3f}s, "
            f"reply {row['wall_s']:.3f}s, quality={row['quality_passed']}",
            flush=True,
        )


def run_launch(
    folder: Path, result: JSONDict, owned: OwnedLaunch, frozen: Frozen, lifecycle: Lifecycle | None = None
) -> None:
    assert_no_model_server()
    check_frozen(frozen)
    result["settle"] = wait_for_headroom()
    result["preflight"] = preflight(False)
    result["power"] = power()
    if frozen.get("hardware_tool"):
        owned.hardware = Sampler(folder)
        owned.hardware.start(frozen["hardware_tool"])
    port = free_port()
    batch, ubatch = PROFILES[result["profile"]]
    command = trial_command(kept_server(port, batch, ubatch, result["engine"]), result["draft_profile"])
    env, flags = configure(os.environ, result["engine"], "on", result["tuning"])
    policy = admit_model("flash")
    result.update(command=command, settings={"batch": batch, "ubatch": ubatch, "metal": flags}, memory_policy=policy)
    write(folder / "result.json", result)
    with (folder / "native.log").open("w") as log:
        with defer_termination():
            owned.process = subprocess.Popen(command, env=env, stdout=log, stderr=log)
            if owned.hardware:
                owned.hardware.model_pid = owned.process.pid
            result["models_loaded"] = True
            owned.monitor = app_monitor(owned.process, folder / "memory.jsonl", policy)
            owned.monitor.thread.start()
        write(folder / "result.json", result)
        base = f"http://127.0.0.1:{port}"
        result["ready_s"] = wait_ready(owned.process, base)
        for case in cases(result["draft_profile"]):
            measure_case(folder, result, owned, base, case)
        if lifecycle:
            lifecycle(folder, result, base)


def accept_launch(folder: Path, result: JSONDict, hardware: bool) -> None:
    if not clean_memory(result["memory"]):
        raise RuntimeError("RAM/swap/cleanup gate failed")
    coverage = result["hardware"] if hardware else None
    if coverage and (not coverage["healthy"] or not all(coverage["sensor_fields_observed"].values())):
        raise RuntimeError("Hardware diagnostic coverage failed; original answers retained")
    text = (folder / "native.log").read_text()
    result["activation"] = feature_receipts(text, ["reduce"])
    result["activation"]["overlap"] = overlap_receipt(text, result["tuning"] == ENGINE_CANDIDATES["overlap"][1])
    result["drafting"] = drafting_receipts(text, result["draft_profile"])
    result["actual_chunks"] = chunk_receipt(text, result["profile"])
    result["status"] = "passed"


def finish_launch(folder: Path, result: JSONDict, owned: OwnedLaunch, frozen: Frozen) -> None:
    stop_owned(owned.process, 5, 5)
    if owned.monitor:
        result["memory"] = owned.monitor.finish()
    if owned.hardware:
        result["hardware"] = owned.hardware.stop()
        for row in result["cases"]:
            row["hardware_window"] = owned.hardware.window(row["begin_monotonic_s"], row["end_monotonic_s"])
    try:
        assert_no_model_server()
        check_frozen(frozen)
        if result["status"] == "completed":
            accept_launch(folder, result, owned.hardware is not None)
    except BaseException as error:
        result.update(status="failed", error=f"{type(error).__name__}: {error}")
    write(folder / "result.json", result)


def launch(
    folder: Path, role: str, profile: str, frozen: Frozen, draft_profile: str = "balanced", arm: Arm | None = None
) -> JSONDict:
    arm = arm or Arm()
    folder.mkdir()
    result: JSONDict = {
        "status": "running",
        "role": role,
        "profile": profile,
        "draft_profile": draft_profile,
        "engine": arm.engine,
        "tuning": arm.tuning,
        "cases": [],
        "models_loaded": False,
    }
    owned = OwnedLaunch()
    try:
        run_launch(folder, result, owned, frozen, arm.lifecycle)
        result["status"] = "completed"
    except BaseException as error:
        result.update(status="failed", error=f"{type(error).__name__}: {error}")
    finally:
        finish_launch(folder, result, owned, frozen)
    if result["status"] != "passed":
        raise RuntimeError(result.get("error", "Launch failed"))
    return result


def copy_sources(output: Path, sources: dict[str, str]) -> None:
    for relative in sources:
        dest = output / "source" / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((ROOT / relative).read_bytes())


def arms(candidate: str, chunks: str = "512", lifecycle: Lifecycle | None = None) -> list[tuple[str, Arm]]:
    """Profile and arm per launch: a chunk candidate changes the chunk size, an engine candidate the engine."""
    engine = ENGINE_CANDIDATES.get(candidate)
    if engine is None and chunks != "512":
        raise ValueError("Chunk candidates are compared with the 512-token control")
    kept = Arm(lifecycle=lifecycle)
    if engine is None:
        return [("512", kept) if role == "control" else (candidate, kept) for role in ORDER]
    return [(chunks, kept if role == "control" else Arm(*engine, lifecycle)) for role in ORDER]


def campaign(
    output: Path,
    candidate: str,
    draft_profile: str,
    frozen: Frozen,
    chunks: str = "512",
    lifecycle: Lifecycle | None = None,
) -> None:
    plan = arms(candidate, chunks, lifecycle)
    result: JSONDict = {
        "schema": 1,
        "status": "running",
        "candidate": candidate,
        "chunks": [profile for profile, _ in plan],
        "engines": [arm.engine for _, arm in plan],
        "draft_profile": draft_profile,
        "order": ORDER,
        "arms": [],
        "frozen": frozen,
        "prompt_cache": False,
        "normal_eos": True,
        "output_cap": MAX_OUTPUT,
        "default_changed": False,
        "cache_state": "unknown; no purge, forced eviction, preload or intervention inside bracket",
    }
    copy_sources(output, frozen["closure"]["sources"])
    write(output / "campaign.json", result)
    try:
        with (ROOT / "bench/.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for i, (role, (profile, arm)) in enumerate(zip(ORDER, plan, strict=True)):
                result["arms"].append(launch(output / f"arm-{i + 1}-{role}", role, profile, frozen, draft_profile, arm))
                write(output / "campaign.json", result)
            result["comparison"] = compare(result["arms"], draft_profile)
            result["status"] = "passed"
    except BaseException as error:
        result.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        result["launches"] = [json.loads(p.read_text()) for p in sorted(output.glob("arm-*/result.json"))]
        write(output / "campaign.json", result)


@cleanup_on_termination()
def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidate", choices=("1024", "1536", "256"), required=True)
    ap.add_argument("--draft-profile", choices=("balanced", "code-edit"), default="balanced")
    sampler = "Owned rootless GPU/thermal/contention sampler; all arms identical"
    ap.add_argument("--telemetry", action="store_true", help=sampler)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args(argv)
    print(
        f"Plan: 512/{args.candidate}/{args.candidate}/512; {args.draft_profile}, kept engine, 4K/F16/MTP3, "
        "two long English inputs, short edit/prose, three normal-EOS responses each.",
        flush=True,
    )
    if not args.run:
        return
    assert_no_model_server()
    require_pass()
    args.output.mkdir(parents=True, exist_ok=False)
    frozen: Frozen = {"closure": closure(), "models": verify_models(["flash", "mtp_shared_packed_q3"])}
    if args.telemetry:
        frozen["hardware_tool"] = tool_pin()
    campaign(args.output, args.candidate, args.draft_profile, frozen)
    print("Trial passed:", args.output, flush=True)


if __name__ == "__main__":
    main()
