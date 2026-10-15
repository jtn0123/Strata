"""N15: how much of the helper's prompt-chunk GPU work runs during the target's, and the overlap/serial comparison.

The m5-overlap engine can give each model context its own Metal command queue (`GGML_M5_LAB_CONTEXT_QUEUE`) and hold
the helper's decode of a prompt chunk until the target's next chunk is queued (`GGML_M5_LAB_HELPER_OVERLAP`). Both
switches on is an overlap launch; both off is a serial launch on the same engine. Command-buffer intervals from both
contexts are merged per request into the GPU time each context was busy, the helper time that fell inside target
work, and the idle time between the request's first and last command buffer.

Under overlap, the helper's work on chunk k runs during the target's chunk k + 1, so per-chunk helper times from
`request_graphs` move one chunk later; request totals do not.
"""

from collections.abc import Iterable, Mapping, Sequence
import statistics
from typing import Literal, TypedDict

from prompt_ops import Buffer
from segment_ops import output_parity

MODES = ("overlap", "serial")
# Native lines that the helper overlap switches print (N15); no other setting prints them.
OVERLAP_MARKERS = ("using a separate command queue for this context", "lab: deferring prompt-chunk helper decodes")
BusyField = Literal["span_ms", "target_ms", "helper_ms", "helper_during_target_ms", "idle_ms"]
BUSY_FIELDS: tuple[BusyField, ...] = ("span_ms", "target_ms", "helper_ms", "helper_during_target_ms", "idle_ms")
Interval = tuple[float, float]


def overlap_receipt(text: str, expected: bool) -> bool:
    """The helper overlap switches reached the engine exactly when the launch set them."""
    if any((marker in text) != expected for marker in OVERLAP_MARKERS):
        raise ValueError("The helper overlap settings did not reach the engine")
    return expected


class Busy(TypedDict):
    span_ms: float
    target_ms: float
    helper_ms: float
    helper_during_target_ms: float
    idle_ms: float


class Prompt(TypedDict):
    name: str
    repeat: int
    prompt_ms: float
    busy: Busy
    output: object


class Generation(TypedDict):
    name: str
    repeat: int
    predicted_n: int
    tok_s: float
    drafted: int
    accepted: int
    content: str


class Memory(TypedDict):
    peak_rss_bytes: int
    minimum_available_bytes: int
    swap_growth_bytes: int


class Launch(TypedDict):
    mode: str
    profile: str
    requests: list[Prompt]
    generations: list[Generation]
    memory: Memory


def union(intervals: Iterable[Interval]) -> list[Interval]:
    """Sorted, non-overlapping intervals covering the same time."""
    merged: list[Interval] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def length(intervals: Iterable[Interval]) -> float:
    return sum(end - start for start, end in intervals)


def shared(first: Sequence[Interval], second: Sequence[Interval]) -> float:
    """Time covered by both of two `union` results."""
    i = j = 0
    total = 0.0
    while i < len(first) and j < len(second):
        total += max(0.0, min(first[i][1], second[j][1]) - max(first[i][0], second[j][0]))
        if first[i][1] < second[j][1]:
            i += 1
        else:
            j += 1
    return total


def request_busy(buffers: Iterable[Buffer], target: str, begin: float, end: float) -> Busy:
    """GPU busy and idle milliseconds for the command buffers inside one request window."""
    inside = [buffer for buffer in buffers if begin <= buffer["gpu_start_s"] and buffer["gpu_end_s"] <= end]
    main = union((b["gpu_start_s"], b["gpu_end_s"]) for b in inside if b["context"] == target)
    if not main:
        raise ValueError("No target GPU work inside the request")
    helper = union((b["gpu_start_s"], b["gpu_end_s"]) for b in inside if b["context"] != target)
    span = max(b["gpu_end_s"] for b in inside) - min(b["gpu_start_s"] for b in inside)
    busy = length(union([*main, *helper]))
    return {
        "span_ms": span * 1000,
        "target_ms": length(main) * 1000,
        "helper_ms": length(helper) * 1000,
        "helper_during_target_ms": shared(main, helper) * 1000,
        "idle_ms": (span - busy) * 1000,
    }


def change_pct(new: float, old: float) -> float:
    return (new - old) / old * 100


def _paired(values: Mapping[str, list[float]]) -> dict[str, object]:
    """Median per mode and the overlap change against serial, when both modes have samples; the percent change only
    when the serial median is not zero (serial launches have no helper time during target work)."""
    row: dict[str, object] = {f"{mode}_samples": len(values.get(mode, [])) for mode in MODES}
    medians = {mode: statistics.median(values[mode]) for mode in MODES if values.get(mode)}
    row.update(medians)
    if len(medians) == len(MODES):
        row["difference"] = medians["overlap"] - medians["serial"]
        if medians["serial"]:
            row["change_pct"] = change_pct(medians["overlap"], medians["serial"])
    return row


def prompt_rows(launches: Sequence[Launch]) -> dict[str, dict[str, object]]:
    """Per case: prompt milliseconds and GPU busy figures; each launch's first request per case is left out."""
    cases: dict[str, dict[str, dict[str, list[float]]]] = {}
    for launch in launches:
        for row in launch["requests"]:
            if row["repeat"] == 0:
                continue
            fields = cases.setdefault(row["name"], {})
            fields.setdefault("prompt_ms", {}).setdefault(launch["mode"], []).append(row["prompt_ms"])
            for field in BUSY_FIELDS:
                fields.setdefault(field, {}).setdefault(launch["mode"], []).append(row["busy"][field])
    return {name: {field: _paired(values) for field, values in fields.items()} for name, fields in cases.items()}


def generation_rows(launches: Sequence[Launch]) -> dict[str, dict[str, object]]:
    """Per case: reply tokens per second. Cases differ in speed, so no pooled median is reported."""
    speeds: dict[str, dict[str, list[float]]] = {}
    for launch in launches:
        for row in launch["generations"]:
            speeds.setdefault(row["name"], {}).setdefault(launch["mode"], []).append(row["tok_s"])
    return {name: {"tok_s": _paired(values)} for name, values in speeds.items()}


def drafts(launches: Sequence[Launch]) -> dict[str, object]:
    """Whether every reply to the same prompt had the same text, length and draft counts."""
    replies = [
        (row["name"], [row["content"], row["predicted_n"], row["drafted"], row["accepted"]])
        for launch in launches
        for row in launch["generations"]
    ]
    counts: dict[str, dict[str, list[int]]] = {}
    for launch in launches:
        for row in launch["generations"]:
            mode = counts.setdefault(row["name"], {}).setdefault(launch["mode"], [0, 0])
            mode[0] += row["drafted"]
            mode[1] += row["accepted"]
    return {"replies": output_parity(replies), "drafted_accepted": counts}


def memory(launches: Sequence[Launch]) -> dict[str, dict[str, object]]:
    """Per mode: the highest peak RSS, the lowest available memory and the largest swap growth over its launches."""
    rows: dict[str, dict[str, object]] = {}
    for mode in MODES:
        own = [launch["memory"] for launch in launches if launch["mode"] == mode]
        if own:
            rows[mode] = {
                "launches": len(own),
                "peak_rss_bytes": max(m["peak_rss_bytes"] for m in own),
                "minimum_available_bytes": min(m["minimum_available_bytes"] for m in own),
                "swap_growth_bytes": max(m["swap_growth_bytes"] for m in own),
            }
    return rows


def compare(launches: Sequence[Launch]) -> dict[str, object]:
    """Per profile: prompt time, GPU overlap, reply speed, output and draft parity, and memory, overlap vs serial."""
    profiles: dict[str, list[Launch]] = {}
    for launch in launches:
        if launch["mode"] not in MODES:
            raise ValueError(f"Unknown overlap launch mode {launch['mode']}")
        profiles.setdefault(launch["profile"], []).append(launch)
    return {
        profile: {
            "launches": [launch["mode"] for launch in own],
            "prompt": prompt_rows(own),
            "generation": generation_rows(own),
            "prompt_parity": output_parity(
                (row["name"], row["output"]) for launch in own for row in launch["requests"]
            ),
            "drafts": drafts(own),
            "memory": memory(own),
        }
        for profile, own in sorted(profiles.items(), key=lambda item: int(item[0]))
    }
