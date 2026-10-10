#!/usr/bin/env python3
"""Build the isolated draft-vocabulary experiment without loading models."""
import argparse
import fcntl
import json
import subprocess

from draft_vocab import vocabulary_info
from engines import source_info, write_receipt
from lab import ROOT


def prepare(args):
    runtime = json.loads((ROOT / "config/runtime.json").read_text())
    manifest = json.loads((ROOT / "config/draft_vocab_experiment.json").read_text())
    source_info("baseline")
    vocabulary_info()
    path = ROOT / manifest["directory"]
    def run(cmd):
        subprocess.run(list(map(str, cmd)), cwd=ROOT, check=True)
    if not path.exists():
        run(["git", "clone", "--no-hardlinks", ROOT / "vendor/llama.cpp", path])
        run(["git", "-C", path, "remote", "set-url", "origin", runtime["llama_cpp"]["repository"]])
        run(["git", "-C", path, "remote", "set-url", "--push", "origin", "no_push"])
        run(["git", "-C", path, "apply", ROOT / manifest["patch"]])
    source_info("draft-vocab")
    cmake = ROOT / ".venv/bin/cmake"
    run([cmake, "-S", path, "-B", path / "build", *runtime["build_flags"]])
    run([cmake, "--build", path / "build", "--target", "llama-server", "-j", args.jobs])
    write_receipt("draft-vocab")
    print("Draft-vocabulary build recorded. No model loaded.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jobs", type=int, default=2)
    args = ap.parse_args()
    if not 1 <= args.jobs <= 4:
        ap.error("Use 1-4 build workers")
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        prepare(args)


if __name__ == "__main__":
    main()
