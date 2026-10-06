#!/usr/bin/env python3
"""Create smaller prediction heads from the pinned BF16 source, preserving the main model."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import subprocess
import time

from benchmark import command_output
from download_models import verify
from lab import ROOT, model_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("quant", choices=["q3", "q2", "q2_0"])
    args = ap.parse_args()
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        prepare(args.quant)


def prepare(quant):
    config_path = ROOT / "config/models.json"
    models = json.loads(config_path.read_text())
    source = models["mtp_bf16"]
    source_path = model_path("mtp_bf16")
    if not verify(source_path, source["files"][0]):
        raise RuntimeError("BF16 source size/SHA256 differs from the pinned file")
    runtime = json.loads((ROOT / "config/runtime.json").read_text())
    directory = ROOT / "vendor/llama.cpp"
    revision = command_output(["git", "-C", str(directory), "rev-parse", "HEAD"])
    if revision != runtime["llama_cpp"]["revision"] or command_output(["git", "-C", str(directory), "status", "--porcelain"]):
        raise RuntimeError("Quantizer source checkout is not clean and pinned")
    model_id = "mtp_" + quant
    if model_id in models:
        if verify(model_path(model_id), models[model_id]["files"][0]):
            print(f"Verified existing {model_id}")
            return
        raise RuntimeError("Existing derived draft failed integrity verification")
    qtype = {"q3": "Q3_K_S", "q2": "Q2_K", "q2_0": "Q2_0"}[quant]
    relative = f"mtp-Qwen3.8-Flash-Next-{qtype}-pure.gguf"
    destination = ROOT / "models" / model_id / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(".gguf.part")
    if destination.exists() or partial.exists():
        raise RuntimeError("Preserve the unregistered draft/partial file before retrying")
    tool = directory / "build/bin/llama-quantize"
    if not tool.exists():
        subprocess.run([str(ROOT / ".venv/bin/cmake"), "--build", str(directory / "build"), "--target", "llama-quantize", "-j", "6"], check=True)
    folder = ROOT / "bench/results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-prepare-" + model_id)
    folder.mkdir()
    command = [str(tool), "--pure", "--max-buffer-size", "512", str(source_path), str(partial), qtype, "8"]
    record = {"schema": 1, "kind": "draft-preparation", "source": source,
              "command": command, "runtime_revision": revision, "status": "running",
              "note": "Quantized from verified BF16, not re-quantized from the Q4 draft. Main-model files are not modified. The pinned tool retains norms/router precision and may choose compatible fallback types for tensor shapes."}
    path = folder / "preparation.json"
    def save():
        path.write_text(json.dumps(record, indent=2) + "\n")
    save()
    started = time.monotonic()
    try:
        with (folder / "quantize.log").open("w") as log:
            subprocess.run(command, stdout=log, stderr=log, check=True)
        digest = hashlib.sha256()
        with partial.open("rb") as stream:
            while chunk := stream.read(32 * 1024**2):
                digest.update(chunk)
        spec = {"path": relative, "size_bytes": partial.stat().st_size, "sha256": digest.hexdigest()}
        partial.rename(destination)
        derived = {"source_model": "mtp_bf16", "source_sha256": source["files"][0]["sha256"],
                   "quant": qtype, "pure": True, "runtime_revision": revision,
                   "receipt": str(path.relative_to(ROOT))}
        models[model_id] = {"derived": derived, "files": [spec]}
        config_path.write_text(json.dumps(models, indent=2) + "\n")
        record.update(status="passed", output=models[model_id], elapsed_s=time.monotonic() - started)
        save()
        print(f"Prepared {model_id}: {spec['size_bytes']/1e9:.3f} GB; SHA256 {spec['sha256']}", flush=True)
        print(f"Saved {path}", flush=True)
    except BaseException as error:
        record.update(status="failed", error=f"{type(error).__name__}: {error}", elapsed_s=time.monotonic() - started)
        save()
        raise


if __name__ == "__main__":
    main()
