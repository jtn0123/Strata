"""Strata plugin using the pinned native llama-server, its tokenizer and template."""
import http.client
import json
import queue
import socket
import sys
import threading
import time
from collections import OrderedDict
from urllib.parse import urlparse

from lab import ROOT, request


def engine_failure(message):
    # The pinned shell records and serializes this exception for both APIs. Import
    # lazily so tokenizer-only tools do not need to initialize the API shell.
    try:
        from serve.server import EngineDied
    except ImportError:
        vendor = ROOT / 'vendor/Strata-macOS'
        if not (vendor / 'serve/server.py').is_file():
            return RuntimeError(message)
        # Standalone adapter/benchmark tools only add scripts/ to their search
        # path. Resolve the same pinned shell used by strata_server.py on faults.
        sys.path.insert(0, str(vendor))
        try:
            from serve.server import EngineDied
        except ImportError:
            return RuntimeError(message)  # Keep the original native error/cause.
    return EngineDied(message)


def validate_native_properties(response):
    settings = response.get('default_generation_settings')
    context = settings.get('n_ctx') if isinstance(settings, dict) else None
    if (type(context) is not int or context <= 0 or
            not all(isinstance(response.get(key), str) for key in ('build_info', 'model_path'))):
        raise ValueError('Expected context, build_info and model_path properties')


def validate_native_response(endpoint, response):
    if not isinstance(response, dict):
        raise ValueError('Expected a JSON object')
    if 'error' in response:
        raise ValueError(f"Native error response: {response['error']}")
    if endpoint == '/tokenize':
        tokens = response.get('tokens')
        if not isinstance(tokens, list) or any(type(token) is not int or token < 0 for token in tokens):
            raise ValueError('Expected a list of nonnegative token IDs')
    elif endpoint in ('/detokenize', '/apply-template'):
        key = 'content' if endpoint == '/detokenize' else 'prompt'
        if not isinstance(response.get(key), str):
            raise ValueError(f'Expected a text {key} field')
    elif endpoint == '/props':
        validate_native_properties(response)
    return response


def native_request(base, endpoint, payload=None):
    try:
        return validate_native_response(endpoint, request(base, endpoint, payload))
    except (OSError, RuntimeError, ValueError) as error:
        raise engine_failure(f"Native {endpoint} failed: {error}") from error


class NativeTokenizer:
    def __init__(self, base, piece_cache=False):
        self.base = base
        self.piece_cache = piece_cache
        self.pieces = OrderedDict()
        self.piece_bytes = 0
        self.prefix = ()
        self.prefix_text = ""
        self.decode_stats = dict(requests=0, input_tokens=0, piece_hits=0, prefix_fallbacks=0)

    def encode(self, text, parse_special=False):
        return native_request(self.base, "/tokenize", {"content": text, "parse_special": parse_special,
                                              "add_special": False})["tokens"]

    def decode(self, ids, errors="replace"):
        ids = tuple(ids)
        if not self.piece_cache:
            return self._decode_native(ids)
        if not ids:
            self.prefix, self.prefix_text = (), ""
            return ""
        append = len(ids) == len(self.prefix) + 1 and ids[:-1] == self.prefix
        if append and not self.prefix_text.endswith("\ufffd"):
            token = ids[-1]
            if token in self.pieces:
                piece = self.pieces.pop(token)
                self.pieces[token] = piece
                self.decode_stats["piece_hits"] += 1
            else:
                piece = self._decode_native((token,))
                if "\ufffd" not in piece:
                    cost = len(piece.encode("utf-8")) + 64
                    if cost <= 1024 * 1024:
                        while self.pieces and (len(self.pieces) >= 4096 or self.piece_bytes + cost > 1024 * 1024):
                            _, old = self.pieces.popitem(last=False)
                            self.piece_bytes -= len(old.encode("utf-8")) + 64
                        self.pieces[token] = piece
                        self.piece_bytes += cost
            if "\ufffd" not in piece:
                text = self.prefix_text + piece
            else:
                self.decode_stats["prefix_fallbacks"] += 1
                text = piece if len(ids) == 1 else self._decode_native(ids)
        else:
            self.decode_stats["prefix_fallbacks"] += 1
            text = self._decode_native(ids)
        self.prefix, self.prefix_text = ids, text
        return text

    def _decode_native(self, ids):
        self.decode_stats["requests"] += 1
        self.decode_stats["input_tokens"] += len(ids)
        return native_request(self.base, "/detokenize", {"tokens": ids})["content"]


class NativeTemplate:
    def __init__(self, base):
        self.base = base

    @staticmethod
    def starts_in_reasoning(prompt):
        return prompt.rfind("<think>") > prompt.rfind("</think>")

    def render(self, messages, tools=None, **kwargs):
        if tools:
            raise ValueError("Tool calls are not supported by this Mac profile")
        if any(isinstance(m.get("content"), list) for m in messages):
            raise ValueError("Images are not supported by this Mac profile")
        return native_request(self.base, "/apply-template", {"messages": messages,
                      "chat_template_kwargs": kwargs})["prompt"]


class NativeEngine:
    def __init__(self, base, props, model_id, prompt_cache=True, *, stop_ids=()):
        self.base = base
        self.prompt_cache = prompt_cache
        self.stop_ids = set(stop_ids)
        self.max_context = props["default_generation_settings"]["n_ctx"]
        self.last = {}
        self.info = {"backend": "metal-native-http", "version": props["build_info"],
                     "expert_streaming": False, "lazy_embeddings": model_id == "flash",
                     "runtime": "llama.cpp", "model_path": props["model_path"],
                     "prompt_cache": prompt_cache}

    def generate(self, ids, max_new, sampling, cancel):
        self.last = {}
        if cancel.is_set():
            return
        url = urlparse(self.base)
        connection = http.client.HTTPConnection(url.hostname, url.port, timeout=600)
        payload = {"prompt": ids, "n_predict": max_new, "stream": True, "return_tokens": True,
                   "cache_prompt": self.prompt_cache, "temperature": sampling.get("temperature", 0.8),
                   "repeat_penalty": sampling.get("repetition_penalty", 1.0)}
        for key in ("top_p", "top_k", "min_p", "frequency_penalty", "presence_penalty", "seed"):
            if sampling.get(key) is not None:
                payload[key] = sampling[key]
        events = queue.Queue()
        stopped = threading.Event()
        final_ready = threading.Event()
        final_record = None
        final_consumed = False
        last_token = None
        failed = False
        transport, reader = None, None
        started, first, count = time.monotonic(), None, 0

        def pump():
            nonlocal final_record
            try:
                response = connection.getresponse()
                if response.status != 200:
                    raise RuntimeError(f"Native inference HTTP {response.status}: {response.read().decode()}")
                for line in response:
                    if stopped.is_set():
                        break
                    if line.startswith(b"data: "):
                        item = json.loads(line[6:])
                        if item.get('error'):
                            raise RuntimeError(f"Native inference error: {item['error']}")
                        if item.get('stop'):
                            final_record = item
                            final_ready.set()
                        events.put(item)
            except BaseException as error:
                events.put(error)
            finally:
                final_ready.set()  # EOF/error must not make finalization wait for its deadline.
                events.put(None)

        try:
            connection.request("POST", "/completion", body=json.dumps(payload),
                               headers={"Content-Type": "application/json"})
            transport = connection.sock
            reader = threading.Thread(target=pump, daemon=True)
            reader.start()
            while not cancel.is_set():
                try:
                    item = events.get(timeout=0.1)
                except queue.Empty:
                    if time.monotonic() - started > 600:
                        raise TimeoutError("Native inference exceeded 600 seconds")
                    yield None
                    continue
                if item is None:
                    raise RuntimeError("Native inference stream ended before its final record")
                if isinstance(item, BaseException):
                    raise item
                for token in item.get("tokens", []):
                    if cancel.is_set():
                        return
                    first = first or time.monotonic()
                    count += 1
                    last_token = token
                    yield token
                if item.get("stop"):
                    final_consumed = True
                    break
        except GeneratorExit as error:
            # The shell can fail while detokenizing a yielded token, then close
            # this generator in its finally block. That active consumer failure
            # is carried as GeneratorExit's context; its timings are incomplete.
            if (last_token not in self.stop_ids and isinstance(error.__context__, Exception)
                    and not cancel.is_set()):
                failed = True
            raise
        except Exception as error:
            if cancel.is_set():
                return
            failed = True
            raise engine_failure(f"Native inference failed: {error}") from error
        finally:
            # The pinned shell closes this generator as soon as it sees EOS. Native
            # timing follows in another SSE packet. Drain only that normal completion,
            # bounded to 0.5s and responsive to cancellation; never wait on a user stop.
            normal_stop = last_token in self.stop_ids
            if normal_stop and not cancel.is_set():
                deadline = time.monotonic() + 0.5
                while not final_ready.is_set() and not cancel.is_set() and time.monotonic() < deadline:
                    final_ready.wait(min(0.05, max(0, deadline - time.monotonic())))
            if not failed and not cancel.is_set() and (final_consumed or normal_stop) and final_record:
                timing = final_record.get('timings')
                if isinstance(timing, dict) and timing:
                    self.last = {"generated": count, "prompt_tokens": len(ids),
                                 "prompt_ms": timing.get("prompt_ms"),
                                 "decode_ms": timing.get("predicted_ms"),
                                 "native_timings": dict(timing), "reused": timing.get("cache_n")}
            stopped.set()
            if transport:
                try:
                    transport.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            if reader is not None and reader.ident is not None:
                reader.join(timeout=2)
            connection.close()
            if not self.last:
                self.last = {"generated": count, "prompt_tokens": len(ids)}
                if not failed:
                    ended = time.monotonic()
                    self.last.update(prompt_ms=((first or ended) - started) * 1000,
                                     decode_ms=(ended - (first or ended)) * 1000)

    def close(self):
        pass


def create_backend(config):
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
    return BackendBundle(NativeEngine(base, props, config["model_name"], prompt_cache, stop_ids=stops), tokenizer,
                         NativeTemplate(base), stops)
