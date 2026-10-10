#!/usr/bin/env python3
"""Compare opt-in token-piece caching on the real Strata service; requires --run."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
import socket
import statistics
import subprocess
import sys
import threading
import time

from benchmark import Monitor, host_snapshot, wait_ready
from check_memory import assert_no_model_server
from engines import ROOT, sha256, verify_engine
from lab import request, server_command
from metal_environment import configure
from model_provenance import assert_unchanged, verify_models
from native_backend import NativeEngine, NativeTemplate, NativeTokenizer
from profile_m5_routes import preflight
from validate_offline import require_pass

sys.path.insert(0, str(ROOT / "vendor/Strata-macOS"))
from serve.server import Service

RESULTS = ROOT / "bench/results/20261009-next-speed-pass/streaming"
TASKS = {
    "code": "Write Python code for a small LRU cache with get and put methods, a capacity limit, and a demonstration. Explain its correctness and time complexity after the code. Be detailed.",
    "prose": "Explain how to design a fair computer performance experiment. Cover warmup, input sizes, background activity, repeated trials, latency, throughput and memory. Use about 700 words with concrete examples.",
}


class RecordingEngine:
    def __init__(self, native):
        self.native = native
        self.info = native.info
        self.tokens = []
        self.first = None

    @property
    def last(self):
        return self.native.last

    def generate(self, *args):
        for token in self.native.generate(*args):
            if token is not None:
                self.first = self.first or time.monotonic()
                self.tokens.append(token)
            yield token


def measure(base, props, model, ids, cache):
    tok = NativeTokenizer(base, piece_cache=cache)
    engine = RecordingEngine(NativeEngine(base, props, model, prompt_cache=False))
    service = Service(engine, tok, None)
    started = time.monotonic()
    events, first_text = [], None
    for kind, item in service.run(ids, False, [], 256, {"temperature": 0.6, "seed": 1234}, threading.Event()):
        if kind == "event":
            events.append(asdict(item))
            if item.text and first_text is None:
                first_text = time.monotonic()
        elif kind == "done":
            done = item
    wall = time.monotonic() - started
    timing = engine.last.get("native_timings")
    if not timing or timing["predicted_n"] != 256 or timing["cache_n"] != 0 or len(engine.tokens) != 256:
        raise ValueError("Incomplete fixed-token output or unexpectedly cached prompt")
    return dict(wall_s=wall, ttft_s=engine.first - started, first_text_s=first_text - started,
                tokens=engine.tokens, events=events, done=done, native_timings=timing,
                decode_stats=tok.decode_stats, cache_entries=len(tok.pieces), cache_bytes=tok.piece_bytes)


def summarize(cases):
    rows = []
    for task in TASKS:
        selected = [c for c in cases if c["task"] == task and not c["warmup"]]
        def med(pass_id, field):
            return statistics.median(c[field] for c in selected if c["pass"] == pass_id)
        control = statistics.median(c["wall_s"] for c in selected if not c["cache"])
        candidate = statistics.median(c["wall_s"] for c in selected if c["cache"])
        gain = 100 * (1 - candidate / control)
        drift = 100 * (1 - med(3, "wall_s") / med(0, "wall_s"))
        groups = {}
        for cache in (False, True):
            subset = [c for c in selected if c["cache"] == cache]
            groups[str(cache)] = {"wall_s": statistics.median(c["wall_s"] for c in subset),
                "native_tps": statistics.median(c["native_timings"]["predicted_per_second"] for c in subset),
                "first_text_s": statistics.median(c["first_text_s"] for c in subset),
                "decode_requests": statistics.median(c["decode_stats"]["requests"] for c in subset),
                "serialized_token_ids": statistics.median(c["decode_stats"]["input_tokens"] for c in subset)}
        rows.append(dict(task=task, control=control, candidate=candidate, reply_reduction_percent=gain,
                         control_drift_percent=drift, qualifies=gain >= 1 and gain > 2 * abs(drift), metrics=groups))
    return rows


def run(model):
    RESULTS.mkdir(parents=True, exist_ok=True)
    folder = RESULTS / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + model)
    folder.mkdir()
    sources = {str(p.relative_to(ROOT)): sha256(p) for p in
               [*sorted((ROOT / "scripts").glob("*.py")), ROOT / "vendor/Strata-macOS/serve/server.py"]}
    record = dict(status="running", model=model, sources=sources, engine=verify_engine("m5-copy"),
                  host_before=host_snapshot(), cases=[], method="One engine, fresh cache-off native requests. Each tokenizer cache is empty per request. Independent ABBA for code/prose, excluded warmup then three repeats. Native TPS is distinct from app reply latency. No final-display latency claim.")
    process, monitor = None, None
    def save():
        (folder / "comparison.json").write_text(json.dumps(record, indent=2) + "\n")
    save()
    try:
        models = verify_models([model, "mtp_shared_packed_q3"] if model == "flash" else [model])
        record["models"] = models
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        command = server_command(model, port, 4096, batch=512, ubatch=512, engine="m5-copy",
            spec="draft-mtp" if model == "flash" else "none", draft=3, draft_placement="mixed" if model == "flash" else "gpu",
            draft_model="mtp_shared_packed_q3", draft_threads=8 if model == "flash" else None,
            draft_p_min=0.0 if model == "flash" else None)
        env, flags = configure(dict(os.environ), "m5-copy", "on", "conv-direct")
        record.update(command=command, metal_environment=flags, launch_preflight=preflight(small=model != "flash"))
        save()
        with (folder / "server.log").open("w") as log:
            baseline = Monitor.baseline()
            process = subprocess.Popen(command, stdout=log, stderr=log, env=env)
            monitor = Monitor(process, folder / "memory.jsonl", 0, 1024**3, baseline=baseline)
            monitor.thread.start()
            record["ready_s"] = wait_ready(process, base)
            props = request(base, "/props")
            record["props"] = props
            tok, template = NativeTokenizer(base), NativeTemplate(base)
            prompts = {name: tok.encode(template.render([{"role": "user", "content": text}], enable_thinking=False), parse_special=True)
                       for name, text in TASKS.items()}
            record["prompts"] = prompts
            # Real native byte-boundary qualification is outside reply timings.
            qualification = []
            for text in ("Hello, cafe\u00e9 - \u2014 \U0001f30d", "<think>reason</think>answer", "def f(x):\n    return x + 1\n" * 4):
                ids = tok.encode(text, parse_special=True)
                candidate = NativeTokenizer(base, piece_cache=True)
                for n in range(1, len(ids) + 1):
                    if candidate.decode(ids[:n]) != tok.decode(ids[:n]):
                        raise ValueError("Actual native prefix qualification mismatch")
                qualification.append(dict(text=text, ids=ids, prefixes=len(ids), decode_stats=candidate.decode_stats))
            record["prefix_qualification"] = qualification
            save()
            for task, ids in prompts.items():
                reference = None
                for pass_id, cache in enumerate((False, True, True, False)):
                    for repetition in range(4):
                        if monitor.guard:
                            raise RuntimeError("Resource guard fired")
                        result = measure(base, props, model, ids, cache)
                        signature = (result["tokens"], result["events"], result["done"])
                        if reference is None:
                            reference = signature
                        if signature != reference:
                            raise ValueError("Exact token/parser event/finish parity failed")
                        record["cases"].append(dict(task=task, cache=cache, **{"pass": pass_id}, repeat=repetition,
                                                     warmup=repetition == 0, **result))
                        save()
                        print(task, pass_id, repetition, round(result["wall_s"], 4), result["decode_stats"], flush=True)
            if {p: sha256(ROOT / p) for p in sources} != sources:
                raise ValueError("Timing sources changed")
            assert_unchanged(models)
            if verify_engine("m5-copy") != record["engine"]:
                raise ValueError("Native engine changed")
            record.update(status="passed", summary=summarize(record["cases"]), exact_outputs=True)
    except BaseException as error:
        record.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=10)
        if monitor:
            record["memory"] = monitor.finish()
            if record["memory"]["swap_growth_bytes"] or record["memory"]["guard"] or not record["memory"]["monitor_healthy"]:
                record.update(status="failed", error="Memory guard or monitor failure")
        record["host_after"] = host_snapshot()
        save()
    if record["status"] != "passed":
        raise RuntimeError(record.get("error", "Comparison failed"))
    lines = ["# Token-piece cache: actual service response comparison", "", record["method"], "",
             "| Task | Control reply s | Candidate reply s | Quicker | Control drift | Qualified |", "| --- | ---: | ---: | ---: | ---: | --- |"]
    for row in record["summary"]:
        lines.append(f"| {row['task']} | {row['control']:.6f} | {row['candidate']:.6f} | {row['reply_reduction_percent']:+.3f}% | {row['control_drift_percent']:+.3f}% | {row['qualifies']} |")
    lines += ["", "All timed token IDs/parser events match; no new swap. >=1% complete-reply improvement on both tasks above twice their own drift is required for adoption. Native TPS changes are observations, not an attributed native acceleration.", "", "[Raw evidence](comparison.json)"]
    (folder / "REPORT.md").write_text("\n".join(lines) + "\n")
    print("Completed:", folder, flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", choices=("small", "flash"), default="small")
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args()
    if not args.run:
        print("Prepared service comparison for", args.model); return
    require_pass()
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert_no_model_server()
        run(args.model)


if __name__ == "__main__":
    main()
