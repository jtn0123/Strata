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
    def __init__(self, process, path):
        self.process, self.path = process, path
        self.done = threading.Event()
        self.initial_swap = psutil.swap_memory().used
        self.first_sample, self.latest_sample, self.guard = None, None, None
        self.peak_rss, self.minimum_available, self.peak_swap = 0, psutil.virtual_memory().total, self.initial_swap
        self.start = time.monotonic()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        proc = psutil.Process(self.process.pid)
        low_since = None
        with self.path.open("w") as stream:
            while not self.done.is_set():
                try:
                    vm, swap = psutil.virtual_memory(), psutil.swap_memory()
                    mem = proc.memory_info()
                    io = psutil.disk_io_counters()
                    sample = {"elapsed_s": round(time.monotonic() - self.start, 3),
                              "rss_bytes": mem.rss, "vms_bytes": mem.vms,
                              "available_bytes": vm.available, "swap_used_bytes": swap.used,
                              "system_disk_read_bytes": io.read_bytes if io else None,
                              "system_disk_write_bytes": io.write_bytes if io else None}
                    self.first_sample = self.first_sample or sample
                    self.latest_sample = sample
                    self.peak_rss = max(self.peak_rss, mem.rss)
                    self.minimum_available = min(self.minimum_available, vm.available)
                    self.peak_swap = max(self.peak_swap, swap.used)
                    stream.write(json.dumps(sample) + "\n")
                    stream.flush()
                    if vm.available < 384 * 1024**2:
                        low_since = low_since or time.monotonic()
                    else:
                        low_since = None
                    if swap.used - self.initial_swap > 2 * 1024**3 or (low_since and time.monotonic() - low_since > 4):
                        self.guard = "Stopped: swap grew by over 2 GiB or available memory stayed below 384 MiB for 4 seconds"
                        self.process.terminate()
                        return
                except psutil.NoSuchProcess:
                    return
                self.done.wait(0.25)

    def finish(self):
        self.done.set()
        self.thread.join(timeout=2)
        if self.first_sample is None:
            return {"guard": self.guard}
        return {"guard": self.guard,
                "peak_rss_bytes": self.peak_rss,
                "minimum_available_bytes": self.minimum_available,
                "peak_swap_bytes": self.peak_swap,
                "swap_growth_bytes": max(0, self.peak_swap - self.initial_swap),
                "system_disk_read_bytes": (self.latest_sample["system_disk_read_bytes"] or 0) - (self.first_sample["system_disk_read_bytes"] or 0),
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
    ap.add_argument("--context", type=int, default=4096)
    ap.add_argument("--batch", type=int, default=512)
    ap.add_argument("--ubatch", type=int, default=128)
    ap.add_argument("--cache-type", default="f16", choices=["f16", "q8_0", "q4_0"])
    ap.add_argument("--spec", default="none", choices=["none", "draft-mtp"])
    ap.add_argument("--draft", type=int, default=3)
    ap.add_argument("--draft-placement", choices=["gpu", "cpu", "output"], default="gpu")
    ap.add_argument("--draft-model", default="mtp")
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--temperature", type=float, default=0)
    ap.add_argument("--extended-checks", action="store_true")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--predict", type=int, default=128)
    ap.add_argument("--prompts", type=int, nargs="+", default=[512, 2048])
    args = ap.parse_args()
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        binary = str(ROOT / "vendor/llama.cpp/build/bin/llama-server")
        if any(p.info["exe"] == binary for p in psutil.process_iter(["exe"])):
            raise RuntimeError("Stop the running lab model before benchmarking")
        record = run(args)
        if record["status"] != "passed":
            raise SystemExit(1)


def run(args):
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + args.label
    folder = ROOT / "bench/results" / run_id
    folder.mkdir()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    command = server_command(args.model, port, args.context, args.batch, args.ubatch,
                             args.spec, args.draft, args.cache_type, args.threads, args.draft_placement,
                             args.draft_model)
    record = {"schema": 1, "run_id": run_id, "status": "running", "settings": vars(args),
              "command": command, "runtime": json.loads((ROOT / "config/runtime.json").read_text()),
              "model": json.loads((ROOT / "config/models.json").read_text())[args.model],
              "host_before": host_snapshot(), "cases": [], "checks": [],
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
    result_path = folder / "result.json"
    if args.spec == "draft-mtp":
        record["draft_model"] = json.loads((ROOT / "config/models.json").read_text())[args.draft_model]
    def save():
        result_path.write_text(json.dumps(record, indent=2) + "\n")
    save()
    process, monitor = None, None
    with (folder / "server.log").open("w") as log:
        try:
            started = time.monotonic()
            process = subprocess.Popen(command, stdout=log, stderr=log)
            monitor = Monitor(process, folder / "memory.jsonl")
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
                for repetition in range(args.repeats):
                    payload = {"prompt": prompt, "n_predict": args.predict, "stream": True,
                               "cache_prompt": False, "temperature": args.temperature, "seed": 1234,
                               "ignore_eos": True, "return_tokens": True}
                    io_before = psutil.disk_io_counters()
                    swap_before = psutil.swap_memory().used
                    result = stream_completion(base, payload)
                    io_after = psutil.disk_io_counters()
                    timings = result["final"]["timings"]
                    case = {"prompt_tokens": length, "repeat": repetition + 1, "prompt_sha256": prompt_hash,
                            "ttft_s": result["ttft_s"], "wall_s": result["wall_s"],
                            "prompt_tok_s": timings["prompt_per_second"],
                            "generation_tok_s": timings["predicted_per_second"],
                            "output_tokens": timings["predicted_n"], "response": result,
                            "system_disk_read_bytes": io_after.read_bytes - io_before.read_bytes if io_before and io_after else None,
                            "swap_before_bytes": swap_before, "swap_after_bytes": psutil.swap_memory().used}
                    if timings["prompt_n"] != length or timings["predicted_n"] != args.predict:
                        raise RuntimeError(f"Benchmark token count mismatch: {timings}")
                    record["cases"].append(case)
                    save()
                    print(f"prompt={length} repeat={repetition+1}: {case['generation_tok_s']:.2f} tok/s, TTFT {case['ttft_s']:.2f}s, prompt {case['prompt_tok_s']:.1f} tok/s", flush=True)
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
                record["checks"].extend(run_answer_checks(base, args.model))
                save()
            with urllib.request.urlopen(base + "/metrics") as response:
                (folder / "metrics.txt").write_bytes(response.read())
            record["run_wall_s"] = time.monotonic() - started
            record["status"] = "passed" if all(c["passed"] for c in record["checks"]) else "completed-check-failure"
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
            if record["cases"]:
                record["summary"] = [{"prompt_tokens": n,
                     "median_generation_tok_s": statistics.median(c["generation_tok_s"] for c in record["cases"] if c["prompt_tokens"] == n),
                     "median_ttft_s": statistics.median(c["ttft_s"] for c in record["cases"] if c["prompt_tokens"] == n),
                     "median_prompt_tok_s": statistics.median(c["prompt_tok_s"] for c in record["cases"] if c["prompt_tokens"] == n)}
                     for n in sorted({c["prompt_tokens"] for c in record["cases"]})]
            save()
            with (folder / "cases.csv").open("w", newline="") as output:
                keys = ["prompt_tokens", "repeat", "ttft_s", "wall_s", "prompt_tok_s", "generation_tok_s", "output_tokens"]
                writer = csv.DictWriter(output, fieldnames=keys, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(record["cases"])
            print(f"Saved {result_path}", flush=True)
    return record


if __name__ == "__main__":
    main()
