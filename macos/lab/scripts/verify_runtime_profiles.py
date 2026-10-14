"""Verify the separate editing launcher through Strata's real local API, then stop it."""

import argparse
import ast
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import socket
import subprocess
import time
from typing import cast
import urllib.request

from benchmark import JSONDict
from benchmark_m5_small_gains import feature_receipts
from benchmark_prompt_chunks import cases, chunk_receipt, quality
from benchmark_signals import cleanup_on_termination, defer_termination
from check_memory import assert_no_model_server, snapshot
from engines import sha256, verify_engine
from lab import request
from memory_monitor import MemorySummary, OwnedProcess
from metal_environment import MetalReceipt
from stop import ActiveSupervisor
import validate_offline

ROOT = Path(__file__).resolve().parents[1]
APP = "http://127.0.0.1:8095"
LAUNCHERS = {
    "balanced": "Start Strata.command",
    "code-edit": "Start Strata - Code Editing.command",
    "long-documents": "Start Strata - Long Documents.command",
}
SOURCE = ROOT / "scripts/runtime_profiles.py"
PORTS = (8095, 8096)
MULTIPLY = "What is 17 multiplied by 23? Reply with only the number."
ANSWERS: tuple[tuple[str, str, str | dict[str, object]], ...] = (
    ("multiply", MULTIPLY, "391"),
    ("json", "Extract the name and age as JSON only: Morgan is 29 years old.", {"name": "Morgan", "age": 29}),
)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--profile", choices=("balanced", "code-edit", "long-documents"), required=True)
parser.add_argument("--output", type=Path, required=True, help="New output directory; never overwrites a previous run")
options: argparse.Namespace | None = parser.parse_args() if __name__ == "__main__" else None
ROLE = "lookup" if options and options.profile == "code-edit" else "control"
OUT: Path | None = options.output.resolve() if options else None
LAUNCHER: Path | None = ROOT / LAUNCHERS[options.profile] if options else None


class ActiveRun(ActiveSupervisor):
    """bench/runtime/active.json written by run.py, including its runtime log folder."""

    log_directory: str


@dataclass
class Verification:
    """Receipt plus the owned launcher state that cleanup needs, published as soon as it exists."""

    out: Path
    record: JSONDict
    child: OwnedProcess | None = None
    active: ActiveRun | None = None
    checks_passed: bool = False

    def save(self) -> None:
        (self.out / "verification.json").write_text(json.dumps(self.record, indent=2) + "\n")


def stop_child(child: OwnedProcess | None) -> None:
    """Terminate, then kill, and always reap the owned launcher.

    A stop request that arrives during the bounded waits restarts the current
    step instead of abandoning the child; cleanup_on_termination ignores later
    requests, so this cannot loop on repeated signals.
    """
    if child is None:
        return
    stop = None
    killing = False
    while child.poll() is None:
        try:
            if killing:
                child.kill()
                child.wait(timeout=3)
            else:
                child.terminate()
                child.wait(timeout=20)
        except subprocess.TimeoutExpired:
            if killing:
                raise
            killing = True
        except KeyboardInterrupt as error:
            stop = error
    if stop:
        raise stop


def ports_closed(ports: Sequence[int] = PORTS) -> list[int]:
    closed = []
    for port in ports:
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))
            closed.append(port)
    return closed


def api(endpoint: str, payload: object = None, timeout: float = 600) -> JSONDict:
    """App API objects are endpoint-specific JSON; each check validates the fields it reads."""
    return cast(JSONDict, request(APP, endpoint, payload, timeout=timeout))


def chat(content: str, temperature: float, max_tokens: int) -> JSONDict:
    payload = {
        "model": "flash",
        "messages": [{"role": "user", "content": content}],
        "temperature": temperature,
        "seed": 1234,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    return api("/v1/chat/completions", payload)


def first_choice(response: JSONDict) -> JSONDict:
    choice: JSONDict = response["choices"][0]
    return choice


def postflight(record: JSONDict, active: ActiveRun | None, size: str, launcher: Path) -> None:
    """Collect shutdown evidence; any missing or failed item raises or marks the receipt failed."""
    if active:
        runtime = Path(active["log_directory"])
        memory: MemorySummary = json.loads((runtime / "memory-summary.json").read_text())
        record["native_memory"] = memory
        record["memory_policy"] = json.loads((runtime / "memory-policy.json").read_text())
        if (
            memory["guard"]
            or not memory["normal_pressure_observed"]
            or memory["swap_growth_bytes"]
            or not memory["monitor_healthy"]
            or not memory["child_exited"]
        ):
            record.update(status="failed", error="Actual app continuous pressure/swap/shutdown gate failed")
        native = (runtime / "native.log").read_text()
        record["activation"] = feature_receipts(native, ["reduce"])
        record["actual_chunks"] = chunk_receipt(native, size)
    assert_no_model_server()
    record.update(
        ports_closed_after_stop=ports_closed(),
        no_model_server_remaining=True,
        postflight=snapshot(),
        default_launcher_unchanged=sha256(ROOT / "Start Strata.command") == record.get("default_launcher_before"),
        launcher_unchanged=sha256(launcher) == record.get("launcher_sha256"),
        source_unchanged=sha256(SOURCE) == record.get("source_sha256"),
    )
    if not (record["default_launcher_unchanged"] and record["launcher_unchanged"] and record["source_unchanged"]):
        record.update(status="failed", error="Launcher or profile source changed during verification")


def configured() -> tuple[str, Path, Path]:
    if options is None or OUT is None or LAUNCHER is None:
        raise RuntimeError("Run this verifier as a script with --profile and --output")
    return options.profile, OUT, LAUNCHER


def wait_for_app(run: Verification, child: OwnedProcess) -> tuple[ActiveRun, JSONDict]:
    """Wait for this launcher's recorded run and a healthy API; publish the run once it is seen."""
    started = time.monotonic()
    while True:
        if child.poll() is not None:
            raise RuntimeError("Optional app launcher exited before ready")
        active_path = ROOT / "bench/runtime/active.json"
        if active_path.exists():
            value = json.loads(active_path.read_text())
            if value["pid"] == child.pid:
                run.active = value
        try:
            health = api("/health", timeout=2)
            if run.active:
                return run.active, health
        except (OSError, RuntimeError):
            pass
        if time.monotonic() - started > 60:
            raise RuntimeError("Optional app readiness timed out")
        time.sleep(0.25)


def check_native_command(record: JSONDict, runtime: Path, size: str) -> None:
    command = json.loads((runtime / "command.json").read_text())
    expected = {
        "--spec-type": "draft-mtp" if ROLE == "control" else "ngram-mod,draft-mtp",
        "--spec-draft-n-max": "3",
        "--spec-draft-threads": "8",
        "--spec-draft-p-min": "0.0",
    }
    expected.update({"-b": size, "-ub": size})
    if ROLE == "lookup":
        expected.update(
            {"--spec-ngram-mod-n-match": "16", "--spec-ngram-mod-n-min": "1", "--spec-ngram-mod-n-max": "3"}
        )
    if any(command[command.index(k) + 1] != v for k, v in expected.items()):
        raise RuntimeError("Actual app command differs from qualified lookup profile")
    metal: MetalReceipt = json.loads((runtime / "metal-environment.json").read_text())
    if metal["tuning"] != "small-reduce" or metal["tensor_api"] != "on":
        raise RuntimeError("Wrong P07/TensorAPI profile")
    record.update(native_command=command, metal_environment=metal)


def json_answer(text: str) -> tuple[object, bool]:
    """Strict JSON, or one fenced JSON block; anything else keeps the original decode error."""
    try:
        return json.loads(text), True
    except json.JSONDecodeError:
        lines = text.splitlines()
        if len(lines) < 3 or not lines[0].startswith("```") or lines[-1] != "```":
            raise
        return json.loads("\n".join(lines[1:-1])), False


def answer_checks(run: Verification) -> None:
    for temperature in (0, 0.6):
        for name, question, expected in ANSWERS:
            response = chat(question, temperature, 96)
            text = first_choice(response)["message"]["content"].strip()
            checked: JSONDict = {"name": name, "temperature": temperature, "response": response}
            run.record["checks"].append(checked)
            run.save()
            if isinstance(expected, dict):
                actual, strict = json_answer(text)
                passed = actual == expected
                checked.update(strict_json=strict, semantic_json=actual)
            else:
                passed = text == expected
            checked["passed"] = passed
            run.save()
            if not passed:
                raise RuntimeError("Actual app answer check failed")


def code_edit_check(run: Verification) -> None:
    case = json.loads((ROOT / "tests/fixtures/runtime-code-edit.json").read_text())
    response = chat(case["prompt"], 0.6, 1536)
    choice = first_choice(response)
    text = choice["message"]["content"]
    passed = ast.dump(ast.parse(text)) == ast.dump(ast.parse(case["expected"])) and choice["finish_reason"] == "stop"
    verbatim = text.strip() == case["expected"].strip()
    run.record["checks"].append(
        {"name": "full-code-edit", "passed": passed, "verbatim": verbatim, "response": response}
    )
    run.save()
    if not passed:
        raise RuntimeError("Actual Strata whole-file edit failed")


def streaming_check(record: JSONDict) -> None:
    payload = {
        "model": "flash",
        "messages": [{"role": "user", "content": MULTIPLY}],
        "temperature": 0,
        "seed": 1234,
        "max_tokens": 32,
        "stream": True,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(APP + "/v1/chat/completions", data=json.dumps(payload).encode(), headers=headers)
    pieces: list[str] = []
    done = False
    with urllib.request.urlopen(req, timeout=30) as stream:
        for line in stream:
            if not line.startswith(b"data: "):
                continue
            value = line[6:].strip()
            if value == b"[DONE]":
                done = True
                break
            event = json.loads(value)
            pieces.append(event["choices"][0].get("delta", {}).get("content", ""))
    if "".join(pieces).strip() != "391" or not done:
        raise RuntimeError("Actual app SSE output/completion failed")
    record["streaming_check"] = {"passed": True, "text": "".join(pieces), "done_marker": done}


def long_document_check(record: JSONDict) -> None:
    long_case = cases()[0]
    response = chat(long_case["content"], 0, 256)
    choice = first_choice(response)
    if choice["finish_reason"] != "stop" or not quality(long_case, choice["message"]["content"]):
        raise RuntimeError("Long-document API facts or normal stop failed")
    metrics = api("/metrics")
    settings = metrics["performance"]["settings"]
    if settings.get("batch") != 1536 or settings.get("ubatch") != 1536:
        raise RuntimeError("Actual chunk settings missing from UI metrics")
    record["long_document_check"] = {"passed": True, "response": response, "metrics": metrics}


def integration_check(run: Verification) -> None:
    command = [str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/verify_integration.py"), "--model", "flash"]
    integration = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
    (run.out / "integration.log").write_text(integration.stdout + integration.stderr)
    run.record["integration_returncode"] = integration.returncode
    run.save()
    if integration.returncode:
        raise RuntimeError("Full API integration failed; see integration.log")
    result_path = next(line[6:] for line in integration.stdout.splitlines() if line.startswith("Saved "))
    run.record["integration"] = json.loads(Path(result_path).read_text())


def run_checks(run: Verification, profile: str, launcher: Path, size: str) -> None:
    record = run.record
    validate_offline.require_pass()
    record.update(
        launcher_sha256=sha256(launcher),
        source_sha256=sha256(SOURCE),
        verifier_sha256=sha256(Path(__file__)),
        engine=verify_engine("m5-small-stack"),
        preflight=snapshot(),
        default_launcher_before=sha256(ROOT / "Start Strata.command"),
    )
    run.save()
    with (run.out / "launcher.log").open("w") as log:
        launched = [str(launcher)]
        record["launched"] = launched
        run.save()
        # Publish the child before a stop request can unwind to cleanup.
        with defer_termination():
            run.child = subprocess.Popen(launched, stdout=log, stderr=log, cwd=ROOT)
        active, health = wait_for_app(run, run.child)
        record.update(active=active, health=health)
        check_native_command(record, Path(active["log_directory"]), size)
        answer_checks(run)
        code_edit_check(run)
        streaming_check(record)
        if profile == "long-documents":
            long_document_check(record)
        integration_check(run)
        # Provisional only: the receipt is accepted after shutdown and postflight evidence.
        run.checks_passed = True
        record["checks_status"] = "passed"
        run.save()


def finalize(run: Verification, size: str, launcher: Path) -> None:
    """Reap the launcher, then accept only with complete shutdown and postflight evidence."""
    failure: BaseException | None = None
    try:
        stop_child(run.child)
    except BaseException as error:
        failure = error
    run.record["exit_code"] = run.child.returncode if run.child else None
    run.save()
    try:
        postflight(run.record, run.active, size, launcher)
    except BaseException as error:
        failure = failure or error
    if failure is not None:
        run.record.update(status="failed", finalization_error=f"{type(failure).__name__}: {failure}")
        run.record.setdefault("error", run.record["finalization_error"])
    elif run.checks_passed and run.record["status"] == "attempting":
        run.record["status"] = "passed"
    run.save()
    # Without an earlier failure in flight, the shutdown/postflight failure is the result.
    if failure is not None and run.checks_passed:
        raise failure


@cleanup_on_termination()
def main() -> None:
    profile, out, launcher = configured()
    if out.exists():
        raise RuntimeError("App verification already attempted; no retry/overwrite")
    assert_no_model_server()
    out.mkdir()
    run = Verification(out, {"status": "attempting", "created_utc": datetime.now(UTC).isoformat(), "checks": []})
    size = "1536" if profile == "long-documents" else "512"
    try:
        run.save()
        run_checks(run, profile, launcher, size)
    except BaseException as error:
        run.record.update(status="failed", error=f"{type(error).__name__}: {error}")
        run.save()
        raise
    finally:
        finalize(run, size, launcher)
    if run.record["status"] != "passed":
        raise RuntimeError(run.record.get("error", "App verification failed"))
    print(
        "Profile API validation: English answers, complete code edit, SSE and integration passed; "
        "zero swap, normal pressure; both ports closed.",
        flush=True,
    )


if __name__ == "__main__":
    main()
