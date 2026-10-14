"""Fixed-workload execution with explicit trial I/O and receipt ownership."""

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol, cast
import urllib.request

JSONDict = dict[str, Any]


class WorkloadRequest(Protocol):
    def __call__(self, base: str, endpoint: str, payload: object = None) -> dict[str, object]: ...


class WorkloadStream(Protocol):
    def __call__(self, base: str, payload: JSONDict) -> JSONDict: ...


class WorkloadValidation(Protocol):
    def __call__(self, case: Mapping[str, object], cached: bool = False) -> object: ...


class DiskCounters(Protocol):
    @property
    def read_bytes(self) -> int: ...


@dataclass
class TrialWorkloads:
    args: argparse.Namespace
    base: str
    folder: Path
    record: JSONDict
    save: Callable[[], None]
    warmups: int
    root: Path
    request: WorkloadRequest
    stream_completion: WorkloadStream
    case_metrics: WorkloadValidation
    disk_io_counters: Callable[[], DiskCounters | None]
    swap_used: Callable[[], int]


def _synthetic_case(
    context: TrialWorkloads, prompt: list[int], length: int, repetition: int, prompt_hash: str
) -> JSONDict:
    payload = {
        "prompt": prompt,
        "n_predict": context.args.predict,
        "stream": True,
        "cache_prompt": False,
        "temperature": context.args.temperature,
        "seed": 1234,
        "ignore_eos": True,
        "return_tokens": True,
    }
    io_before = context.disk_io_counters()
    swap_before = context.swap_used()
    result = context.stream_completion(context.base, payload)
    io_after = context.disk_io_counters()
    timings = result["final"]["timings"]
    case = {
        "prompt_tokens": length,
        "repeat": repetition + 1,
        "prompt_sha256": prompt_hash,
        "workload": "synthetic",
        "ttft_s": result["ttft_s"],
        "wall_s": result["wall_s"],
        "prompt_tok_s": timings["prompt_per_second"],
        "generation_tok_s": timings["predicted_per_second"],
        "output_tokens": timings["predicted_n"],
        "response": result,
        "system_disk_read_bytes": io_after.read_bytes - io_before.read_bytes if io_before and io_after else None,
        "swap_before_bytes": swap_before,
        "swap_after_bytes": context.swap_used(),
    }
    if timings["prompt_n"] != length or timings["predicted_n"] != context.args.predict:
        raise RuntimeError(f"Benchmark token count mismatch: {timings}")
    context.case_metrics(case)
    return case


def _synthetic_workloads(context: TrialWorkloads) -> None:
    record = context.record
    save = context.save
    filler = (
        "The lab machine has 48 GB of memory. Its SSD stores model lookup rows. We compare repeatable inference runs, preserve the baseline, and record speed and memory. "
        * 600
    )
    rendered = context.request(
        context.base,
        "/apply-template",
        {
            "messages": [{"role": "user", "content": filler + "Explain a repeatable benchmark in plain language."}],
            "chat_template_kwargs": {"enable_thinking": False},
        },
    )["prompt"]
    tokens = cast(
        list[int],
        context.request(context.base, "/tokenize", {"content": rendered, "add_special": False, "parse_special": True})[
            "tokens"
        ],
    )
    for length in context.args.prompts:
        if length + context.args.predict + 8 > context.args.context or length < 64:
            raise ValueError("Prompt/output length does not fit configured context")
        prompt = tokens[: length - 48] + tokens[-48:]
        prompt_hash = hashlib.sha256(json.dumps(prompt).encode()).hexdigest()
        (context.folder / f"prompt-{length}.json").write_text(json.dumps(prompt) + "\n")
        for repetition in range(-context.warmups, context.args.repeats):
            case = _synthetic_case(context, prompt, length, repetition, prompt_hash)
            record["warmups" if repetition < 0 else "cases"].append(case)
            save()
            phase = f"warmup={repetition + context.warmups + 1}" if repetition < 0 else f"repeat={repetition + 1}"
            print(
                f"prompt={length} {phase}: {case['generation_tok_s']:.2f} tok/s, TTFT {case['ttft_s']:.2f}s, prompt {case['prompt_tok_s']:.1f} tok/s",
                flush=True,
            )


def _real_tasks(context: TrialWorkloads) -> JSONDict:
    record = context.record
    save = context.save
    tasks = {
        "code": "Write Python code for a small LRU cache with get and put methods, a capacity limit, and a demonstration. Explain its correctness and time complexity after the code. Be detailed.",
        "prose": "Explain how to design a fair computer performance experiment. Cover warmup, input sizes, background activity, repeated trials, latency, throughput and memory. Use about 700 words with concrete examples.",
    }
    if getattr(context.args, "real_workload_file", None):
        fixture = context.root / context.args.real_workload_file
        fixture_bytes = fixture.read_bytes()
        if hashlib.sha256(fixture_bytes).hexdigest() != context.args.real_workload_sha256:
            raise ValueError("Real-workload fixture changed since settings were pinned")
        tasks = json.loads(fixture_bytes)
        if set(tasks) != {"code", "prose"} or any(
            not isinstance(v, str) or not v.strip() or len(v) > 32768 for v in tasks.values()
        ):
            raise ValueError("Expected two bounded English code/prose workload strings")
        record["real_workload_fixture"] = {
            "path": context.args.real_workload_file,
            "sha256": context.args.real_workload_sha256,
            "tasks": tasks,
        }
        save()
    return tasks


def _real_workloads(context: TrialWorkloads) -> None:
    record = context.record
    save = context.save
    tasks = _real_tasks(context)
    for name, content in tasks.items():
        rendered = context.request(
            context.base,
            "/apply-template",
            {"messages": [{"role": "user", "content": content}], "chat_template_kwargs": {"enable_thinking": False}},
        )["prompt"]
        prompt = cast(
            list[int],
            context.request(
                context.base, "/tokenize", {"content": rendered, "add_special": False, "parse_special": True}
            )["tokens"],
        )
        if len(prompt) + context.args.predict + 8 > context.args.context:
            raise ValueError("Real prompt/output length does not fit configured context")
        prompt_hash = hashlib.sha256(json.dumps(prompt).encode()).hexdigest()
        for repetition in range(-context.warmups, context.args.repeats):
            result = context.stream_completion(
                context.base,
                {
                    "prompt": prompt,
                    "n_predict": context.args.predict,
                    "stream": True,
                    "cache_prompt": False,
                    "temperature": context.args.temperature,
                    "seed": 1234,
                    "ignore_eos": True,
                    "return_tokens": True,
                },
            )
            timings = result["final"]["timings"]
            if timings["prompt_n"] != len(prompt) or timings["predicted_n"] != context.args.predict:
                raise RuntimeError(f"Real-workload token count mismatch: {timings}")
            case = {
                "workload": name,
                "prompt_tokens": len(prompt),
                "repeat": repetition + 1,
                "prompt_sha256": prompt_hash,
                "ttft_s": result["ttft_s"],
                "wall_s": result["wall_s"],
                "prompt_tok_s": timings["prompt_per_second"],
                "generation_tok_s": timings["predicted_per_second"],
                "output_tokens": timings["predicted_n"],
                "response": result,
            }
            context.case_metrics(case)
            record["warmups" if repetition < 0 else "cases"].append(case)
            save()
            print(
                f"{name} {('warmup' if repetition < 0 else 'repeat=' + str(repetition + 1))}: {case['generation_tok_s']:.2f} tok/s, TTFT {case['ttft_s']:.2f}s",
                flush=True,
            )


def _answer_checks(context: TrialWorkloads) -> None:
    record = context.record
    save = context.save
    for prompt, expected in [
        ("What is 17 multiplied by 23? Reply with only the number.", "391"),
        ("The lab's secret label is violet-730. Repeat only that exact label.", "violet-730"),
    ]:
        response = context.request(
            context.base,
            "/v1/chat/completions",
            {
                "model": context.args.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "seed": 1234,
                "max_tokens": 96,
                "chat_template_kwargs": {"enable_thinking": False},
                "reasoning_effort": "none",
            },
        )
        choices = cast(list[JSONDict], response["choices"])
        content = choices[0]["message"].get("content") or ""
        record["checks"].append(
            {"prompt": prompt, "expected": expected, "passed": content.strip() == expected, "response": response}
        )
        save()
    if context.args.extended_checks:
        from answer_checks import run_answer_checks

        record["checks"].extend(run_answer_checks(context.base, context.args.model, multilingual=False))
        save()


def _cached_workloads(context: TrialWorkloads) -> None:
    record = context.record
    save = context.save
    from benchmark_cache import build_workload, clean, correct, measure, stop_tokens
    from native_backend import NativeEngine, NativeTemplate, NativeTokenizer

    tokenizer, template = (NativeTokenizer(context.base), NativeTemplate(context.base))
    native = NativeEngine(context.base, record["props"], context.args.model, True, stop_ids=stop_tokens(tokenizer))
    record["cached_cases"] = []

    def encode(messages: Sequence[JSONDict]) -> list[int]:
        return tokenizer.encode(template.render(messages, enable_thinking=False), parse_special=True)

    for budget in (512, 2048):
        for repetition in range(context.args.repeats + 1):
            workload = build_workload(template, tokenizer, budget, repetition)
            native.prompt_cache = False
            prime = measure(native, tokenizer, encode(workload["messages"]), 16, context.args.temperature)
            native.prompt_cache = True
            if prime["native_timings"]["cache_n"]:
                raise AssertionError("Ledger priming unexpectedly reused prompt tokens")
            if clean(prime["text"]) != "READY":
                raise AssertionError(f"Ledger priming failed: {prime['text']}")
            messages = workload["messages"] + [
                {"role": "assistant", "content": clean(prime["text"])},
                {"role": "user", "content": workload["question"]},
            ]
            result = measure(native, tokenizer, encode(messages), 96, context.args.temperature)
            if not result["native_timings"]["cache_n"]:
                raise AssertionError("Cached follow-up did not reuse its primed history")
            passed = correct(result["text"], workload["expected"])
            record["checks"].append(
                {"name": "cached-ledger", "budget": budget, "repeat": repetition, "passed": passed, "response": result}
            )
            case = {
                "history_budget": budget,
                "repeat": repetition,
                "warmup": repetition == 0,
                "expected": workload["expected"],
                **result,
            }
            context.case_metrics(case, cached=True)
            record["cached_cases"].append(case)
            save()
            print(
                f"cached {budget} {('warmup' if repetition == 0 else 'repeat=' + str(repetition))}: {result['native_timings']['predicted_per_second']:.2f} tok/s, TTFT {result['ttft_s']:.3f}s, correct={passed}",
                flush=True,
            )


def measure_workloads(context: TrialWorkloads) -> None:
    _synthetic_workloads(context)
    if getattr(context.args, "real_workloads", False):
        _real_workloads(context)
    _answer_checks(context)
    if getattr(context.args, "cached_workloads", False):
        _cached_workloads(context)
    if getattr(context.args, "retrieval_budget", None):
        from context_fixture import run_checks

        record = context.record
        record["retrieval_cases"] = run_checks(context.base, context.args.context, context.args.retrieval_budget)
        record["checks"].extend(
            {"name": "long-context-retrieval", "seed": case["seed"], "passed": case["passed"]}
            for case in record["retrieval_cases"]
        )
        context.save()
    with urllib.request.urlopen(context.base + "/metrics") as response:
        (context.folder / "metrics.txt").write_bytes(response.read())
