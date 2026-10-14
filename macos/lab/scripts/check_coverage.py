#!/usr/bin/env python3
"""Require fresh guarded branch coverage for the maintained Mac Python scope."""

import argparse
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from contextlib import chdir
from pathlib import Path
from typing import TypedDict, cast

from coverage import Coverage, __version__
from coverage.exceptions import CoverageException

import validate_offline
from check_quality import scope
from lab import ROOT

COVERAGE_VERSION = "7.16.2"
BASELINE = "config/coverage-baseline.json"
OFFLINE_RECEIPT = "bench/features/offline-validation.json"
COVERAGE_DIRECTORY = "bench/features/coverage"

# These legacy guarded-inventory helpers are outside the static-analysis scope.
# Their only boundary here is their existing path -> source/inventory contract.
fingerprint = cast(Callable[[Path], dict[str, str]], validate_offline.fingerprint)
inventory = cast(Callable[[Path], dict[str, object]], validate_offline.inventory)


class Counts(TypedDict):
    covered_lines: int
    missing_lines: int
    covered_branches: int
    missing_branches: int


class Floors(TypedDict):
    line_percent: int
    branch_percent: int | None


class FileBaseline(TypedDict):
    counts: Counts
    floors: Floors


class CoverageBaseline(TypedDict):
    schema: int
    coverage_version: str
    python_modules: list[str]
    totals: Counts
    floors: Floors
    files: dict[str, FileBaseline]


def object_record(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label}: expected a JSON object")
    return cast(dict[str, object], value)


def load_record(path: Path) -> dict[str, object]:
    return object_record(json.loads(path.read_text()), str(path))


def count_value(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label}: expected a nonnegative integer")
    return value


def counts(value: object) -> Counts:
    raw = object_record(value, "coverage counts")
    return {
        "covered_lines": count_value(raw.get("covered_lines"), "covered_lines"),
        "missing_lines": count_value(raw.get("missing_lines"), "missing_lines"),
        "covered_branches": count_value(raw.get("covered_branches"), "covered_branches"),
        "missing_branches": count_value(raw.get("missing_branches"), "missing_branches"),
    }


def floors(value: Counts) -> Floors:
    lines = value["covered_lines"] + value["missing_lines"]
    branches = value["covered_branches"] + value["missing_branches"]
    return {
        "line_percent": 100 * value["covered_lines"] // lines if lines else 0,
        "branch_percent": 100 * value["covered_branches"] // branches if branches else None,
    }


def recorded_floors(value: object, expected: Floors) -> Floors:
    raw = object_record(value, "coverage floors")
    line = count_value(raw.get("line_percent"), "line_percent")
    branch_value = raw.get("branch_percent")
    branch = None if branch_value is None else count_value(branch_value, "branch_percent")
    result: Floors = {"line_percent": line, "branch_percent": branch}
    if result != expected:
        raise ValueError("Coverage baseline floors must equal recorded percentages rounded down")
    return result


def total_counts(files: Mapping[str, Counts]) -> Counts:
    return {
        "covered_lines": sum(item["covered_lines"] for item in files.values()),
        "missing_lines": sum(item["missing_lines"] for item in files.values()),
        "covered_branches": sum(item["covered_branches"] for item in files.values()),
        "missing_branches": sum(item["missing_branches"] for item in files.values()),
    }


def measured_scope(root: Path = ROOT) -> list[str]:
    modules = scope(root)["python_modules"]
    if any("," in module or "\n" in module for module in modules):
        raise ValueError("Coverage scope paths cannot contain commas or newlines")
    return modules


def measurement_context(root: Path = ROOT) -> str:
    payload = {
        "sources": fingerprint(root),
        "coverage_config_sha256": hashlib.sha256((root / "config/coverage.ini").read_bytes()).hexdigest(),
        "python_modules": measured_scope(root),
        "coverage_version": COVERAGE_VERSION,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return f"strata-mac:{digest}"


def verify_offline(root: Path, data_file: Path) -> None:
    receipt_path = root / OFFLINE_RECEIPT
    receipt = load_record(receipt_path)
    if receipt.get("status") != "passed" or receipt.get("sources") != fingerprint(root):
        raise ValueError("Offline coverage evidence is failed or stale")
    if receipt.get("inventory") != inventory(root):
        raise ValueError("Offline coverage inventory differs from current guarded inventory")
    flags = ("models_loaded", "gpu_tests_run", "builds_run", "native_cpu_self_tests_run", "real_sockets_opened")
    if any(receipt.get(flag) is not False for flag in flags):
        raise ValueError("Coverage requires the native/network-denying offline inventory")
    if (
        count_value(receipt.get("failures"), "failures") != 0
        or count_value(receipt.get("errors"), "errors") != 0
        or count_value(receipt.get("tests_run"), "tests_run") == 0
    ):
        raise ValueError("Coverage requires a successful nonempty offline test run")
    if data_file.stat().st_mtime_ns < receipt_path.stat().st_mtime_ns:
        raise ValueError("Coverage data predates the guarded offline receipt")


def relative_source(filename: str, root: Path) -> str:
    path = Path(filename)
    if not path.is_absolute():
        path = root / path
    return path.resolve().relative_to(root.resolve()).as_posix()


def validate_summary(raw: object) -> Counts:
    summary = object_record(raw, "coverage summary")
    result = counts(summary)
    if (
        count_value(summary.get("num_statements"), "num_statements")
        != result["covered_lines"] + result["missing_lines"]
    ):
        raise ValueError("Coverage statement totals are inconsistent")
    if (
        count_value(summary.get("num_branches"), "num_branches")
        != result["covered_branches"] + result["missing_branches"]
    ):
        raise ValueError("Coverage branch totals are inconsistent")
    if count_value(summary.get("excluded_lines"), "excluded_lines") != 0:
        raise ValueError("Maintained coverage cannot exclude source lines")
    return result


def measured_files(root: Path = ROOT) -> dict[str, Counts]:
    root = root.resolve()
    if __version__ != COVERAGE_VERSION:
        raise ValueError(f"Coverage tool must be pinned to {COVERAGE_VERSION}")
    data_file = root / COVERAGE_DIRECTORY / ".coverage"
    verify_offline(root, data_file)
    coverage = Coverage(config_file=str(root / "config/coverage.ini"), data_file=str(data_file))
    coverage.load()
    data = coverage.get_data()
    modules = measured_scope(root)
    actual = {relative_source(filename, root) for filename in data.measured_files()}
    if actual != set(modules):
        raise ValueError("Measured coverage source scope differs from maintained modules")
    context = measurement_context(root)
    if not data.has_arcs() or data.measured_contexts() != {context}:
        raise ValueError("Coverage branch data is missing or its source context is stale")
    output = root / COVERAGE_DIRECTORY / "coverage.json"
    # Relative data filenames belong to the lab root, including when a caller
    # invokes this gate from another directory. Retain absolute fixture support.
    patterns = [pattern for module in modules for pattern in (module, str(root / module))]
    with chdir(root):
        coverage.json_report(outfile=str(output), include=patterns)
    report = load_record(output)
    raw_files = object_record(report.get("files"), "coverage files")
    result = {
        relative_source(filename, root): validate_summary(object_record(value, filename).get("summary"))
        for filename, value in raw_files.items()
    }
    if set(result) != set(modules):
        raise ValueError("Coverage report omits maintained modules")
    if validate_summary(report.get("totals")) != total_counts(result):
        raise ValueError("Coverage report totals differ from its file evidence")
    if measurement_context(root) != context:
        raise ValueError("Coverage sources changed while checking their evidence")
    return result


def baseline_file(raw: object) -> FileBaseline:
    item = object_record(raw, "coverage baseline file")
    measured = counts(item.get("counts"))
    required = recorded_floors(item.get("floors"), floors(measured))
    return {"counts": measured, "floors": required}


def load_baseline(root: Path = ROOT) -> CoverageBaseline:
    raw = load_record(root / BASELINE)
    modules = measured_scope(root)
    if (
        raw.get("schema") != 1
        or raw.get("coverage_version") != COVERAGE_VERSION
        or raw.get("python_modules") != modules
    ):
        raise ValueError("Coverage baseline schema, version or maintained scope differs")
    files = {name: baseline_file(item) for name, item in object_record(raw.get("files"), "baseline files").items()}
    if set(files) != set(modules):
        raise ValueError("Coverage baseline file scope differs from maintained modules")
    totals = total_counts({name: item["counts"] for name, item in files.items()})
    required = recorded_floors(raw.get("floors"), floors(totals))
    if counts(raw.get("totals")) != totals:
        raise ValueError("Coverage baseline totals or floors differ from recorded file evidence")
    return {
        "schema": 1,
        "coverage_version": COVERAGE_VERSION,
        "python_modules": modules,
        "totals": totals,
        "floors": required,
        "files": files,
    }


def require_floors(actual: Counts, required: Floors, label: str) -> None:
    lines = actual["covered_lines"] + actual["missing_lines"]
    branches = actual["covered_branches"] + actual["missing_branches"]
    if not lines or actual["covered_lines"] * 100 < required["line_percent"] * lines:
        raise ValueError(f"{label}: line coverage is below its recorded floor")
    branch_floor = required["branch_percent"]
    if branch_floor is not None and (not branches or actual["covered_branches"] * 100 < branch_floor * branches):
        raise ValueError(f"{label}: branch coverage is below its recorded floor")


def check_coverage(root: Path = ROOT) -> dict[str, object]:
    baseline = load_baseline(root)
    files = measured_files(root)
    totals = total_counts(files)
    require_floors(totals, baseline["floors"], "Maintained total")
    for module, measured in files.items():
        require_floors(measured, baseline["files"][module]["floors"], module)
    return {
        "schema": 1,
        "status": "passed",
        "python_modules": baseline["python_modules"],
        "totals": totals,
        "floors": baseline["floors"],
        "files": files,
        "source_context": measurement_context(root),
        "coverage_version": COVERAGE_VERSION,
    }


def initialize_baseline(root: Path = ROOT) -> CoverageBaseline:
    files = measured_files(root)
    totals = total_counts(files)
    baseline: CoverageBaseline = {
        "schema": 1,
        "coverage_version": COVERAGE_VERSION,
        "python_modules": measured_scope(root),
        "totals": totals,
        "floors": floors(totals),
        "files": {name: {"counts": item, "floors": floors(item)} for name, item in files.items()},
    }
    with (root / BASELINE).open("x") as stream:
        stream.write(json.dumps(baseline, indent=2, sort_keys=True) + "\n")
    return baseline


def save_receipt(receipt: Mapping[str, object], root: Path = ROOT) -> None:
    output = root / COVERAGE_DIRECTORY / "gate.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n")


def main(argv: Sequence[str] | None = None, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--scope", action="store_true", help="Print the maintained run include patterns")
    mode.add_argument("--context", action="store_true", help="Print the source identity bound to the coverage run")
    mode.add_argument(
        "--initialize-baseline", action="store_true", help="Create the first baseline; refuse an existing one"
    )
    args = parser.parse_args(argv)
    try:
        if args.scope:
            print(",".join(str(root / module) for module in measured_scope(root)))
            return 0
        if args.context:
            print(measurement_context(root))
            return 0
        if args.initialize_baseline:
            initialize_baseline(root)
            print("Coverage baseline initialized; rerun guarded coverage to include its source identity.")
            return 0
        receipt = check_coverage(root)
        save_receipt(receipt, root)
        print(f"Coverage gate: passed; {len(measured_scope(root))} maintained Mac Python modules")
        return 0
    except (OSError, ValueError, RuntimeError, CoverageException) as error:
        save_receipt({"schema": 1, "status": "failed", "error": str(error)}, root)
        print(f"Coverage gate: failed; {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
