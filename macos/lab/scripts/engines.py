"""Select an isolated native engine and verify its source/build provenance."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from typing import NamedTuple, NotRequired, TypedDict, cast
import subprocess

from lab import ROOT

OTOOL = "/usr/bin/otool"
# macOS serves these from the dyld shared cache; the OS version, not the lab, owns them.
SYSTEM_LIBRARY_PREFIXES = ("/usr/lib/", "/System/Library/")
DYLIB_LOADS = frozenset(
    {"LC_LOAD_DYLIB", "LC_LOAD_WEAK_DYLIB", "LC_REEXPORT_DYLIB", "LC_LOAD_UPWARD_DYLIB", "LC_LAZY_LOAD_DYLIB"}
)
OFFSET_SUFFIX = re.compile(r"^(?P<value>.+) \(offset \d+\)$")
# provision.py --local-http-only builds the baseline without OpenSSL; preparers repeat that choice.
LOCAL_HTTP_ONLY_FLAG = "-DLLAMA_OPENSSL=OFF"

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
    "m5-segments": "m5_segments_experiment.json",
    "m5-overlap": "m5_overlap_experiment.json",
    "m5-advise": "m5_advise_experiment.json",
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


class ExternalLibrary(TypedDict):
    """A non-system dylib the server loads from outside its build directory."""

    path: str
    install_names: list[str]
    sha256: str
    versions: dict[str, str]


class MachOLinks(NamedTuple):
    identity_versions: dict[str, str]
    loads: list[str]
    rpaths: list[str]


class BuildReceipt(EngineSource):
    artifacts: dict[str, str]
    external_libraries: list[ExternalLibrary]
    binary_version: str
    build_settings: dict[str, str]
    compiler: str


class StoredBuildReceipt(EngineSource):
    artifacts: dict[str, str]
    # Receipts written before external libraries were recorded have no such field.
    external_libraries: NotRequired[list[ExternalLibrary]]
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


def baseline_build_flags(flags: list[str], root: Path = ROOT) -> list[str]:
    """Runtime build flags plus the baseline's local-HTTP-only choice, so engine preparers link the same way."""
    cache = root / "vendor/llama.cpp/build/CMakeCache.txt"
    disabled = cache.is_file() and "LLAMA_OPENSSL:BOOL=OFF" in cache.read_text().splitlines()
    return [*flags, LOCAL_HTTP_ONLY_FLAG] if disabled and LOCAL_HTTP_ONLY_FLAG not in flags else list(flags)


def mach_o_links(path: Path) -> MachOLinks:
    """The dylib loads, own install-name versions and run paths that `otool -l` reports for one file."""
    commands: list[dict[str, str]] = []
    for line in subprocess.check_output([OTOOL, "-l", str(path)], text=True).splitlines():
        if line.startswith("Load command "):
            commands.append({})
        elif commands:
            key, _, value = line.strip().partition(" ")
            match = OFFSET_SUFFIX.match(value)
            commands[-1][key] = match["value"] if match else value.removeprefix("version ")
    identity = next((command for command in commands if command.get("cmd") == "LC_ID_DYLIB"), {})
    return MachOLinks(
        {key: identity[key] for key in ("current", "compatibility") if key in identity},
        [command["name"] for command in commands if command.get("cmd") in DYLIB_LOADS],
        [command["path"] for command in commands if command.get("cmd") == "LC_RPATH"],
    )


def _expand(path: str, loader: Path, executable: Path) -> Path:
    for token, base in (("@loader_path", loader.parent), ("@executable_path", executable.parent)):
        if path == token or path.startswith(token + "/"):
            return base / path[len(token) :].lstrip("/")
    return Path(path)


def _resolve_load(name: str, loader: Path, executable: Path, rpaths: tuple[Path, ...]) -> Path:
    """Follow dyld's @rpath/@loader_path/@executable_path expansion to the file that would load."""
    if name.startswith("@rpath/"):
        candidates = [rpath / name.removeprefix("@rpath/") for rpath in rpaths]
    else:
        candidates = [_expand(name, loader, executable)]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise RuntimeError(f"Missing native library {name}, loaded by {loader}")


def _refuse_duplicate_libraries(libraries: list[ExternalLibrary]) -> None:
    names = Counter(Path(library["path"]).name for library in libraries)
    duplicated = sorted(name for name, count in names.items() if count > 1)
    if duplicated:
        raise RuntimeError(f"Different external files provide the same native library: {', '.join(duplicated)}")


def _note_library(found: dict[Path, ExternalLibrary], target: Path, name: str, build: Path) -> None:
    """Record one install name of a library outside the build directory, hashing each file once."""
    if target.parent == build:
        return
    if target not in found:
        found[target] = {"path": str(target), "install_names": [], "sha256": sha256(target), "versions": {}}
    if name not in found[target]["install_names"]:
        found[target]["install_names"].append(name)


def external_libraries(binary: Path) -> list[ExternalLibrary]:
    """The non-system dylib closure the server loads from outside its build directory.

    Files inside the build directory are already hashed as artifacts. Install names that reach the same file
    through a symlink are one library; system libraries are ignored.
    """
    executable = binary.resolve()
    pending: list[tuple[Path, tuple[Path, ...]]] = [(executable, ())]
    seen = {executable}
    found: dict[Path, ExternalLibrary] = {}
    while pending:
        loader, inherited = pending.pop()
        links = mach_o_links(loader)
        if loader in found:
            found[loader]["versions"] = links.identity_versions
        # dyld searches the loading image's run paths, then those of the images that loaded it.
        rpaths = (*(_expand(path, loader, executable) for path in links.rpaths), *inherited)
        for name in links.loads:
            if name.startswith(SYSTEM_LIBRARY_PREFIXES):
                continue
            target = _resolve_load(name, loader, executable, rpaths)
            _note_library(found, target, name, executable.parent)
            if target not in seen:
                seen.add(target)
                pending.append((target, rpaths))
    libraries = [found[path] for path in sorted(found)]
    for library in libraries:
        library["install_names"].sort()
    _refuse_duplicate_libraries(libraries)
    return libraries


def verify_external_libraries(engine: str, recorded: list[ExternalLibrary], binary: Path) -> None:
    """Refuse an engine whose recorded external dylibs changed, disappeared or appeared."""
    paths = [library["path"] for library in recorded]
    if len(set(paths)) != len(paths):
        raise RuntimeError(f"Build receipt lists an external native library more than once: {engine}")
    try:
        current = external_libraries(binary)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        raise RuntimeError(f"External native libraries changed since the build receipt: {engine}: {error}") from error
    if current != recorded:
        before = {library["path"]: library for library in recorded}
        after = {library["path"]: library for library in current}
        changed = sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path))
        raise RuntimeError(f"External native libraries changed since the build receipt: {engine}: {', '.join(changed)}")


def external_library_status(engine: VerifiedEngine) -> str:
    """How verify_engine treated external dylibs; legacy receipts are accepted without that record."""
    receipt = engine.get("build_receipt")
    if receipt is None:
        return "not checked: no build receipt"
    if "external_libraries" not in receipt:
        return "unrecorded: the build receipt predates external library records"
    count = len(receipt["external_libraries"])
    return f"verified: {count} external {'library' if count == 1 else 'libraries'} unchanged"


def write_receipt(engine: str) -> BuildReceipt:
    info = source_info(engine)
    binary = engine_binary(engine)
    if not binary.is_file():
        raise RuntimeError(f"Native engine is not built: {binary}")
    artifacts = artifact_hashes(binary.parent)
    libraries = external_libraries(binary)
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
        "LLAMA_OPENSSL",
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
        "external_libraries": libraries,
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
        # Older receipts have no external library record; they stay accepted and are never rewritten here.
        if "external_libraries" in saved:
            verify_external_libraries(engine, saved["external_libraries"], binary)
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
