#!/usr/bin/env python3
"""Inventory GGUF headers without touching tensor payloads, including partial downloads."""
import argparse
import json
import math
from pathlib import Path
import sys

from lab import ROOT
sys.path.insert(0, str(ROOT / "vendor/llama.cpp/gguf-py"))
from gguf import GGML_QUANT_SIZES, GGMLQuantizationType, GGUFReader, GGUFValueType


class HeaderReader(GGUFReader):
    def _build_tensors(self, start_offs, fields):
        self.inventory = []
        for field in fields:
            _, name, _, dims, dtype, offset = field.parts
            quant = GGMLQuantizationType(int(dtype[0]))
            block, size = GGML_QUANT_SIZES[quant]
            self.inventory.append({"name": name.tobytes().decode(), "shape": dims.tolist(),
                                   "quant": quant.name,
                                   "size_bytes": math.prod(dims.tolist()) * size // block,
                                   "offset": start_offs + int(offset[0])})


def inventory(model_id):
    model = json.loads((ROOT / "config/models.json").read_text())[model_id]
    shards = []
    for spec in model["files"]:
        path = ROOT / "models" / model_id / spec["path"]
        if not path.exists():
            path = path.with_suffix(".gguf.part")
        reader = HeaderReader(path)
        metadata = {name: value.contents() for name, value in reader.fields.items()
                    if name not in {"tokenizer.chat_template"} and value.types[0] != GGUFValueType.ARRAY}
        tensors = reader.inventory
        shards.append({"path": spec["path"], "expected_file_bytes": spec["size_bytes"],
                       "header_bytes": reader.data_offset, "metadata": metadata,
                       "tensor_bytes": sum(t["size_bytes"] for t in tensors), "tensors": tensors})
    record = {"model": model_id, "shards": shards,
              "note": "Tensor payloads were not read. Header inventory is not file integrity verification."}
    output = ROOT / "bench/results" / f"{model_id}-gguf-inventory.json"
    output.write_text(json.dumps(record, indent=2) + "\n")
    for shard in shards:
        tables = [t for t in shard["tensors"] if "per_layer_token_embd" in t["name"]]
        print(f"{Path(shard['path']).name}: {len(shard['tensors'])} tensors, {shard['tensor_bytes']/1e9:.3f} GB payload, {len(tables)} lazy lookup tables")
        for tensor in tables:
            print(tensor)
    print(f"Saved {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("model", choices=["small", "flash", "mtp"])
    inventory(parser.parse_args().model)
