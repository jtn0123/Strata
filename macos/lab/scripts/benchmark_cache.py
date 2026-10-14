#!/usr/bin/env python3
"""Compare the real Strata adapter with prompt reuse off/on on one pinned engine."""

import argparse
import csv
from datetime import UTC, datetime
import fcntl
import hashlib
import json
import socket
import statistics
import subprocess
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any, NamedTuple

import psutil
from benchmark import _Receipt, command_output, host_snapshot
from memory_monitor import Monitor as Monitor, OwnedProcess, wait_ready as wait_ready
from benchmark_metrics import attach_response_failure, case_metrics, completion_counts
from benchmark_signals import cleanup_on_termination, defer_termination
from trial_workloads import cache_workload as build_workload
from trial_workloads import cache_stop_tokens as stop_tokens
from engines import sha256, verify_engine
from lab import ROOT, request, server_command
from model_provenance import ModelVerification, assert_unchanged, verify_models
from native_backend import DETOKENIZE_ENDPOINT, NativeEngine, NativeTemplate, NativeTokenizer, validate_native_response


JSONDict = dict[str, Any]


@contextmanager
def _preserve_rejection(receipt: _Receipt, case: JSONDict) -> Iterator[None]:
    try:
        yield
    except BaseException as error:
        detail = f"{type(error).__name__}: {error}"
        response = getattr(error, "benchmark_response", case.get(case["stage"]))
        if isinstance(response, dict):
            case[case["stage"]] = {**response, "status": "rejected", "error": detail}
        case.update(status="rejected", error=detail)
        receipt.record.setdefault("rejected_cases", []).append(case)
        receipt.save()
        raise


def _failure_text(tokenizer: NativeTokenizer, tokens: Sequence[int], error: BaseException) -> JSONDict:
    if isinstance(error, (KeyboardInterrupt, SystemExit)):
        return {"text_error": "Diagnostic decode skipped after cancellation; token IDs retained"}
    try:
        base = getattr(tokenizer, "base", None)
        if isinstance(base, str):
            response = validate_native_response(
                DETOKENIZE_ENDPOINT, request(base, DETOKENIZE_ENDPOINT, {"tokens": tokens}, timeout=2)
            )
            return {"text": response["content"]}
        return {"text": tokenizer.decode(tokens)}
    except BaseException as decode_error:
        return {"text_error": f"{type(decode_error).__name__}: {decode_error}"}


def measure(
    engine: NativeEngine, tokenizer: NativeTokenizer, ids: Sequence[int], max_new: int = 96, temperature: float = 0
) -> JSONDict:
    first, tokens = None, []
    result: JSONDict = {
        "prompt_tokens": len(ids),
        "prompt_token_ids": list(ids),
        "prompt_sha256": hashlib.sha256(json.dumps(ids).encode()).hexdigest(),
        "max_new": max_new,
        "cache": engine.prompt_cache,
    }
    started = time.monotonic()
    try:
        try:
            with closing(
                engine.generate(ids, max_new, {"temperature": temperature, "seed": 1234}, threading.Event())
            ) as generated:
                for token in generated:
                    if token is not None:
                        first = first or time.monotonic()
                        tokens.append(token)
        finally:
            result.update(
                ttft_s=first - started if first is not None else None,
                wall_s=time.monotonic() - started,
                native_timings=engine.last.get("native_timings"),
                token_ids=tokens,
            )
        timings = result["native_timings"]
        if first is None or not timings:
            raise RuntimeError("Missing first token or native final timings")
        completion_counts(timings, tokens, len(ids), cached=engine.prompt_cache, max_new=max_new)
        if tokens[-1] not in engine.stop_ids:
            raise ValueError("Complete normal-EOS cached answer required")
        result["text"] = tokenizer.decode(tokens)
        case_metrics(result, cached=True)
        result["status"] = "accepted"
        return result
    except BaseException as error:
        if "text" not in result:
            result.update(_failure_text(tokenizer, tokens, error))
        attach_response_failure(error, result)
        raise


def clean(text: str) -> str:
    return text.replace("<|im_end|>", "").replace("<|endoftext|>", "").strip()


def correct(text: str, expected: Sequence[str]) -> bool:
    return clean(text).replace(" ", "") == ",".join(expected)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("model", choices=["small", "flash"], default="flash", nargs="?")
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--histories", type=int, nargs="+", default=[512, 2048])
    ap.add_argument("--spec", choices=["none", "draft-mtp"], default="none")
    ap.add_argument("--draft-model", default="mtp")
    ap.add_argument("--draft", type=int, default=3)
    ap.add_argument("--draft-placement", choices=["gpu", "cpu", "output"], default="gpu")
    ap.add_argument("--label", default="conversation-cache")
    ap.add_argument("--temperature", type=float, default=0)
    args = ap.parse_args()
    if args.repeats < 1 or any(n < 128 or n > 3000 for n in args.histories):
        ap.error("Use at least one repeat and history budgets between 128 and 3000")
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        from check_memory import assert_no_model_server

        assert_no_model_server()
        run(args)


class _PreparedCache(NamedTuple):
    base: str
    command: list[str]
    model_proof: ModelVerification
    engine_info: Mapping[str, Any]


class _CacheSession:
    def __init__(self, args: argparse.Namespace, base: str, process: OwnedProcess) -> None:
        props = request(base, "/props")
        self.tokenizer, self.template = NativeTokenizer(base), NativeTemplate(base)
        stops = stop_tokens(self.tokenizer)
        self.engines = {flag: NativeEngine(base, props, args.model, flag, stop_ids=stops) for flag in (False, True)}
        self.proc = psutil.Process(process.pid)
        self.args = args

    def evaluate(self, engine: NativeEngine, ids: Sequence[int], max_new: int = 96) -> JSONDict:
        return measure(engine, self.tokenizer, ids, max_new, self.args.temperature)

    def encode(self, messages: Sequence[JSONDict]) -> list[int]:
        return self.tokenizer.encode(self.template.render(messages, enable_thinking=False), parse_special=True)


def _source_receipts(record: JSONDict) -> None:
    record["actual_sources"] = {}
    for name, directory in [("llama_cpp", "llama.cpp"), ("strata_macos", "Strata-macOS")]:
        source = ROOT / "vendor" / directory
        revision = command_output(["git", "-C", str(source), "rev-parse", "HEAD"])
        dirty = command_output(["git", "-C", str(source), "status", "--porcelain"])
        record["actual_sources"][name] = {"revision": revision, "dirty": dirty}
        if revision != record["runtime"][name]["revision"] or dirty:
            raise RuntimeError(f"Unpinned or modified source checkout: {directory}")


def _prepare_cache(args: argparse.Namespace, receipt: _Receipt) -> _PreparedCache:
    record = receipt.record
    engine_info = verify_engine("baseline")
    model_ids = [args.model] + ([args.draft_model] if args.spec == "draft-mtp" else [])
    model_proof = verify_models(model_ids, ROOT)
    record.update(selected_engine=engine_info, model_provenance=model_proof)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    command = server_command(
        args.model,
        port,
        4096,
        ubatch=512,
        spec=args.spec,
        draft=args.draft,
        draft_placement=args.draft_placement,
        draft_model=args.draft_model,
    )
    record.update(
        command=command,
        runtime=json.loads((ROOT / "config/runtime.json").read_text()),
        model=json.loads((ROOT / "config/models.json").read_text())[args.model],
        binary_version=command_output([command[0], "--version"]),
        host_before=host_snapshot(),
    )
    record["adapter_sha256"] = hashlib.sha256((ROOT / "scripts/native_backend.py").read_bytes()).hexdigest()
    record["benchmark_sha256"] = hashlib.sha256((ROOT / "scripts/benchmark_cache.py").read_bytes()).hexdigest()
    record["workload_sha256"] = sha256(Path(__file__).with_name("trial_workloads.py"))
    if args.spec == "draft-mtp":
        record["draft_model"] = json.loads((ROOT / "config/models.json").read_text())[args.draft_model]
    _source_receipts(record)
    receipt.save()
    return _PreparedCache(base, command, model_proof, engine_info)


def _paired_case(
    session: _CacheSession,
    receipt: _Receipt,
    workload: JSONDict,
    first_ids: Sequence[int],
    budget: int,
    repetition: int,
    flag: bool,
    order: list[bool],
) -> JSONDict:
    case = {
        "history_budget": budget,
        "repeat": repetition,
        "warmup": repetition == 0,
        "cache": flag,
        "order": order,
        "expected": workload["expected"],
        "messages": workload["messages"],
        "stage": "prime",
    }
    with _preserve_rejection(receipt, case):
        prime = session.evaluate(session.engines[False], first_ids, 16)
        case["prime"] = prime
        if clean(prime["text"]) != "READY":
            raise AssertionError(f"Prime did not follow the ledger instruction: {prime['text']}")
        followup = workload["messages"] + [
            {"role": "assistant", "content": clean(prime["text"])},
            {"role": "user", "content": workload["question"]},
        ]
        case.update(stage="followup", messages=followup)
        ids = session.encode(followup)
        case.update(
            prompt_token_ids=ids,
            rss_before_bytes=session.proc.memory_info().rss,
            swap_before_bytes=psutil.swap_memory().used,
        )
        response = session.evaluate(session.engines[flag], ids)
        case["followup"] = response
        case.update(response)
        case["rss_after_bytes"] = session.proc.memory_info().rss
        case["swap_after_bytes"] = psutil.swap_memory().used
        case["correct"] = correct(case["text"], workload["expected"])
        if not flag and case["native_timings"]["cache_n"]:
            raise AssertionError("Baseline unexpectedly reused prompt tokens")
        if flag and not case["native_timings"]["cache_n"]:
            raise AssertionError("Cached follow-up did not reuse its primed history")
        case.pop("followup")
    return case


def _paired_histories(session: _CacheSession, receipt: _Receipt) -> None:
    record = receipt.record
    args = session.args
    for budget in args.histories:
        for repetition in range(args.repeats + 1):
            workload = build_workload(session.template, session.tokenizer, budget, repetition)
            first_ids = session.encode(workload["messages"])
            order = [False, True] if repetition % 2 == 0 else [True, False]
            paired = {}
            for flag in order:
                case = _paired_case(session, receipt, workload, first_ids, budget, repetition, flag, order)
                record["cases"].append(case)
                paired[flag] = case
                receipt.save()
                print(
                    f"history={budget} repeat={repetition} cache={flag}: TTFT {case['ttft_s']:.3f}s, total {case['wall_s']:.3f}s, reused {case['native_timings']['cache_n']}/{len(case['prompt_token_ids'])}, correct={case['correct']}",
                    flush=True,
                )
            if paired[False]["prompt_sha256"] != paired[True]["prompt_sha256"]:
                raise AssertionError("Paired prompts differ")
            record["checks"].append(
                {
                    "name": f"history-{budget}-pair-{repetition}",
                    "passed": all(case["correct"] for case in paired.values()),
                    "exact_token_match": paired[False]["token_ids"] == paired[True]["token_ids"],
                }
            )


def _cache_state_checks(session: _CacheSession, receipt: _Receipt) -> None:
    record = receipt.record
    # Change an earlier ledger entry and start unrelated chats to detect stale state.
    ledger = build_workload(session.template, session.tokenizer, max(session.args.histories), 20)
    for name, messages, expected in [
        (
            "edit-earlier-record",
            [{**m, "content": m["content"].replace(ledger["expected"][0], "maple-99117")} for m in ledger["messages"]]
            + [{"role": "assistant", "content": "READY"}, {"role": "user", "content": ledger["question"]}],
            ["maple-99117", *ledger["expected"][1:]],
        ),
        (
            "new-chat",
            [{"role": "user", "content": "The fresh chat label is plum-70291. Reply only with that label."}],
            ["plum-70291"],
        ),
        (
            "replace-new-chat-label",
            [{"role": "user", "content": "The fresh chat label is lime-81302. Reply only with that label."}],
            ["lime-81302"],
        ),
    ]:
        seed_messages = ledger["messages"]
        if name == "replace-new-chat-label":
            seed_messages = [
                {"role": "user", "content": "The fresh chat label is plum-70291. Reply only with that label."}
            ]
        check: JSONDict = {"name": name, "expected": expected, "messages": messages, "stage": "seed"}
        with _preserve_rejection(receipt, check):
            check["seed"] = session.evaluate(session.engines[False], session.encode(seed_messages), 32)
            check["stage"] = "cache_on"
            ids = session.encode(messages)
            check["prompt_token_ids"] = ids
            on = session.evaluate(session.engines[True], ids)
            check.update(cache_on=on, stage="cache_off")
            off = session.evaluate(session.engines[False], ids)
            check.update(
                cache_off=off,
                status="accepted",
                passed=correct(on["text"], expected) and correct(off["text"], expected),
                exact_token_match=on["token_ids"] == off["token_ids"],
            )
            record["checks"].append(check)
        receipt.save()


def _stop_cache(process: OwnedProcess | None, monitor: Monitor | None, record: JSONDict) -> None:
    with defer_termination():
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if monitor:
            record["memory"] = monitor.finish()
            if (
                record["memory"]["guard"]
                or not record["memory"]["monitor_healthy"]
                or not record["memory"]["child_exited"]
            ):
                record.update(
                    status="failed",
                    error=record["memory"]["guard"] or "Memory monitoring or child cleanup was incomplete",
                )


def _mode_summary(cases: Sequence[JSONDict]) -> JSONDict:
    return {
        "repeats": len(cases),
        "median_ttft_s": statistics.median(c["ttft_s"] for c in cases),
        "median_wall_s": statistics.median(c["wall_s"] for c in cases),
        "median_generation_tok_s": statistics.median(c["native_timings"]["predicted_per_second"] for c in cases),
        "median_reused_tokens": statistics.median(c["native_timings"]["cache_n"] for c in cases),
        "median_prompt_tokens": statistics.median(c["prompt_tokens"] for c in cases),
        "median_rss_after_bytes": statistics.median(c["rss_after_bytes"] for c in cases),
        "all_correct": all(c["correct"] for c in cases),
    }


def _summarize_cache(args: argparse.Namespace, record: JSONDict) -> None:
    record["summary"] = []
    for budget in args.histories:
        modes = {}
        for flag in (False, True):
            cases = [
                c
                for c in record["cases"]
                if c["history_budget"] == budget
                and c["cache"] == flag
                and not c["warmup"]
                and c.get("status", "accepted") == "accepted"
            ]
            if cases:
                modes[str(flag).lower()] = _mode_summary(cases)
        if len(modes) == 2:
            off, on = modes["false"], modes["true"]
            record["summary"].append(
                {
                    "history_budget": budget,
                    "cache_off": off,
                    "cache_on": on,
                    "ttft_reduction_percent": 100 * (1 - on["median_ttft_s"] / off["median_ttft_s"]),
                    "total_time_reduction_percent": 100 * (1 - on["median_wall_s"] / off["median_wall_s"]),
                    "generation_increase_percent": 100
                    * (on["median_generation_tok_s"] / off["median_generation_tok_s"] - 1),
                    "rss_increase_percent": 100 * (on["median_rss_after_bytes"] / off["median_rss_after_bytes"] - 1),
                }
            )


def _publish_cases(folder: Path, receipt: _Receipt) -> None:
    record = receipt.record
    save = receipt.save
    save()
    with (folder / "cases.csv").open("w", newline="") as output:
        keys = [
            "history_budget",
            "repeat",
            "warmup",
            "cache",
            "prompt_tokens",
            "ttft_s",
            "wall_s",
            "correct",
            "rss_after_bytes",
            "swap_after_bytes",
        ]
        writer = csv.DictWriter(output, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(record["cases"])
    print(f"Saved {receipt.path}", flush=True)


def _finish_cache(
    args: argparse.Namespace,
    prepared: _PreparedCache,
    process: OwnedProcess | None,
    monitor: Monitor | None,
    folder: Path,
    receipt: _Receipt,
) -> None:
    record = receipt.record
    try:
        _stop_cache(process, monitor, record)
        try:
            assert_unchanged(prepared.model_proof, ROOT)
            if verify_engine("baseline") != prepared.engine_info:
                raise RuntimeError("Native engine changed during cache comparison")
        except Exception as error:
            record.update(status="failed", error=f"{type(error).__name__}: {error}")
        record["host_after"] = host_snapshot()
        _summarize_cache(args, record)
        _publish_cases(folder, receipt)
    except BaseException as error:
        record.update(status="failed", cleanup_error=f"{type(error).__name__}: {error}")
        record.setdefault("error", record["cleanup_error"])
        raise
    finally:
        receipt.save()


@cleanup_on_termination()
def run(args: argparse.Namespace) -> None:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + args.model + "-" + args.label
    folder = ROOT / "bench/results" / run_id
    folder.mkdir()
    record = {
        "schema": 1,
        "kind": "conversation-cache" if args.spec == "none" else "prediction-cache",
        "run_id": run_id,
        "settings": vars(args),
        "status": "running",
        "cases": [],
        "checks": [],
        "method": "Paired real adapter runs. Each variant is primed with the same uncached first turn. Follow-up uses identical tokens with cache off/on; order alternates AB/BA. Seed 1234 and temperature from settings, normal EOS, max 96 answer tokens. Each history has an excluded warm-up pair. Compare TTFT and wall time on matched follow-ups, not the earlier synthetic cold-prompt benchmark. OS cache and background activity are uncontrolled. No extra multi-conversation RAM cache. Speculative settings and draft identity are recorded.",
    }
    receipt = _Receipt(folder / "comparison.json", record)
    receipt.save()
    try:
        prepared = _prepare_cache(args, receipt)
    except BaseException as error:
        record.update(status="failed", preparation_failed=True, error=f"{type(error).__name__}: {error}")
        receipt.save()
        raise
    process, monitor = None, None
    with (folder / "server.log").open("w") as log:
        try:
            launch_baseline = Monitor.baseline()
            with defer_termination():
                process = subprocess.Popen(prepared.command, stdout=log, stderr=log)
                monitor = Monitor(process, folder / "memory.jsonl", baseline=launch_baseline)
                monitor.thread.start()
            record["ready_s"] = wait_ready(process, prepared.base)
            session = _CacheSession(args, prepared.base, process)
            _paired_histories(session, receipt)
            _cache_state_checks(session, receipt)
            record["status"] = "passed" if all(case["passed"] for case in record["checks"]) else "correctness-failure"
        except BaseException as error:
            record["status"], record["error"] = "failed", f"{type(error).__name__}: {error}"
            raise
        finally:
            _finish_cache(args, prepared, process, monitor, folder, receipt)
    if record["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
