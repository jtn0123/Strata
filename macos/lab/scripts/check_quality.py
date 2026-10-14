#!/usr/bin/env python3
"""Run maintained Mac checks and report file/function size without loading models."""

from __future__ import annotations

import ast
import configparser
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import TypedDict, cast

ROOT = Path(__file__).resolve().parents[1]


class QualityScope(TypedDict):
    schema: int
    python_modules: list[str]
    file_warning_lines: int
    function_warning_lines: int


class FunctionSize(TypedDict):
    name: str
    line: int
    lines: int


class FileSize(TypedDict):
    path: str
    lines: int
    sha256: str
    functions: list[FunctionSize]


def validate_module(item: str, root: Path) -> None:
    path = Path(item)
    if not path.parts or path.is_absolute() or path.parts[0] != "scripts" or ".." in path.parts or path.suffix != ".py":
        raise ValueError(f"Quality module must be a Mac script: {item}")
    source = root / path
    if not source.resolve().is_relative_to((root / "scripts").resolve()) or not source.is_file():
        raise ValueError(f"Quality module missing or outside Mac scripts: {item}")


def scope(root: Path = ROOT) -> QualityScope:
    data = json.loads((root / "config/quality_modules.json").read_text())
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise ValueError("Expected quality scope schema 1")
    modules = data.get("python_modules")
    if not isinstance(modules, list) or not modules or not all(isinstance(item, str) for item in modules):
        raise ValueError("Expected maintained Python module paths")
    if len(set(modules)) != len(modules):
        raise ValueError("Duplicate maintained module")
    for item in modules:
        validate_module(item, root)
    for key in ("file_warning_lines", "function_warning_lines"):
        if type(data.get(key)) is not int or data[key] <= 0:
            raise ValueError(f"Expected a positive {key}")
    return cast(QualityScope, data)


def check_mypy_scope(settings: QualityScope, root: Path = ROOT) -> None:
    config = configparser.ConfigParser(interpolation=None)
    config.read(root / "config/mypy.ini")
    prefix = "$MYPY_CONFIG_FILE_DIR/../"
    configured = [item.strip().removeprefix(prefix) for item in config["mypy"]["files"].split(",")]
    if sorted(configured) != sorted(settings["python_modules"]):
        raise ValueError("Mypy files and maintained quality scope differ")


def file_size(relative: str, root: Path = ROOT) -> FileSize:
    source = root / relative
    content = source.read_bytes()
    functions: list[FunctionSize] = []
    tree = ast.parse(content, filename=relative)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = node.end_lineno or node.lineno
            functions.append({"name": node.name, "line": node.lineno, "lines": end - node.lineno + 1})
    return {
        "path": relative,
        "lines": len(content.splitlines()),
        "sha256": hashlib.sha256(content).hexdigest(),
        "functions": sorted(functions, key=lambda function: (-function["lines"], function["line"])),
    }


def report_sizes(settings: QualityScope, root: Path = ROOT) -> None:
    files = [file_size(relative, root) for relative in settings["python_modules"]]
    files.sort(key=lambda item: (-item["lines"], item["path"]))
    warnings = []
    for item in files:
        if item["lines"] > settings["file_warning_lines"]:
            warnings.append(f"{item['path']}: {item['lines']} lines exceeds file warning limit")
        for function in item["functions"]:
            if function["lines"] > settings["function_warning_lines"]:
                warnings.append(
                    f"{item['path']}:{function['line']} {function['name']}: {function['lines']} function lines"
                )
    receipt = root / "bench/features/code-quality/latest-sizes.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({"scope": settings, "files": files, "warnings": warnings}, indent=2) + "\n")
    print(f"Size report: {len(files)} maintained Mac files, {len(warnings)} warnings")
    for warning in warnings:
        print(f"  {warning}")


def main() -> None:
    settings = scope()
    check_mypy_scope(settings)
    modules = settings["python_modules"]
    checks = (
        ["ruff", "check", "--config", "config/ruff.toml", "--select", "E9,F63,F7,F82", "scripts", "tests"],
        ["ruff", "check", "--config", "config/ruff.toml", "--", *modules],
        ["ruff", "format", "--check", "--config", "config/ruff.toml", "--", *modules],
        ["mypy", "--config-file", "config/mypy.ini"],
    )
    for arguments in checks:
        subprocess.run([sys.executable, "-m", *arguments], cwd=ROOT, check=True)
    report_sizes(settings)


if __name__ == "__main__":
    main()
