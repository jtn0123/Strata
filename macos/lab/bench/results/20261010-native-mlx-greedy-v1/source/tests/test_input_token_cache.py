"""Exact token IDs, isolation, bounded retention and failure recovery without a server."""
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from input_token_cache import InputCacheTokenizer
from native_backend import NativeTokenizer


class InputCacheTests(unittest.TestCase):
    def native(self, base, endpoint, payload):
        self.assertEqual(endpoint, "/tokenize")
        self.assertIs(payload["add_special"], False)
        return {"tokens": list(payload["content"].encode("utf-8")) +
                ([900] if payload["parse_special"] else [])}

    def test_control_and_candidate_match_full_text_and_special_modes(self):
        with patch("native_backend.request", side_effect=self.native):
            control = NativeTokenizer("local")
            candidate = InputCacheTokenizer("local", enabled=True)
            for _ in range(2):
                for text in ("", "English code: print('hello')", "café 😀", "<|im_end|>"):
                    for special in (False, True):
                        self.assertEqual(control.encode(text, special), candidate.encode(text, special))
            self.assertEqual(candidate.encode_stats["hits"], 8)
            self.assertEqual(candidate.encode_stats["requests"], 8)
            self.assertEqual(candidate.encode("ab"), [97, 98])
            self.assertEqual(candidate.encode("a b"), [97, 32, 98])

    def test_returns_defensive_copies_and_instances_do_not_share(self):
        with patch("native_backend.request", side_effect=self.native) as request:
            one = InputCacheTokenizer("same-port", enabled=True)
            two = InputCacheTokenizer("same-port", enabled=True)
            one.encode("abc").append(999)
            self.assertEqual(one.encode("abc"), [97, 98, 99])
            two.encode("abc")
            self.assertEqual(request.call_count, 2)
            one.clear_input_cache()
            one.encode("abc")
            self.assertEqual(request.call_count, 3)
            self.assertEqual(two.encode_stats["hits"], 0)

    def test_lru_eviction_and_oversized_inputs_preserve_ids(self):
        with patch("native_backend.request", side_effect=self.native):
            tok = InputCacheTokenizer("local", enabled=True, max_entries=2, budget=1500)
            tok.encode("a"); tok.encode("b"); tok.encode("a"); tok.encode("c")
            self.assertNotIn(("b", False), tok.entries)
            for text in ("b", "x" * 1000, "x" * 1000, "d"):
                self.assertEqual(tok.encode(text), self.native("local", "/tokenize", dict(
                    content=text, parse_special=False, add_special=False))["tokens"])
                self.assertLessEqual(tok.accounted_bytes, tok.budget)
                self.assertLessEqual(len(tok.entries), 2)
            self.assertEqual(tok.encode_stats["bypasses"], 2)

    def test_errors_and_malformed_replies_are_never_cached(self):
        with patch("native_backend.request", side_effect=[RuntimeError("disconnect"),
                   {"tokens": [True]}, {"tokens": [-1]}, {"tokens": [4]}, {"tokens": [5]}]) as request:
            tok = InputCacheTokenizer("local", enabled=True)
            for error in (RuntimeError, ValueError, ValueError):
                with self.assertRaises(error): tok.encode("same")
                self.assertFalse(tok.entries)
            self.assertEqual(tok.encode("same"), [4])
            self.assertEqual(tok.encode("same"), [4])
            self.assertEqual(request.call_count, 4)
            tok.clear_input_cache()
            self.assertEqual(tok.encode("same"), [5])

    def test_disabled_path_repeats_requests_and_retains_no_inputs(self):
        with patch("native_backend.request", side_effect=self.native) as request:
            tok = InputCacheTokenizer("local")
            tok.encode("test"); tok.encode("test")
            self.assertEqual(request.call_count, 2)
            self.assertEqual(tok.accounted_bytes, 0)
            self.assertFalse(tok.entries)
            self.assertEqual(tok.encode_stats["hits"], 0)

    def test_bad_configuration_and_keys_are_rejected(self):
        for kwargs in (dict(enabled=1), dict(profile="yes"), dict(budget=True), dict(max_entries=0)):
            with self.assertRaises(ValueError): InputCacheTokenizer("local", **kwargs)
        tok = InputCacheTokenizer("local", enabled=True)
        for text, special in ((None, False), ("text", 1)):
            with self.assertRaises(ValueError): tok.encode(text, special)

    def test_clear_serializes_with_an_inflight_native_reply(self):
        entered, release, cleared = threading.Event(), threading.Event(), threading.Event()
        def delayed(*args):
            entered.set()
            if not release.wait(2): raise RuntimeError("Fixture timeout")
            return {"tokens": [1]}
        tok = InputCacheTokenizer("local", enabled=True)
        with patch("native_backend.request", side_effect=delayed):
            encode = threading.Thread(target=lambda: tok.encode("input"))
            clear = threading.Thread(target=lambda: (tok.clear_input_cache(), cleared.set()))
            encode.start(); self.assertTrue(entered.wait(1)); clear.start()
            self.assertFalse(cleared.wait(.02))
            release.set(); encode.join(1); clear.join(1)
            self.assertFalse(encode.is_alive()); self.assertFalse(clear.is_alive())
            self.assertTrue(cleared.is_set()); self.assertFalse(tok.entries)
            self.assertEqual(tok.accounted_bytes, 0)


if __name__ == "__main__": unittest.main()
