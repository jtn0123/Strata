#!/usr/bin/env python3
"""Prepare an isolated GPU tuning build without loading models or running GPU tests."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import subprocess

from engines import sha256, source_info, verify_engine, write_receipt
from lab import ROOT


def inventory(root=ROOT):
    data = json.loads((root / "bench/results/flash-gguf-inventory.json").read_text())
    formats = {}
    for shard in data["shards"]:
        for tensor in shard["tensors"]:
            group = formats.setdefault(tensor["quant"], {"count": 0, "bytes": 0, "examples": []})
            group["count"] += 1
            group["bytes"] += tensor["size_bytes"]
            if len(group["examples"]) < 3:
                group["examples"].append({k: tensor[k] for k in ("name", "shape", "size_bytes")})
    return {"source": "bench/results/flash-gguf-inventory.json", "formats": formats,
            "note": "Saved GGUF headers only. No weight payload read, conversion, download or inference. Bytes are not operation timings."}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--jobs", type=int, default=1)
    args = ap.parse_args(argv)
    if not 1 <= args.jobs <= 2:
        ap.error("Use one or two build workers")
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        runtime = json.loads((ROOT / "config/runtime.json").read_text())
        manifest = json.loads((ROOT / "config/m5_lab_experiment.json").read_text())
        for component in manifest["components"]:
            if sha256(ROOT / component["patch"]) != component["sha256"]:
                raise RuntimeError("Component patch changed")
        controls = {name: verify_engine(name) for name in ("baseline", "mtp-mma")}
        path = ROOT / manifest["directory"]
        def call(parts):
            subprocess.run(list(map(str, parts)), cwd=ROOT, check=True)
        if args.build:
            if not path.exists():
                call(["git", "clone", "--no-hardlinks", ROOT / "vendor/llama.cpp", path])
                call(["git", "-C", path, "remote", "set-url", "origin", runtime["llama_cpp"]["repository"]])
                call(["git", "-C", path, "remote", "set-url", "--push", "origin", "no_push"])
                call(["git", "-C", path, "apply", ROOT / manifest["patch"]])
            source_info("m5-lab")
            cmake = ROOT / ".venv/bin/cmake"
            flags = [f for f in runtime["build_flags"] if not f.startswith("-DLLAMA_BUILD_TESTS=")]
            call([cmake, "-S", path, "-B", path / "build", *flags, "-DLLAMA_BUILD_TESTS=ON"])
            call([cmake, "--build", path / "build", "--target", "llama-server", "test-backend-ops", "-j", args.jobs])
            write_receipt("m5-lab")
        candidate = verify_engine("m5-lab") if (path / "build/lab-receipt.json").exists() else source_info("m5-lab")
        if any(verify_engine(name) != pin for name, pin in controls.items()):
            raise RuntimeError("An existing control changed during preparation")
        record = {"schema": 1, "kind": "m5-preparation", "status": "built-awaiting-tests" if args.build else "prepared",
                  "models_loaded": False, "gpu_tests_run": False, "benchmarks_run": False,
                  "controls": controls, "candidate": candidate, "weight_inventory": inventory(),
                  "plan": json.loads((ROOT / "config/m5_test_plan.json").read_text())}
        folder = ROOT / "bench/features"
        output = folder / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-m5-preparation.json")
        output.write_text(json.dumps(record, indent=2) + "\n")
        print(f"Saved {output}. No model loaded, GPU math tested or benchmark run.")


if __name__ == "__main__":
    main()
