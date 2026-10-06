#!/usr/bin/env python3
"""Resume public, revision-pinned GGUF downloads and verify every byte."""
import argparse
import concurrent.futures
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def verify(path, spec):
    if not path.exists() or path.stat().st_size != spec["size_bytes"]:
        return False
    digest = hashlib.sha256()
    with path.open("rb", buffering=0) as stream:
        fcntl.fcntl(stream.fileno(), 48, 1)  # macOS F_NOCACHE
        while chunk := stream.read(32 * 1024**2):
            digest.update(chunk)
    return digest.hexdigest() == spec["sha256"]


def download(model_id, model, spec):
    destination = ROOT / "models" / model_id / spec["path"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    if verify(destination, spec):
        print(f"Verified existing {destination.name}", flush=True)
        return
    if destination.exists():
        raise RuntimeError(f"Existing final file failed integrity check: {destination}")
    partial = destination.with_suffix(".gguf.part")
    url = f"https://huggingface.co/{model['repository']}/resolve/{model['revision']}/{spec['path']}?download=true"
    log_path = partial.with_suffix(".download.log")
    with log_path.open("a") as log:
        process = subprocess.Popen([
            "curl", "--fail", "--location", "--silent", "--show-error",
            "--retry", "5", "--retry-delay", "2", "--connect-timeout", "30",
            "--continue-at", "-", "--output", str(partial), url,
        ], stdout=log, stderr=log)
        started, previous_time, previous_bytes = time.monotonic(), time.monotonic(), partial.stat().st_size if partial.exists() else 0
        while process.poll() is None:
            time.sleep(5)
            current = partial.stat().st_size if partial.exists() else 0
            now = time.monotonic()
            speed = (current - previous_bytes) / max(now - previous_time, 0.001) / 1e6
            print(f"{destination.name}: {current/1e9:.2f}/{spec['size_bytes']/1e9:.2f} GB ({speed:.1f} MB/s)", flush=True)
            previous_time, previous_bytes = now, current
        if process.returncode:
            raise RuntimeError(f"Download failed with exit {process.returncode}; resumable file retained. {log_path.read_text()[-1500:]}")
    print(f"Checking SHA256: {destination.name}", flush=True)
    if not verify(partial, spec):
        raise RuntimeError(f"Download failed size/SHA256 verification: {partial}")
    partial.rename(destination)
    destination.with_suffix(".source.json").write_text(json.dumps({**model, "downloaded_file": spec, "download_seconds": round(time.monotonic()-started, 2)}, indent=2)+"\n")
    print(f"Verified {destination.name}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    models = json.loads((ROOT / "config/models.json").read_text())
    parser.add_argument("model", choices=list(models))
    args = parser.parse_args()
    model = models[args.model]
    if model.get("derived"):
        raise RuntimeError("This draft is generated locally; use scripts/prepare_draft.py")
    remaining = sum(max(0, spec["size_bytes"] - ((ROOT / "models" / args.model / spec["path"]).with_suffix(".gguf.part").stat().st_size if (ROOT / "models" / args.model / spec["path"]).with_suffix(".gguf.part").exists() else 0)) for spec in model["files"] if not (ROOT / "models" / args.model / spec["path"]).exists())
    if shutil.disk_usage(ROOT).free < remaining + 20 * 1024**3:
        raise RuntimeError("Insufficient disk headroom for download plus 20 GiB reserve")
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(download, args.model, model, spec) for spec in model["files"]]
        for future in futures:
            future.result()


if __name__ == "__main__":
    main()
