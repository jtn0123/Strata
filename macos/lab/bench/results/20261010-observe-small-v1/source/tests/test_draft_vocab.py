"""Reject invalid or changed vocabulary files before inference; scope the environment."""
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from draft_vocab import experiment_environment, read_ids, vocabulary_info


class VocabularyTests(unittest.TestCase):
    def test_nonidentity_order_is_preserved(self):
        self.assertEqual(read_ids(struct.pack("<4i", 9, 2, 7, 0), 10), [9, 2, 7, 0])

    def test_reject_invalid_ids_and_partial_files(self):
        for data in (b"", b"\x01", struct.pack("<i", -1), struct.pack("<i", 10),
                     struct.pack("<2i", 2, 2)):
            with self.subTest(data=data), self.assertRaises(ValueError):
                read_ids(data, 10)

    def test_baseline_cannot_inherit_vocabulary_override(self):
        with patch.dict(os.environ, {"MELD_DRAFT_VOCAB": "/untrusted/input"}):
            env, info = experiment_environment("baseline")
            self.assertNotIn("MELD_DRAFT_VOCAB", env)
            self.assertIsNone(info)

    def test_wrong_engine_rejected(self):
        with self.assertRaises(ValueError):
            experiment_environment("baseline", "106k")

    def test_pinned_multilingual_list(self):
        info = vocabulary_info()
        self.assertEqual(info["count"], 106299)
        self.assertEqual(info["full_count"], 248320)

    def test_changed_file_rejected(self):
        with patch("draft_vocab.sha256", return_value="changed"):
            with self.assertRaises(RuntimeError):
                vocabulary_info()


if __name__ == "__main__":
    unittest.main()
