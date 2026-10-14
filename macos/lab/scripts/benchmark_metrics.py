"""Reject invalid measurements before aggregation or percentage calculation."""

import json
import math
import statistics
from collections.abc import Mapping, Sequence
from typing import Literal, Protocol, TypedDict, cast

type MetricName = Literal["generation_tok_s", "prompt_tok_s", "ttft_s", "wall_s"]
type Number = int | float
type Rates = dict[MetricName, Number]
METRICS: tuple[MetricName, ...] = ("generation_tok_s", "prompt_tok_s", "ttft_s", "wall_s")


class RejectedEvidence(Protocol):
    benchmark_response: dict[str, object]


def attach_response_failure(error: BaseException, response: Mapping[str, object]) -> None:
    """Retain JSON-native rejected evidence without changing the original error.

    Native JSON may contain invalid nonfinite counters. Keep them as explicit
    diagnostic strings, so a strict receipt can be saved without publishing TPS.
    """
    evidence = dict(response, status="rejected", error=f"{type(error).__name__}: {error}")
    safe = cast(dict[str, object], json.loads(json.dumps(evidence), parse_constant=str))
    cast(RejectedEvidence, error).benchmark_response = safe


class TimingEvidence(TypedDict, total=False):
    predicted_n: object
    prompt_n: object
    cache_n: object
    predicted_per_second: object
    prompt_per_second: object
    draft_n: object
    draft_n_accepted: object


class FinalEvidence(TypedDict):
    timings: TimingEvidence


class CompletionEvidence(TypedDict):
    final: FinalEvidence


class MeasurementCase(TypedDict, total=False):
    workload: str
    prompt_tokens: int
    history_budget: int
    repeat: int
    generation_tok_s: object
    prompt_tok_s: object
    ttft_s: object
    wall_s: object
    native_timings: TimingEvidence
    response: CompletionEvidence


class AggregateMetrics(TypedDict):
    generation_tok_s: Number
    prompt_tok_s: Number
    ttft_s: Number
    wall_s: Number
    draft_acceptance_percent: float | None


class MetricChanges(TypedDict):
    generation_increase_percent: float
    prompt_increase_percent: float
    ttft_reduction_percent: float
    total_time_reduction_percent: float


def positive(value: object, label: str) -> Number:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label}: expected a finite positive measurement, got {value!r}")
    return value


def counter(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label}: expected a nonnegative integer counter, got {value!r}")
    return value


def elapsed(value: object, label: str) -> Number:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{label}: expected a finite nonnegative measurement, got {value!r}")
    return value


def completion_counts(
    timings: Mapping[str, object],
    ids: Sequence[object],
    prompt_tokens: int | None = None,
    *,
    cached: bool = False,
    max_new: int | None = None,
) -> int:
    """Match native counters to the actual request and emitted token IDs."""
    if not ids or any(type(token) is not int or token < 0 for token in ids):
        raise ValueError("Actual nonempty output token IDs required")
    return validate_final_record(timings, len(ids), prompt_tokens, cached=cached, max_new=max_new)


def validate_final_record(
    timings: Mapping[str, object],
    emitted: int,
    prompt_tokens: int | None = None,
    *,
    cached: bool = False,
    max_new: int | None = None,
) -> int:
    """A final record must describe this request: each emitted token, the whole prompt, real times.

    predicted_n counts every streamed token, the end-of-turn token included (llama.cpp n_gen).
    """
    generated = counter(timings["predicted_n"], "predicted_n")
    if generated != emitted or max_new is not None and generated > max_new:
        raise ValueError("Native output count differs from emitted tokens or requested cap")
    if prompt_tokens is not None:
        read = counter(timings["prompt_n"], "prompt_n")
        reused = counter(timings.get("cache_n", 0), "cache_n")
        if read + reused != prompt_tokens or not cached and reused:
            raise ValueError("Native prompt count differs from the complete requested input")
    for key in ("prompt_ms", "predicted_ms"):
        elapsed(timings.get(key), key)
    for key in ("prompt_per_second", "predicted_per_second"):
        if key in timings:
            elapsed(timings.get(key), key)
    if counter(timings.get("draft_n_accepted", 0), "draft_n_accepted") > counter(timings.get("draft_n", 0), "draft_n"):
        raise ValueError("Native accepted draft count exceeds proposals")
    return generated


def case_metrics(case: Mapping[str, object], cached: bool = False) -> tuple[Rates, int, int]:
    label = (
        f"{case.get('workload', 'cached' if cached else 'case')}/"
        f"{case.get('prompt_tokens', case.get('history_budget', '?'))}/repeat={case.get('repeat', '?')}"
    )
    # Cases enter from saved/native JSON. Narrow their nested container contract
    # here; positive/counter below still validate every raw numerical value.
    evidence = cast(MeasurementCase, case)
    values: Mapping[str, object] = (
        {
            "generation_tok_s": evidence["native_timings"]["predicted_per_second"],
            "prompt_tok_s": evidence["native_timings"]["prompt_per_second"],
            "ttft_s": case["ttft_s"],
            "wall_s": case["wall_s"],
        }
        if cached
        else case
    )
    rates: Rates = {key: positive(values[key], f"{label}/{key}") for key in METRICS}
    timings = evidence["native_timings"] if cached else evidence["response"]["final"]["timings"]
    drafted = counter(timings.get("draft_n", 0), f"{label}/draft_n")
    accepted = counter(timings.get("draft_n_accepted", 0), f"{label}/draft_n_accepted")
    if accepted > drafted:
        raise ValueError(f"{label}: accepted draft count exceeds proposals")
    return rates, drafted, accepted


def metrics(cases: Sequence[Mapping[str, object]], cached: bool = False) -> AggregateMetrics:
    if not cases:
        raise ValueError("Cannot aggregate an empty measured case set")
    samples = [case_metrics(case, cached) for case in cases]
    medians: Rates = {
        key: positive(statistics.median(sample[0][key] for sample in samples), f"median/{key}") for key in METRICS
    }
    drafted, accepted = sum(sample[1] for sample in samples), sum(sample[2] for sample in samples)
    return {
        "generation_tok_s": medians["generation_tok_s"],
        "prompt_tok_s": medians["prompt_tok_s"],
        "ttft_s": medians["ttft_s"],
        "wall_s": medians["wall_s"],
        "draft_acceptance_percent": 100 * accepted / drafted if drafted else None,
    }


def change(before: Mapping[str, object], after: Mapping[str, object]) -> MetricChanges:
    control: Rates = {key: positive(before[key], f"control/{key}") for key in METRICS}
    candidate: Rates = {key: positive(after[key], f"candidate/{key}") for key in METRICS}
    result: MetricChanges = {
        "generation_increase_percent": 100 * (candidate["generation_tok_s"] / control["generation_tok_s"] - 1),
        "prompt_increase_percent": 100 * (candidate["prompt_tok_s"] / control["prompt_tok_s"] - 1),
        "ttft_reduction_percent": 100 * (1 - candidate["ttft_s"] / control["ttft_s"]),
        "total_time_reduction_percent": 100 * (1 - candidate["wall_s"] / control["wall_s"]),
    }
    if not all(math.isfinite(value) for value in cast(dict[str, float], result).values()):
        raise ValueError("Computed percentage is nonfinite; measurements cannot be compared")
    return result
