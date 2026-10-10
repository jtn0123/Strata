"""Small files reproduce changed model identity without loading or downloading GGUFs."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import model_provenance as proof


class ProvenanceTests(unittest.TestCase):
    def fixture(self, root):
        (root/"config").mkdir(); (root/"models/small").mkdir(parents=True)
        path=root/"models/small/tiny.gguf"; path.write_bytes(b"weights")
        (root/"config/models.json").write_text(json.dumps({"small":{"files":[{
            "path":"tiny.gguf","size_bytes":7,"sha256":hashlib.sha256(b"weights").hexdigest()}]}}))
        return path

    def test_cache_reuses_hash_only_while_identity_and_registry_match(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); path=self.fixture(root)
            receipt=proof.verify_models(["small"],root)
            self.assertTrue(receipt["models"]["small"]["files"][0]["hash_scan_performed"])
            with patch.object(proof,"file_digest",side_effect=AssertionError("Unneeded hash scan")):
                cached=proof.verify_models(["small"],root)
            self.assertFalse(cached["models"]["small"]["files"][0]["hash_scan_performed"])
            path.write_bytes(b"changed")
            with self.assertRaisesRegex(RuntimeError,"Verified model changed"):proof.assert_unchanged(receipt,root)
            with self.assertRaisesRegex(RuntimeError,"SHA256 differs"):proof.verify_models(["small"],root)

    def test_mutation_during_hashing_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=self.fixture(root);original=proof.file_digest
            def mutate(p):
                digest=original(p);p.write_bytes(b"changed");return digest
            with patch.object(proof,"file_digest",side_effect=mutate),self.assertRaisesRegex(RuntimeError,"during verification"):
                proof.verify_models(["small"],root)


if __name__ == "__main__":unittest.main()
