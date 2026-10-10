"""Exact prefix decoding and bounded token-piece reuse without native execution."""
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "vendor/Strata-macOS"))
from native_backend import NativeTokenizer
from serve.server import Detokenizer, Service


class PieceCacheTests(unittest.TestCase):
    def setUp(self):
        self.pieces = {0: b"", 1: b"hello ", 2: b"world", 3: b"!", 4: b"\xe2",
                       5: b"\x80", 6: b"\x94", 7: b"\xff", 8: b"\xef\xbf\xbd",
                       9: b"<think>", 10: b"</think>", 11: b"cafe\xc3\xa9"}
        self.calls = []

    def native(self, base, endpoint, payload):
        self.assertEqual(endpoint, "/detokenize")
        ids = tuple(payload["tokens"])
        self.calls.append(ids)
        return {"content": b"".join(self.pieces[t] for t in ids).decode("utf-8", "replace")}

    def test_all_prefixes_match_native_including_split_and_invalid_utf8(self):
        ids = [1, 4, 5, 6, 2, 3, 7, 1, 8, 2, 0, 11, 4, 1, 9, 10]
        with patch("native_backend.request", side_effect=self.native):
            tok = NativeTokenizer("http://127.0.0.1:1", piece_cache=True)
            for n in range(len(ids) + 1):
                expected = self.native(tok.base, "/detokenize", {"tokens": ids[:n]})["content"]
                self.assertEqual(tok.decode(ids[:n]), expected)
            self.assertGreater(tok.decode_stats["prefix_fallbacks"], 0)
            self.assertNotIn(4, tok.pieces)
            self.assertNotIn(7, tok.pieces)
            self.assertNotIn(8, tok.pieces)

    def test_repeated_valid_pieces_reduce_calls_and_serialized_ids(self):
        ids = [1, 2, 3] * 80
        with patch("native_backend.request", side_effect=self.native):
            control = NativeTokenizer("local")
            candidate = NativeTokenizer("local", piece_cache=True)
            for n in range(1, len(ids) + 1):
                self.assertEqual(candidate.decode(ids[:n]), control.decode(ids[:n]))
            self.assertEqual(control.decode_stats["requests"], 240)
            self.assertEqual(control.decode_stats["input_tokens"], 28920)
            self.assertEqual(candidate.decode_stats["requests"], 3)
            self.assertEqual(candidate.decode_stats["input_tokens"], 3)

    def test_changed_prefix_reset_and_arbitrary_decode_use_exact_fallback(self):
        with patch("native_backend.request", side_effect=self.native):
            tok = NativeTokenizer("local", piece_cache=True)
            for ids in ([1], [1, 2], [2, 1], [2, 1, 3], [], [1], [1, 1], [1, 1], [0, 0, 0]):
                self.assertEqual(tok.decode(ids), self.native("local", "/detokenize", {"tokens": ids})["content"])

    def test_cache_bound_and_eviction_preserve_text(self):
        self.pieces.update({t: b"x" for t in range(20, 4120)})
        with patch("native_backend.request", side_effect=self.native):
            tok = NativeTokenizer("local", piece_cache=True)
            ids = []
            for t in range(20, 4120):
                ids.append(t)
                self.assertEqual(tok.decode(ids), "x" * len(ids))
            self.assertEqual(len(tok.pieces), 4096)
            self.assertLessEqual(tok.piece_bytes, 1024 * 1024)
            self.assertNotIn(20, tok.pieces)
            ids.append(20)
            self.assertEqual(tok.decode(ids), "x" * len(ids))

    def test_parser_events_and_cancellation_recovery_match(self):
        class Engine:
            info = {}
            last = {}
            def generate(inner, ids, max_new, sampling, cancel):
                for i, token in enumerate(inner.tokens):
                    if cancel.is_set():
                        return
                    if inner.cancel_after == i:
                        cancel.set()
                        return
                    yield token
        with patch("native_backend.request", side_effect=self.native), patch.object(NativeTokenizer, "encode", return_value=[99]):
            engine = Engine()
            services = [Service(engine, NativeTokenizer("local", piece_cache=flag), None) for flag in (False, True)]
            for cancel_after in (None, 4, None):
                engine.tokens = [9, 1, 2, 10, 1, 4, 5, 6, 11, 3, 99]
                engine.cancel_after = cancel_after
                traces = [list(s.run([], True, [], 32, {}, threading.Event())) for s in services]
                self.assertEqual(traces[0], traces[1])
                self.assertEqual(traces[0][-1][1]["finish"], "cancel" if cancel_after is not None else "stop")


if __name__ == "__main__":
    unittest.main()
