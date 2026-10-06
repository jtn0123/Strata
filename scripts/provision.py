#!/usr/bin/env python3
"""Recreate pinned tools and sources without installing a login service."""
import json
from pathlib import Path
import platform
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def run(command):
    print(" ".join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), cwd=ROOT, check=True)


def main():
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("Use native Apple Silicon macOS for this experiment")
    uv = shutil.which("uv") or str(Path.home() / ".local/bin/uv")
    if not Path(uv).is_file():
        raise RuntimeError("Install uv before provisioning this lab")
    if not (ROOT / ".venv").exists():
        run([uv, "venv", "--python", "3.12", ".venv"])
    run([uv, "pip", "install", "--python", ".venv/bin/python", "-r", "requirements.txt"])
    runtime = json.loads((ROOT / "config/runtime.json").read_text())
    for key, directory in [("llama_cpp", "llama.cpp"), ("strata_macos", "Strata-macOS")]:
        path = ROOT / "vendor" / directory
        source = runtime[key]
        if not path.exists():
            run(["git", "init", path])
            run(["git", "-C", path, "remote", "add", "origin", source["repository"]])
            run(["git", "-C", path, "fetch", "--depth", "1", "origin", source["revision"]])
            run(["git", "-C", path, "checkout", "--detach", "FETCH_HEAD"])
        revision = subprocess.check_output(["git", "-C", path, "rev-parse", "HEAD"], text=True).strip()
        if revision != source["revision"]:
            raise RuntimeError(f"{path} revision differs from config/runtime.json; preserve that checkout and use a new lab directory")
    cmake = ROOT / ".venv/bin/cmake"
    run([cmake, "-S", "vendor/llama.cpp", "-B", "vendor/llama.cpp/build", *runtime["build_flags"]])
    run([cmake, "--build", "vendor/llama.cpp/build", "--target", "llama-server", "llama-bench", "-j", "12"])


if __name__ == "__main__":
    main()
