"""N02: lazy lookup-row advice per request, and the comparison between advice modes.

The m5-advise engine prints one M5_ADVISE line each time the target is about to gather a batch's rows from the lazy
lookup table: the rows and pages asked for, how many of those pages were not resident beforehand (mincore), and the
time the advice took. Lines are matched to requests by their monotonic timestamps. A request's first calls are its
prompt chunks, in the server's chunk order; the rest come from its reply.

Each document is read twice in a row: first exposure, then an exact replay whose rows are already resident. The
first-exposure penalty (first prompt time minus replay prompt time, same document, same launch) removes the
document's length and content from the comparison; what is left is mostly the time spent waiting for lookup pages.
"""

from collections.abc import Iterable, Mapping, Sequence
import json
import statistics
from typing import TypedDict

from segment_ops import output_parity

MODES = ("no-advice", "madvise", "rdadvise")
CONTROL = "no-advice"
MARKER = "M5_ADVISE "


class Advice(TypedDict):
    t_us: int
    mode: str
    rows: int
    spans: int
    pages: int
    bytes: int
    capped_spans: int
    overflow_rows: int
    outside_spans: int
    cold_before: int
    cold_after: int
    advice_us: int
    check_us: int
    failures: int
    errno: int


class AdviceSum(TypedDict):
    calls: int
    rows: int
    pages: int
    cold_before: int
    advice_ms: float
    check_ms: float
    failures: int
    skipped_spans: int


class RequestAdvice(TypedDict):
    prompt: AdviceSum
    reply: AdviceSum


class Request(TypedDict):
    name: str
    kind: str
    prompt_tokens: int
    prompt_ms: float
    tok_s: float
    content: str
    disk_read_bytes: int | None
    advice: RequestAdvice


class Memory(TypedDict):
    peak_rss_bytes: int
    minimum_available_bytes: int
    swap_growth_bytes: int


class Launch(TypedDict):
    mode: str
    requests: list[Request]
    memory: Memory


def parse(lines: Iterable[str]) -> list[Advice]:
    return [json.loads(line.split(MARKER, 1)[1]) for line in lines if MARKER in line]


def total(calls: Sequence[Advice]) -> AdviceSum:
    return {
        "calls": len(calls),
        "rows": sum(c["rows"] for c in calls),
        "pages": sum(c["pages"] for c in calls),
        "cold_before": sum(c["cold_before"] for c in calls),
        "advice_ms": sum(c["advice_us"] for c in calls) / 1000,
        "check_ms": sum(c["check_us"] for c in calls) / 1000,
        "failures": sum(c["failures"] for c in calls),
        "skipped_spans": sum(c["capped_spans"] + c["outside_spans"] for c in calls),
    }


def request_advice(calls: Sequence[Advice], begin_us: int, end_us: int, chunks: Sequence[int]) -> RequestAdvice:
    """Advice inside one request window, split into its prompt chunks and its reply."""
    inside = [c for c in calls if begin_us <= c["t_us"] <= end_us]
    prompt = inside[: len(chunks)]
    if len(prompt) != len(chunks) or not chunks:
        raise ValueError(f"Expected {len(chunks)} prompt advice calls, found {len(prompt)}")
    per_token, extra = divmod(prompt[0]["rows"], chunks[0])
    if extra or any(c["rows"] != per_token * size for c, size in zip(prompt, chunks, strict=True)):
        raise ValueError("Prompt advice rows do not follow the server's chunks")
    return {"prompt": total(prompt), "reply": total(inside[len(chunks) :])}


def change_pct(new: object, old: object) -> float | None:
    """Percent change, when both are numbers and the old one is not zero."""
    if not isinstance(new, int | float) or not isinstance(old, int | float) or not old:
        return None
    return (new - old) / old * 100


def _median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def _fit(points: Sequence[tuple[float, float]]) -> dict[str, float] | None:
    """Least-squares penalty in ms per 1,000 cold pages, and the penalty with no cold pages."""
    if len(points) < 2 or len({x for x, _ in points}) < 2:
        return None
    slope, intercept = statistics.linear_regression([x for x, _ in points], [y for _, y in points])
    return {"ms_per_1000_cold_pages": slope * 1000, "intercept_ms": intercept, "points": len(points)}


def documents(launches: Sequence[Launch]) -> dict[str, dict[str, object]]:
    """Per mode: first-exposure and replay prompt time, the penalty between them, cold pages and advice cost."""
    rows: dict[str, dict[str, object]] = {}
    for mode in MODES:
        pairs = []
        for launch in launches:
            if launch["mode"] != mode:
                continue
            replays = {r["name"]: r for r in launch["requests"] if r["kind"] == "replay"}
            pairs += [(r, replays[r["name"]]) for r in launch["requests"] if r["kind"] == "first"]
        if not pairs:
            continue
        penalty = [(f["advice"]["prompt"]["cold_before"], f["prompt_ms"] - r["prompt_ms"]) for f, r in pairs]
        cold = sum(x for x, _ in penalty)
        disk = [f["disk_read_bytes"] / 2**20 for f, _ in pairs if f["disk_read_bytes"] is not None]
        rows[mode] = {
            "documents": len(pairs),
            "first_prompt_ms": _median([f["prompt_ms"] for f, _ in pairs]),
            "replay_prompt_ms": _median([r["prompt_ms"] for _, r in pairs]),
            "penalty_ms": _median([y for _, y in penalty]),
            "cold_pages": _median([x for x, _ in penalty]),
            "replay_cold_pages": _median([r["advice"]["prompt"]["cold_before"] for _, r in pairs]),
            "penalty_ms_per_1000_cold_pages": sum(y for _, y in penalty) / cold * 1000 if cold else None,
            "fit": _fit(penalty),
            "first_advice_ms": _median([f["advice"]["prompt"]["advice_ms"] for f, _ in pairs]),
            "replay_advice_ms": _median([r["advice"]["prompt"]["advice_ms"] for _, r in pairs]),
            "first_check_ms": _median([f["advice"]["prompt"]["check_ms"] for f, _ in pairs]),
            "first_disk_read_mib": _median(disk),
            "first_replay_identical": all(f["content"] == r["content"] for f, r in pairs),
            "failures": sum(f["advice"]["prompt"]["failures"] + r["advice"]["prompt"]["failures"] for f, r in pairs),
            "skipped_spans": sum(f["advice"]["prompt"]["skipped_spans"] for f, _ in pairs),
        }
    return rows


def changes(rows: Mapping[str, Mapping[str, object]]) -> dict[str, dict[str, float | None]]:
    """Each advice mode against the no-advice control, for the figures where lower is better."""
    control = rows.get(CONTROL)
    if not control:
        return {}
    fields = ("penalty_ms", "replay_prompt_ms", "penalty_ms_per_1000_cold_pages")
    result: dict[str, dict[str, float | None]] = {}
    for mode, row in rows.items():
        if mode == CONTROL:
            continue
        result[mode] = {}
        for field in fields:
            result[mode][field] = change_pct(row[field], control[field])
    return result


def warm(launches: Sequence[Launch]) -> dict[str, object]:
    """The standard cases answered with a reply: speed per case and mode, and whether every mode wrote the same."""
    speeds: dict[str, dict[str, list[float]]] = {}
    for launch in launches:
        for row in launch["requests"]:
            if row["kind"] == "warm":
                speeds.setdefault(row["name"], {}).setdefault(launch["mode"], []).append(row["tok_s"])
    return {
        "tok_s": {name: {mode: statistics.median(v) for mode, v in modes.items()} for name, modes in speeds.items()},
        "parity": output_parity(
            (row["name"], row["content"]) for launch in launches for row in launch["requests"] if row["kind"] == "warm"
        ),
    }


def memory(launches: Sequence[Launch]) -> dict[str, dict[str, int]]:
    rows: dict[str, dict[str, int]] = {}
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
    for launch in launches:
        if launch["mode"] not in MODES:
            raise ValueError(f"Unknown advice launch mode {launch['mode']}")
    rows = documents(launches)
    return {
        "launches": [launch["mode"] for launch in launches],
        "documents": rows,
        "changes": changes(rows),
        "warm": warm(launches),
        "memory": memory(launches),
    }
