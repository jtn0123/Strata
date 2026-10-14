"""Strata plugin using the pinned native llama-server, its tokenizer and template."""

import http.client
import json
import queue
import socket
import sys
import threading
import time
from collections import OrderedDict
from collections.abc import Generator, Iterable, Mapping, Sequence
from typing import Any, cast
from urllib.parse import urlparse

from benchmark_metrics import validate_final_record
from lab import ROOT, request

JSONDict = dict[str, Any]
DETOKENIZE_ENDPOINT = "/detokenize"
PIECE_CACHE_BYTES = 1024 * 1024
PIECE_CACHE_ENTRIES = 4096


def engine_failure(message: str) -> RuntimeError:
    # The pinned shell records and serializes this exception for both APIs. Import
    # lazily so tokenizer-only tools do not need to initialize the API shell.
    try:
        from serve.server import EngineDied
    except ImportError:
        vendor = ROOT / "vendor/Strata-macOS"
        if not (vendor / "serve/server.py").is_file():
            return RuntimeError(message)
        # Standalone adapter/benchmark tools only add scripts/ to their search
        # path. Resolve the same pinned shell used by strata_server.py on faults.
        sys.path.insert(0, str(vendor))
        try:
            from serve.server import EngineDied
        except ImportError:
            return RuntimeError(message)  # Keep the original native error/cause.
    return cast(RuntimeError, EngineDied(message))


def validate_native_properties(response: Mapping[str, Any]) -> None:
    settings = response.get("default_generation_settings")
    context = settings.get("n_ctx") if isinstance(settings, dict) else None
    if (
        type(context) is not int
        or context <= 0
        or not all(isinstance(response.get(key), str) for key in ("build_info", "model_path"))
    ):
        raise ValueError("Expected context, build_info and model_path properties")


def token_ids(value: object) -> bool:
    return isinstance(value, list) and all(type(token) is int and token >= 0 for token in value)


def validate_native_response(endpoint: str, response: object) -> JSONDict:
    if not isinstance(response, dict):
        raise ValueError("Expected a JSON object")
    if "error" in response:
        raise ValueError(f"Native error response: {response['error']}")
    if endpoint == "/tokenize":
        if not token_ids(response.get("tokens")):
            raise ValueError("Expected a list of nonnegative token IDs")
    elif endpoint in (DETOKENIZE_ENDPOINT, "/apply-template"):
        key = "content" if endpoint == DETOKENIZE_ENDPOINT else "prompt"
        if not isinstance(response.get(key), str):
            raise ValueError(f"Expected a text {key} field")
    elif endpoint == "/props":
        validate_native_properties(response)
    return response


def validate_completion_packet(packet: object) -> JSONDict:
    """One streamed completion record: token IDs the tokenizer can decode and a boolean stop flag."""
    if not isinstance(packet, dict):
        raise ValueError("Expected a JSON object completion packet")
    if packet.get("error"):
        raise RuntimeError(f"Native inference error: {packet['error']}")
    if not token_ids(packet.get("tokens", [])):
        raise ValueError("Expected a list of nonnegative token IDs in a completion packet")
    if not isinstance(packet.get("stop", False), bool):
        raise ValueError("Expected a boolean completion stop flag")
    return packet


def native_request(base: str, endpoint: str, payload: JSONDict | None = None) -> JSONDict:
    try:
        return validate_native_response(endpoint, request(base, endpoint, payload))
    except (OSError, RuntimeError, ValueError) as error:
        raise engine_failure(f"Native {endpoint} failed: {error}") from error


class NativeTokenizer:
    def __init__(self, base: str, piece_cache: bool = False) -> None:
        self.base = base
        self.piece_cache = piece_cache
        self.pieces: OrderedDict[int, str] = OrderedDict()
        self.piece_bytes = 0
        self.prefix: tuple[int, ...] = ()
        self.prefix_text = ""
        self.decode_stats = {
            "requests": 0,
            "input_tokens": 0,
            "piece_hits": 0,
            "prefix_fallbacks": 0,
        }

    def encode(self, text: str, parse_special: bool = False) -> list[int]:
        response = native_request(
            self.base,
            "/tokenize",
            {"content": text, "parse_special": parse_special, "add_special": False},
        )
        return cast(list[int], response["tokens"])

    def decode(self, ids: Iterable[int], errors: str = "replace") -> str:
        """Keep errors for the shell's tokenizer API; native HTTP owns UTF-8 decoding.

        The endpoint already returns text, so errors cannot change its decoding
        policy. Both cached and uncached paths retain that native policy.
        """
        ids = tuple(ids)
        if not self.piece_cache:
            return self._decode_native(ids)
        if not ids:
            self.prefix, self.prefix_text = (), ""
            return ""
        if self._can_append(ids):
            text = self._append_piece(ids)
        else:
            self.decode_stats["prefix_fallbacks"] += 1
            text = self._decode_native(ids)
        self.prefix, self.prefix_text = ids, text
        return text

    def _can_append(self, ids: tuple[int, ...]) -> bool:
        return len(ids) == len(self.prefix) + 1 and ids[:-1] == self.prefix and not self.prefix_text.endswith("\ufffd")

    def _append_piece(self, ids: tuple[int, ...]) -> str:
        piece = self._piece(ids[-1])
        if "\ufffd" not in piece:
            return self.prefix_text + piece
        self.decode_stats["prefix_fallbacks"] += 1
        return piece if len(ids) == 1 else self._decode_native(ids)

    def _piece(self, token: int) -> str:
        if token in self.pieces:
            piece = self.pieces.pop(token)
            self.pieces[token] = piece
            self.decode_stats["piece_hits"] += 1
            return piece
        piece = self._decode_native((token,))
        if "\ufffd" not in piece:
            self._cache_piece(token, piece)
        return piece

    def _cache_piece(self, token: int, piece: str) -> None:
        cost = len(piece.encode("utf-8")) + 64
        if cost > PIECE_CACHE_BYTES:
            return
        while self.pieces and (len(self.pieces) >= PIECE_CACHE_ENTRIES or self.piece_bytes + cost > PIECE_CACHE_BYTES):
            _, old = self.pieces.popitem(last=False)
            self.piece_bytes -= len(old.encode("utf-8")) + 64
        self.pieces[token] = piece
        self.piece_bytes += cost

    def _decode_native(self, ids: Sequence[int]) -> str:
        self.decode_stats["requests"] += 1
        self.decode_stats["input_tokens"] += len(ids)
        response = native_request(self.base, DETOKENIZE_ENDPOINT, {"tokens": ids})
        return cast(str, response["content"])


class NativeTemplate:
    def __init__(self, base: str) -> None:
        self.base = base

    @staticmethod
    def starts_in_reasoning(prompt: str) -> bool:
        return prompt.rfind("<think>") > prompt.rfind("</think>")

    def render(self, messages: Sequence[JSONDict], tools: object = None, **kwargs: Any) -> str:
        if tools:
            raise ValueError("Tool calls are not supported by this Mac profile")
        if any(isinstance(m.get("content"), list) for m in messages):
            raise ValueError("Images are not supported by this Mac profile")
        response = native_request(
            self.base,
            "/apply-template",
            {"messages": messages, "chat_template_kwargs": kwargs},
        )
        return cast(str, response["prompt"])


class _NativeStream:
    """One completion's reader, cancellation state, counters, and owned transport."""

    def __init__(
        self,
        connection: http.client.HTTPConnection,
        prompt_ids: Sequence[int],
        cancel: threading.Event,
        *,
        max_new: int,
        cached: bool,
    ) -> None:
        self.connection = connection
        self.prompt_ids = prompt_ids
        self.cancel = cancel
        self.max_new = max_new
        self.cached = cached
        self.timing_error: str | None = None
        self.rejected_timings: JSONDict | None = None
        self.events: queue.Queue[JSONDict | BaseException | None] = queue.Queue()
        self.stopped = threading.Event()
        self.final_ready = threading.Event()
        self.final_record: JSONDict | None = None
        self.final_consumed = False
        self.last_token: int | None = None
        self.failed = False
        self.transport: socket.socket | None = None
        self.reader: threading.Thread | None = None
        self.started = time.monotonic()
        self.first: float | None = None
        self.count = 0

    def start(self, payload: JSONDict) -> None:
        self.connection.request(
            "POST",
            "/completion",
            body=json.dumps(payload, allow_nan=False),
            headers={"Content-Type": "application/json"},
        )
        self.transport = self.connection.sock
        self.reader = threading.Thread(target=self._pump, daemon=True)
        self.reader.start()

    def _pump(self) -> None:
        try:
            response = self.connection.getresponse()
            if response.status != 200:
                raise RuntimeError(f"Native inference HTTP {response.status}: {response.read().decode()}")
            for line in response:
                if self.stopped.is_set():
                    break
                if line.startswith(b"data: "):
                    self._publish_packet(validate_completion_packet(json.loads(line[6:])))
        except BaseException as error:
            self.events.put(error)
        finally:
            # EOF/error must not make finalization wait for its deadline.
            self.final_ready.set()
            self.events.put(None)

    def _publish_packet(self, item: JSONDict) -> None:
        if item.get("stop"):
            self.final_record = item
            self.final_ready.set()
        self.events.put(item)

    def _next_event(self) -> JSONDict | None:
        try:
            item = self.events.get(timeout=0.1)
        except queue.Empty:
            if time.monotonic() - self.started > 600:
                raise TimeoutError("Native inference exceeded 600 seconds") from None
            return None  # Heartbeat while native inference is quiet.
        if item is None:
            raise RuntimeError("Native inference stream ended before its final record")
        if isinstance(item, BaseException):
            raise item
        return item

    def tokens(self) -> Generator[int | None, None, None]:
        while not self.cancel.is_set():
            item = self._next_event()
            if item is None:
                yield None
                continue
            for token in item.get("tokens", []):
                if self.cancel.is_set():
                    return
                self.first = self.first or time.monotonic()
                self.count += 1
                self.last_token = token
                yield token
            if item.get("stop"):
                self.final_consumed = True
                break

    def wait_for_final(self, normal_stop: bool) -> None:
        # The shell closes at EOS, before the following native timing packet.
        # Drain only normal completion, bounded to 0.5s and cancellable.
        if not normal_stop or self.cancel.is_set():
            return
        deadline = time.monotonic() + 0.5
        while not self.final_ready.is_set() and not self.cancel.is_set() and time.monotonic() < deadline:
            self.final_ready.wait(min(0.05, max(0, deadline - time.monotonic())))

    def native_metrics(self, normal_stop: bool) -> JSONDict:
        if self.failed or self.cancel.is_set() or not (self.final_consumed or normal_stop) or not self.final_record:
            return {}
        timing = self.final_record.get("timings")
        if not isinstance(timing, dict) or not timing:
            return {}
        try:
            limit = self.max_new if self.max_new > 0 else None
            validate_final_record(timing, self.count, len(self.prompt_ids), cached=self.cached, max_new=limit)
        except (KeyError, ValueError) as error:
            # Impossible counters never become native rates; server-derived timing remains.
            self.timing_error = f"{type(error).__name__}: {error}"
            self.rejected_timings = dict(timing)
            return {}
        return {
            "generated": self.count,
            "prompt_tokens": len(self.prompt_ids),
            "prompt_ms": timing.get("prompt_ms"),
            "decode_ms": timing.get("predicted_ms"),
            "native_timings": dict(timing),
            "reused": timing.get("cache_n"),
        }

    def fallback_metrics(self) -> JSONDict:
        metrics: JSONDict = {
            "generated": self.count,
            "prompt_tokens": len(self.prompt_ids),
        }
        if self.timing_error:
            # Kept apart from native_timings so a benchmark receipt can show what was rejected.
            metrics.update(native_timing_error=self.timing_error, rejected_native_timings=self.rejected_timings)
        if not self.failed:
            ended = time.monotonic()
            metrics.update(
                prompt_ms=((self.first or ended) - self.started) * 1000,
                decode_ms=(ended - (self.first or ended)) * 1000,
            )
        return metrics

    def close(self) -> None:
        self.stopped.set()
        if self.transport:
            try:
                self.transport.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        if self.reader is not None and self.reader.ident is not None:
            self.reader.join(timeout=2)
        self.connection.close()


class NativeEngine:
    def __init__(
        self,
        base: str,
        props: JSONDict,
        model_id: str,
        prompt_cache: bool = True,
        *,
        stop_ids: Iterable[int] = (),
    ) -> None:
        self.base = base
        self.prompt_cache = prompt_cache
        self.stop_ids = set(stop_ids)
        self.max_context = props["default_generation_settings"]["n_ctx"]
        self.last: JSONDict = {}
        self.info = {
            "backend": "metal-native-http",
            "version": props["build_info"],
            "expert_streaming": False,
            "lazy_embeddings": model_id == "flash",
            "runtime": "llama.cpp",
            "model_path": props["model_path"],
            "prompt_cache": prompt_cache,
        }

    def _completion_payload(self, ids: Sequence[int], max_new: int, sampling: Mapping[str, Any]) -> JSONDict:
        payload = {
            "prompt": ids,
            "n_predict": max_new,
            "stream": True,
            "return_tokens": True,
            "cache_prompt": self.prompt_cache,
            "temperature": sampling.get("temperature", 0.8),
            "repeat_penalty": sampling.get("repetition_penalty", 1.0),
        }
        for key in (
            "top_p",
            "top_k",
            "min_p",
            "frequency_penalty",
            "presence_penalty",
            "seed",
        ):
            if sampling.get(key) is not None:
                payload[key] = sampling[key]
        return payload

    def generate(
        self,
        ids: Sequence[int],
        max_new: int,
        sampling: Mapping[str, Any],
        cancel: threading.Event,
    ) -> Generator[int | None, None, None]:
        self.last = {}
        if cancel.is_set():
            return
        url = urlparse(self.base)
        hostname = url.hostname
        if hostname is None:
            raise engine_failure("Native inference URL has no hostname")
        connection = http.client.HTTPConnection(hostname, url.port, timeout=600)
        payload = self._completion_payload(ids, max_new, sampling)
        stream = _NativeStream(connection, ids, cancel, max_new=max_new, cached=self.prompt_cache)
        try:
            stream.start(payload)
            yield from stream.tokens()
        except GeneratorExit as error:
            # The shell can fail while detokenizing a yielded token, then close
            # this generator in its finally block. That active consumer failure
            # is carried as GeneratorExit's context; its timings are incomplete.
            if (
                stream.last_token not in self.stop_ids
                and isinstance(error.__context__, Exception)
                and not cancel.is_set()
            ):
                stream.failed = True
            raise
        except Exception as error:
            if cancel.is_set():
                return
            stream.failed = True
            raise engine_failure(f"Native inference failed: {error}") from error
        finally:
            normal_stop = stream.last_token in self.stop_ids
            stream.wait_for_final(normal_stop)
            self.last = stream.native_metrics(normal_stop)
            stream.close()
            if not self.last:
                self.last = stream.fallback_metrics()

    def close(self) -> None:
        # Each generate call owns and closes its HTTP connection and reader;
        # the engine has no persistent transport to close between requests.
        pass


def create_backend(config: JSONDict) -> Any:
    from serve.backends import BackendBundle

    base = config["native_url"]
    parsed = urlparse(base)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1":
        raise ValueError("The lab native backend must use local HTTP on 127.0.0.1")
    props = native_request(base, "/props")
    piece_cache = config.get("stream_piece_cache", False)
    if not isinstance(piece_cache, bool):
        raise ValueError("stream_piece_cache must be a boolean")
    tokenizer = NativeTokenizer(base, piece_cache=piece_cache)
    stops = set()
    for text in ("<|im_end|>", "<|endoftext|>"):
        ids = tokenizer.encode(text, parse_special=True)
        if len(ids) == 1:
            stops.add(ids[0])
    if not stops:
        raise ValueError("No supported Qwen end-of-turn token found")
    prompt_cache = config.get("prompt_cache", True)
    if not isinstance(prompt_cache, bool):
        raise ValueError("prompt_cache must be a boolean")
    return BackendBundle(
        NativeEngine(base, props, config["model_name"], prompt_cache, stop_ids=stops),
        tokenizer,
        NativeTemplate(base),
        stops,
    )
