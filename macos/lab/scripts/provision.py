#!/usr/bin/env python3
"""Recreate pinned tools and sources without installing a login service."""
import argparse
import json
from pathlib import Path
import platform
import shutil
import subprocess

from engines import LOCAL_HTTP_ONLY_FLAG, external_library_status, verify_engine, write_receipt

ROOT = Path(__file__).resolve().parents[1]
LAB_PYTHON = ".venv/bin/python"
# Runtime packages, then the quality tools the mandatory offline coverage tests need. Both locks pin exact
# versions with wheel hashes; CI installs the same two files.
LOCKS = ("requirements-ci.lock", "requirements-quality.lock")
LOCKED_INSTALL = ("--only-binary", ":all:", "--require-hashes")


def run(command):
    print(" ".join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), cwd=ROOT, check=True)


def source_check(path, source):
    revision = subprocess.check_output(["git", "-C", path, "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", path, "status", "--porcelain", "--untracked-files=all"], text=True).strip()
    if revision != source["revision"] or dirty:
        raise RuntimeError(f"{path} must be clean at its pinned revision; preserve it and use a new lab directory")


def preflight():
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("Use native Apple Silicon macOS for this experiment")
    runtime = json.loads((ROOT / "config/runtime.json").read_text())
    for key, directory in (("llama_cpp", "llama.cpp"), ("strata_macos", "Strata-macOS")):
        path = ROOT / "vendor" / directory
        if path.exists(): source_check(path, runtime[key])
    python = ROOT / LAB_PYTHON
    if (ROOT / ".venv").exists():
        if not python.is_file(): raise RuntimeError("Existing .venv has no Python executable; preserve it and use a fresh lab")
        version = subprocess.check_output([python, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"], text=True).strip()
        if version != "3.12": raise RuntimeError(f"Existing .venv uses Python {version}; this lab requires Python 3.12")
    return runtime


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--check-only", action="store_true", help="Validate existing checkouts/Python and receipt; no installs or builds")
    ap.add_argument("--local-http-only", action="store_true", help="Fresh-directory policy: disable optional OpenSSL/HTTPS support")
    args = ap.parse_args(argv)
    if not 1 <= args.jobs <= 2: ap.error("Use one or two build workers")
    runtime = preflight()
    if args.check_only:
        status = external_library_status(verify_engine("baseline"))
        print(f"Pinned clean sources, Python 3.12 and baseline receipt verify; external libraries {status}; no mutations")
        return
    uv = shutil.which("uv") or str(Path.home() / ".local/bin/uv")
    if not Path(uv).is_file():
        raise RuntimeError("Install uv before provisioning this lab")
    if not (ROOT / ".venv").exists():
        run([uv, "venv", "--python", "3.12", ".venv"])
    for lock in LOCKS:
        run([uv, "pip", "install", "--python", LAB_PYTHON, *LOCKED_INSTALL, "-r", lock])
    for key, directory in [("llama_cpp", "llama.cpp"), ("strata_macos", "Strata-macOS")]:
        path = ROOT / "vendor" / directory
        source = runtime[key]
        if not path.exists():
            run(["git", "init", path])
            run(["git", "-C", path, "remote", "add", "origin", source["repository"]])
            run(["git", "-C", path, "fetch", "--depth", "1", "origin", source["revision"]])
            run(["git", "-C", path, "checkout", "--detach", "FETCH_HEAD"])
        source_check(path, source)
    cmake = ROOT / ".venv/bin/cmake"
    # A local-HTTP-only baseline has no OpenSSL link; engine preparers read this choice from its CMake cache.
    flags = runtime["build_flags"] + ([LOCAL_HTTP_ONLY_FLAG] if args.local_http_only else [])
    run([cmake, "-S", "vendor/llama.cpp", "-B", "vendor/llama.cpp/build", *flags])
    run([cmake, "--build", "vendor/llama.cpp/build", "--target", "llama-server", "llama-bench", "llama-quantize", "-j", args.jobs])
    write_receipt("baseline")
    verify_engine("baseline")


if __name__ == "__main__":
    main()
