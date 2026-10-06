#!/usr/bin/env python3
"""Check a strict multilingual answer with and without the isolated vocabulary graph."""
from datetime import datetime, timezone
import fcntl
import json
import socket
import subprocess

from benchmark import Monitor, wait_ready
from check_memory import assert_no_model_server
from draft_vocab import experiment_environment, read_ids, vocabulary_info
from engines import verify_engine
from lab import ROOT, model_path, request, server_command

OLD = '城市是杭州，数量是37。只返回一个JSON对象，键为city和count，不要解释。'
STRICT = OLD + '不要使用Markdown或代码块。'


def main():
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        folder = ROOT / "bench/features" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-draft-vocab")
        folder.mkdir()
        record = {"status": "running", "profiles": [], "note": "Normal EOS and greedy/sampled strict JSON. "
            "The original Chinese prompt is also checked on the unchanged engine to diagnose its code-fence output."}
        from inspect_gguf import HeaderReader
        info = vocabulary_info()
        subset_ids = set(read_ids((ROOT / info["path"]).read_bytes(), info["full_count"]))
        reader = HeaderReader(model_path("flash"))
        token_types = reader.get_field("tokenizer.ggml.token_type").contents()
        outside = next(i for i, kind in enumerate(token_types) if kind == 1 and i not in subset_ids)
        record["outside_draft_vocabulary_token"] = outside
        try:
            for name, engine, mode, spec in (("plain", "baseline", "off", "none"),
                                           ("subset", "draft-vocab", "106k", "draft-mtp")):
                assert_no_model_server()
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", 0))
                    port = sock.getsockname()[1]
                base = f"http://127.0.0.1:{port}"
                command = server_command("flash", port, 4096, 512, 512, spec, 2,
                                         draft_placement="output", draft_model="mtp_q3", engine=engine)
                env, vocab = experiment_environment(engine, mode)
                profile = {"name": name, "engine": verify_engine(engine), "command": command,
                           "vocabulary": vocab, "checks": []}
                record["profiles"].append(profile)
                process, monitor = None, None
                with (folder / (name + ".log")).open("w") as log:
                    try:
                        process = subprocess.Popen(command, stdout=log, stderr=log, env=env)
                        monitor = Monitor(process, folder / (name + "-memory.jsonl"))
                        monitor.thread.start()
                        profile["ready_s"] = wait_ready(process, base)
                        tasks = [(STRICT, t) for t in (0, 0.6)]
                        if name == "plain":
                            tasks.insert(0, (OLD, 0))
                        for prompt, temperature in tasks:
                            response = request(base, "/v1/chat/completions", {"model": "flash",
                                "messages": [{"role": "user", "content": prompt}], "temperature": temperature,
                                "seed": 1234, "max_tokens": 96, "reasoning_effort": "none",
                                "chat_template_kwargs": {"enable_thinking": False}})
                            content = response["choices"][0]["message"].get("content", "").strip()
                            try:
                                passed = json.loads(content) == {"city": "杭州", "count": 37}
                            except ValueError:
                                passed = False
                            passed &= response["choices"][0]["finish_reason"] == "stop"
                            profile["checks"].append({"prompt": prompt, "temperature": temperature,
                                "strict": prompt == STRICT, "passed": passed, "response": response})
                            print(f"{name}, strict={prompt == STRICT}, temperature={temperature}: "
                                  f"passed={passed}; {content!r}", flush=True)
                        if any(not c["passed"] for c in profile["checks"] if c["strict"]):
                            raise AssertionError("Strict multilingual check failed")
                        response = request(base, "/completion", {"prompt": "Write a short message.",
                            "n_predict": 4, "ignore_eos": True, "cache_prompt": False,
                            "temperature": 0, "seed": 1234, "return_tokens": True,
                            "logit_bias": [[outside, 1000.0]]})
                        passed = response["tokens"] == [outside] * 4
                        profile["checks"].append({"name": "target-can-emit-token-outside-draft-subset",
                            "forced_token_id": outside, "passed": passed, "response": response})
                        if not passed:
                            raise AssertionError("Target output was limited by the draft vocabulary")
                    finally:
                        if monitor:
                            profile["memory"] = monitor.finish()
                        if process and process.poll() is None:
                            process.terminate()
                            try:
                                process.wait(timeout=10)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait()
                if mode != "off" and "using draft vocabulary graph (106299 output rows)" not in (folder / (name + ".log")).read_text():
                    raise AssertionError("Subset graph never activated")
                if profile.get("memory", {}).get("guard"):
                    raise AssertionError("Memory guard stopped feature check")
            record["status"] = "passed"
        except BaseException as error:
            record.update(status="failed", error=f"{type(error).__name__}: {error}")
            raise
        finally:
            (folder / "checks.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
            print(f"Saved {folder}", flush=True)


if __name__ == "__main__":
    main()
