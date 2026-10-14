#!/usr/bin/env python3
"""Qualify complete English file edits, then compare isolated drafting policies."""

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any, TypedDict, cast
import urllib.request

from benchmark import JSONDict, stream_completion, wait_ready
from benchmark_metrics import metrics
from benchmark_signals import cleanup_on_termination, defer_termination
from benchmark_m5_small_gains import feature_receipts, launch_row
from benchmark_m5_next import wait_for_headroom
from check_memory import assert_no_model_server
from engines import VerifiedEngine, sha256, verify_engine
from lab import ROOT, request
from metal_environment import configure
from model_provenance import ModelVerification, assert_unchanged, verify_models
from profile_m5_routes import preflight
from runtime_memory import admit_model, app_monitor
from trial_support import (
    ENGINE,
    FIXTURES,
    LANGUAGES,
    MAX_OUTPUT,
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

ORDER = ("control", "candidate", "candidate", "control")
EXPERIMENTS = {
    "editing": ("balanced", "code-edit"),
    "prompt-local": ("code-edit", "prompt-local"),
    "prompt-map": ("code-edit", "prompt-map"),
}
REPEATS = 3
PROSE_CONTROL = (
    "Explain a fair computer speed comparison in exactly four short sentences. "
    "Mention warmup, repeated trials, background activity and memory. No headings."
)
REUSE_QUESTION = "What is 17 multiplied by 23? Reply with only the number."


class EditTask(TypedDict):
    name: str
    language: str
    content: str
    fixture: EditFixture | None


class Closure(TypedDict):
    sources: dict[str, str]
    fixture_sha256: str
    engine: VerifiedEngine
    native_probe_sha256: str


class Frozen(TypedDict):
    created_utc: str
    closure: Closure
    models: ModelVerification
    matcher_proof_sha256: str | None


def edit_tasks(cohort: str) -> list[EditTask]:
    tasks: list[EditTask] = [
        {"name": c["name"], "language": c["language"], "content": prompt(c), "fixture": c}
        for c in fixtures()
        if c["cohort"] == cohort
    ]
    tasks.append({"name": "prose-control", "language": "prose", "content": PROSE_CONTROL, "fixture": None})
    return tasks


def signature(case: Mapping[str, Any]) -> dict[str, object]:
    response = case["response"]
    return {
        "text": hashlib.sha256(response["text"].encode()).hexdigest(),
        "tokens": hashlib.sha256(json.dumps(response["generated_token_ids"]).encode()).hexdigest(),
        "prompt": case["prompt_sha256"],
        "output_tokens": case["output_tokens"],
    }


def outputs(arm: Mapping[str, Any]) -> dict[tuple[str, int], dict[str, object]]:
    return {(c["name"], c["repeat"]): signature(c) for c in arm["cases"]}


def closure() -> Closure:
    return {
        "sources": fingerprint(),
        "fixture_sha256": sha256(FIXTURES),
        "engine": verify_engine(ENGINE),
        "native_probe_sha256": sha256(ROOT / "native/ngram_short_probe.cpp"),
    }


def matcher_proof() -> str:
    folder = ROOT / "bench/features/20261013-ngram-short-mechanism"
    proof = json.loads((folder / "proof.json").read_text())
    obj = ROOT / "vendor/llama-m5-small-stack/build/common/CMakeFiles/llama-common.dir/ngram-map.cpp.o"
    if (
        proof["status"] != "passed"
        or proof["cases"] != 18
        or proof["models_loaded"] is not False
        or proof["gpu_tests"] is not False
        or proof["map_maximum_width"] != 3
        or proof["engine"] != verify_engine(ENGINE)
        or proof["source_sha256"] != sha256(ROOT / "native/ngram_short_probe.cpp")
        or proof["native_object_sha256"] != sha256(obj)
        or proof["binary_sha256"] != sha256(folder / "probe")
    ):
        raise RuntimeError("A current, bounded native CPU matcher proof is required")
    return sha256(folder / "proof.json")


def assert_frozen(frozen: Frozen) -> None:
    require_pass()
    if closure() != frozen["closure"]:
        raise RuntimeError("Experiment source, fixtures or engine changed; start a new campaign")
    assert_unchanged(frozen["models"])
    if frozen.get("matcher_proof_sha256") and matcher_proof() != frozen["matcher_proof_sha256"]:
        raise RuntimeError("Native CPU matcher proof changed")


def require_complete_bracket(arms: Sequence[JSONDict]) -> None:
    if (
        len(arms) != 4
        or any(a["status"] != "passed" or not clean_memory(a["memory"]) for a in arms)
        or [a["role"] for a in arms] != list(ORDER)
    ):
        raise ValueError("Four complete, guarded A/B/B/A launches required")
    cohort = arms[0]["cohort"]
    if cohort not in ("screen", "confirm") or any(a["cohort"] != cohort for a in arms):
        raise ValueError("A bracket cannot mix fixture cohorts")
    names = {c["name"] for c in fixtures() if c["cohort"] == cohort} | {"prose-control"}
    expected = {(name, repeat) for name in names for repeat in range(REPEATS + 1)}
    if any(
        len(a["cases"]) != len(expected) or {(c["name"], c["repeat"]) for c in a["cases"]} != expected for a in arms
    ):
        raise ValueError("The full frozen file/repetition inventory is required")
    reference = outputs(arms[0])
    if any(outputs(a) != reference for a in arms[1:]):
        raise ValueError("Complete text, token IDs or prompt identity changed across policies")


def scored_row(arms: Sequence[JSONDict], name: str, phase: str, memory_clean: bool) -> JSONDict:
    first = phase == "first-exposure"
    groups = [
        [c for c in a["cases"] if c["name"] == name and (c["repeat"] == 0 if first else c["repeat"] > 0)] for a in arms
    ]
    if any(len(g) != (1 if first else REPEATS) for g in groups):
        raise ValueError("Missing/duplicate first exposure or warmed repetition")
    row: JSONDict = launch_row([metrics(g) for g in groups])
    row.update(name=name, language=groups[0][0]["language"], cohort=phase)
    values = row["launch_medians"]
    row["worst_ttft_cost_ms"] = 1000 * max(values[b]["ttft_s"] - values[a]["ttft_s"] for b in (1, 2) for a in (0, 3))
    # Editing can trade <=100 ms first-token delay for a faster complete reply.
    regressed = any(x in row["regressions"] for x in ("generation_increase_percent", "total_time_reduction_percent"))
    safe = memory_clean and row["worst_ttft_cost_ms"] <= 100 and not regressed
    q = row["qualifying_metrics"]
    scopes = ["reply"] + (["generation"] if q["generation_increase_percent"] else [])
    row["qualified_scopes"] = scopes if safe and q["total_time_reduction_percent"] else []
    return row


def compare(arms: Sequence[JSONDict]) -> JSONDict:
    require_complete_bracket(arms)
    rss = [a["memory"]["peak_rss_bytes"] for a in arms]
    extra = (rss[1] + rss[2] - rss[0] - rss[3]) / 2
    memory_clean = extra <= max(128 * 1024**2, 2 * abs(rss[3] - rss[0]))
    names = sorted({c["name"] for c in arms[0]["cases"]})
    rows = [scored_row(arms, name, phase, memory_clean) for name in names for phase in ("first-exposure", "warmed")]
    eligible = {
        r["language"]
        for r in rows
        if r["language"] in LANGUAGES and r["cohort"] == "first-exposure" and r["qualified_scopes"]
    }
    return {
        "rows": rows,
        "eligible_languages": sorted(eligible),
        "memory_clean": memory_clean,
        "candidate_extra_rss_bytes": extra,
        "exact_output_parity": True,
    }


def lifecycle(base: str) -> dict[str, object]:
    payload = {
        "prompt": "Write a detailed guide to fair benchmarks.",
        "n_predict": 1536,
        "stream": True,
        "cache_prompt": False,
        "temperature": 0,
        "seed": 1234,
        "ignore_eos": True,
    }
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(base + "/completion", data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        for line in response:
            if line.startswith(b"data: ") and json.loads(line[6:]).get("content"):
                break
        else:
            raise RuntimeError("No first text before disconnect")
    question = {
        "model": "flash",
        "messages": [{"role": "user", "content": REUSE_QUESTION}],
        "temperature": 0,
        "seed": 1234,
        "max_tokens": 32,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    choice = cast(list[JSONDict], request(base, "/v1/chat/completions", question, timeout=60)["choices"])[0]
    if choice["message"]["content"].strip() != "391" or choice["finish_reason"] != "stop":
        raise RuntimeError("Disconnect/reuse answer failed")
    return {"disconnect_after_first_text": True, "reuse_answer": "391", "passed": True}


def measure_task(base: str, task: EditTask, record: JSONDict, path: Path) -> None:
    ids = prompt_tokens(base, task["content"])
    if len(ids) + MAX_OUTPUT + 8 > 4096:
        raise ValueError("Complete edit budget does not fit the maintained context")
    prompt_sha = hashlib.sha256(json.dumps(ids).encode()).hexdigest()
    payload = {
        "prompt": ids,
        "n_predict": MAX_OUTPUT,
        "stream": True,
        "cache_prompt": False,
        "temperature": 0.6,
        "seed": 1234,
        "return_tokens": True,
    }
    for repeat in range(REPEATS + 1):
        response = stream_completion(base, payload)
        result = validate_response(response, task["fixture"])
        result.update(name=task["name"], language=task["language"], repeat=repeat)
        result.update(prompt_sha256=prompt_sha, input_tokens=len(ids))
        record["cases"].append(result)
        write(path, record)
        label = "first" if repeat == 0 else f"warm{repeat}"
        print(
            f"{record['profile']} {task['name']} {label}: "
            f"{result['generation_tok_s']:.2f} TPS, full reply {result['wall_s']:.3f}s",
            flush=True,
        )
        timings = response["final"]["timings"]
        if timings["prompt_n"] != len(ids) or timings.get("cache_n", 0):
            raise ValueError("Fresh prompt unexpectedly reused native prefix state")


def run_arm(folder: Path, record: JSONDict, owned: OwnedServer, frozen: Frozen) -> None:
    path = folder / "result.json"
    assert_frozen(frozen)
    assert_no_model_server()
    record["power_before"] = power()
    record["headroom_settle"] = wait_for_headroom()
    record["preflight"] = preflight()
    policy = admit_model("flash")
    record["memory_policy"] = policy
    env, metal = configure(os.environ, ENGINE, "on", "small-reduce")
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    command = trial_command(kept_server(port, 512, 512), record["profile"])
    record.update(command=command, metal_environment=metal)
    write(path, record)
    with (folder / "server.log").open("w") as log:
        with defer_termination():
            owned.process = subprocess.Popen(command, stdout=log, stderr=log, env=env)
            owned.monitor = app_monitor(owned.process, folder / "memory.jsonl", policy)
            owned.monitor.thread.start()
        record["ready_s"] = wait_ready(owned.process, base, timeout=180)
        for task in edit_tasks(record["cohort"]):
            measure_task(base, task, record, path)
        record["lifecycle"] = lifecycle(base)
    record["power_after"] = power()
    assert_frozen(frozen)


def activation(record: JSONDict, text: str) -> None:
    try:
        record["activation"] = feature_receipts(text, ["reduce"])
        if "borrowing target embeddings/output; draft KV remains separate" not in text:
            raise ValueError("Shared helper activation missing")
        record["drafting_receipts"] = drafting_receipts(text, record["profile"])
    except ValueError as error:
        record.update(status="failed", activation_error=str(error))


def finish_arm(folder: Path, record: JSONDict, owned: OwnedServer) -> None:
    stop_owned(owned.process, 15, 3)
    if owned.monitor:
        record["memory"] = owned.monitor.finish()
        if not clean_memory(record["memory"]):
            record.update(status="failed", resource_failure=True)
    if owned.process:
        record["exit_code"] = owned.process.returncode
        activation(record, (folder / "server.log").read_text())
    assert_no_model_server()
    write(folder / "result.json", record)


def arm(folder: Path, profile: str, role: str, cohort: str, frozen: Frozen) -> JSONDict:
    folder.mkdir()
    record: JSONDict = {"status": "attempting", "profile": profile, "role": role, "cohort": cohort, "cases": []}
    write(folder / "result.json", record)
    owned = OwnedServer()
    try:
        run_arm(folder, record, owned, frozen)
        record["status"] = "passed"
    except BaseException as error:
        record.update(status="failed", error=f"{type(error).__name__}: {error}")
        print(f"{profile}: {record['error']}", flush=True)
    finally:
        finish_arm(folder, record, owned)
    return record


def unscored(folder: Path, index: int, error: str) -> JSONDict:
    result = {
        "status": "failed",
        "failed_arm": index + 1,
        "eligible_languages": [],
        "error": error,
        "partial_results_not_scored": True,
    }
    write(folder / "comparison.json", result)
    return result


def bracket(folder: Path, profiles: Sequence[str], cohort: str, frozen: Frozen) -> JSONDict:
    folder.mkdir()
    arms: list[JSONDict] = []
    for index, role in enumerate(ORDER):
        if index:
            time.sleep(15)
        record = arm(folder / f"arm-{index + 1}", profiles[0 if role == "control" else 1], role, cohort, frozen)
        arms.append(record)
        if record["status"] != "passed":
            error = record.get("error") or record.get("activation_error") or "Resource gate failed"
            return unscored(folder, index, error)
        if index and outputs(record) != outputs(arms[0]):
            return unscored(folder, index, "Cross-policy exact output parity failed")
    result = {"status": "completed", **compare(arms)}
    write(folder / "comparison.json", result)
    return result


def campaign_plan(experiment: str) -> JSONDict:
    return {
        "schema": 1,
        "experiment": experiment,
        "profiles": EXPERIMENTS[experiment],
        "order": ORDER,
        "files": [{"name": c["name"], "language": c["language"], "cohort": c["cohort"]} for c in fixtures()],
        "repeats": REPEATS,
        "temperature": 0.6,
        "seed": 1234,
        "normal_eos": True,
        "maximum_output_tokens": MAX_OUTPUT,
        "first_exposure": "First encounter with each disjoint file; first file is also the first request after load. OS cache is uncontrolled.",
        "warmed": "Three subsequent repeats are separate from first exposure; global lookup pool may remember the same file.",
        "confirm": "Independent A/B/B/A on three held-out files; same language scope must qualify in screen and confirmation.",
        "acceptance": "No minimum percentage: both candidate launches beat both controls, gain above twice control drift, faster complete reply, no material TPS regression, <=100ms extra first-token latency; exact text/token parity, guards and activation required.",
        "resources": "34GiB entry, 1GiB ongoing floor, continuous normal pressure, zero new swap, AC Automatic, quiet preflight, no cleanup during brackets.",
        "stop": "One attempt per arm; no partial scoring, overwrites or unchanged retries. No automatic launcher changes.",
    }


def confirm_scopes(record: JSONDict) -> None:
    screen, confirm = record["screen"], record["confirm"]
    record["confirmed_languages"] = sorted(set(screen["eligible_languages"]) & set(confirm["eligible_languages"]))
    record["confirmed_scopes"] = {}
    for language in record["confirmed_languages"]:
        scopes = [
            {
                s
                for r in phase["rows"]
                if (r["language"], r["cohort"]) == (language, "first-exposure")
                for s in r["qualified_scopes"]
            }
            for phase in (screen, confirm)
        ]
        record["confirmed_scopes"][language] = sorted(scopes[0] & scopes[1])


def run_campaign(folder: Path, experiment: str, frozen: Frozen) -> JSONDict:
    profiles = EXPERIMENTS[experiment]
    record: JSONDict = {"status": "running", "experiment": experiment, "confirmed_languages": []}
    write(folder / "campaign.json", record)
    record["screen"] = bracket(folder / "screen", profiles, "screen", frozen)
    if record["screen"]["eligible_languages"]:
        record["confirm"] = bracket(folder / "confirm", profiles, "confirm", frozen)
        confirm_scopes(record)
    if any(record[p]["status"] == "failed" for p in ("screen", "confirm") if p in record):
        record["status"] = "failed"
    else:
        record["status"] = "confirmed" if record["confirmed_languages"] else "no confirmed gain"
    write(folder / "campaign.json", record)
    return record


@cleanup_on_termination()
def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--experiment", choices=EXPERIMENTS, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args(argv)
    plan = campaign_plan(args.experiment)
    print(json.dumps(plan, indent=2), flush=True)
    if not args.run:
        return
    if args.experiment == "prompt-local":
        raise RuntimeError("E02 is parked: this native matcher produces zero guesses under width3. No model loaded.")
    cpu_proof = matcher_proof() if args.experiment == "prompt-map" else None
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    with (ROOT / "bench/.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require_pass()
        assert_no_model_server()
        power()
        write(folder / "plan.json", plan)
        frozen: Frozen = {
            "created_utc": datetime.now(UTC).isoformat(),
            "closure": closure(),
            "models": verify_models(["flash", "mtp_shared_packed_q3"]),
            "matcher_proof_sha256": cpu_proof,
        }
        write(folder / "frozen.json", frozen)
        record = run_campaign(folder, args.experiment, frozen)
        confirmed = record["confirmed_languages"]
        print(f"Campaign: {record['status']}; independently confirmed languages: {confirmed}", flush=True)
        if record["status"] == "failed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
