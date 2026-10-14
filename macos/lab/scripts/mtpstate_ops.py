"""N06: MTP draft state across context checkpoint restores, per request, and the comparison between modes.

The MTP draft pairs the first token of each prompt batch with the last hidden row of the previous target batch.
The pinned engine does not save that row with a context checkpoint, so after a restore the next batch pairs its
first token with the row the previous request left behind. The m5-mtpstate engine saves the row with every
checkpoint and, with GGML_M5_LAB_MTP_STATE=restore, applies it on restore (llama.cpp PR 30141). Its trace prints
one M5_MTPSTATE line per save and per restore; a restore line says how far the row in use is from the saved one.

Requests come in conversations: a first reply, the same request again (regenerate), a follow-up turn and an edited
follow-up. The target checks every draft token, so the text should not depend on the mode; the draft acceptance can.
With greedy sampling the drafts are repeatable, so two launches of one mode should match request for request, and
with the state restored a regenerated reply should draft exactly as the first one did.
"""

from collections.abc import Iterable, Sequence
import json
import statistics
from typing import TypedDict

from advise_ops import Measured, change_pct, memory
from segment_ops import output_parity

MODES = ("stale", "restore")
CONTROL = "stale"
KINDS = ("first", "regenerate", "follow-up", "edit")
MARKER = "M5_MTPSTATE "


class Event(TypedDict, total=False):
    t_us: int
    event: str
    seq: int
    rows: int
    bytes: int
    valid: bool
    applied: bool
    saved_rows: int
    current_rows: int
    pending_rel_diff: float
    pending_max_abs: float


class Restore(TypedDict):
    valid: bool
    applied: bool
    pending_rel_diff: float
    pending_max_abs: float


class RequestState(TypedDict):
    saves: int
    save_bytes: int
    restores: list[Restore]


class Request(TypedDict):
    name: str
    kind: str
    prompt_n: int
    cache_n: int
    predicted_n: int
    tok_s: float
    drafted: int
    accepted: int
    content: str
    state: RequestState


class Launch(Measured):
    requests: list[Request]


def parse(lines: Iterable[str]) -> list[Event]:
    return [json.loads(line.split(MARKER, 1)[1]) for line in lines if MARKER in line]


def request_state(events: Sequence[Event], begin_us: int, end_us: int) -> RequestState:
    """Saves and restores inside one request window."""
    inside = [e for e in events if begin_us <= e["t_us"] <= end_us]
    saves = [e for e in inside if e["event"] == "save"]
    return {
        "saves": len(saves),
        "save_bytes": sum(e["bytes"] for e in saves),
        "restores": [
            {
                "valid": e["valid"],
                "applied": e["applied"],
                "pending_rel_diff": e["pending_rel_diff"],
                "pending_max_abs": e["pending_max_abs"],
            }
            for e in inside
            if e["event"] == "restore"
        ],
    }


def _key(row: Request) -> tuple[str, str]:
    return row["name"], row["kind"]


def _draft(row: Request) -> tuple[int, int, int, str]:
    return row["drafted"], row["accepted"], row["predicted_n"], row["content"]


def repeatable(launches: Sequence[Launch]) -> dict[str, dict[str, object]]:
    """Per mode: whether every launch drafted, accepted and wrote the same for every request."""
    result: dict[str, dict[str, object]] = {}
    for mode in MODES:
        own = [launch["requests"] for launch in launches if launch["mode"] == mode]
        if len(own) < 2:
            continue
        first = {_key(r): _draft(r) for r in own[0]}
        differing = sorted({" ".join(_key(r)) for rows in own[1:] for r in rows if first.get(_key(r)) != _draft(r)})
        result[mode] = {"launches": len(own), "identical": not differing, "differing": differing}
    return result


def regenerated(launches: Sequence[Launch]) -> dict[str, dict[str, object]]:
    """Per mode: how many regenerated replies drafted, accepted and wrote exactly as the first reply did."""
    result: dict[str, dict[str, object]] = {}
    for mode in MODES:
        pairs = []
        for launch in launches:
            if launch["mode"] != mode:
                continue
            firsts = {r["name"]: r for r in launch["requests"] if r["kind"] == "first"}
            pairs += [(firsts[r["name"]], r) for r in launch["requests"] if r["kind"] == "regenerate"]
        if pairs:
            result[mode] = {
                "pairs": len(pairs),
                "identical_drafts": sum(_draft(f) == _draft(r) for f, r in pairs),
                "same_text": sum(f["content"] == r["content"] for f, r in pairs),
                "accepted_change": sum(r["accepted"] - f["accepted"] for f, r in pairs),
            }
    return result


def acceptance(launches: Sequence[Launch]) -> dict[str, dict[str, dict[str, object]]]:
    """Per mode and request kind: drafted and accepted tokens over every launch, and the acceptance rate."""
    result: dict[str, dict[str, dict[str, object]]] = {}
    for mode in MODES:
        rows = [r for launch in launches if launch["mode"] == mode for r in launch["requests"] if r["kind"] in KINDS]
        if not rows:
            continue
        result[mode] = {}
        for kind in (*KINDS, "all"):
            own = [r for r in rows if kind in ("all", r["kind"])]
            drafted = sum(r["drafted"] for r in own)
            accepted = sum(r["accepted"] for r in own)
            result[mode][kind] = {
                "requests": len(own),
                "drafted": drafted,
                "accepted": accepted,
                "rate": accepted / drafted if drafted else None,
                "tok_s": statistics.median([r["tok_s"] for r in own]) if own else None,
            }
    return result


def restores(launches: Sequence[Launch]) -> dict[str, dict[str, object]]:
    """Per mode and request kind: checkpoint restores, how many applied the saved row, and how stale the row was."""
    result: dict[str, dict[str, object]] = {}
    for mode in MODES:
        rows = [r for launch in launches if launch["mode"] == mode for r in launch["requests"]]
        if not rows:
            continue
        found = [(r["kind"], s) for r in rows for s in r["state"]["restores"]]
        drift = [s["pending_rel_diff"] for _, s in found if s["valid"]]
        result[mode] = {
            "restores": len(found),
            "by_kind": {kind: sum(k == kind for k, _ in found) for kind in KINDS},
            "applied": sum(s["applied"] for _, s in found),
            "invalid": sum(not s["valid"] for _, s in found),
            "pending_rel_diff_median": statistics.median(drift) if drift else None,
            "pending_rel_diff_max": max(drift) if drift else None,
            "saves": sum(r["state"]["saves"] for r in rows),
            "save_bytes_max": max((r["state"]["save_bytes"] for r in rows), default=0),
        }
    return result


def paired(launches: Sequence[Launch]) -> dict[str, object]:
    """Accepted tokens per request, restore against stale, matched by conversation and turn."""
    totals: dict[str, dict[tuple[str, str], list[int]]] = {mode: {} for mode in MODES}
    for launch in launches:
        for r in launch["requests"]:
            if r["kind"] in KINDS:
                totals[launch["mode"]].setdefault(_key(r), []).append(r["accepted"])
    keys = sorted(set(totals["stale"]) & set(totals["restore"]))
    deltas = {
        f"{name} {kind}": statistics.mean(totals["restore"][(name, kind)])
        - statistics.mean(totals["stale"][(name, kind)])
        for name, kind in keys
    }
    stale = sum(statistics.mean(totals["stale"][k]) for k in keys)
    restored = sum(statistics.mean(totals["restore"][k]) for k in keys)
    return {
        "requests": len(keys),
        "accepted_stale": stale,
        "accepted_restore": restored,
        "accepted_change_pct": change_pct(restored, stale),
        "higher": sum(d > 0 for d in deltas.values()),
        "lower": sum(d < 0 for d in deltas.values()),
        "deltas": {k: d for k, d in deltas.items() if d},
    }


def compare(launches: Sequence[Launch]) -> dict[str, object]:
    for launch in launches:
        if launch["mode"] not in MODES:
            raise ValueError(f"Unknown MTP state launch mode {launch['mode']}")
    return {
        "launches": [launch["mode"] for launch in launches],
        "repeatable": repeatable(launches),
        "regenerated": regenerated(launches),
        "acceptance": acceptance(launches),
        "restores": restores(launches),
        "paired": paired(launches),
        "parity": output_parity(
            (f"{r['name']} {r['kind']}", r["content"]) for launch in launches for r in launch["requests"]
        ),
        "memory": memory(launches, MODES),
    }
