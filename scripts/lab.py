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
                   spec="none", draft=3, cache_type="f16", threads=8, draft_placement="gpu"):
    command = [str(BIN), "-m", str(model_path(model_id)), "--host", "127.0.0.1",
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
        command.extend(["-md", str(model_path("mtp")), "--spec-draft-ngl", "all" if draft_placement == "gpu" else "0"])
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
