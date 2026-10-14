"""Numeric local telemetry; never retains prompts, replies, file paths or API keys."""

from collections import deque
from collections.abc import Mapping
import json
import math
from pathlib import Path
import time
from typing import Any, Protocol, cast

import psutil
from lab import ROOT

JSONDict = dict[str, Any]
Number = int | float


class EngineTelemetry(Protocol):
    last: JSONDict


class ServiceTelemetry(Protocol):
    engine: EngineTelemetry
    status: JSONDict
    history: deque[JSONDict]

    def kind(self) -> str: ...


def number(value: object, minimum: Number = 0) -> Number | None:
    if type(value) is int or type(value) is float:
        return value if math.isfinite(value) and value >= minimum else None
    return None


def measured_history(
    record: Mapping[str, Any],
    status: Mapping[str, Any],
    last: Mapping[str, Any],
    kind: str,
) -> JSONDict:
    row = dict(record)
    start, first = number(status.get("started")), number(status.get("first_token"))
    native = last.get("native_timings") or {}
    if not isinstance(native, dict):
        native = {}
    proposed, accepted = (
        number(native.get("draft_n")),
        number(native.get("draft_n_accepted")),
    )
    row.update(
        measurement_kind=kind,
        server_first_token_ms=1000 * (first - start)
        if start is not None and first is not None and first >= start
        else None,
        server_duration_ms=number(1000 * (time.time() - start)) if start is not None else None,
        generation_tps=number(native.get("predicted_per_second")),
        prompt_tps=number(native.get("prompt_per_second")),
        draft_acceptance_percent=100 * (accepted / proposed)
        if proposed and accepted is not None and accepted <= proposed
        else None,
    )
    if row["generation_tps"] is None:
        row["generation_tps"] = number(record.get("decode_tok_s"))
        row["generation_source"] = "server-derived" if row["generation_tps"] else "unreported"
    else:
        row["generation_source"] = "native" if row["generation_tps"] else "unreported"
    return row


def guard_sample(
    path: str | Path | None, now: float | None = None, runtime_root: Path | None = None
) -> JSONDict | None:
    """Read at most 16 KiB from the existing owned guard; no extra pressure subprocess."""
    if not path:
        return None
    root = (runtime_root or ROOT / "bench/runtime").resolve()
    source = Path(path).resolve()
    if not source.is_relative_to(root) or source.name != "memory.jsonl":
        return None
    try:
        age = (time.time() if now is None else now) - source.stat().st_mtime
        if age < 0 or age > 3:
            return None
        with source.open("rb") as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - 16384))
            data = stream.read(16384)
        # A writer can be midway through its final line. Use the last complete sample.
        lines = data.split(b"\n")[:-1]
        for line in reversed(lines):
            try:
                sample = json.loads(line)
                if isinstance(sample, dict):
                    return sample
            except (ValueError, UnicodeDecodeError):
                continue
    except OSError:
        pass
    return None


def resources(config: Mapping[str, Any]) -> JSONDict:
    vm, swap = psutil.virtual_memory(), psutil.swap_memory()
    sample = guard_sample(config.get("monitor_file")) or {}
    initial = number(config.get("initial_swap_bytes"))
    return {
        "available_bytes": vm.available,
        "total_bytes": vm.total,
        "swap_used_bytes": swap.used,
        "new_swap_bytes": max(0, swap.used - initial) if initial is not None else None,
        "model_rss_bytes": number(sample.get("rss_bytes")),
        "pressure_level": sample.get("pressure_level") if sample.get("pressure_level") in (1, 2, 4) else None,
    }


def tracked_service(original: type[Any], mock_type: type[Any], config: Mapping[str, Any] | None = None) -> type[Any]:
    performance_config = dict(config or {})
    allowed = (
        "model",
        "engine",
        "context",
        "cache_type",
        "spec",
        "draft",
        "draft_model",
        "lookup_profile",
        "tensor_api",
        "m5_tuning",
        "batch",
        "ubatch",
        "draft_threads",
        "draft_placement",
        "draft_p_min",
    )

    class TrackedService(original):
        history: deque[JSONDict]

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            service = cast(ServiceTelemetry, self)

            class History(deque[JSONDict]):
                def append(self, row: JSONDict) -> None:
                    # The pinned shell calls append while holding status_lock, immediately
                    # after copying engine.last. Preserve its deque and lifecycle semantics.
                    last = dict(getattr(service.engine, "last", {}) or {})
                    super().append(measured_history(row, service.status, last, service.kind()))

            self.history = History(self.history, maxlen=self.history.maxlen)

        def kind(self) -> str:
            if isinstance(self.engine, mock_type):
                return "mock"
            backend = (getattr(self.engine, "info", {}) or {}).get("backend")
            if backend == "metal-native-http":
                return "model"
            return "unverified"

        def metrics(self) -> JSONDict:
            result: JSONDict = super().metrics()
            try:
                memory = resources(performance_config)
            except (OSError, ValueError, psutil.Error):
                memory = {}
            result["performance"] = {
                "schema": 1,
                "measurement_kind": self.kind(),
                "settings": {key: performance_config[key] for key in allowed if key in performance_config},
                "resources": memory,
                "scope": "Server timings start after queue admission; browser and engine timings have different scopes.",
            }
            return result

    return TrackedService
