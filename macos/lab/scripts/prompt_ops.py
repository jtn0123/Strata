"""Parse N00 native logs: encoded Metal dispatches with shapes and fusion, and command-buffer GPU intervals.

Graph-debug lines come from the pinned encoder (`ggml_metal_op_encode_impl`) at verbosity 5. One dispatch is one
encoded kernel; its `fuse N ops` line says how many graph nodes it covers. Node indexes count only nodes that hold
data, so any other gap is a node the encoder skipped without compute. The launch-wide fusion statistics are kept as
printed, but the pinned encoder records each MoE-reduce fusion twice, so the per-dispatch lines are the count used.
Command-buffer intervals are GPU elapsed time for a range of nodes, not the cost of any one kernel.
"""

from collections import Counter
from collections.abc import Iterable, Sequence
import hashlib
import json
import math
import re
import statistics
from typing import TypedDict, cast

NODE = re.compile(r"ggml_metal_op_encode_impl: node\[ *(\d+)\] - (\S+) +(\S.*)?$")
TENSOR = re.compile(r"ggml_metal_op_encode_impl: (src\d|node) - \s*(\S+) \[([^\]]*)\] \[[^\]]*\], [01], ")
FUSE = re.compile(r"ggml_metal_op_encode_impl:\s+fuse (\d+) ops$")
FUSION = re.compile(r"ggml_metal_free: - (\S+): (\d+)$")
LAYER = re.compile(r"-(\d+)$")
PROFILE = "M5_PROFILE "
METADATA = {"NONE", "VIEW", "RESHAPE", "PERMUTE", "TRANSPOSE"}


class Tensor(TypedDict):
    type: str
    shape: list[int]


class Dispatch(TypedDict):
    index: int
    op: str
    name: str
    concurrent: bool
    fused: int
    sources: list[Tensor]
    output: Tensor | None


class Graph(TypedDict):
    dispatches: list[Dispatch]
    noops: int
    unencoded: int


class GraphLabel(TypedDict):
    role: str
    chunk: int
    tokens: int


class Buffer(TypedDict):
    context: str
    graph: int
    cb: int
    original_nodes: int
    gpu_start_s: float
    gpu_end_s: float
    gpu_ms: float


class GraphTime(TypedDict):
    context: str
    graph: int
    buffers_ms: list[float]
    start_s: float
    end_s: float
    gpu_ms: float
    original_nodes: int


class ChunkTime(TypedDict):
    tokens: int
    gpu_ms: float
    ms_per_token: float
    buffers_ms: list[float]
    helper_ms: float


class RequestGPU(TypedDict):
    chunks: list[ChunkTime]


class _Reader:
    """Log-order state: the open graph, the last logged node index and the dispatch tensor lines belong to."""

    def __init__(self) -> None:
        self.graphs: list[Graph] = []
        self.last = -1
        self.dispatch: Dispatch | None = None

    def node(self, index: int, op: str, rest: str) -> None:
        if index <= self.last or not self.graphs:
            self.graphs.append({"dispatches": [], "noops": 0, "unencoded": index})
        else:
            gap = index - self.last - 1
            fused = self.dispatch["fused"] if self.dispatch else 0
            if gap < fused:
                raise ValueError("Fused nodes exceed the node-index gap")
            self.graphs[-1]["unencoded"] += gap - fused
        self.dispatch = None
        self.last = index
        if rest == "(noop)":
            self.graphs[-1]["noops"] += 1
            return
        concurrent = rest.endswith("(concurrent)")
        name = rest.removesuffix("(concurrent)").rstrip()
        dispatch: Dispatch = {
            "index": index,
            "op": op,
            "name": name,
            "concurrent": concurrent,
            "fused": 0,
            "sources": [],
            "output": None,
        }
        self.dispatch = dispatch
        self.graphs[-1]["dispatches"].append(dispatch)

    def tensor(self, role: str, kind: str, shape: str) -> None:
        if self.dispatch is None:
            raise ValueError("Tensor line without an encoded dispatch")
        tensor: Tensor = {
            "type": kind,
            "shape": [int(value) for value in shape.split(",")],
        }
        if role == "node":
            self.dispatch["output"] = tensor
        else:
            self.dispatch["sources"].append(tensor)

    def fuse(self, count: int) -> None:
        if self.dispatch is None:
            raise ValueError("Fusion line without an encoded dispatch")
        self.dispatch["fused"] = count - 1


def dispatch_graphs(lines: Iterable[str]) -> list[Graph]:
    """Encoded graphs in log order; a node index that does not increase starts the next graph."""
    reader = _Reader()
    for line in lines:
        if node := NODE.search(line):
            reader.node(int(node[1]), node[2], (node[3] or "").rstrip())
        elif tensor := TENSOR.search(line):
            reader.tensor(tensor[1], tensor[2], tensor[3])
        elif fuse := FUSE.search(line):
            reader.fuse(int(fuse[1]))
    return reader.graphs


def fusion_counts(lines: Iterable[str]) -> dict[str, int]:
    """Launch-wide fused patterns printed when the Metal context is freed."""
    return {match[1]: int(match[2]) for line in lines if (match := FUSION.search(line))}


def tensor_key(tensor: Tensor) -> str:
    return f"{tensor['type']}{tensor['shape']}"


def shape_key(dispatch: Dispatch) -> str:
    sources = " ".join(tensor_key(source) for source in dispatch["sources"])
    output = tensor_key(dispatch["output"]) if dispatch["output"] else "-"
    return f"{dispatch['op']} {sources} -> {output}"


def graph_layers(graph: Graph) -> int:
    """Distinct layer suffixes (`-N`) in dispatch names."""
    return len({match[1] for dispatch in graph["dispatches"] if (match := LAYER.search(dispatch["name"]))})


def label_graphs(graphs: Sequence[Graph], schedule: Sequence[int]) -> list[GraphLabel]:
    """Each target graph (the most layers) reads the next scheduled batch; helper graphs after it read the same batch.

    Rows cannot be read from one graph alone: hidden states here are [width, streams, tokens], so a one-token graph
    and a batch as wide as the stream count look alike. The first dispatch's output must still include the
    scheduled row count, which catches a schedule that does not match the log.
    """
    layers = [graph_layers(graph) for graph in graphs]
    most = max(layers, default=0)
    targets = {i for i, count in enumerate(layers) if count == most} if graphs else set()
    if len(targets) != len(schedule):
        raise ValueError(f"Expected {len(schedule)} target graphs, found {len(targets)}")
    if graphs and 0 not in targets:
        raise ValueError("Helper graph before the first target graph")
    labels: list[GraphLabel] = []
    chunk = -1
    for i, graph in enumerate(graphs):
        if i in targets:
            chunk += 1
        tokens = schedule[chunk]
        first = graph["dispatches"][0]["output"] if graph["dispatches"] else None
        if first is None or tokens not in first["shape"][1:]:
            raise ValueError(f"Graph {i} does not read {tokens} rows")
        labels.append({"role": "target" if i in targets else "helper", "chunk": chunk, "tokens": tokens})
    return labels


def summarize(graph: Graph) -> dict[str, object]:
    dispatches = graph["dispatches"]
    fused: Counter[str] = Counter()
    for dispatch in dispatches:
        fused[dispatch["op"]] += dispatch["fused"]
    shapes = [shape_key(dispatch) for dispatch in dispatches]
    return {
        "layers": graph_layers(graph),
        "dispatches": len(dispatches),
        "barriers": sum(not dispatch["concurrent"] for dispatch in dispatches),
        "fused_nodes": sum(fused.values()),
        "unencoded_nodes": graph["unencoded"],
        "noops": graph["noops"],
        "by_op": dict(Counter(dispatch["op"] for dispatch in dispatches).most_common()),
        "fused_by_leader_op": {op: count for op, count in fused.most_common() if count},
        "by_shape": dict(Counter(shapes).most_common()),
        "signature": hashlib.sha256(json.dumps(shapes).encode()).hexdigest(),
    }


def inventory(graphs: Sequence[Graph], labels: Sequence[GraphLabel]) -> list[dict[str, object]]:
    """Distinct graph inventories in first-seen order, with the scheduled chunks (0 is warm-up) that encoded each."""
    distinct: dict[tuple[str, int, str], dict[str, object]] = {}
    for graph, label in zip(graphs, labels, strict=True):
        summary = summarize(graph)
        key = (label["role"], label["tokens"], cast(str, summary["signature"]))
        entry = distinct.setdefault(key, {"role": label["role"], "tokens": label["tokens"], **summary, "chunks": []})
        cast(list[int], entry["chunks"]).append(label["chunk"])
    return list(distinct.values())


def timed_buffer(record: dict[str, object]) -> Buffer | None:
    """One timed buffer; an untimed buffer is dropped only when it holds metadata operations alone."""
    counts = cast(dict[str, int], record.get("op_counts", {}))
    if record.get("valid") is not True:
        if record.get("completed") and set(counts) <= METADATA and record.get("gpu_ms") == 0:
            return None
        raise ValueError("Untimed computational GPU buffer: cost coverage is incomplete")
    start, end, elapsed = (float(cast(float, record[key])) for key in ("gpu_start_s", "gpu_end_s", "gpu_ms"))
    if (
        record.get("completed") is not True
        or not all(map(math.isfinite, (start, end, elapsed)))
        or end <= start
        or abs(elapsed - (end - start) * 1000) > 0.01
    ):
        raise ValueError("Invalid GPU timestamp record")
    return {
        "context": str(record["context"]),
        "graph": int(cast(int, record["graph"])),
        "cb": int(cast(int, record["cb"])),
        "original_nodes": int(cast(int, record["original_nodes"])),
        "gpu_start_s": start,
        "gpu_end_s": end,
        "gpu_ms": elapsed,
    }


def command_buffers(lines: Iterable[str]) -> list[Buffer]:
    rows = (json.loads(line.split(PROFILE, 1)[1]) for line in lines if PROFILE in line)
    return [buffer for row in rows if (buffer := timed_buffer(row)) is not None]


def graph_times(buffers: Iterable[Buffer]) -> list[GraphTime]:
    """Command buffers grouped by context and graph call, in GPU start order."""
    graphs: dict[tuple[str, int], GraphTime] = {}
    for buffer in sorted(buffers, key=lambda item: (item["gpu_start_s"], item["cb"])):
        key = (buffer["context"], buffer["graph"])
        graph = graphs.setdefault(
            key,
            {
                "context": key[0],
                "graph": key[1],
                "buffers_ms": [],
                "start_s": buffer["gpu_start_s"],
                "end_s": buffer["gpu_end_s"],
                "gpu_ms": 0.0,
                "original_nodes": 0,
            },
        )
        graph["buffers_ms"].append(buffer["gpu_ms"])
        graph["end_s"] = max(graph["end_s"], buffer["gpu_end_s"])
        graph["gpu_ms"] += buffer["gpu_ms"]
        graph["original_nodes"] = max(graph["original_nodes"], buffer["original_nodes"])
    return sorted(graphs.values(), key=lambda graph: graph["start_s"])


def target_context(graphs: Sequence[GraphTime]) -> str:
    """The target model's context encodes the largest graphs; the shared helper's are much smaller."""
    if not graphs:
        raise ValueError("No timed GPU graphs")
    return max(graphs, key=lambda graph: graph["original_nodes"])["context"]


def chunk_sizes(prompt_tokens: int, batch: int, ubatch: int) -> list[int]:
    """Prompt batches as the pinned server forms them for this recurrent hybrid: up to `batch` tokens each, broken
    where min(batch, 4 + ubatch) or min(batch, 4) tokens remain so state checkpoints can be taken there."""
    breaks = {min(batch, 4 + ubatch), min(batch, 4)}
    sizes: list[int] = []
    done = 0
    while done < prompt_tokens:
        size = 0
        while done < prompt_tokens and size < batch:
            done += 1
            size += 1
            if prompt_tokens - done in breaks:
                break
        sizes.append(size)
    return sizes


def request_graphs(
    graphs: Sequence[GraphTime],
    begin: float,
    end: float,
    prompt_tokens: int,
    batch: int,
    ubatch: int,
) -> RequestGPU:
    """GPU graphs inside one request window: one target graph per prompt chunk, in order, and nothing else.

    A one-token reply is sampled from the last chunk, so no decode graph runs. Helper graphs that start after a
    chunk's target graph and before the next one read that chunk and are added to its `helper_ms`.
    """
    target = target_context(graphs)
    inside = [g for g in graphs if begin <= g["start_s"] and g["end_s"] <= end]
    main = [g for g in inside if g["context"] == target]
    helpers = [g for g in inside if g["context"] != target]
    sizes = chunk_sizes(prompt_tokens, batch, ubatch)
    if len(main) != len(sizes):
        raise ValueError(f"Expected {len(sizes)} target prompt graphs, found {len(main)}")
    if helpers and helpers[0]["start_s"] < main[0]["start_s"]:
        raise ValueError("Helper GPU graph before the first prompt graph")
    bounds = [g["start_s"] for g in main[1:]] + [end]
    chunks: list[ChunkTime] = [
        {
            "tokens": size,
            "gpu_ms": g["gpu_ms"],
            "ms_per_token": g["gpu_ms"] / size,
            "buffers_ms": g["buffers_ms"],
            "helper_ms": sum(h["gpu_ms"] for h in helpers if g["start_s"] <= h["start_s"] < bound),
        }
        for size, g, bound in zip(sizes, main, bounds, strict=True)
    ]
    return {"chunks": chunks}


def median_by_size(rows: Iterable[ChunkTime]) -> dict[str, dict[str, float | int]]:
    """Median target and helper GPU milliseconds, and target milliseconds per token, for each chunk size."""
    sizes: dict[int, list[ChunkTime]] = {}
    for row in rows:
        sizes.setdefault(row["tokens"], []).append(row)
    medians: dict[str, dict[str, float | int]] = {}
    for size in sorted(sizes):
        target = statistics.median(row["gpu_ms"] for row in sizes[size])
        medians[str(size)] = {
            "samples": len(sizes[size]),
            "gpu_ms": target,
            "ms_per_token": target / size,
            "helper_ms": statistics.median(row["helper_ms"] for row in sizes[size]),
        }
    return medians
