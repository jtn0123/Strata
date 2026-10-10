#!/usr/bin/env python3
"""Exercise real local engine/API behavior. Saves pass/fail evidence, not speed claims."""
import argparse
from datetime import datetime, timezone
import http.client
import json
import threading
import time
import sys
import urllib.error
import urllib.request

from lab import ROOT, request
sys.path.insert(0, str(ROOT / "vendor/Strata-macOS"))
from native_backend import create_backend


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="small")
    ap.add_argument("--native-port", type=int, default=8096)
    ap.add_argument("--port", type=int, default=8095)
    args = ap.parse_args()
    native, app = f"http://127.0.0.1:{args.native_port}", f"http://127.0.0.1:{args.port}"
    record = {"schema": 1, "kind": "integration", "model": args.model, "checks": [],
              "note": "Real local native engine and Strata app. Functional tests can run during downloads; their timings are not benchmark results."}
    backend = create_backend({"native_url": native, "model_name": args.model})
    payload = {"model": args.model, "messages": [{"role": "user", "content": "What is 17 multiplied by 23? Reply with only the number."}],
               "temperature": 0, "seed": 1234, "max_tokens": 64, "reasoning_effort": "none"}

    def check(name, action):
        try:
            detail = action()
            record["checks"].append({"name": name, "passed": True, "detail": detail})
            print(f"PASS {name}", flush=True)
        except Exception as error:
            record["checks"].append({"name": name, "passed": False, "error": f"{type(error).__name__}: {error}"})
            print(f"FAIL {name}: {error}", flush=True)

    def unicode_roundtrip():
        text = "Hello, café 🌍 中文"
        ids = backend.tokenizer.encode(text)
        assert backend.tokenizer.decode(ids) == text
        return {"text": text, "tokens": ids}

    def parity():
        prompt = backend.template.render(payload["messages"], enable_thinking=False)
        ids = backend.tokenizer.encode(prompt, parse_special=True)
        direct = request(native, "/completion", {"prompt": ids, "n_predict": 64, "temperature": 0,
                         "seed": 1234, "cache_prompt": False, "return_tokens": True})
        routed = [t for t in backend.engine.generate(ids, 64, {"temperature": 0, "seed": 1234}, threading.Event())
                  if t is not None]
        assert routed == direct["tokens"], (routed, direct["tokens"])
        return {"native_token_ids": direct["tokens"], "adapter_token_ids": routed, "text": direct["content"]}

    def openai():
        result = request(app, "/v1/chat/completions", payload)
        assert result["choices"][0]["message"]["content"].strip() == "391"
        assert result["choices"][0]["finish_reason"] == "stop"
        return result

    def openai_stream():
        req = urllib.request.Request(app + "/v1/chat/completions", data=json.dumps({**payload, "stream": True}).encode(),
                                     headers={"Content-Type": "application/json"})
        content, done = [], False
        with urllib.request.urlopen(req, timeout=60) as response:
            for line in response:
                if not line.startswith(b"data: "):
                    continue
                raw = line[6:].strip()
                if raw == b"[DONE]":
                    done = True
                    break
                item = json.loads(raw)
                for choice in item.get("choices", []):
                    content.append(choice["delta"].get("content", ""))
        assert done and "".join(content).strip() == "391"
        return {"content": "".join(content), "done": done}

    def anthropic():
        result = request(app, "/v1/messages", {"model": args.model, "messages": payload["messages"],
                         "max_tokens": 64, "temperature": 0, "thinking": {"type": "disabled"}})
        content = "".join(part.get("text", "") for part in result["content"] if part["type"] == "text")
        assert content.strip() == "391" and result["stop_reason"] == "end_turn"
        return result

    def rejected(extra):
        req = urllib.request.Request(app + "/v1/chat/completions", data=json.dumps({**payload, **extra}).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=60).close()
        except urllib.error.HTTPError as error:
            assert error.code == 400, error.code
            return json.loads(error.read())
        raise AssertionError("Expected HTTP 400")

    def cancellation():
        prompt = backend.template.render([{"role": "user", "content": "Write a very long detailed essay about astronomy."}], enable_thinking=False)
        ids = backend.tokenizer.encode(prompt, parse_special=True)
        cancel = threading.Event()
        generator = backend.engine.generate(ids, 2048, {"temperature": 0}, cancel)
        for token in generator:
            if token is not None:
                break
        started = time.monotonic()
        cancel.set()
        assert list(generator) == []
        elapsed = time.monotonic() - started
        assert elapsed < 3, elapsed
        result = openai()
        return {"cancel_seconds": elapsed, "subsequent_response": result}

    def client_disconnect():
        connection = http.client.HTTPConnection("127.0.0.1", args.port, timeout=60)
        connection.request("POST", "/v1/chat/completions", body=json.dumps({**payload, "stream": True,
                           "max_tokens": 2048, "messages": [{"role": "user", "content": "Write a long essay about astronomy."}]}),
                           headers={"Content-Type": "application/json"})
        transport = connection.sock
        response = connection.getresponse()
        assert response.status == 200
        response.readline()
        import socket
        transport.shutdown(socket.SHUT_RDWR)
        connection.close()
        return openai()

    check("Unicode tokenizer roundtrip", unicode_roundtrip)
    check("Native/Strata adapter greedy token parity", parity)
    check("OpenAI non-stream content and EOS", openai)
    check("OpenAI streaming completion", openai_stream)
    check("Anthropic content and EOS", anthropic)
    check("Tools rejected explicitly", lambda: rejected({"tools": [{"type": "function", "function": {"name": "ping", "parameters": {"type": "object"}}}]}))
    check("Context overflow rejected explicitly", lambda: rejected({"messages": [{"role": "user", "content": "long word " * 6000}]}))
    check("Cancellation and subsequent request", cancellation)
    check("Client disconnect and subsequent request", client_disconnect)
    record["passed"] = all(c["passed"] for c in record["checks"])
    output = ROOT / "bench/results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + args.model + "-integration.json")
    output.write_text(json.dumps(record, indent=2) + "\n")
    print(f"Saved {output}")
    if not record["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
