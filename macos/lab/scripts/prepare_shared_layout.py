#!/usr/bin/env python3
"""Pack CPU experts together so Metal maps only the helper's small dense region."""
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import sys

from download_models import verify
from engines import sha256
from lab import ROOT, model_path


def prepare():
    sys.path.insert(0, str(ROOT / "vendor/llama.cpp/gguf-py"))
    from gguf import GGUFReader, GGUFWriter, GGUFValueType
    config = ROOT / "config/models.json"
    models = json.loads(config.read_text())
    model_id = "mtp_shared_packed_q3"
    registered = models.get(model_id)
    filename = registered["files"][0]["path"] if registered else "mtp-Qwen3.8-Flash-Next-Q3_K_S-shared-packed.gguf"
    path = ROOT / "models" / model_id / filename
    if registered and path.exists():
        if not verify(path, registered["files"][0]):
            raise RuntimeError("Existing packed helper differs from the registered hash")
        return registered
    source = model_path("mtp_shared_q3")
    if not verify(source, models["mtp_shared_q3"]["files"][0]):
        raise RuntimeError("Shared helper source hash differs")
    reader = GGUFReader(source)
    experts = [t for t in reader.tensors if t.name.endswith("_exps.weight")]
    dense = [t for t in reader.tensors if not t.name.endswith("_exps.weight")]
    if len(experts) != 3 or len(dense) != 29:
        raise ValueError("Expected three expert tables and 29 small tensors")
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".gguf.part")
    if partial.exists() or path.exists():
        raise RuntimeError("Preserve the unregistered packed file before retrying")
    folder = ROOT / "bench/results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-prepare-shared-layout")
    folder.mkdir()
    record = {"status": "running", "source": models["mtp_shared_q3"], "layout": "CPU expert tables first, GPU dense tensors last",
              "note": "Only tensor order/offsets change. Every tensor byte, quantization, shape and metadata field must match."}
    try:
        ordered = experts + dense
        writer = GGUFWriter(partial, reader.get_field("general.architecture").contents(), endianess=reader.endianess)
        for field in reader.fields.values():
            if field.name == "general.architecture" or field.name.startswith("GGUF."):
                continue
            kind = field.types[0]
            writer.add_key_value(field.name, field.contents(), kind,
                sub_type=field.types[-1] if kind == GGUFValueType.ARRAY else None)
        for tensor in ordered:
            writer.add_tensor_info(tensor.name, tensor.data.shape, tensor.data.dtype,
                                   tensor.data.nbytes, tensor.tensor_type)
        writer.write_header_to_file()
        writer.write_kv_data_to_file()
        writer.write_ti_data_to_file()
        for tensor in ordered:
            writer.write_tensor_data(tensor.data, tensor_endianess=reader.endianess)
        writer.close()
        other = GGUFReader(partial)
        before = {t.name: t for t in reader.tensors}
        after = {t.name: t for t in other.tensors}
        if before.keys() != after.keys() or [t.name for t in other.tensors] != [t.name for t in ordered]:
            raise AssertionError("Tensor set or requested order changed")
        proofs = []
        for name, a in before.items():
            b = after[name]
            digest = hashlib.sha256(a.data).hexdigest()
            if a.tensor_type != b.tensor_type or a.shape.tolist() != b.shape.tolist() or digest != hashlib.sha256(b.data).hexdigest():
                raise AssertionError(f"Tensor changed: {name}")
            proofs.append({"name": name, "bytes": a.n_bytes, "sha256": digest})
        for name, field in reader.fields.items():
            if name.startswith("GGUF."):
                continue
            b = other.get_field(name)
            if b is None or field.types != b.types or field.contents() != b.contents():
                raise AssertionError(f"Metadata changed: {name}")
        spec = {"path": path.name, "size_bytes": partial.stat().st_size, "sha256": sha256(partial)}
        if registered and spec != registered["files"][0]:
            raise RuntimeError("Recreated packed helper differs from the pinned file; partial retained")
        result = registered or {"derived": {"source_model": "mtp_shared_q3", "source_sha256": models["mtp_shared_q3"]["files"][0]["sha256"],
            "layout": record["layout"], "required_engine": "mtp-shared",
            "receipt": str((folder / "preparation.json").relative_to(ROOT))}, "files": [spec]}
        partial.rename(path)
        if not registered:
            models[model_id] = result
            config.write_text(json.dumps(models, indent=2) + "\n")
        record.update(status="passed", output=result, retained_tensor_proofs=proofs,
                      cpu_expert_bytes=sum(t.n_bytes for t in experts), gpu_dense_bytes=sum(t.n_bytes for t in dense))
        print(f"Packed helper verified: {len(proofs)} unchanged tensors; GPU dense region {record['gpu_dense_bytes']/1024**2:.2f} MiB")
        return result
    except BaseException as error:
        record.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        (folder / "preparation.json").write_text(json.dumps(record, indent=2) + "\n")


if __name__ == "__main__":
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        prepare()
