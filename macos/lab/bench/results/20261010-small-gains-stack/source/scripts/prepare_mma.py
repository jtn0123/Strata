#!/usr/bin/env python3
"""Build the isolated few-row Metal candidate and a separate control operation tester."""
import argparse
import fcntl
import json
import subprocess

from engines import sha256, source_info, write_receipt
from lab import ROOT


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jobs", type=int, default=2)
    args = ap.parse_args()
    if not 1 <= args.jobs <= 4:
        ap.error("Use 1-4 build workers")
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        runtime = json.loads((ROOT / "config/runtime.json").read_text())
        manifest = json.loads((ROOT / "config/mtp_mma_experiment.json").read_text())
        source_info("baseline")
        source_info("mtp-shared")
        for component in manifest["components"]:
            if sha256(ROOT / component["patch"]) != component["sha256"]:
                raise RuntimeError("Component patch changed")
        path = ROOT / manifest["directory"]
        def run(parts):
            subprocess.run(list(map(str, parts)), cwd=ROOT, check=True)
        if not path.exists():
            run(["git", "clone", "--no-hardlinks", ROOT / "vendor/llama.cpp", path])
            run(["git", "-C", path, "remote", "set-url", "origin", runtime["llama_cpp"]["repository"]])
            run(["git", "-C", path, "remote", "set-url", "--push", "origin", "no_push"])
            run(["git", "-C", path, "apply", ROOT / manifest["patch"]])
        source_info("mtp-mma")
        cmake = ROOT / ".venv/bin/cmake"
        flags = [f for f in runtime["build_flags"] if not f.startswith("-DLLAMA_BUILD_TESTS=")]
        flags.append("-DLLAMA_BUILD_TESTS=ON")
        run([cmake, "-S", path, "-B", path / "build", *flags])
        run([cmake, "--build", path / "build", "--target", "llama-server", "test-backend-ops", "-j", args.jobs])
        write_receipt("mtp-mma")
        control = ROOT / "vendor/llama-mtp-shared"
        run([cmake, "-S", control, "-B", control / "build-ops", *flags])
        run([cmake, "--build", control / "build-ops", "--target", "test-backend-ops", "-j", args.jobs])
        print("Candidate and control operation tester built. No model loaded.")


if __name__ == "__main__":
    main()
