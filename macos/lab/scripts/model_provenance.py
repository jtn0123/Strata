"""Verify GGUF bytes once per file identity; record exact inputs without rereading warm models."""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from collections.abc import Iterable
from typing import TypedDict

from lab import ROOT


class FileIdentity(TypedDict):
    device: int
    inode: int
    size: int
    mtime_ns: int
    ctime_ns: int


class ModelFileSpec(TypedDict):
    path: str
    size_bytes: int
    sha256: str


class ModelRegistryEntry(TypedDict):
    files: list[ModelFileSpec]


class CachedFile(TypedDict):
    path: str
    identity: FileIdentity
    sha256: str


class VerifiedFile(CachedFile):
    hash_scan_performed: bool


class ModelCache(TypedDict):
    schema: int
    files: dict[str, CachedFile]


class VerifiedModel(TypedDict):
    registry: ModelRegistryEntry
    files: list[VerifiedFile]
    routing_geometry: dict[str, object] | None


class ModelVerification(TypedDict):
    models: dict[str, VerifiedModel]
    hash_io_policy: str


def identity(path: Path) -> FileIdentity:
    st = path.stat()
    return {
        "device": st.st_dev,
        "inode": st.st_ino,
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "ctime_ns": st.st_ctime_ns,
    }


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb", buffering=0) as stream:
        if sys.platform == "darwin":
            fcntl.fcntl(
                stream.fileno(), 48, 1
            )  # F_NOCACHE: avoid populating the model page cache.
        while chunk := stream.read(16 * 1024**2):
            digest.update(chunk)
    return digest.hexdigest()


def geometry(model_id: str, path: Path) -> dict[str, object] | None:
    if model_id not in ("flash", "mtp_shared_packed_q3"):
        return None
    from inspect_gguf import HeaderReader

    reader = HeaderReader(path)
    keys = (
        "general.architecture",
        "qwen4exp.block_count",
        "qwen4exp.embedding_length",
        "qwen4exp.expert_count",
        "qwen4exp.expert_used_count",
    )
    observed: dict[str, object] = {k: reader.fields[k].contents() for k in keys}
    expected = dict(
        zip(
            keys,
            ("qwen4exp", 48 if model_id == "flash" else 49, 2560, 512, 10),
            strict=True,
        )
    )
    if observed != expected:
        raise RuntimeError(f"Unexpected routing geometry for {model_id}: {observed}")
    if model_id == "mtp_shared_packed_q3":
        layers = {
            int(t["name"].split(".")[1])
            for t in reader.inventory
            if t["name"].startswith("blk.")
        }
        if (
            layers != {48}
            or reader.fields["qwen4exp.nextn_predict_layers"].contents() != 1
        ):
            raise RuntimeError(
                "Helper does not contain precisely the layer48 prediction block"
            )
    return observed


def verify_models(model_ids: Iterable[str], root: Path = ROOT) -> ModelVerification:
    registry: dict[str, ModelRegistryEntry] = json.loads(
        (root / "config/models.json").read_text()
    )
    cache_path = root / "bench/runtime/model-verification.json"
    cache: ModelCache = (
        json.loads(cache_path.read_text())
        if cache_path.exists()
        else {"schema": 1, "files": {}}
    )
    result: dict[str, VerifiedModel] = {}
    for name in model_ids:
        model = registry[name]
        files: list[VerifiedFile] = []
        for spec in model["files"]:
            path = root / "models" / name / spec["path"]
            key = str(path.relative_to(root))
            before = identity(path)
            if before["size"] != spec["size_bytes"]:
                raise RuntimeError(f"Model size differs: {key}")
            previous = cache["files"].get(key)
            reused = bool(
                previous
                and previous["identity"] == before
                and previous["sha256"] == spec["sha256"]
            )
            actual = (
                previous["sha256"]
                if previous is not None and reused
                else file_digest(path)
            )
            if actual != spec["sha256"]:
                raise RuntimeError(f"Model SHA256 differs: {key}")
            if identity(path) != before:
                raise RuntimeError(f"Model changed during verification: {key}")
            entry: CachedFile = {"path": key, "identity": before, "sha256": actual}
            cache["files"][key] = entry
            files.append({**entry, "hash_scan_performed": not reused})
        observed_geometry = geometry(name, root / files[0]["path"])
        if any(identity(root / f["path"]) != f["identity"] for f in files):
            raise RuntimeError(f"Model changed while reading geometry: {name}")
        result[name] = {
            "registry": model,
            "files": files,
            "routing_geometry": observed_geometry,
        }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=cache_path.parent,
            prefix=cache_path.name + ".",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(cache, indent=2) + "\n")
        os.replace(temporary, cache_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {
        "models": result,
        "hash_io_policy": "Initial or changed files: bounded reads with macOS F_NOCACHE outside measurements. Cached verification uses identity/size/mtime/ctime; not protection against adversarial modification. Headers are read; cache state remains uncontrolled.",
    }


def assert_unchanged(receipt: ModelVerification, root: Path = ROOT) -> None:
    registry: dict[str, ModelRegistryEntry] = json.loads(
        (root / "config/models.json").read_text()
    )
    for name, model in receipt["models"].items():
        if registry[name] != model["registry"]:
            raise RuntimeError(f"Model registry changed: {name}")
        for f in model["files"]:
            if identity(root / f["path"]) != f["identity"]:
                raise RuntimeError(f"Verified model changed: {f['path']}")
