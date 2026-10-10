"""Private, instance-local exact-input cache; no conversation or inference-state reuse."""
from collections import OrderedDict
import json
import sys
import threading
import time

from native_backend import NativeTokenizer


class InputCacheTokenizer(NativeTokenizer):
    def __init__(self, base, *, enabled=False, profile=False, budget=2 * 1024 * 1024,
                 max_entries=128, piece_cache=False):
        super().__init__(base, piece_cache=piece_cache)
        if type(enabled) is not bool or type(profile) is not bool:
            raise ValueError("Input cache/profile must be booleans")
        if type(budget) is not int or budget < 1 or type(max_entries) is not int or max_entries < 1:
            raise ValueError("Input cache bounds must be positive integers")
        self.enabled, self.profile = enabled, profile
        self.budget, self.max_entries = budget, max_entries
        self.entries, self.accounted_bytes = OrderedDict(), 0
        self.cache_lock = threading.RLock()
        self.encode_stats = dict(calls=0, hits=0, requests=0, bypasses=0, errors=0,
                                 evictions=0, requested_tokens=0, native_seconds=0.0)

    def clear_input_cache(self):
        # A new backend creates a new tokenizer. Explicit clearing also serializes
        # with in-flight encode calls, so an old reply cannot refill a cleared cache.
        with self.cache_lock:
            self.entries.clear()
            self.accounted_bytes = 0

    @staticmethod
    def entry_cost(text, tokens):
        # Conservative accounting for retained Python objects and LRU bookkeeping.
        # This is a cache bound, not a measurement of total process RSS.
        return (sys.getsizeof(text) + sys.getsizeof(tokens)
                + sum(sys.getsizeof(token) for token in tokens)
                + sys.getsizeof((text, False)) + 256)

    def encode(self, text, parse_special=False):
        if type(text) is not str or type(parse_special) is not bool:
            raise ValueError("Exact-input keys require text and a boolean special-token mode")
        key = (text, parse_special)
        with self.cache_lock:
            self.encode_stats["calls"] += 1
            try:
                if self.enabled and key in self.entries:
                    tokens, cost = self.entries.pop(key)
                    self.entries[key] = (tokens, cost)
                    self.encode_stats["hits"] += 1
                    return list(tokens)
                self.encode_stats["requests"] += 1
                started = time.perf_counter()
                try:
                    tokens = super().encode(text, parse_special=parse_special)
                finally:
                    self.encode_stats["native_seconds"] += time.perf_counter() - started
                if (type(tokens) is not list or
                        any(type(token) is not int or token < 0 for token in tokens)):
                    raise ValueError("Native tokenizer returned invalid token IDs")
                self.encode_stats["requested_tokens"] += len(tokens)
                if self.enabled:
                    frozen = tuple(tokens)
                    cost = self.entry_cost(text, frozen)
                    if cost > self.budget:
                        self.encode_stats["bypasses"] += 1
                    else:
                        while self.entries and (len(self.entries) >= self.max_entries or
                                                self.accounted_bytes + cost > self.budget):
                            _, (_, old_cost) = self.entries.popitem(last=False)
                            self.accounted_bytes -= old_cost
                            self.encode_stats["evictions"] += 1
                        self.entries[key] = (frozen, cost)
                        self.accounted_bytes += cost
                return list(tokens)
            except BaseException:
                self.encode_stats["errors"] += 1
                raise
            finally:
                if self.profile:
                    print("STRATA_INPUT_TOKENS " + json.dumps(dict(
                        self.encode_stats, enabled=self.enabled, entries=len(self.entries),
                        accounted_bytes=self.accounted_bytes)), file=sys.stderr, flush=True)
