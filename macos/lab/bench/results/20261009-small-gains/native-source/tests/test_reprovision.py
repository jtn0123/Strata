"""A cloned registry must regenerate missing derived files without changing pins."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "vendor/llama.cpp/gguf-py"))
import numpy as np
from gguf import GGUFWriter
import prepare_draft
import prepare_shared
import prepare_shared_layout


def file_spec(path):
    return {"path": path.name, "size_bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


class ReprovisionTests(unittest.TestCase):
    def source(self, root):
        source = root / "source.gguf"
        writer = GGUFWriter(source, "qwen4exp")
        writer.add_array("tokenizer.ggml.tokens", ["a", "中", "café"])
        writer.add_uint32("qwen4exp.embedding_length", 8)
        for n in range(29):
            writer.add_tensor(f"dense-{n}.weight", np.arange(8, dtype=np.float32).reshape(2, 4))
            if n < 3:
                name = f"blk.48.ffn_{['down', 'gate', 'up'][n]}_exps.weight"
                writer.add_tensor(name, np.arange(64, dtype=np.float32).reshape(8, 8))
        for name in prepare_shared.REMOVED:
            writer.add_tensor(name, np.arange(24, dtype=np.float32).reshape(3, 8))
        writer.write_header_to_file()
        writer.write_kv_data_to_file()
        writer.write_tensors_to_file()
        writer.close()
        (root / "config").mkdir()
        (root / "bench/results").mkdir(parents=True)
        config = root / "config/models.json"
        config.write_text(json.dumps({"mtp_q3": {"files": [file_spec(source)]}}))
        def model_path(name):
            if name == "mtp_q3":
                return source
            spec = json.loads(config.read_text())[name]["files"][0]
            path = root / "models" / name / spec["path"]
            if not path.is_file():
                raise FileNotFoundError(path)
            return path
        return config, model_path

    def clock(self, module):
        mocked = patch.object(module, "datetime")
        clock = mocked.start()
        self.addCleanup(mocked.stop)
        clock.now.side_effect = [datetime(2026, 10, 6, 0, 0, n, tzinfo=timezone.utc) for n in range(4)]

    def test_shared_and_packed_registry_rebuild_missing_files_with_identical_pins(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, model_path = self.source(root)
            self.clock(prepare_shared)
            self.clock(prepare_shared_layout)
            with patch.object(prepare_shared, "ROOT", root), patch.object(prepare_shared, "model_path", model_path), \
                    patch.object(prepare_shared_layout, "ROOT", root), patch.object(prepare_shared_layout, "model_path", model_path):
                shared = prepare_shared.derive()
                packed = prepare_shared_layout.prepare()
                registry = config.read_text()
                model_path("mtp_shared_q3").unlink()
                model_path("mtp_shared_packed_q3").unlink()
                self.assertEqual(prepare_shared.derive(), shared)
                self.assertEqual(prepare_shared_layout.prepare(), packed)
                self.assertEqual(file_spec(model_path("mtp_shared_q3")), shared["files"][0])
                self.assertEqual(file_spec(model_path("mtp_shared_packed_q3")), packed["files"][0])
                self.assertEqual(config.read_text(), registry)

    def test_shared_rebuild_rejects_a_changed_registered_hash(self):
        self.bad_shared_pin(False)

    def test_packed_rebuild_rejects_a_changed_registered_hash(self):
        self.bad_shared_pin(True)

    def bad_shared_pin(self, packed):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, model_path = self.source(root)
            self.clock(prepare_shared)
            self.clock(prepare_shared_layout)
            with patch.object(prepare_shared, "ROOT", root), patch.object(prepare_shared, "model_path", model_path), \
                    patch.object(prepare_shared_layout, "ROOT", root), patch.object(prepare_shared_layout, "model_path", model_path):
                prepare_shared.derive()
                if packed:
                    prepare_shared_layout.prepare()
                name = "mtp_shared_packed_q3" if packed else "mtp_shared_q3"
                destination = model_path(name)
                destination.unlink()
                models = json.loads(config.read_text())
                models[name]["files"][0]["sha256"] = "0" * 64
                config.write_text(json.dumps(models))
                registry = config.read_text()
                with self.assertRaisesRegex(RuntimeError, "pinned"):
                    (prepare_shared_layout.prepare if packed else prepare_shared.derive)()
                self.assertFalse(destination.exists())
                self.assertEqual(config.read_text(), registry)

    def test_quantized_registry_rebuilds_missing_output_with_identical_pin(self):
        self.quantized(False)

    def test_quantized_rebuild_rejects_changed_pin(self):
        self.quantized(True)

    def quantized(self, bad_pin):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "bench/results").mkdir(parents=True)
            source = root / "bf16.gguf"
            source.write_bytes(b"verified BF16 fixture")
            output = b"deterministic quantizer fixture"
            spec = {"path": "mtp-Qwen3.8-Flash-Next-Q3_K_S-pure.gguf", "size_bytes": len(output),
                    "sha256": "0" * 64 if bad_pin else hashlib.sha256(output).hexdigest()}
            models = {"mtp_bf16": {"files": [file_spec(source)]}, "mtp_q3": {"files": [spec],
                      "derived": {"source_model": "mtp_bf16", "receipt": "original-proof.json"}}}
            config = root / "config/models.json"
            config.write_text(json.dumps(models))
            registry = config.read_text()
            (root / "config/runtime.json").write_text(json.dumps({"llama_cpp": {"revision": "pinned"}}))
            tool = root / "vendor/llama.cpp/build/bin/llama-quantize"
            tool.parent.mkdir(parents=True)
            tool.touch()
            destination = root / "models/mtp_q3" / spec["path"]
            def model_path(name):
                path = source if name == "mtp_bf16" else destination
                if not path.is_file():
                    raise FileNotFoundError(path)
                return path
            def quantize(command, **kwargs):
                Path(command[-3]).write_bytes(output)
            with patch.object(prepare_draft, "ROOT", root), patch.object(prepare_draft, "model_path", model_path), \
                    patch.object(prepare_draft, "command_output", side_effect=lambda cmd: "pinned" if cmd[-1] == "HEAD" else ""), \
                    patch.object(prepare_draft.subprocess, "run", side_effect=quantize):
                if bad_pin:
                    with self.assertRaisesRegex(RuntimeError, "pinned"):
                        prepare_draft.prepare("q3")
                    self.assertFalse(destination.exists())
                else:
                    prepare_draft.prepare("q3")
                    self.assertEqual(destination.read_bytes(), output)
                self.assertEqual(config.read_text(), registry)


if __name__ == "__main__":
    unittest.main()
