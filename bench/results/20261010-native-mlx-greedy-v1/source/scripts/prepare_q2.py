#!/usr/bin/env python3
"""Build the isolated Q2 candidate without loading a model or running benchmarks."""
import argparse
import json
import subprocess

from engines import source_info, write_receipt
from lab import ROOT


def run(command):
    print(" ".join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), cwd=ROOT, check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jobs", type=int, default=2)
    args = ap.parse_args()
    if not 1 <= args.jobs <= 4:
        ap.error("Use 1-4 build workers to keep preparation memory modest")
    runtime = json.loads((ROOT / "config/runtime.json").read_text())
    manifest = json.loads((ROOT / "config/q2_experiment.json").read_text())
    source_info("baseline")
    path = ROOT / manifest["directory"]
    if not path.exists():
        run(["git", "clone", "--no-hardlinks", ROOT / "vendor/llama.cpp", path])
        run(["git", "-C", path, "remote", "set-url", "origin", runtime["llama_cpp"]["repository"]])
        run(["git", "-C", path, "remote", "set-url", "--push", "origin", "no_push"])
        run(["git", "-C", path, "apply", ROOT / manifest["patch"]])
    source_info("q2-masked")
    cmake = ROOT / ".venv/bin/cmake"
    flags = [flag for flag in runtime["build_flags"] if not flag.startswith("-DLLAMA_BUILD_TESTS=")]
    run([cmake, "-S", path, "-B", path / "build", *flags, "-DLLAMA_BUILD_TESTS=ON"])
    run([cmake, "--build", path / "build", "--target", "llama-server", "llama-bench",
         "test-backend-ops", "-j", args.jobs])
    for engine in ("baseline", "q2-masked"):
        write_receipt(engine)
    print("Both engines recorded. No models loaded; no benchmarks run.")


if __name__ == "__main__":
    main()
