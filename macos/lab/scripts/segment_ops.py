"""Parse the m5-segments timer: GPU time for each part of a prompt chunk.

With `GGML_M5_LAB_SEGMENTS` set, the isolated engine encodes each graph into one command buffer per segment. A segment
ends after every hyper-connection merge, and each layer's routed expert matrices get a segment of their own. A target
graph therefore has four segments per layer, and one after the last layer when the chunk samples a token:

- **mixer** (`recurrent` or `attention`): the layer's gated-delta-net or attention block with its hyper-connection
  mix. From layer 1 on it also holds the per-layer embedding work that follows the previous layer.
- **router**: the feed-forward hyper-connection mix, the router and the shared expert's gate and up matrices.
- **experts**: the routed expert gate, up and down matrices, plus the shared expert's activation and down matrix,
  which the graph places between them.
- **combine**: the weighted expert sum, the feed-forward output and the hyper-connection merge.
- **output**: everything after the last merge. Only the chunk that samples a token runs the output head. In other
  chunks those nodes carry no compute flag, so the encoder skips them and they join the last combine segment without
  a dispatch. The output part is therefore reported per chunk but not fitted.

Each interval is GPU elapsed time for one command buffer. A new command buffer is a full barrier, so the segment sum
also pays for overlap lost at each boundary; compare it with unsegmented chunks from the same engine.
"""

from collections.abc import Iterable, Mapping, Sequence
import json
import statistics
from typing import TypedDict, cast

from prompt_ops import PROFILE, ChunkTime, GraphTime, request_graphs, target_context, timed_buffer

MIXERS = {"GATED_DELTA_NET": "recurrent", "FLASH_ATTN_EXT": "attention"}
PARTS = ("recurrent", "attention", "router", "experts", "combine", "output")
FITTED_PARTS = PARTS[:-1]
MERGE = "DSV4_HC_POST"
EXPERT = "MUL_MAT_ID"
EXPERT_MATRICES = 3
# Very small chunks do not pay the full per-chunk cost (N00: 4 tokens cost 40-51 ms), so fits start here.
MIN_FIT_TOKENS = 256


class Segment(TypedDict):
    context: str
    graph: int
    index: int
    cause: str
    first_node: int
    end_node: int
    graph_nodes: int
    dispatches: int
    last_op: str
    op_counts: dict[str, int]
    gpu_start_s: float
    gpu_end_s: float
    gpu_ms: float


class ChunkParts(TypedDict):
    tokens: int
    position: int
    busy_ms: float
    span_ms: float
    helper_ms: float
    parts_ms: dict[str, float]
    dispatches: dict[str, int]


class Fit(TypedDict):
    per_chunk_ms: float
    per_token_ms: float
    per_token_per_1000_context_ms: float
    max_residual_pct: float
    samples: int


def segments(lines: Iterable[str]) -> list[Segment]:
    """Timed segment buffers; buffers without a segment record come from graphs the timer did not split."""
    rows: list[Segment] = []
    for line in lines:
        if PROFILE not in line:
            continue
        record = json.loads(line.split(PROFILE, 1)[1])
        if "segment" not in record:
            continue
        buffer = timed_buffer(record)
        if buffer is None:
            raise ValueError("Segment buffer without GPU time")
        segment = cast(dict[str, object], record["segment"])
        rows.append(
            {
                "context": buffer["context"],
                "graph": buffer["graph"],
                "index": int(cast(int, segment["index"])),
                "cause": str(segment["cause"]),
                "first_node": int(cast(int, segment["first_node"])),
                "end_node": int(cast(int, segment["end_node"])),
                "graph_nodes": buffer["original_nodes"],
                "dispatches": int(cast(int, segment["dispatches"])),
                "last_op": str(segment["last_op"]),
                "op_counts": cast(dict[str, int], record["op_counts"]),
                "gpu_start_s": buffer["gpu_start_s"],
                "gpu_end_s": buffer["gpu_end_s"],
                "gpu_ms": buffer["gpu_ms"],
            }
        )
    return rows


def by_graph(rows: Iterable[Segment]) -> dict[tuple[str, int], list[Segment]]:
    """Segments of each graph in order; together they must cover every graph node exactly once."""
    graphs: dict[tuple[str, int], list[Segment]] = {}
    for row in rows:
        graphs.setdefault((row["context"], row["graph"]), []).append(row)
    for key, parts in graphs.items():
        parts.sort(key=lambda row: row["index"])
        ends = [0, *(row["end_node"] for row in parts)]
        if (
            [row["index"] for row in parts] != list(range(len(parts)))
            or [row["first_node"] for row in parts] != ends[:-1]
            or ends[-1] != parts[0]["graph_nodes"]
        ):
            raise ValueError(f"Segments of graph {key[1]} do not cover its nodes once")
    return graphs


def _expect(segment: Segment, ok: bool, kind: str) -> None:
    if not ok:
        raise ValueError(f"Segment {segment['index']} is not the expected {kind}")


def _mixer(segment: Segment) -> str:
    kinds = {kind for op, kind in MIXERS.items() if op in segment["op_counts"]}
    _expect(segment, len(kinds) == 1 and segment["last_op"] == MERGE, "mixer")
    return kinds.pop()


def layer_parts(graph: Sequence[Segment]) -> list[tuple[int, str]]:
    """(layer, part) for each segment of a target graph, checked against the four-part layer pattern."""
    if len(graph) < 4 or len(graph) % 4 > 1:
        raise ValueError("Target graph is not four segments per layer and at most one output segment")
    labels: list[tuple[int, str]] = []
    layers = len(graph) // 4
    for layer in range(layers):
        mixer, router, experts, combine = graph[4 * layer : 4 * layer + 4]
        kind = _mixer(mixer)
        _expect(router, router["cause"] == "hc_post" and router["last_op"] != MERGE, "router")
        _expect(router, EXPERT not in router["op_counts"], "router")
        _expect(experts, experts["cause"] == "experts", "experts")
        _expect(experts, experts["op_counts"].get(EXPERT) == EXPERT_MATRICES, "experts")
        _expect(combine, combine["cause"] == "after_experts" and combine["last_op"] == MERGE, "combine")
        labels += [(layer, kind), (layer, "router"), (layer, "experts"), (layer, "combine")]
    if len(graph) % 4 == 0:
        return labels
    output = graph[-1]
    _expect(output, output["cause"] == "hc_post" and output["last_op"] != MERGE, "output")
    _expect(output, EXPERT not in output["op_counts"], "output")
    labels.append((layers - 1, "output"))
    return labels


def chunk_parts(graph: Sequence[Segment]) -> tuple[float, float, dict[str, float], dict[str, int]]:
    """Busy GPU time, first-start to last-end span, and time and dispatches per part for one target graph."""
    times = dict.fromkeys(PARTS, 0.0)
    dispatches = dict.fromkeys(PARTS, 0)
    for (_, part), segment in zip(layer_parts(graph), graph, strict=True):
        times[part] += segment["gpu_ms"]
        dispatches[part] += segment["dispatches"]
    busy = sum(segment["gpu_ms"] for segment in graph)
    span = (max(s["gpu_end_s"] for s in graph) - min(s["gpu_start_s"] for s in graph)) * 1000
    return busy, span, times, dispatches


def request_parts(
    graphs: Sequence[GraphTime],
    split: Mapping[tuple[str, int], Sequence[Segment]],
    window: tuple[float, float],
    prompt_tokens: int,
    profile: tuple[int, int],
) -> list[ChunkParts]:
    """Part times of each prompt chunk in one request window, with the helper GPU time that followed it."""
    begin, end = window
    chunks = request_graphs(graphs, begin, end, prompt_tokens, *profile)["chunks"]
    target = target_context(graphs)
    main = [g for g in graphs if g["context"] == target and begin <= g["start_s"] and g["end_s"] <= end]
    rows: list[ChunkParts] = []
    position = 0
    for chunk, graph in zip(chunks, main, strict=True):
        key = (graph["context"], graph["graph"])
        if key not in split:
            raise ValueError(f"Prompt graph {graph['graph']} has no segment timing")
        busy, span, times, dispatches = chunk_parts(split[key])
        rows.append(
            {
                "tokens": chunk["tokens"],
                "position": position,
                "busy_ms": busy,
                "span_ms": span,
                "helper_ms": chunk["helper_ms"],
                "parts_ms": times,
                "dispatches": dispatches,
            }
        )
        position += chunk["tokens"]
    return rows


def median_parts(rows: Iterable[ChunkParts]) -> dict[str, dict[str, object]]:
    """Median busy time, span and part times for each chunk size at each position."""
    groups: dict[tuple[int, int], list[ChunkParts]] = {}
    for row in rows:
        groups.setdefault((row["tokens"], row["position"]), []).append(row)
    medians: dict[str, dict[str, object]] = {}
    for (tokens, position), group in sorted(groups.items()):
        medians[f"{tokens}@{position}"] = {
            "tokens": tokens,
            "position": position,
            "samples": len(group),
            "busy_ms": statistics.median(row["busy_ms"] for row in group),
            "span_ms": statistics.median(row["span_ms"] for row in group),
            "parts_ms": {part: statistics.median(row["parts_ms"][part] for row in group) for part in PARTS},
            "dispatches": group[0]["dispatches"],
        }
    return medians


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting for a small square system."""
    n = len(vector)
    rows = [[*matrix[i], vector[i]] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(rows[r][col]))
        if abs(rows[pivot][col]) < 1e-12:
            raise ValueError("Chunk sizes and positions do not separate the fit terms")
        rows[col], rows[pivot] = rows[pivot], rows[col]
        for r in range(n):
            if r != col:
                factor = rows[r][col] / rows[col][col]
                rows[r] = [a - factor * b for a, b in zip(rows[r], rows[col], strict=True)]
    return [rows[i][n] / rows[i][i] for i in range(n)]


def _context(tokens: int, position: int) -> float:
    """Earlier tokens a chunk's token sees on average: those before the chunk and half the chunk itself."""
    return position + tokens / 2


def fit(points: Sequence[tuple[int, int, float]]) -> Fit:
    """Least-squares ms = a + b*tokens + c*tokens*context/1000 over (tokens, position, ms) chunk medians."""
    used = [point for point in points if point[0] >= MIN_FIT_TOKENS]
    if len(used) < 3:
        raise ValueError("Too few chunk sizes to fit")
    terms = [[1.0, float(tokens), tokens * _context(tokens, position) / 1000] for tokens, position, _ in used]
    normal = [[sum(row[i] * row[j] for row in terms) for j in range(3)] for i in range(3)]
    target = [sum(row[i] * point[2] for row, point in zip(terms, used, strict=True)) for i in range(3)]
    a, b, c = _solve(normal, target)
    if any(ms <= 0 for _, _, ms in used):
        raise ValueError("A fitted chunk has no GPU time")
    residuals = [
        abs(a + b * tokens + c * tokens * _context(tokens, position) / 1000 - ms) / ms * 100
        for tokens, position, ms in used
    ]
    return {
        "per_chunk_ms": a,
        "per_token_ms": b,
        "per_token_per_1000_context_ms": c,
        "max_residual_pct": max(residuals),
        "samples": len(used),
    }


def fit_parts(medians: Mapping[str, Mapping[str, object]]) -> dict[str, Fit]:
    """The per-chunk, per-token and position terms for the busy total and for each fitted part."""
    rows = list(medians.values())
    points = {
        "busy": [(cast(int, r["tokens"]), cast(int, r["position"]), cast(float, r["busy_ms"])) for r in rows],
    }
    for part in FITTED_PARTS:
        points[part] = [
            (cast(int, r["tokens"]), cast(int, r["position"]), cast(dict[str, float], r["parts_ms"])[part])
            for r in rows
        ]
    return {name: fit(values) for name, values in points.items()}


def control_medians(requests: Iterable[Sequence[ChunkTime]]) -> dict[str, dict[str, float | int]]:
    """Median unsegmented GPU time for each chunk size at each position, from requests' chunks in order."""
    groups: dict[tuple[int, int], list[float]] = {}
    for chunks in requests:
        position = 0
        for chunk in chunks:
            groups.setdefault((chunk["tokens"], position), []).append(chunk["gpu_ms"])
            position += chunk["tokens"]
    return {
        f"{tokens}@{position}": {
            "tokens": tokens,
            "position": position,
            "samples": len(times),
            "gpu_ms": statistics.median(times),
        }
        for (tokens, position), times in sorted(groups.items())
    }


def overhead(
    segmented: Mapping[str, Mapping[str, object]], control: Mapping[str, Mapping[str, float | int]]
) -> dict[str, float]:
    """Segment-sum minus unsegmented chunk time, in percent, for chunks measured both ways."""
    return {
        key: (cast(float, row["busy_ms"]) / control[key]["gpu_ms"] - 1) * 100
        for key, row in segmented.items()
        if key in control
    }


def output_parity(outputs: Iterable[tuple[str, object]]) -> dict[str, object]:
    """Whether every request for the same prompt produced the same token and probabilities."""
    seen: dict[str, list[str]] = {}
    for name, output in outputs:
        seen.setdefault(name, []).append(json.dumps(output, sort_keys=True))
    differing = sorted(name for name, values in seen.items() if len(set(values)) > 1)
    return {
        "cases": len(seen),
        "requests": sum(map(len, seen.values())),
        "identical": not differing,
        "differing_cases": differing,
    }
