"""N15 qualification: the lifecycle checks of each launch, memory per bracket and the decision over all brackets.

After its timed requests, every launch of qualify_overlap.py runs these checks, in this order:
- conversations: per case, a first reply, a regenerate, a follow-up and an edited follow-up through the chat endpoint
  with the prompt cache on. A regenerate must write what its first reply wrote, the server must restore context
  checkpoints, and every launch of a bracket must write the same text and draft the same tokens;
- cancel: a long prompt is sent with the prompt cache on, and the connection closed while the server reads it. The
  server must stop before the end of the prompt. It samples the first reply token only after the whole prompt, so
  no reply existed yet. The client also records whether reply data had arrived; headers alone do not count, as the
  server sends them when it starts reading a streamed prompt;
- resume: the same prompt again, to completion, must pass its quality check. Every launch of a bracket must reuse
  the cancelled request's cache, or every launch must not;
- repeat: a fresh short request must write exactly what the same request wrote earlier in that launch.

The decision is fixed before the run. Every bracket needs exact output parity, passing quality checks, passing
lifecycle checks, clean memory and no regressed row, under the prompt-chunk protocol's own regression rule. The
default app's bracket must also show the long prompts' first text and whole reply sooner, first exposure and replay.
"""

from collections.abc import Mapping, Sequence
from typing import TypedDict

# Extra average peak RSS of the candidate arms that still counts as clean: at least this, or twice the control spread.
RSS_ALLOWANCE = 128 * 2**20
# The bracket whose long prompts must show the gain: the default app's settings.
MAIN = "default"
RULE = (
    "Every bracket: exact output parity, quality checks, lifecycle checks and clean memory, and no row with a "
    "regression (TTFT, whole reply or generation TPS worse than max(1%, twice the control drift)). The default "
    "bracket's long prompts must have first text and whole reply sooner in first exposure and replay, above twice "
    "the control drift, with both candidate launches better than both control launches."
)


class Cancel(TypedDict):
    after_s: float
    reply_started: bool
    prompt_tokens: int
    stopped_tokens: int


class Resume(TypedDict):
    prompt_n: int
    cache_n: int
    drafted: int
    accepted: int
    quality_passed: bool
    matches_fresh: bool


class Turn(TypedDict):
    name: str
    kind: str
    prompt_n: int
    cache_n: int
    prompt_ms: float
    predicted_n: int
    tok_s: float
    drafted: int
    accepted: int
    content: str


class Lifecycle(TypedDict):
    cancel: Cancel
    resume: Resume
    repeat_matches: bool
    conversation: list[Turn]
    restores: int


class LaunchMemory(TypedDict):
    peak_rss_bytes: int
    minimum_available_bytes: int


class Row(TypedDict):
    name: str
    phase: str
    regressions: list[str]
    eligible_prompt_scope: bool


class Bracket(TypedDict):
    rows: list[Row]
    exact_output_parity: bool
    all_quality_checks_pass: bool
    lifecycle: dict[str, object]
    memory: dict[str, object]


def checks(lifecycle: Lifecycle) -> dict[str, bool]:
    """One launch's lifecycle checks."""
    cancel = lifecycle["cancel"]
    turns = lifecycle["conversation"]
    firsts = {t["name"]: t["content"] for t in turns if t["kind"] == "first"}
    regenerated = [t for t in turns if t["kind"] == "regenerate"]
    return {
        "cancelled_mid_prompt": cancel["stopped_tokens"] < cancel["prompt_tokens"],
        "resumed": lifecycle["resume"]["quality_passed"],
        "repeat_matches": lifecycle["repeat_matches"],
        "regenerate_matches": bool(regenerated) and all(t["content"] == firsts.get(t["name"]) for t in regenerated),
        "restored": lifecycle["restores"] > 0,
    }


def lifecycle_bracket(launches: Sequence[Lifecycle]) -> dict[str, object]:
    """Every launch's checks, and whether the launches of one bracket agree with each other."""
    per_launch = [checks(launch) for launch in launches]
    texts = [{(t["name"], t["kind"]): t["content"] for t in launch["conversation"]} for launch in launches]
    drafts = [[(t["drafted"], t["accepted"]) for t in launch["conversation"]] for launch in launches]
    reuse = {launch["resume"]["cache_n"] > 0 for launch in launches}
    parity = bool(texts) and bool(texts[0]) and all(t == texts[0] for t in texts[1:])
    same_drafts = all(d == drafts[0] for d in drafts[1:])
    return {
        "launches": per_launch,
        "conversation_parity": parity,
        "same_drafts": same_drafts,
        "same_reuse_after_cancel": len(reuse) == 1,
        "stopped_tokens": [launch["cancel"]["stopped_tokens"] for launch in launches],
        "resume_cache_n": [launch["resume"]["cache_n"] for launch in launches],
        "resume_matches_fresh": [launch["resume"]["matches_fresh"] for launch in launches],
        "restores": [launch["restores"] for launch in launches],
        "resume_drafts": [(launch["resume"]["accepted"], launch["resume"]["drafted"]) for launch in launches],
        "passed": parity and same_drafts and len(reuse) == 1 and all(all(c.values()) for c in per_launch),
    }


def memory(launches: Sequence[LaunchMemory]) -> dict[str, object]:
    """Peak RSS in A/B/B/A order: the candidate arms' extra average against the control arms' own spread."""
    if len(launches) != 4:
        raise ValueError("Four launches in A/B/B/A order required")
    rss = [m["peak_rss_bytes"] for m in launches]
    extra = (rss[1] + rss[2] - rss[0] - rss[3]) / 2
    allowed = max(RSS_ALLOWANCE, 2 * abs(rss[3] - rss[0]))
    return {
        "peak_rss_bytes": rss,
        "minimum_available_bytes": [m["minimum_available_bytes"] for m in launches],
        "candidate_extra_average_rss_bytes": extra,
        "allowed_bytes": allowed,
        "clean": extra <= allowed,
    }


def _faults(name: str, bracket: Bracket) -> list[str]:
    faults = []
    if not bracket["exact_output_parity"]:
        faults.append(f"{name}: the outputs differ between launches")
    if not bracket["all_quality_checks_pass"]:
        faults.append(f"{name}: a quality check failed")
    if not bracket["lifecycle"]["passed"]:
        faults.append(f"{name}: a lifecycle check failed")
    if not bracket["memory"]["clean"]:
        faults.append(f"{name}: the candidate used more memory than allowed")
    faults += [
        f"{name}: {row['name']} {row['phase']} regressed in {', '.join(row['regressions'])}"
        for row in bracket["rows"]
        if row["regressions"]
    ]
    return faults


def decision(brackets: Mapping[str, Bracket]) -> dict[str, object]:
    """Qualified only if every bracket passes and the default app's long prompts are read sooner."""
    faults = [fault for name, bracket in brackets.items() for fault in _faults(name, bracket)]
    main = brackets.get(MAIN)
    long_rows = [row for row in main["rows"] if row["name"].startswith("long-")] if main else []
    missing = [f"{row['name']} {row['phase']}" for row in long_rows if not row["eligible_prompt_scope"]]
    if not long_rows:
        faults.append(f"{MAIN}: no long-prompt rows to qualify")
    elif missing:
        faults.append(f"{MAIN}: no qualifying gain for {', '.join(missing)}")
    return {"qualified": not faults, "reasons": faults, "brackets": sorted(brackets), "rule": RULE}
