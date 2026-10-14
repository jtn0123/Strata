"""Kept-engine trial pieces shared by the editing, prompt-chunk and lookup drivers.

Edit fixtures and drafting policies, normal-EOS response and resource gates, and
owned-server launch helpers. Importing this module loads no model and opens nothing.
"""

from collections.abc import Sequence
from dataclasses import dataclass
import json
from pathlib import Path
import re
import socket
import subprocess
from typing import TypedDict, cast

from benchmark import JSONDict
from benchmark_metrics import case_metrics, completion_counts
from lab import ROOT, request, server_command
from memory_monitor import MemorySummary, Monitor, OwnedProcess

FIXTURES = ROOT / "tests/fixtures/editing-workloads.json"
ENGINE = "m5-small-stack"
LANGUAGES = {"python", "javascript", "json"}
MAX_OUTPUT = 1536
# The only drafting trial that enables each optional matcher; ngram-mod is on in every non-balanced trial.
MATCHERS = {"ngram-simple": "prompt-local", "ngram-map-k": "prompt-map"}
COUNTERS = (
    r"statistics\s+{kind}:.*?#gen drafts\s*=\s*(\d+),.*?#acc drafts\s*=\s*(\d+),"
    r".*?#gen tokens\s*=\s*(\d+),.*?#acc tokens\s*=\s*(\d+)"
)


class EditFixture(TypedDict):
    name: str
    language: str
    cohort: str
    source: str
    old: str
    new: str


class PowerState(TypedDict):
    on_ac: bool
    mode: int


class DraftCounters(TypedDict):
    generated_drafts: int
    accepted_drafts: int
    proposed_tokens: int
    accepted_tokens: int


@dataclass
class OwnedServer:
    """Server and monitor references, published inside the deferred-termination window."""

    process: OwnedProcess | None = None
    monitor: Monitor | None = None


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def fixtures(path: Path = FIXTURES) -> list[EditFixture]:
    spec = json.loads(path.read_text())
    cases: list[EditFixture] = spec["cases"]
    if spec.get("schema") != 1 or len(cases) != 6 or len({c["name"] for c in cases}) != 6:
        raise ValueError("Six unique, bounded synthetic files required")
    for cohort in ("screen", "confirm"):
        selected = [c for c in cases if c["cohort"] == cohort]
        if len(selected) != 3 or {c["language"] for c in selected} != LANGUAGES:
            raise ValueError("Each cohort requires separate Python, JavaScript and JSON files")
    for case in cases:
        if (
            not all(isinstance(value, str) and value for value in (case["source"], case["old"], case["new"]))
            or not 100 <= len(case["source"]) <= 8192
            or case["source"].count(case["old"]) != 1
            or case["old"] == case["new"]
        ):
            raise ValueError("Every file needs precisely one explicit replacement")
    return cases


def prompt(case: EditFixture) -> str:
    return (
        f"Make exactly one change to this {case['language']} file: replace "
        f"{case['old']!r} with {case['new']!r}. Return the entire updated file "
        "verbatim, including all unchanged code, spacing and blank lines. "
        "Do not add Markdown fences, explanations or any other changes.\n\n" + case["source"]
    )


def kept_server(port: int, batch: int, ubatch: int) -> list[str]:
    """Kept 4K/F16/MTP3 launch with the mixed shared helper; trial_command applies the drafting policy."""
    return server_command(
        "flash",
        port,
        4096,
        batch,
        ubatch,
        "draft-mtp",
        3,
        "f16",
        8,
        "mixed",
        "mtp_shared_packed_q3",
        engine=ENGINE,
        draft_threads=8,
        draft_p_min=0.0,
    )


def trial_command(command: Sequence[str], profile: str) -> list[str]:
    if profile not in {"balanced", "code-edit", "prompt-local", "prompt-map"}:
        raise ValueError("Unknown drafting trial")
    if profile == "prompt-local":
        raise ValueError(
            "E02: native ngram-simple cannot draft width3 with match12; use the qualified prompt-map mechanism"
        )
    command = list(command)
    if (
        command[command.index("--spec-type") + 1] != "draft-mtp"
        or command[command.index("--spec-draft-n-max") + 1] != "3"
    ):
        raise ValueError("Preserve the qualified MTP configuration and maximum width three")
    if profile == "balanced":
        return command
    command[command.index("--spec-type") + 1] = (
        "ngram-mod,draft-mtp" if profile == "code-edit" else "ngram-map-k,ngram-mod,draft-mtp"
    )
    command += ["--spec-ngram-mod-n-match", "16", "--spec-ngram-mod-n-min", "1", "--spec-ngram-mod-n-max", "3"]
    if profile == "prompt-map":
        # size-m participates in native allocation sizing; never use the default 48.
        command += ["--spec-ngram-map-k-size-n", "12", "--spec-ngram-map-k-size-m", "3"]
        command += ["--spec-ngram-map-k-min-hits", "1"]
    return command


def validate_response(response: JSONDict, case: EditFixture | None = None) -> JSONDict:
    final = response["final"]
    if not final.get("stop") or final.get("stop_type") != "eos":
        raise ValueError("Complete normal-EOS response required; capped output is ineligible")
    ids = response["generated_token_ids"]
    if not ids or any(type(t) is not int or t < 0 for t in ids):
        raise ValueError("Actual output token IDs required")
    if case is not None:
        expected = case["source"].replace(case["old"], case["new"])
        if response["text"].strip() != expected.strip():
            raise ValueError(f"Complete verbatim edit failed: {case['name']}")
    timings = final["timings"]
    completion_counts(timings, ids, max_new=MAX_OUTPUT)
    result = {
        "ttft_s": response["ttft_s"],
        "wall_s": response["wall_s"],
        "generation_tok_s": timings["predicted_per_second"],
        "prompt_tok_s": timings["prompt_per_second"],
        "output_tokens": timings["predicted_n"],
        "response": response,
    }
    case_metrics(result)
    return result


def clean_memory(memory: MemorySummary) -> bool:
    return (
        memory.get("monitor_healthy") is True
        and memory.get("child_exited") is True
        and memory.get("normal_pressure_required") is True
        and memory.get("normal_pressure_observed") is True
        and memory.get("pressure_live_samples", 0) > 0
        and not memory.get("guard")
        and memory.get("swap_growth_bytes") == 0
    )


def drafting_receipt(text: str, profile: str, kind: str) -> DraftCounters | None:
    """One matcher's last cumulative statistics, or None when the profile does not enable it."""
    enabled = profile != "balanced" if kind == "ngram-mod" else profile == MATCHERS[kind]
    if (f"adding speculative implementation '{kind}'" in text) != enabled:
        raise ValueError(f"Unexpected or missing {kind} initialization")
    counters = [tuple(map(int, values)) for values in re.findall(COUNTERS.format(kind=re.escape(kind)), text)]
    if not enabled:
        if counters:
            raise ValueError(f"Unexpected {kind} statistics")
        return None
    required_active = kind != "ngram-mod" or profile == "code-edit"
    if not counters or required_active and not any(all(value > 0 for value in row) for row in counters):
        raise ValueError(f"{kind} produced no accepted drafts")
    if any(a > g or at > t or t > 3 * g for g, a, t, at in counters):
        raise ValueError(f"Invalid or unbounded {kind} draft counters")
    g, a, t, at = counters[-1]
    return {"generated_drafts": g, "accepted_drafts": a, "proposed_tokens": t, "accepted_tokens": at}


def drafting_receipts(text: str, profile: str) -> dict[str, DraftCounters]:
    """Normal trace verbosity emits cumulative statistics, not per-draft debug lines."""
    receipts: dict[str, DraftCounters] = {}
    for kind in ("ngram-mod", "ngram-simple", "ngram-map-k"):
        receipt = drafting_receipt(text, profile, kind)
        if receipt is not None:
            receipts[kind] = receipt
    return receipts


def power() -> PowerState:
    battery = subprocess.check_output(["pmset", "-g", "batt"], text=True)
    ac = subprocess.check_output(["pmset", "-g", "custom"], text=True).split("AC Power:", 1)[1]
    mode = int(next(line.split()[1] for line in ac.splitlines() if line.strip().startswith("powermode ")))
    if "AC Power" not in battery or mode != 0:
        raise RuntimeError("This campaign requires AC power and unchanged Automatic mode")
    return {"on_ac": True, "mode": mode}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    return port


def prompt_tokens(base: str, content: str) -> list[int]:
    """Render one user turn without thinking, then tokenize it exactly as the server reads it."""
    messages = [{"role": "user", "content": content}]
    template = request(
        base, "/apply-template", {"messages": messages, "chat_template_kwargs": {"enable_thinking": False}}
    )
    tokens = request(base, "/tokenize", {"content": template["prompt"], "add_special": False, "parse_special": True})
    return cast(list[int], tokens["tokens"])


def stop_owned(process: OwnedProcess | None, timeout: float, kill_timeout: float) -> None:
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=kill_timeout)
