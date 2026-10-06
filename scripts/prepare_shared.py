#!/usr/bin/env python3
"""Build isolated weight borrowing and derive a helper without duplicated tables. No inference."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import subprocess
import sys

from download_models import verify
from engines import sha256, source_info, write_receipt
from lab import ROOT, model_path

REMOVED = {"output.weight", "token_embd.weight"}


def derive():
    sys.path.insert(0, str(ROOT / "vendor/llama.cpp/gguf-py"))
    from gguf import GGUFReader, GGUFWriter, GGUFValueType
    config = ROOT / "config/models.json"
    models = json.loads(config.read_text())
    registered = models.get("mtp_shared_q3")
    filename = registered["files"][0]["path"] if registered else "mtp-Qwen3.8-Flash-Next-Q3_K_S-shared.gguf"
    path = ROOT / "models/mtp_shared_q3" / filename
    if registered and path.exists():
        if not verify(path, registered["files"][0]):
            raise RuntimeError("Existing shared helper differs from its registered hash")
        return registered
    source = model_path("mtp_q3")
    if not verify(source, models["mtp_q3"]["files"][0]):
        raise RuntimeError("Source Q3 helper differs from the pinned hash")
    reader = GGUFReader(source)
    if {t.name for t in reader.tensors} & REMOVED != REMOVED:
        raise ValueError("Source helper is missing one of the expected duplicated tensors")
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".gguf.part")
    if path.exists() or partial.exists():
        raise RuntimeError("Preserve the unregistered helper or partial file before retrying")
    folder = ROOT / "bench/results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-prepare-mtp-shared")
    folder.mkdir()
    record = {"status": "running", "source": models["mtp_q3"], "removed": sorted(REMOVED),
              "note": "Only two tensors removed; all metadata and retained quantized tensor bytes must match. "
              "Requires the isolated sharing engine; cannot be loaded on its own. Target files are unchanged."}
    try:
        writer = GGUFWriter(partial, reader.get_field("general.architecture").contents(), endianess=reader.endianess)
        for field in reader.fields.values():
            if field.name == "general.architecture" or field.name.startswith("GGUF."):
                continue
            kind = field.types[0]
            writer.add_key_value(field.name, field.contents(), kind,
                                 sub_type=field.types[-1] if kind == GGUFValueType.ARRAY else None)
        retained = [t for t in reader.tensors if t.name not in REMOVED]
        for tensor in retained:
            writer.add_tensor_info(tensor.name, tensor.data.shape, tensor.data.dtype,
                                   tensor.data.nbytes, tensor.tensor_type)
        writer.write_header_to_file()
        writer.write_kv_data_to_file()
        writer.write_ti_data_to_file()
        for tensor in retained:
            writer.write_tensor_data(tensor.data, tensor_endianess=reader.endianess)
        writer.close()
        derived = GGUFReader(partial)
        old = {t.name: t for t in retained}
        new = {t.name: t for t in derived.tensors}
        if old.keys() != new.keys():
            raise AssertionError("Retained tensor names changed")
        proof = []
        for name in old:
            a, b = old[name], new[name]
            ah, bh = hashlib.sha256(a.data).hexdigest(), hashlib.sha256(b.data).hexdigest()
            if a.tensor_type != b.tensor_type or a.shape.tolist() != b.shape.tolist() or ah != bh:
                raise AssertionError(f"Tensor changed during copy: {name}")
            proof.append({"name": name, "bytes": a.n_bytes, "sha256": ah})
        for name, field in reader.fields.items():
            if name.startswith("GGUF."):
                continue
            other = derived.get_field(name)
            if other is None or field.types != other.types or field.contents() != other.contents():
                raise AssertionError(f"Metadata changed: {name}")
        spec = {"path": path.name, "size_bytes": partial.stat().st_size, "sha256": sha256(partial)}
        if registered and spec != registered["files"][0]:
            raise RuntimeError("Recreated shared helper differs from the pinned file; partial retained")
        result = registered or {"derived": {"source_model": "mtp_q3", "source_sha256": models["mtp_q3"]["files"][0]["sha256"],
            "removed_tensors": sorted(REMOVED), "required_engine": "mtp-shared",
            "receipt": str((folder / "preparation.json").relative_to(ROOT))}, "files": [spec]}
        partial.rename(path)
        if not registered:
            models["mtp_shared_q3"] = result
            config.write_text(json.dumps(models, indent=2) + "\n")
        record.update(status="passed", output=result, retained_tensor_proofs=proof,
                      saved_bytes=source.stat().st_size - spec["size_bytes"])
        print(f"Prepared shared helper: {spec['size_bytes']/1e9:.3f} GB; saved {record['saved_bytes']/1024**2:.1f} MiB")
        return result
    except BaseException as error:
        record.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        (folder / "preparation.json").write_text(json.dumps(record, indent=2) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jobs", type=int, default=2)
    args = ap.parse_args()
    if not 1 <= args.jobs <= 4:
        ap.error("Use 1-4 build workers")
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        runtime = json.loads((ROOT / "config/runtime.json").read_text())
        manifest = json.loads((ROOT / "config/mtp_shared_experiment.json").read_text())
        source_info("baseline")
        path = ROOT / manifest["directory"]
        def command(parts):
            subprocess.run(list(map(str, parts)), cwd=ROOT, check=True)
        if not path.exists():
            command(["git", "clone", "--no-hardlinks", ROOT / "vendor/llama.cpp", path])
            command(["git", "-C", path, "remote", "set-url", "origin", runtime["llama_cpp"]["repository"]])
            command(["git", "-C", path, "remote", "set-url", "--push", "origin", "no_push"])
            command(["git", "-C", path, "apply", ROOT / manifest["patch"]])
        source_info("mtp-shared")
        cmake = ROOT / ".venv/bin/cmake"
        command([cmake, "-S", path, "-B", path / "build", *runtime["build_flags"]])
        command([cmake, "--build", path / "build", "--target", "llama-server", "-j", args.jobs])
        write_receipt("mtp-shared")
        derive()
        print("Sharing build and helper recorded. No model loaded.")


if __name__ == "__main__":
    main()
