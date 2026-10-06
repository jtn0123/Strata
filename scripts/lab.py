"""Shared local runtime settings and HTTP calls. No cloud inference."""
import json
from pathlib import Path
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "vendor/llama.cpp/build/bin/llama-server"


def model_path(model_id):
    model = json.loads((ROOT / "config/models.json").read_text())[model_id]
    paths = [ROOT / "models" / model_id / f["path"] for f in model["files"]]
    if not all(p.is_file() for p in paths):
        raise FileNotFoundError(f"Download and verify {model_id} first: scripts/download_models.py {model_id}")
    return paths[0]


def server_command(model_id, port=8096, context=4096, batch=512, ubatch=128,
                   spec="none", draft=3, cache_type="f16", threads=8, draft_placement="gpu",
                   draft_model="mtp", engine="baseline", draft_threads=None):
    from engines import engine_binary
    command = [str(engine_binary(engine)), "-m", str(model_path(model_id)), "--host", "127.0.0.1",
               "--port", str(port), "-c", str(context), "-b", str(batch), "-ub", str(ubatch),
               "-t", str(threads), "-tb", str(threads), "-ngl", "all", "-fit", "off",
               "-fa", "on", "-lm", "mmap", "-lzm", "on", "-np", "1",
               "-ctk", cache_type, "-ctv", cache_type, "--cache-ram", "0",
               "--spec-type", spec, "--spec-draft-n-max", str(draft),
               "--metrics", "--jinja", "--no-webui", "--alias", model_id,
               "--verbosity", "4", "--cors-origins", "localhost"]
    if spec == "draft-mtp":
        if model_id != "flash":
            raise ValueError("The lab MTP head is only compatible with Flash-Next")
        draft_spec = json.loads((ROOT / "config/models.json").read_text())[draft_model]
        required = draft_spec.get("derived", {}).get("required_engine")
        if required and engine != required:
            raise ValueError(f"{draft_model} requires the {required} engine")
        if draft_placement == "mixed" and draft_model != "mtp_shared_packed_q3":
            raise ValueError("Mixed placement requires the packed shared helper")
        layers = {"gpu": "all", "cpu": "0", "output": "1", "mixed": "all"}[draft_placement]
        command.extend(["-md", str(model_path(draft_model)), "--spec-draft-ngl", layers])
        if draft_placement == "mixed":
            command.extend(["--spec-draft-cpu-moe", "--no-op-offload"])
        if draft_threads is not None:
            if draft_threads < 1:
                raise ValueError("Use at least one helper CPU thread")
            command.extend(["--spec-draft-threads", str(draft_threads),
                            "--spec-draft-threads-batch", str(draft_threads)])
    elif draft_threads is not None:
        raise ValueError("Helper CPU threads require prediction enabled")
    return command


def request(base, endpoint, payload=None, timeout=600):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(base + endpoint, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"HTTP {error.code} {endpoint}: {error.read().decode()}") from error
