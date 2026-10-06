#!/usr/bin/env python3
"""Compare the real Strata adapter with prompt reuse off/on on one pinned engine."""
import argparse
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import socket
import statistics
import subprocess
import sys
import threading
import time

import psutil
from benchmark import Monitor, command_output, host_snapshot, wait_ready
from lab import ROOT, request, server_command
from native_backend import NativeEngine, NativeTemplate, NativeTokenizer


def measure(engine, tokenizer, ids, max_new=96, temperature=0):
    started, first, tokens = time.monotonic(), None, []
    for token in engine.generate(ids, max_new, {"temperature": temperature, "seed": 1234}, threading.Event()):
        if token is not None:
            first = first or time.monotonic()
            tokens.append(token)
    elapsed = time.monotonic() - started
    timings = engine.last.get("native_timings")
    if first is None or not timings:
        raise RuntimeError("Missing first token or native final timings")
    if timings["prompt_n"] + timings["cache_n"] != len(ids):
        raise RuntimeError(f"Prompt accounting mismatch: {timings}")
    return {"ttft_s": first - started, "wall_s": elapsed,
            "native_timings": timings, "token_ids": tokens,
            "text": tokenizer.decode(tokens), "prompt_tokens": len(ids),
            "prompt_sha256": hashlib.sha256(json.dumps(ids).encode()).hexdigest()}


def build_workload(template, tokenizer, budget, variant):
    system = {"role": "system", "content": "Use the supplied ledger. Do not guess labels. Follow the requested output format."}
    rows, labels, messages = [], [], None
    for n in range(300):
        label = f"{['cedar', 'violet', 'basil', 'amber'][n % 4]}-{10000 + variant * 317 + n * 43}"
        row = f"R{n:03d}: label={label}; count={(n * 17 + 11) % 97}; color={['red', 'green', 'blue'][n % 3]}."
        candidate = [system, {"role": "user", "content": "Keep this ledger for my next question. Reply only READY.\n" + "\n".join(rows + [row])}]
        ids = tokenizer.encode(template.render(candidate, enable_thinking=False), parse_special=True)
        if len(ids) > budget and rows:
            break
        rows.append(row)
        labels.append(label)
        messages = candidate
    targets = [len(rows) // 4, len(rows) // 2, len(rows) - 1]
    question = "Give only the labels for " + ", ".join(f"R{n:03d}" for n in targets) + ", in that order, separated by commas."
    return {"messages": messages, "question": question, "expected": [labels[n] for n in targets], "records": len(rows)}


def clean(text):
    return text.replace("<|im_end|>", "").replace("<|endoftext|>", "").strip()


def correct(text, expected):
    return clean(text).replace(" ", "") == ",".join(expected)


def main():
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


def run(args):
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + args.model + "-" + args.label
    folder = ROOT / "bench/results" / run_id
    folder.mkdir()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    command = server_command(args.model, port, 4096, ubatch=512, spec=args.spec, draft=args.draft,
                             draft_placement=args.draft_placement, draft_model=args.draft_model)
    record = {"schema": 1, "kind": "conversation-cache" if args.spec == "none" else "prediction-cache", "run_id": run_id,
              "settings": vars(args), "command": command, "status": "running",
              "runtime": json.loads((ROOT / "config/runtime.json").read_text()),
              "model": json.loads((ROOT / "config/models.json").read_text())[args.model],
              "binary_version": command_output([command[0], "--version"]),
              "host_before": host_snapshot(), "cases": [], "checks": [],
              "method": "Paired real adapter runs. Each variant is primed with the same uncached first turn. Follow-up uses identical tokens with cache off/on; order alternates AB/BA. Seed 1234 and temperature from settings, normal EOS, max 96 answer tokens. Each history has an excluded warm-up pair. Compare TTFT and wall time on matched follow-ups, not the earlier synthetic cold-prompt benchmark. OS cache and background activity are uncontrolled. No extra multi-conversation RAM cache. Speculative settings and draft identity are recorded."}
    record["adapter_sha256"] = hashlib.sha256((ROOT / "scripts/native_backend.py").read_bytes()).hexdigest()
    record["benchmark_sha256"] = hashlib.sha256((ROOT / "scripts/benchmark_cache.py").read_bytes()).hexdigest()
    if args.spec == "draft-mtp":
        record["draft_model"] = json.loads((ROOT / "config/models.json").read_text())[args.draft_model]
    record["actual_sources"] = {}
    for name, directory in [("llama_cpp", "llama.cpp"), ("strata_macos", "Strata-macOS")]:
        path = ROOT / "vendor" / directory
        revision = command_output(["git", "-C", str(path), "rev-parse", "HEAD"])
        dirty = command_output(["git", "-C", str(path), "status", "--porcelain"])
        record["actual_sources"][name] = {"revision": revision, "dirty": dirty}
        if revision != record["runtime"][name]["revision"] or dirty:
            raise RuntimeError(f"Unpinned or modified source checkout: {directory}")
    path = folder / "comparison.json"
    def save():
        path.write_text(json.dumps(record, indent=2) + "\n")
    save()
    process, monitor = None, None
    with (folder / "server.log").open("w") as log:
        try:
            process = subprocess.Popen(command, stdout=log, stderr=log)
            monitor = Monitor(process, folder / "memory.jsonl")
            monitor.thread.start()
            record["ready_s"] = wait_ready(process, base)
            props = request(base, "/props")
            tokenizer, template = NativeTokenizer(base), NativeTemplate(base)
            engines = {flag: NativeEngine(base, props, args.model, flag) for flag in (False, True)}
            proc = psutil.Process(process.pid)
            def evaluate(engine, ids, max_new=96):
                return measure(engine, tokenizer, ids, max_new, args.temperature)
            def encode(messages):
                return tokenizer.encode(template.render(messages, enable_thinking=False), parse_special=True)
            for budget in args.histories:
                for repetition in range(args.repeats + 1):
                    workload = build_workload(template, tokenizer, budget, repetition)
                    first_ids = encode(workload["messages"])
                    order = [False, True] if repetition % 2 == 0 else [True, False]
                    paired = {}
                    for flag in order:
                        prime = evaluate(engines[False], first_ids, 16)
                        if clean(prime["text"]) != "READY":
                            raise AssertionError(f"Prime did not follow the ledger instruction: {prime['text']}")
                        followup = workload["messages"] + [{"role": "assistant", "content": clean(prime["text"])},
                                                           {"role": "user", "content": workload["question"]}]
                        ids = encode(followup)
                        case = {"history_budget": budget, "repeat": repetition, "warmup": repetition == 0,
                                "cache": flag, "order": order, "expected": workload["expected"],
                                "messages": followup, "prompt_token_ids": ids, "prime": prime,
                                "rss_before_bytes": proc.memory_info().rss, "swap_before_bytes": psutil.swap_memory().used}
                        case.update(evaluate(engines[flag], ids))
                        case["rss_after_bytes"] = proc.memory_info().rss
                        case["swap_after_bytes"] = psutil.swap_memory().used
                        case["correct"] = correct(case["text"], workload["expected"])
                        if not flag and case["native_timings"]["cache_n"]:
                            raise AssertionError("Baseline unexpectedly reused prompt tokens")
                        record["cases"].append(case)
                        paired[flag] = case
                        save()
                        print(f"history={budget} repeat={repetition} cache={flag}: TTFT {case['ttft_s']:.3f}s, total {case['wall_s']:.3f}s, reused {case['native_timings']['cache_n']}/{len(ids)}, correct={case['correct']}", flush=True)
                    if paired[False]["prompt_sha256"] != paired[True]["prompt_sha256"]:
                        raise AssertionError("Paired prompts differ")
                    record["checks"].append({"name": f"history-{budget}-pair-{repetition}",
                        "passed": all(c["correct"] for c in paired.values()),
                        "exact_token_match": paired[False]["token_ids"] == paired[True]["token_ids"]})
            # Change an earlier ledger entry and start unrelated chats to detect stale state.
            ledger = build_workload(template, tokenizer, max(args.histories), 20)
            for name, messages, expected in [
                ("edit-earlier-record", [{**m, "content": m["content"].replace(ledger["expected"][0], "maple-99117")} for m in ledger["messages"]] +
                  [{"role": "assistant", "content": "READY"}, {"role": "user", "content": ledger["question"]}], ["maple-99117", *ledger["expected"][1:]]),
                ("new-chat", [{"role": "user", "content": "The fresh chat label is plum-70291. Reply only with that label."}], ["plum-70291"]),
                ("replace-new-chat-label", [{"role": "user", "content": "The fresh chat label is lime-81302. Reply only with that label."}], ["lime-81302"]),
            ]:
                seed_messages = ledger["messages"]
                if name == "replace-new-chat-label":
                    seed_messages = [{"role": "user", "content": "The fresh chat label is plum-70291. Reply only with that label."}]
                evaluate(engines[False], encode(seed_messages), 32)
                ids = encode(messages)
                on = evaluate(engines[True], ids)
                off = evaluate(engines[False], ids)
                record["checks"].append({"name": name, "passed": correct(on["text"], expected) and correct(off["text"], expected),
                                         "expected": expected, "prompt_token_ids": ids, "cache_on": on, "cache_off": off,
                                         "exact_token_match": on["token_ids"] == off["token_ids"]})
                save()
            record["status"] = "passed" if all(c["passed"] for c in record["checks"]) else "correctness-failure"
        except BaseException as error:
            record["status"], record["error"] = "failed", f"{type(error).__name__}: {error}"
            raise
        finally:
            if monitor:
                record["memory"] = monitor.finish()
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            record["host_after"] = host_snapshot()
            record["summary"] = []
            for budget in args.histories:
                modes = {}
                for flag in (False, True):
                    cases = [c for c in record["cases"] if c["history_budget"] == budget and c["cache"] == flag and not c["warmup"]]
                    if cases:
                        modes[str(flag).lower()] = {"repeats": len(cases), "median_ttft_s": statistics.median(c["ttft_s"] for c in cases),
                            "median_wall_s": statistics.median(c["wall_s"] for c in cases),
                            "median_generation_tok_s": statistics.median(c["native_timings"]["predicted_per_second"] for c in cases),
                            "median_reused_tokens": statistics.median(c["native_timings"]["cache_n"] for c in cases),
                            "median_prompt_tokens": statistics.median(c["prompt_tokens"] for c in cases),
                            "median_rss_after_bytes": statistics.median(c["rss_after_bytes"] for c in cases),
                            "all_correct": all(c["correct"] for c in cases)}
                if len(modes) == 2:
                    off, on = modes["false"], modes["true"]
                    record["summary"].append({"history_budget": budget, "cache_off": off, "cache_on": on,
                        "ttft_reduction_percent": 100 * (1 - on["median_ttft_s"] / off["median_ttft_s"]),
                        "total_time_reduction_percent": 100 * (1 - on["median_wall_s"] / off["median_wall_s"]),
                        "generation_increase_percent": 100 * (on["median_generation_tok_s"] / off["median_generation_tok_s"] - 1),
                        "rss_increase_percent": 100 * (on["median_rss_after_bytes"] / off["median_rss_after_bytes"] - 1)})
            save()
            with (folder / "cases.csv").open("w", newline="") as output:
                keys = ["history_budget", "repeat", "warmup", "cache", "prompt_tokens", "ttft_s", "wall_s", "correct", "rss_after_bytes", "swap_after_bytes"]
                writer = csv.DictWriter(output, fieldnames=keys, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(record["cases"])
            print(f"Saved {path}", flush=True)
    if record["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
