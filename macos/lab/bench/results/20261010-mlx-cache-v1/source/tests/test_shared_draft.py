"""Verify that removing duplicated tensors preserves the helper body and metadata."""
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
from gguf import GGUFReader, GGUFWriter
import prepare_shared
import prepare_shared_layout
from lab import server_command
from inspect_gguf import HeaderReader


class SharedDraftTests(unittest.TestCase):
    def write_source(self, root, duplicated=True):
        source = root / "source.gguf"
        writer = GGUFWriter(source, "qwen4exp")
        writer.add_name("copy test")
        writer.add_array("tokenizer.ggml.tokens", ["a", "中", "café"])
        writer.add_uint32("qwen4exp.embedding_length", 8)
        writer.add_tensor("blk.48.ffn_down_exps.weight", np.arange(64, dtype=np.float32).reshape(8, 8))
        if duplicated:
            for name in prepare_shared.REMOVED:
                writer.add_tensor(name, np.arange(24, dtype=np.float32).reshape(3, 8))
        writer.write_header_to_file()
        writer.write_kv_data_to_file()
        writer.write_tensors_to_file()
        writer.close()
        (root / "config").mkdir()
        models = {"mtp_q3": {"files": [{"path": source.name, "size_bytes": source.stat().st_size,
                  "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}]}}
        (root / "config/models.json").write_text(json.dumps(models))
        (root / "bench/results").mkdir(parents=True)
        return source

    def test_real_gguf_copy_preserves_retained_bytes_and_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.write_source(root)
            with patch.object(prepare_shared, "ROOT", root), patch.object(prepare_shared, "model_path", return_value=source):
                result = prepare_shared.derive()
            derived = root / "models/mtp_shared_q3" / result["files"][0]["path"]
            before, after = GGUFReader(source), GGUFReader(derived)
            self.assertEqual([t.name for t in after.tensors], ["blk.48.ffn_down_exps.weight"])
            self.assertEqual(before.tensors[0].data.tobytes(), after.tensors[0].data.tobytes())
            self.assertEqual(after.get_field("tokenizer.ggml.tokens").contents(), ["a", "中", "café"])
            proof = next((root / "bench/results").glob("*/preparation.json"))
            self.assertEqual(json.loads(proof.read_text())["status"], "passed")
            self.assertEqual(result["derived"]["required_engine"], "mtp-shared")

    def test_source_without_the_expected_tables_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.write_source(root, duplicated=False)
            with patch.object(prepare_shared, "ROOT", root), patch.object(prepare_shared, "model_path", return_value=source):
                with self.assertRaises(ValueError):
                    prepare_shared.derive()
            self.assertFalse((root / "models/mtp_shared_q3").exists())

    def test_shared_helper_cannot_be_sent_to_the_stock_loader(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config/models.json").write_text(json.dumps({"mtp_shared_q3": {
                "derived": {"required_engine": "mtp-shared"}}}))
            with patch("lab.ROOT", root), patch("lab.model_path", return_value=root / "unused.gguf"), \
                    patch("engines.engine_binary", return_value=root / "unused-server"):
                with self.assertRaisesRegex(ValueError, "requires the mtp-shared engine"):
                    server_command("flash", spec="draft-mtp", draft_model="mtp_shared_q3")


class PackedLayoutTests(unittest.TestCase):
    def test_pack_reduces_gpu_span_without_changing_any_tensor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "shared.gguf"
            writer = GGUFWriter(source, "qwen4exp")
            writer.add_array("tokenizer.ggml.tokens", ["a", "中", "café"])
            names = []
            for n in range(29):
                name = f"dense-{n}.weight"
                names.append(name)
                writer.add_tensor(name, np.arange(8, dtype=np.float32).reshape(2, 4))
                if n < 3:
                    name = f"blk.48.ffn_{['down', 'gate', 'up'][n]}_exps.weight"
                    names.append(name)
                    writer.add_tensor(name, np.arange(1024, dtype=np.float32).reshape(128, 8))
            writer.write_header_to_file()
            writer.write_kv_data_to_file()
            writer.write_tensors_to_file()
            writer.close()
            (root / "config").mkdir()
            (root / "bench/results").mkdir(parents=True)
            (root / "config/models.json").write_text(json.dumps({"mtp_shared_q3": {"files": [{
                "path": source.name, "size_bytes": source.stat().st_size,
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}]}}))
            with patch.object(prepare_shared_layout, "ROOT", root), \
                    patch.object(prepare_shared_layout, "model_path", return_value=source):
                result = prepare_shared_layout.prepare()
            destination = root / "models/mtp_shared_packed_q3" / result["files"][0]["path"]
            old, new = GGUFReader(source), GGUFReader(destination)
            before = {t.name: t.data.tobytes() for t in old.tensors}
            self.assertEqual(before, {t.name: t.data.tobytes() for t in new.tensors})
            self.assertTrue(all(t.name.endswith("_exps.weight") for t in new.tensors[:3]))
            self.assertEqual(new.get_field("tokenizer.ggml.tokens").contents(), ["a", "中", "café"])
            def span(path):
                dense = [t for t in HeaderReader(path).inventory if not t["name"].endswith("_exps.weight")]
                return max(t["offset"] + t["size_bytes"] for t in dense) - min(t["offset"] for t in dense)
            self.assertLess(span(destination), span(source) / 10)


if __name__ == "__main__":
    unittest.main()
