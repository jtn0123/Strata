"""Select an isolated native engine and verify its source/build provenance."""

import hashlib
import json
from pathlib import Path
from typing import NotRequired, TypedDict, cast
import subprocess

from lab import ROOT

EXPERIMENTS = {
    "q2-masked": "q2_experiment.json",
    "draft-vocab": "draft_vocab_experiment.json",
    "mtp-shared": "mtp_shared_experiment.json",
    "mtp-mma": "mtp_mma_experiment.json",
    "m5-lab": "m5_lab_experiment.json",
    "m5-trace": "m5_trace_experiment.json",
    "m5-correctness": "m5_correctness_experiment.json",
    "m5-copy": "m5_copy_experiment.json",
    "m5-reduce": "m5_reduce_experiment.json",
    "m5-sampling": "m5_sampling_experiment.json",
    "m5-hc": "m5_hc_experiment.json",
    "m5-group": "m5_group_experiment.json",
    "m5-gate": "m5_gate_experiment.json",
    "m5-gdn": "m5_gdn_experiment.json",
    "m5-lookup": "m5_lookup_experiment.json",
    "m5-gate-lanes": "m5_gate_lanes_experiment.json",
    "m5-encoders": "m5_encoders_experiment.json",
    "m5-head": "m5_head_experiment.json",
    "m5-embedding": "m5_embedding_experiment.json",
    "m5-draftcap": "m5_draftcap_experiment.json",
    "m5-top10": "m5_top10_experiment.json",
    "m5-qsa": "m5_qsa_experiment.json",
    "m5-route-map": "m5_route_map_experiment.json",
    "m5-compact": "m5_compact_experiment.json",
    "m5-compact-cols": "m5_compact_cols_experiment.json",
    "m5-small-stack": "m5_small_stack_experiment.json",
    "m5-waits": "m5_waits_experiment.json",
}
ENGINES = ("baseline", *EXPERIMENTS)


class RevisionPin(TypedDict):
    revision: str


class RuntimeSettings(TypedDict):
    llama_cpp: RevisionPin


class ExperimentManifest(TypedDict):
    base_revision: str
    directory: str
    patch: str
    patch_sha256: str
    source_diff_sha256: str
    modified_files: list[str]
    features: NotRequired[list[str]]


class EngineSource(TypedDict):
    engine: str
    directory: str
    revision: str
    source_diff_sha256: str
    patch: ExperimentManifest | None


class BuildReceipt(EngineSource):
    artifacts: dict[str, str]
    binary_version: str
    build_settings: dict[str, str]
    compiler: str


class StoredBuildReceipt(EngineSource):
    artifacts: dict[str, str]
    binary_version: NotRequired[str]
    build_settings: NotRequired[dict[str, str]]
    compiler: NotRequired[str]


class VerifiedEngine(EngineSource):
    artifacts: dict[str, str]
    build_receipt: NotRequired[StoredBuildReceipt]


def experiment_manifest(engine: str, root: Path = ROOT) -> ExperimentManifest:
    # The pinned manifest is a configuration boundary; keep its additional fields.
    return cast(ExperimentManifest, json.loads((root / "config" / EXPERIMENTS[engine]).read_text()))


def supports_feature(engine: str, feature: str, root: Path = ROOT) -> bool:
    if engine == feature:
        return True
    if engine not in EXPERIMENTS:
        return False
    manifest = experiment_manifest(engine, root)
    return feature in manifest.get("features", [])


def sha256(path: Path | str) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git(path: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(path), *args]).strip()


def _verified_source_diff(path: Path, directory: str, revision: str, manifest: ExperimentManifest | None) -> bytes:
    """Validate the pinned checkout before its diff can become receipt evidence."""
    if git(path, "rev-parse", "HEAD").decode() != revision:
        raise RuntimeError(f"Unpinned native checkout: {directory}")
    status = git(path, "status", "--porcelain", "--untracked-files=all").decode()
    diff = subprocess.check_output(["git", "-C", str(path), "diff", "HEAD", "--binary"])
    if manifest:
        expected_status = "\n".join(f" M {name}" for name in manifest["modified_files"])
        if status.strip() != expected_status.strip() or git(path, "diff", "--cached"):
            raise RuntimeError("Candidate contains changes beyond the experiment patch")
        if hashlib.sha256(diff).hexdigest() != manifest["source_diff_sha256"]:
            raise RuntimeError("Candidate source diff differs from the experiment patch")
    elif status or diff:
        raise RuntimeError("Baseline native checkout must remain unmodified")
    return diff


def source_info(engine: str, root: Path = ROOT) -> EngineSource:
    runtime = cast(RuntimeSettings, json.loads((root / "config/runtime.json").read_text()))
    revision = runtime["llama_cpp"]["revision"]
    if engine == "baseline":
        directory = "vendor/llama.cpp"
        manifest = None
    elif engine in EXPERIMENTS:
        manifest = experiment_manifest(engine, root)
        directory = manifest["directory"]
        if manifest["base_revision"] != revision:
            raise RuntimeError(f"{engine} experiment does not match the pinned baseline")
        if sha256(root / manifest["patch"]) != manifest["patch_sha256"]:
            raise RuntimeError(f"{engine} patch hash differs from the experiment manifest")
    else:
        raise ValueError(f"Unknown engine: {engine}")
    diff = _verified_source_diff(root / directory, directory, revision, manifest)
    return {
        "engine": engine,
        "directory": directory,
        "revision": revision,
        "source_diff_sha256": hashlib.sha256(diff).hexdigest(),
        "patch": manifest,
    }


def engine_binary(engine: str, root: Path = ROOT) -> Path:
    if engine not in ENGINES:
        raise ValueError(f"Unknown engine: {engine}")
    directory = "vendor/llama.cpp" if engine == "baseline" else experiment_manifest(engine, root)["directory"]
    return root / directory / "build/bin/llama-server"


def artifact_hashes(path: Path) -> dict[str, str]:
    files = [path / "llama-server", *sorted(path.glob("*.dylib"))]
    return {file.name: sha256(file) for file in files}


def write_receipt(engine: str) -> BuildReceipt:
    info = source_info(engine)
    binary = engine_binary(engine)
    if not binary.is_file():
        raise RuntimeError(f"Native engine is not built: {binary}")
    artifacts = artifact_hashes(binary.parent)
    binary_version = subprocess.check_output([str(binary), "--version"], text=True, stderr=subprocess.STDOUT).strip()
    cache = binary.parent.parent / "CMakeCache.txt"
    keys = (
        "CMAKE_BUILD_TYPE",
        "GGML_METAL",
        "GGML_METAL_EMBED_LIBRARY",
        "LLAMA_BUILD_TESTS",
        "LLAMA_BUILD_TOOLS",
        "GGML_CPU",
        "GGML_BLAS",
        "GGML_NATIVE",
        "GGML_METAL_USE_BF16",
    )
    build_settings = {
        line.split(":", 1)[0]: line.split("=", 1)[1]
        for line in cache.read_text().splitlines()
        if any(line.startswith(key + ":") for key in keys)
    }
    compiler = subprocess.check_output(["clang", "--version"], text=True).strip()
    receipt: BuildReceipt = {
        **info,
        "artifacts": artifacts,
        "binary_version": binary_version,
        "build_settings": build_settings,
        "compiler": compiler,
    }
    path = ROOT / info["directory"] / "build/lab-receipt.json"
    path.write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def verify_engine(engine: str, root: Path = ROOT, require_receipt: bool = True) -> VerifiedEngine:
    info = source_info(engine, root)
    binary = engine_binary(engine, root)
    if not binary.is_file():
        raise RuntimeError(f"Native engine is not built: {binary}")
    hashes = artifact_hashes(binary.parent)
    receipt = binary.parent.parent / "lab-receipt.json"
    if require_receipt or receipt.exists():
        saved = cast(StoredBuildReceipt, json.loads(receipt.read_text()))
        if any(saved.get(key) != value for key, value in info.items()) or saved["artifacts"] != hashes:
            raise RuntimeError(f"Source or native binaries changed since the build receipt: {engine}")
    result: VerifiedEngine = {
        "engine": info["engine"],
        "directory": info["directory"],
        "revision": info["revision"],
        "source_diff_sha256": info["source_diff_sha256"],
        "patch": info["patch"],
        "artifacts": hashes,
    }
    if receipt.exists():
        result["build_receipt"] = cast(StoredBuildReceipt, json.loads(receipt.read_text()))
    return result
