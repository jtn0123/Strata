"""Strata plugin using the pinned native llama-server, its tokenizer and template."""
import http.client
import json
import queue
import socket
import threading
import time
from urllib.parse import urlparse

from lab import request


class NativeTokenizer:
    def __init__(self, base):
        self.base = base

    def encode(self, text, parse_special=False):
        return request(self.base, "/tokenize", {"content": text, "parse_special": parse_special,
                                              "add_special": False})["tokens"]

    def decode(self, ids, errors="replace"):
        return request(self.base, "/detokenize", {"tokens": ids})["content"]


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
        return request(self.base, "/apply-template", {"messages": messages,
                      "chat_template_kwargs": kwargs})["prompt"]


class NativeEngine:
    def __init__(self, base, props, model_id):
        self.base = base
        self.max_context = props["default_generation_settings"]["n_ctx"]
        self.last = {}
        self.info = {"backend": "metal-native-http", "version": props["build_info"],
                     "expert_streaming": False, "lazy_embeddings": model_id == "flash",
                     "runtime": "llama.cpp", "model_path": props["model_path"]}

    def generate(self, ids, max_new, sampling, cancel):
        if cancel.is_set():
            return
        url = urlparse(self.base)
        connection = http.client.HTTPConnection(url.hostname, url.port, timeout=600)
        payload = {"prompt": ids, "n_predict": max_new, "stream": True, "return_tokens": True,
                   "cache_prompt": False, "temperature": sampling.get("temperature", 0.8),
                   "repeat_penalty": sampling.get("repetition_penalty", 1.0)}
        for key in ("top_p", "top_k", "min_p", "frequency_penalty", "presence_penalty", "seed"):
            if sampling.get(key) is not None:
                payload[key] = sampling[key]
        events = queue.Queue()
        stopped = threading.Event()
        self.last = {}
        started, first, count = time.monotonic(), None, 0
        connection.request("POST", "/completion", body=json.dumps(payload),
                           headers={"Content-Type": "application/json"})
        transport = connection.sock

        def pump():
            try:
                response = connection.getresponse()
                if response.status != 200:
                    raise RuntimeError(f"Native inference HTTP {response.status}: {response.read().decode()}")
                for line in response:
                    if stopped.is_set():
                        break
                    if line.startswith(b"data: "):
                        events.put(json.loads(line[6:]))
            except BaseException as error:
                events.put(error)
            finally:
                events.put(None)

        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        try:
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
                    yield token
                if item.get("stop"):
                    timing = item.get("timings", {})
                    self.last = {"generated": count, "prompt_tokens": len(ids),
                                 "prompt_ms": timing.get("prompt_ms"),
                                 "decode_ms": timing.get("predicted_ms"),
                                 "native_timings": timing}
                    break
        finally:
            stopped.set()
            if transport:
                try:
                    transport.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            reader.join(timeout=2)
            connection.close()
            if not self.last:
                ended = time.monotonic()
                self.last = {"generated": count, "prompt_tokens": len(ids),
                             "prompt_ms": ((first or ended) - started) * 1000,
                             "decode_ms": (ended - (first or ended)) * 1000}

    def close(self):
        pass


def create_backend(config):
    from serve.backends import BackendBundle
    base = config["native_url"]
    parsed = urlparse(base)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1":
        raise ValueError("The lab native backend must use local HTTP on 127.0.0.1")
    props = request(base, "/props")
    tokenizer = NativeTokenizer(base)
    stops = set()
    for text in ("<|im_end|>", "<|endoftext|>"):
        ids = tokenizer.encode(text, parse_special=True)
        if len(ids) == 1:
            stops.add(ids[0])
    if not stops:
        raise ValueError("No supported Qwen end-of-turn token found")
    return BackendBundle(NativeEngine(base, props, config["model_name"]), tokenizer,
                         NativeTemplate(base), stops)
