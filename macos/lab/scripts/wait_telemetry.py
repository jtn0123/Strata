"""Validate diagnostic wait envelopes without treating them as speed gains."""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import NoReturn, cast

type Record = dict[str, object]
BEGIN = "begin_us"
END = "end_us"
THREADS = "threads"
PREFIXES = {
    "M5_HELPER_SCOPE": "helper",
    "M5_CPU_GRAPH": "cpu",
    "M5_CPU_POOL": "pool",
    "M5_CPU_WORKER": "worker",
    "M5_GPU_WAIT": "gpu",
}


@dataclass(frozen=True)
class Event:
    kind: str
    data: Record


def integer(data: Record, key: str, minimum: int = 0) -> int:
    value = data.get(key)
    if type(value) is not int or value < minimum:
        raise ValueError(f"{key}: expected an integer at least {minimum}")
    return value


def flag(data: Record, key: str) -> bool:
    value = data.get(key)
    if type(value) is not bool:
        raise ValueError(f"{key}: expected a boolean")
    return value


def interval(data: Record) -> None:
    if integer(data, END) < integer(data, BEGIN):
        raise ValueError("Diagnostic interval runs backwards")


def helper(data: Record) -> None:
    interval(data)
    integer(data, "rows")
    if data.get("phase") not in ("process", "draft", "accept"):
        raise ValueError("Unknown MTP helper phase")


def cpu(data: Record) -> None:
    interval(data)
    integer(data, THREADS, 1)
    integer(data, "nodes")
    integer(data, "status", -100)
    flag(data, "disposable_pool")


def pool(data: Record) -> None:
    interval(data)
    integer(data, THREADS, 1)
    if data.get("action") not in ("create", "free"):
        raise ValueError("Unknown CPU pool lifecycle action")


def worker(data: Record) -> None:
    if integer(data, "sample") >= 512:
        raise ValueError("Worker observation exceeds the native bound")
    integer(data, "timestamp_us")
    if integer(data, "worker") >= integer(data, THREADS, 1):
        raise ValueError("Worker index is outside the pool")
    integer(data, "qos_class")
    integer(data, "relative_priority", -15)
    integer(data, "thread_id")
    flag(data, "qos_valid")
    flag(data, "thread_id_valid")


VALIDATORS: dict[str, Callable[[Record], None]] = {
    "helper": helper,
    "cpu": cpu,
    "pool": pool,
    "worker": worker,
    "gpu": interval,
}


def unique_object(pairs: list[tuple[str, object]]) -> Record:
    result: Record = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate diagnostic key: {key}")
        result[key] = value
    return result


def nonfinite(value: str) -> NoReturn:
    raise ValueError(f"Nonfinite diagnostic value: {value}")


def parse(text: str, *, require_helper: bool = True) -> list[Event]:
    events: list[Event] = []
    for line in text.splitlines():
        prefix, separator, payload = line.partition(" ")
        if prefix not in PREFIXES:
            continue
        if not separator:
            raise ValueError("Diagnostic marker has no JSON payload")
        value: object = json.loads(payload, object_pairs_hook=unique_object, parse_constant=nonfinite)
        if not isinstance(value, dict):
            raise ValueError("Diagnostic payload must be an object")
        data = cast(Record, value)
        kind = PREFIXES[prefix]
        VALIDATORS[kind](data)
        events.append(Event(kind, data))
    if not events or require_helper and not any(event.kind == "helper" for event in events):
        raise ValueError("Required native diagnostic coverage is missing")
    return events


def contains(parent: Event, child: Event) -> bool:
    return integer(parent.data, BEGIN) <= integer(child.data, BEGIN) and integer(child.data, END) <= integer(
        parent.data, END
    )


def union_us(events: Sequence[Event]) -> int:
    ranges = sorted((integer(event.data, BEGIN), integer(event.data, END)) for event in events)
    total = end = 0
    for begin, stop in ranges:
        total += max(0, stop - max(begin, end))
        end = max(end, stop)
    return total


def within(events: Sequence[Event], scopes: Sequence[Event]) -> list[Event]:
    return [event for event in events if any(contains(scope, event) for scope in scopes)]


def worker_scopes(events: Sequence[Event], scopes: Sequence[Event]) -> list[Event]:
    return [
        event
        for event in events
        if any(
            integer(scope.data, BEGIN) <= integer(event.data, "timestamp_us") <= integer(scope.data, END)
            for scope in scopes
        )
    ]


def summarize(events: Sequence[Event]) -> Record:
    # Revalidate callers that supply Event objects instead of using parse().
    if not events:
        raise ValueError("Required native diagnostic coverage is missing")
    for event in events:
        if event.kind not in VALIDATORS:
            raise ValueError("Unknown diagnostic event kind")
        VALIDATORS[event.kind](event.data)
    scopes = [event for event in events if event.kind == "helper"]
    graphs = [event for event in events if event.kind == "cpu"]
    pools = [event for event in events if event.kind == "pool"]
    waits = [event for event in events if event.kind == "gpu"]
    helper_graphs = within(graphs, scopes)
    helper_pools = within(pools, scopes)
    workers = [event for event in events if event.kind == "worker"]
    helper_workers = worker_scopes(workers, scopes)
    failures = [event for event in graphs if integer(event.data, "status", -100) != 0]
    return {
        "status": "diagnostic-failure" if failures else "parsed",
        "helper_phase_envelope_us": {
            phase: union_us([event for event in scopes if event.data["phase"] == phase])
            for phase in ("process", "draft", "accept")
        },
        "cpu_graphs": len(graphs),
        "failed_cpu_graphs": len(failures),
        "helper_cpu_graphs": len(helper_graphs),
        "helper_disposable_graphs": sum(flag(event.data, "disposable_pool") for event in helper_graphs),
        "helper_cpu_envelope_us": union_us(helper_graphs),
        "helper_pool_create_calls": sum(event.data["action"] == "create" for event in helper_pools),
        "helper_pool_free_calls": sum(event.data["action"] == "free" for event in helper_pools),
        "helper_pool_lifecycle_envelope_us": union_us(helper_pools),
        "gpu_wait_calls": len(waits),
        "gpu_wait_envelope_us": union_us(waits),
        "helper_gpu_wait_envelope_us": union_us(within(waits, scopes)),
        "worker_samples": len(workers),
        "helper_worker_samples": len(helper_workers),
        "helper_requested_qos_classes": sorted(
            {integer(event.data, "qos_class") for event in helper_workers if flag(event.data, "qos_valid")}
        ),
        "requested_qos_classes": sorted(
            {integer(event.data, "qos_class") for event in workers if flag(event.data, "qos_valid")}
        ),
        "requested_qos_unavailable_samples": sum(
            not flag(event.data, "qos_valid") or integer(event.data, "qos_class") == 0 for event in workers
        ),
        "effective_qos_measured": False,
        "timings_excluded_from_speed_results": True,
        "limitation": "Wall envelopes include scheduling and observer cost, can overlap, and must not be added. "
        "Worker samples are bounded requested QoS; unspecified values are not proof of low priority. "
        "These are not GPU kernel times, exclusive CPU time or model speed gains.",
    }
