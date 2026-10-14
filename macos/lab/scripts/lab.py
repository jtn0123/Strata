"""Shared local runtime settings and HTTP calls. No cloud inference."""

import json
from pathlib import Path
from typing import NamedTuple, NotRequired, TypedDict, Unpack, cast
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "vendor/llama.cpp/build/bin/llama-server"


class ModelFile(TypedDict):
    path: str
    size_bytes: int
    sha256: str


class ModelDerivation(TypedDict, total=False):
    required_engine: str


class ModelSettings(TypedDict):
    files: list[ModelFile]
    derived: NotRequired[ModelDerivation]


class DraftSettings(NamedTuple):
    model: str
    placement: str
    engine: str
    threads: int | None
    minimum_probability: float | None


class DraftTuning(TypedDict, total=False):
    draft_threads: int | None
    draft_p_min: float | None


def _draft_tuning(options: DraftTuning) -> tuple[int | None, float | None]:
    """Bind the two optional helper settings while rejecting unsupported names."""
    for name in options:
        if name not in ("draft_threads", "draft_p_min"):
            raise TypeError(f"server_command() got an unexpected keyword argument {name!r}")
    return options.get("draft_threads"), options.get("draft_p_min")


def model_settings(model_id: str) -> ModelSettings:
    # This is the revision-controlled model registry boundary; retain all metadata.
    registry = cast(dict[str, ModelSettings], json.loads((ROOT / "config/models.json").read_text()))
    return registry[model_id]


def model_path(model_id: str) -> Path:
    model = model_settings(model_id)
    paths = [ROOT / "models" / model_id / spec["path"] for spec in model["files"]]
    if not all(path.is_file() for path in paths):
        raise FileNotFoundError(f"Download and verify {model_id} first: scripts/download_models.py {model_id}")
    return paths[0]


def _helper_threads(threads: int | None) -> list[str]:
    if threads is None:
        return []
    if threads < 1:
        raise ValueError("Use at least one helper CPU thread")
    return ["--spec-draft-threads", str(threads), "--spec-draft-threads-batch", str(threads)]


def _draft_command(model_id: str, settings: DraftSettings) -> list[str]:
    from engines import supports_feature

    if model_id != "flash":
        raise ValueError("The lab MTP head is only compatible with Flash-Next")
    required = model_settings(settings.model).get("derived", {}).get("required_engine")
    if required and not supports_feature(settings.engine, required):
        raise ValueError(f"{settings.model} requires the {required} engine")
    if settings.placement == "mixed" and settings.model != "mtp_shared_packed_q3":
        raise ValueError("Mixed placement requires the packed shared helper")
    command = []
    if supports_feature(settings.engine, "m5-draftcap"):
        command.extend(["--spec-draft-n-min", "0", "--spec-draft-sampling", "greedy"])
    layers = {"gpu": "all", "cpu": "0", "output": "1", "mixed": "all"}[settings.placement]
    command.extend(["-md", str(model_path(settings.model)), "--spec-draft-ngl", layers])
    if settings.placement == "mixed":
        command.extend(["--spec-draft-cpu-moe", "--no-op-offload"])
    command.extend(_helper_threads(settings.threads))
    if settings.minimum_probability is not None:
        command.extend(["--spec-draft-p-min", str(settings.minimum_probability)])
    return command


def server_command(
    model_id: str,
    port: int = 8096,
    context: int = 4096,
    batch: int = 512,
    ubatch: int = 128,
    spec: str = "none",
    draft: int = 3,
    cache_type: str = "f16",
    threads: int = 8,
    draft_placement: str = "gpu",
    draft_model: str = "mtp",
    engine: str = "baseline",
    **draft_tuning: Unpack[DraftTuning],
) -> list[str]:
    draft_threads, draft_p_min = _draft_tuning(draft_tuning)
    from engines import engine_binary
    from metal_environment import validate_confidence

    validate_confidence(draft_p_min)
    if draft_p_min is not None and spec != "draft-mtp":
        raise ValueError("Draft confidence requires prediction enabled")
    command = [
        str(engine_binary(engine)),
        "-m",
        str(model_path(model_id)),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "-c",
        str(context),
        "-b",
        str(batch),
        "-ub",
        str(ubatch),
        "-t",
        str(threads),
        "-tb",
        str(threads),
        "-ngl",
        "all",
        "-fit",
        "off",
        "-fa",
        "on",
        "-lm",
        "mmap",
        "-lzm",
        "on",
        "-np",
        "1",
        "-ctk",
        cache_type,
        "-ctv",
        cache_type,
        "--cache-ram",
        "0",
        "--spec-type",
        spec,
        "--spec-draft-n-max",
        str(draft),
        "--metrics",
        "--jinja",
        "--no-webui",
        "--alias",
        model_id,
        "--verbosity",
        "4",
        "--cors-origins",
        "localhost",
    ]
    if spec == "draft-mtp":
        settings = DraftSettings(draft_model, draft_placement, engine, draft_threads, draft_p_min)
        command.extend(_draft_command(model_id, settings))
    elif draft_threads is not None:
        raise ValueError("Helper CPU threads require prediction enabled")
    return command


def request(base: str, endpoint: str, payload: object = None, timeout: float = 600) -> dict[str, object]:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(base + endpoint, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            # Endpoints return JSON objects. Their callers retain endpoint-specific
            # schema validation and the original errors for malformed replies.
            return cast(dict[str, object], json.load(response))
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"HTTP {error.code} {endpoint}: {error.read().decode()}") from error
