#!/usr/bin/env python3
"""Run fixed workloads, preserve raw results, and monitor Mac memory pressure."""
import argparse
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import platform
import socket
import statistics
import subprocess
import threading
import time
import urllib.request

import psutil
from lab import ROOT, request, server_command
from engines import ENGINES, verify_engine
from draft_vocab import experiment_environment
from check_memory import assert_no_model_server
from metal_environment import TUNING, configure
from benchmark_metrics import case_metrics


def command_output(command):
    return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()


def host_snapshot():
    return {"os": platform.platform(), "machine": platform.machine(),
            "chip": command_output(["sysctl", "-n", "machdep.cpu.brand_string"]),
            "ram_bytes": psutil.virtual_memory().total, "cpu_count": psutil.cpu_count(),
            "power": command_output(["pmset", "-g", "batt"]),
            "power_settings": command_output(["pmset", "-g", "custom"]),
            "thermal_status": command_output(["pmset", "-g", "therm"]),
            "gpu_wired_limit": command_output(["sysctl", "iogpu.wired_limit_mb"]),
            "vm_stat": command_output(["vm_stat"]),
            "swap": psutil.swap_memory()._asdict(),
            "available_bytes": psutil.virtual_memory().available}


class Monitor:
    @staticmethod
    def baseline():
        return {"swap_used_bytes": psutil.swap_memory().used,
                "available_bytes": psutil.virtual_memory().available}

    def __init__(self, process, path, swap_guard_bytes=2 * 1024**3, minimum_available_bytes=384 * 1024**2, *, baseline=None):
        self.process, self.path = process, path
        self.swap_guard_bytes = swap_guard_bytes
        self.minimum_available_bytes = minimum_available_bytes
        self.done = threading.Event()
        self.baseline_before_launch = baseline is not None
        self.launch_baseline = baseline if baseline is not None else self.baseline()
        self.initial_swap = self.launch_baseline["swap_used_bytes"]
        self.first_sample, self.latest_sample, self.guard = None, None, None
        self.peak_rss, self.minimum_available, self.peak_swap = 0, self.launch_baseline["available_bytes"], self.initial_swap
        self.sample_count, self.live_samples, self.monitor_error = 0, 0, None
        self.start = time.monotonic()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def stop_owned_child(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)

    def fail(self, error):
        self.monitor_error = f"{type(error).__name__}: {error}"
        self.guard = self.guard or "Monitoring failed: " + self.monitor_error
        try:
            self.stop_owned_child()
        except Exception as stop_error:
            self.monitor_error += f"; child stop failed: {stop_error}"

    def sample(self, mem=None):
        vm, swap, io = psutil.virtual_memory(), psutil.swap_memory(), psutil.disk_io_counters()
        sample = {"elapsed_s": round(time.monotonic() - self.start, 3),
                  "rss_bytes": mem.rss if mem else 0, "vms_bytes": mem.vms if mem else 0,
                  "available_bytes": vm.available, "swap_used_bytes": swap.used,
                  "system_disk_read_bytes": io.read_bytes if io else None,
                  "system_disk_write_bytes": io.write_bytes if io else None}
        self.first_sample = self.first_sample or sample
        self.latest_sample = sample
        self.sample_count += 1
        self.live_samples += int(mem is not None)
        self.peak_rss = max(self.peak_rss, sample["rss_bytes"])
        self.minimum_available = min(self.minimum_available, vm.available)
        self.peak_swap = max(self.peak_swap, swap.used)
        return sample

    def run(self):
        low_since = None
        try:
            proc = psutil.Process(self.process.pid)
            with self.path.open("w") as stream:
                while not self.done.is_set():
                    try:
                        mem = proc.memory_info()
                    except psutil.NoSuchProcess:
                        mem = None
                    sample = self.sample(mem)
                    stream.write(json.dumps(sample) + "\n")
                    stream.flush()
                    if sample["available_bytes"] < self.minimum_available_bytes:
                        low_since = low_since or time.monotonic()
                    else:
                        low_since = None
                    if sample["swap_used_bytes"] - self.initial_swap > self.swap_guard_bytes or (low_since and time.monotonic() - low_since > 4):
                        self.guard = (f"Stopped: swap grew by over {self.swap_guard_bytes/1024**2:.0f} MiB "
                                      f"or available memory stayed below {self.minimum_available_bytes/1024**2:.0f} MiB for 4 seconds")
                        self.stop_owned_child()
                        return
                    if mem is None or self.process.poll() is not None:
                        return
                    self.done.wait(0.25)
        except Exception as error:
            self.fail(error)

    def finish(self):
        if self.process.poll() is None:
            self.fail(RuntimeError("Monitoring finished before the owned child exited"))
        self.done.set()
        if self.thread.ident is not None:
            self.thread.join(timeout=2)
        if self.thread.is_alive():
            self.fail(RuntimeError("Monitoring thread did not stop"))
        else:
            try:
                sample = self.sample()
                with self.path.open("a") as stream:
                    stream.write(json.dumps({**sample, "after_child_exit": self.process.poll() is not None}) + "\n")
            except Exception as error:
                self.fail(error)
        if not self.live_samples:
            self.guard = self.guard or "No live child samples; monitoring coverage is incomplete"
        if not self.baseline_before_launch:
            self.guard = self.guard or "No prelaunch memory baseline; update this launch path"
        first_read = (self.first_sample or {}).get("system_disk_read_bytes")
        latest_read = (self.latest_sample or {}).get("system_disk_read_bytes")
        return {"guard": self.guard,
                "monitor_healthy": not self.monitor_error and bool(self.live_samples) and self.baseline_before_launch and not self.thread.is_alive(),
                "monitor_error": self.monitor_error, "samples": self.sample_count,
                "live_samples": self.live_samples, "baseline_before_launch": self.baseline_before_launch,
                "child_exited": self.process.poll() is not None,
                "launch_baseline": self.launch_baseline,
                "peak_rss_bytes": self.peak_rss,
                "minimum_available_bytes": self.minimum_available,
                "peak_swap_bytes": self.peak_swap,
                "swap_growth_bytes": max(0, self.peak_swap - self.initial_swap),
                "system_disk_read_bytes": latest_read - first_read if first_read is not None and latest_read is not None else None,
                "sampling_interval_s": 0.25,
                "note": "RSS is not total Metal memory. Disk counters include all system activity. See native allocation log and vm_stat."}


def wait_ready(process, base, timeout=600):
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        if process.poll() is not None:
            raise RuntimeError(f"Server exited during load with code {process.returncode}; see server.log")
        try:
            if request(base, "/health", timeout=2).get("status") == "ok":
                return time.monotonic() - started
        except (OSError, RuntimeError):
            pass
        time.sleep(0.25)
    raise TimeoutError("Server did not become ready within 600 seconds")


def stream_completion(base, payload):
    started, first, final = time.monotonic(), None, None
    text, ids = [], []
    req = urllib.request.Request(base + "/completion", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as response:
        for line in response:
            if not line.startswith(b"data: "):
                continue
            item = json.loads(line[6:])
            if first is None and (item.get("tokens") or item.get("content")):
                first = time.monotonic()
            text.append(item.get("content", ""))
            ids.extend(item.get("tokens", []))
            if item.get("stop"):
                final = item
    elapsed = time.monotonic() - started
    if final is None or first is None:
        raise RuntimeError("Streaming response has no first token or final timing record")
    return {"ttft_s": first - started, "wall_s": elapsed, "text": "".join(text),
            "generated_token_ids": ids, "final": final}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model", choices=["small", "flash"])
    ap.add_argument("--label", required=True)
    ap.add_argument("--engine", choices=ENGINES, default="baseline")
    ap.add_argument("--draft-vocab", choices=["off", "106k"], default="off")
    ap.add_argument("--real-workloads", action="store_true")
    ap.add_argument("--cached-workloads", action="store_true")
    ap.add_argument("--context", type=int, default=4096)
    ap.add_argument("--batch", type=int, default=512)
    ap.add_argument("--ubatch", type=int, default=128)
    ap.add_argument("--cache-type", default="f16", choices=["f16", "q8_0", "q4_0"])
    ap.add_argument("--spec", default="none", choices=["none", "draft-mtp"])
    ap.add_argument("--draft", type=int, default=3)
    ap.add_argument("--draft-placement", choices=["gpu", "cpu", "output", "mixed"], default="gpu")
    ap.add_argument("--draft-model", default="mtp")
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--draft-threads", type=int)
    ap.add_argument("--draft-p-min", type=float)
    ap.add_argument("--tensor-api", choices=["auto", "on", "off"], default="auto")
    ap.add_argument("--m5-tuning", choices=TUNING, default="stock")
    ap.add_argument("--temperature", type=float, default=0)
    ap.add_argument("--extended-checks", action="store_true")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--warmups", type=int, default=0)
    ap.add_argument("--predict", type=int, default=128)
    ap.add_argument("--prompts", type=int, nargs="+", default=[512, 2048])
    args = ap.parse_args()
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert_no_model_server()
        record = run(args)
        if record["status"] != "passed":
            raise SystemExit(1)


def run(args):
    engine = getattr(args, "engine", "baseline")
    warmups = getattr(args, "warmups", 0)
    if args.repeats < 1 or warmups < 0:
        raise ValueError("Use at least one measured repeat and nonnegative warmups")
    engine_info = verify_engine(engine)
    vocab_mode = getattr(args, "draft_vocab", "off")
    if vocab_mode != "off" and args.spec != "draft-mtp":
        raise ValueError("A draft vocabulary can only be used with prediction enabled")
    env, vocab_info = experiment_environment(engine, vocab_mode)
    env, metal_info = configure(env, engine, getattr(args, "tensor_api", "auto"),
                                getattr(args, "m5_tuning", "stock"))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + args.label
    folder = ROOT / "bench/results" / run_id
    folder.mkdir()
    result_path = folder / "result.json"
    record = {"schema": 1, "run_id": run_id, "status": "running", "settings": vars(args)}
    def save():
        result_path.write_text(json.dumps(record, indent=2) + "\n")
    save()
    try:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        command = server_command(args.model, port, args.context, args.batch, args.ubatch,
                                 args.spec, args.draft, args.cache_type, args.threads, args.draft_placement,
                                 args.draft_model, engine=engine,
                                 draft_threads=getattr(args, "draft_threads", None),
                                 draft_p_min=getattr(args, "draft_p_min", None))
        record = {"schema": 1, "run_id": run_id, "status": "running", "settings": vars(args),
                  "command": command, "runtime": json.loads((ROOT / "config/runtime.json").read_text()),
                  "model": json.loads((ROOT / "config/models.json").read_text())[args.model],
                  "host_before": host_snapshot(), "cases": [], "warmups": [], "checks": [],
                  "selected_engine": engine_info,
                  "draft_vocabulary": vocab_info,
                  "metal_environment": metal_info,
                  "method": "Single slot, full Metal offload, fixed seed 1234; sampling temperature is recorded in settings. Exact synthetic chat prompt sizes and fixed output count from settings; no prompt reuse; ignore EOS for timing only. No model downloads during a run. Warm OS file cache is uncontrolled. TTFT includes HTTP and prompt evaluation. Correctness checks use normal EOS handling."}
        record["actual_sources"] = {}
        for name, directory in [("llama_cpp", "llama.cpp"), ("strata_macos", "Strata-macOS")]:
            path = ROOT / "vendor" / directory
            revision = command_output(["git", "-C", str(path), "rev-parse", "HEAD"])
            dirty = command_output(["git", "-C", str(path), "status", "--porcelain"])
            record["actual_sources"][name] = {"revision": revision, "dirty": dirty}
            if revision != record["runtime"][name]["revision"] or dirty:
                raise RuntimeError(f"Unpinned or modified source checkout: {directory}")
        record["binary_version"] = command_output([command[0], "--version"])
        if args.spec == "draft-mtp":
            record["draft_model"] = json.loads((ROOT / "config/models.json").read_text())[args.draft_model]
        save()
    except BaseException as error:
        record.update(status="failed", error=f"{type(error).__name__}: {error}", preparation_failed=True)
        save()
        raise
    process, monitor = None, None
    with (folder / "server.log").open("w") as log:
        try:
            started = time.monotonic()
            if getattr(args, "require_quiet_host", False):
                from profile_m5_routes import preflight
                record["launch_preflight"] = preflight(small=args.model != "flash")
                save()
            launch_baseline = Monitor.baseline()
            process = subprocess.Popen(command, stdout=log, stderr=log, env=env)
            monitor = Monitor(process, folder / "memory.jsonl",
                              getattr(args, "swap_guard_bytes", 2 * 1024**3),
                              getattr(args, "minimum_available_bytes", 384 * 1024**2), baseline=launch_baseline)
            monitor.thread.start()
            record["ready_s"] = wait_ready(process, base)
            record["props"] = request(base, "/props")
            print(f"{run_id}: ready in {record['ready_s']:.2f}s", flush=True)
            filler = ("The lab machine has 48 GB of memory. Its SSD stores model lookup rows. We compare repeatable inference runs, preserve the baseline, and record speed and memory. " * 600)
            rendered = request(base, "/apply-template", {"messages": [{"role": "user", "content": filler + "Explain a repeatable benchmark in plain language."}], "chat_template_kwargs": {"enable_thinking": False}})["prompt"]
            tokens = request(base, "/tokenize", {"content": rendered, "add_special": False, "parse_special": True})["tokens"]
            for length in args.prompts:
                if length + args.predict + 8 > args.context or length < 64:
                    raise ValueError("Prompt/output length does not fit configured context")
                prompt = tokens[:length - 48] + tokens[-48:]
                prompt_hash = hashlib.sha256(json.dumps(prompt).encode()).hexdigest()
                (folder / f"prompt-{length}.json").write_text(json.dumps(prompt) + "\n")
                for repetition in range(-warmups, args.repeats):
                    payload = {"prompt": prompt, "n_predict": args.predict, "stream": True,
                               "cache_prompt": False, "temperature": args.temperature, "seed": 1234,
                               "ignore_eos": True, "return_tokens": True}
                    io_before = psutil.disk_io_counters()
                    swap_before = psutil.swap_memory().used
                    result = stream_completion(base, payload)
                    io_after = psutil.disk_io_counters()
                    timings = result["final"]["timings"]
                    case = {"prompt_tokens": length, "repeat": repetition + 1, "prompt_sha256": prompt_hash,
                            "workload": "synthetic",
                            "ttft_s": result["ttft_s"], "wall_s": result["wall_s"],
                            "prompt_tok_s": timings["prompt_per_second"],
                            "generation_tok_s": timings["predicted_per_second"],
                            "output_tokens": timings["predicted_n"], "response": result,
                            "system_disk_read_bytes": io_after.read_bytes - io_before.read_bytes if io_before and io_after else None,
                            "swap_before_bytes": swap_before, "swap_after_bytes": psutil.swap_memory().used}
                    if timings["prompt_n"] != length or timings["predicted_n"] != args.predict:
                        raise RuntimeError(f"Benchmark token count mismatch: {timings}")
                    case_metrics(case)
                    record["warmups" if repetition < 0 else "cases"].append(case)
                    save()
                    phase = f"warmup={repetition + warmups + 1}" if repetition < 0 else f"repeat={repetition+1}"
                    print(f"prompt={length} {phase}: {case['generation_tok_s']:.2f} tok/s, TTFT {case['ttft_s']:.2f}s, prompt {case['prompt_tok_s']:.1f} tok/s", flush=True)
            if getattr(args, "real_workloads", False):
                tasks = {
                    "code": "Write Python code for a small LRU cache with get and put methods, a capacity limit, and a demonstration. Explain its correctness and time complexity after the code. Be detailed.",
                    "prose": "Explain how to design a fair computer performance experiment. Cover warmup, input sizes, background activity, repeated trials, latency, throughput and memory. Use about 700 words with concrete examples.",
                    "chinese": "请用中文详细解释如何公平比较两个本地人工智能模型运行程序的性能。讨论预热、输入长度、重复测试、后台程序、首字延迟、生成速度和内存，给出具体例子，写约八百字。",
                }
                for name, content in tasks.items():
                    rendered = request(base, "/apply-template", {"messages": [{"role": "user", "content": content}],
                        "chat_template_kwargs": {"enable_thinking": False}})["prompt"]
                    prompt = request(base, "/tokenize", {"content": rendered, "add_special": False, "parse_special": True})["tokens"]
                    prompt_hash = hashlib.sha256(json.dumps(prompt).encode()).hexdigest()
                    for repetition in range(-warmups, args.repeats):
                        result = stream_completion(base, {"prompt": prompt, "n_predict": args.predict, "stream": True,
                            "cache_prompt": False, "temperature": args.temperature, "seed": 1234,
                            "ignore_eos": True, "return_tokens": True})
                        timings = result["final"]["timings"]
                        if timings["prompt_n"] != len(prompt) or timings["predicted_n"] != args.predict:
                            raise RuntimeError(f"Real-workload token count mismatch: {timings}")
                        case = {"workload": name, "prompt_tokens": len(prompt), "repeat": repetition + 1,
                            "prompt_sha256": prompt_hash, "ttft_s": result["ttft_s"], "wall_s": result["wall_s"],
                            "prompt_tok_s": timings["prompt_per_second"], "generation_tok_s": timings["predicted_per_second"],
                            "output_tokens": timings["predicted_n"], "response": result}
                        case_metrics(case)
                        record["warmups" if repetition < 0 else "cases"].append(case)
                        save()
                        print(f"{name} {'warmup' if repetition < 0 else 'repeat=' + str(repetition+1)}: "
                              f"{case['generation_tok_s']:.2f} tok/s, TTFT {case['ttft_s']:.2f}s", flush=True)
            for prompt, expected in [("What is 17 multiplied by 23? Reply with only the number.", "391"),
                                     ("The lab's secret label is violet-730. Repeat only that exact label.", "violet-730")]:
                response = request(base, "/v1/chat/completions", {"model": args.model,
                                   "messages": [{"role": "user", "content": prompt}],
                                   "temperature": 0, "seed": 1234, "max_tokens": 96,
                                   "chat_template_kwargs": {"enable_thinking": False}, "reasoning_effort": "none"})
                content = response["choices"][0]["message"].get("content") or ""
                record["checks"].append({"prompt": prompt, "expected": expected, "passed": content.strip() == expected,
                                         "response": response})
                save()
            if args.extended_checks:
                from answer_checks import run_answer_checks
                record["checks"].extend(run_answer_checks(base, args.model,
                    multilingual=getattr(args, "real_workloads", False)))
                save()
            if getattr(args, "cached_workloads", False):
                from benchmark_cache import build_workload, clean, correct, measure
                from native_backend import NativeEngine, NativeTemplate, NativeTokenizer
                tokenizer, template = NativeTokenizer(base), NativeTemplate(base)
                native = NativeEngine(base, record["props"], args.model, True)
                record["cached_cases"] = []
                def encode(messages):
                    return tokenizer.encode(template.render(messages, enable_thinking=False), parse_special=True)
                for budget in (512, 2048):
                    for repetition in range(args.repeats + 1):
                        workload = build_workload(template, tokenizer, budget, repetition)
                        native.prompt_cache = False
                        prime = measure(native, tokenizer, encode(workload["messages"]), 16, args.temperature)
                        native.prompt_cache = True
                        if prime["native_timings"]["cache_n"]:
                            raise AssertionError("Ledger priming unexpectedly reused prompt tokens")
                        if clean(prime["text"]) != "READY":
                            raise AssertionError(f"Ledger priming failed: {prime['text']}")
                        messages = workload["messages"] + [{"role": "assistant", "content": clean(prime["text"])},
                            {"role": "user", "content": workload["question"]}]
                        result = measure(native, tokenizer, encode(messages), 96, args.temperature)
                        if not result["native_timings"]["cache_n"]:
                            raise AssertionError("Cached follow-up did not reuse its primed history")
                        passed = correct(result["text"], workload["expected"])
                        record["checks"].append({"name": "cached-ledger", "budget": budget,
                            "repeat": repetition, "passed": passed, "response": result})
                        case = {"history_budget": budget, "repeat": repetition,
                            "warmup": repetition == 0, "expected": workload["expected"], **result}
                        case_metrics(case, cached=True)
                        record["cached_cases"].append(case)
                        save()
                        print(f"cached {budget} {'warmup' if repetition == 0 else 'repeat=' + str(repetition)}: "
                              f"{result['native_timings']['predicted_per_second']:.2f} tok/s, "
                              f"TTFT {result['ttft_s']:.3f}s, correct={passed}", flush=True)
            if getattr(args, "retrieval_budget", None):
                from context_fixture import run_checks
                record["retrieval_cases"] = run_checks(base, args.context, args.retrieval_budget)
                record["checks"].extend({"name":"long-context-retrieval","seed":c["seed"],"passed":c["passed"]} for c in record["retrieval_cases"])
                save()
            with urllib.request.urlopen(base + "/metrics") as response:
                (folder / "metrics.txt").write_bytes(response.read())
            record["run_wall_s"] = time.monotonic() - started
            record["status"] = "passed" if all(c["passed"] for c in record["checks"]) else "completed-check-failure"
        except BaseException as error:
            record["status"], record["error"] = "failed", f"{type(error).__name__}: {error}"
            raise
        finally:
            try:
                if process and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                if monitor:
                    record["memory"] = monitor.finish()
                    if record["memory"]["guard"] or not record["memory"]["monitor_healthy"]:
                        record["status"] = "failed"
                        record.setdefault("error", record["memory"]["guard"] or "Memory monitoring was incomplete")
                record["host_after"] = host_snapshot()
                if record["cases"]:
                    record["summary"] = [{"workload": name, "prompt_tokens": n,
                         **{"median_" + metric: statistics.median(c[metric] for c in record["cases"]
                             if c["prompt_tokens"] == n and c["workload"] == name)
                            for metric in ("generation_tok_s", "ttft_s", "prompt_tok_s")}}
                         for name, n in sorted({(c["workload"], c["prompt_tokens"]) for c in record["cases"]})]
                save()
                with (folder / "cases.csv").open("w", newline="") as output:
                    keys = ["workload", "prompt_tokens", "repeat", "ttft_s", "wall_s", "prompt_tok_s", "generation_tok_s", "output_tokens"]
                    writer = csv.DictWriter(output, fieldnames=keys, extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(record["cases"])
                print(f"Saved {result_path}", flush=True)
            except BaseException as error:
                record.update(status="failed", cleanup_error=f"{type(error).__name__}: {error}")
                record.setdefault("error", record["cleanup_error"])
            finally:
                save()
    return record


if __name__ == "__main__":
    main()
