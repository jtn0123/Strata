"""Keep Metal experiments explicit and independent of inherited debug flags."""

import math
from collections.abc import Mapping
from typing import NamedTuple, TypedDict


class MetalReceipt(TypedDict):
    tensor_api: str
    tuning: str
    profile: bool
    variables: dict[str, str]


class TuningRule(NamedTuple):
    setting: str
    prefix: bool
    engines: tuple[str, ...]
    message: str


TUNING: dict[str, dict[str, str]] = {
    "stock": {},
    "small-reduce": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_REDUCE10": "1"},
    "small-top10": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_TOP10": "1"},
    "small-reduce-top10": {
        "GGML_M5_LAB_CONV_DIRECT": "1",
        "GGML_M5_LAB_REDUCE10": "1",
        "GGML_M5_LAB_TOP10": "1",
    },
    "small-compact": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_COMPACT_TILES": "1"},
    "small-reduce-compact": {
        "GGML_M5_LAB_CONV_DIRECT": "1",
        "GGML_M5_LAB_REDUCE10": "1",
        "GGML_M5_LAB_COMPACT_TILES": "1",
    },
    "small-top10-compact": {
        "GGML_M5_LAB_CONV_DIRECT": "1",
        "GGML_M5_LAB_TOP10": "1",
        "GGML_M5_LAB_COMPACT_TILES": "1",
    },
    "small-reduce-top10-compact": {
        "GGML_M5_LAB_CONV_DIRECT": "1",
        "GGML_M5_LAB_REDUCE10": "1",
        "GGML_M5_LAB_TOP10": "1",
        "GGML_M5_LAB_COMPACT_TILES": "1",
    },
    "bf16-row3": {"GGML_M5_LAB_BF16_MIN_ROWS": "3"},
    "q2-row2": {"GGML_M5_LAB_Q2_MIN_ROWS": "2"},
    "nt1": {"GGML_M5_LAB_NT_MAX": "1"},
    "nt2": {"GGML_M5_LAB_NT_MAX": "2"},
    "nsg4": {"GGML_M5_LAB_NSG": "4"},
    "nsg8": {"GGML_M5_LAB_NSG": "8"},
    "copy-scalar": {"GGML_M5_LAB_COPY_WIDTH": "1"},
    "copy-v4": {"GGML_M5_LAB_COPY_WIDTH": "4"},
    "copy-v8": {"GGML_M5_LAB_COPY_WIDTH": "8"},
    "conv-direct": {"GGML_M5_LAB_CONV_DIRECT": "1"},
    "draftcap-tail": {
        "GGML_M5_LAB_CONV_DIRECT": "1",
        "GGML_M5_LAB_DRAFT_EARLY_STOP": "1",
    },
    "draftcap2": {
        "GGML_M5_LAB_CONV_DIRECT": "1",
        "GGML_M5_LAB_DRAFT_EARLY_STOP": "1",
        "GGML_M5_LAB_DRAFT_CAP": "2",
    },
    "draftcap3": {
        "GGML_M5_LAB_CONV_DIRECT": "1",
        "GGML_M5_LAB_DRAFT_EARLY_STOP": "1",
        "GGML_M5_LAB_DRAFT_CAP": "3",
    },
    "route-map": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_ROUTE_MAP": "1"},
    "compact-tiles": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_COMPACT_TILES": "1"},
    "compact-cols": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_COMPACT_TILES": "1"},
    "qsa-all-pools": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_QSA_ALL_POOLS": "1"},
    "top10": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_TOP10": "1"},
    "head2": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_HEAD_NR0": "2"},
    "head4": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_HEAD_NR0": "4"},
    "encoders0": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_N_CB": "0"},
    "encoders2": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_N_CB": "2"},
    "expert-group": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_EXPERT_GROUP": "1"},
    "gate-up8": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_GATE_UP": "1"},
    "gate-up4": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_GATE_UP": "2"},
    "gdn-row1": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_GDN_ROWS": "1"},
    "gdn-row2": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_GDN_ROWS": "2"},
    "gdn-row4": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_GDN_ROWS": "4"},
    "reduce10": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_REDUCE10": "1"},
    "sampling-view": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_SAMPLING_VIEW": "1"},
    "hc-special": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_HC_SPECIAL": "1"},
    "hc-down-ks1": {
        "GGML_M5_LAB_CONV_DIRECT": "1",
        "GGML_M5_LAB_HC_TENSOR": "1",
        "GGML_M5_LAB_HC_DOWN_SPLIT": "1",
    },
    "hc-down-ks2": {
        "GGML_M5_LAB_CONV_DIRECT": "1",
        "GGML_M5_LAB_HC_TENSOR": "1",
        "GGML_M5_LAB_HC_DOWN_SPLIT": "2",
    },
    "hc-down-ks4": {
        "GGML_M5_LAB_CONV_DIRECT": "1",
        "GGML_M5_LAB_HC_TENSOR": "1",
        "GGML_M5_LAB_HC_DOWN_SPLIT": "4",
    },
    "hc-down-ks8": {
        "GGML_M5_LAB_CONV_DIRECT": "1",
        "GGML_M5_LAB_HC_TENSOR": "1",
        "GGML_M5_LAB_HC_DOWN_SPLIT": "8",
    },
    "hc-down-ks16": {
        "GGML_M5_LAB_CONV_DIRECT": "1",
        "GGML_M5_LAB_HC_TENSOR": "1",
        "GGML_M5_LAB_HC_DOWN_SPLIT": "16",
    },
    "hc-up": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_HC_TENSOR": "2"},
}


TUNING_RULES = (
    TuningRule(
        "small-",
        True,
        ("m5-small-stack", "m5-waits", "m5-segments", "m5-overlap"),
        "Small-gain combination requires isolated m5-small-stack engine",
    ),
    TuningRule("route-map", False, ("m5-route-map",), "Route-map reuse requires isolated m5-route-map engine"),
    TuningRule("compact-tiles", False, ("m5-compact",), "Compact tile dispatch requires isolated m5-compact engine"),
    TuningRule(
        "compact-cols",
        False,
        ("m5-compact-cols",),
        "Column-first compact dispatch requires isolated m5-compact-cols engine",
    ),
    TuningRule("qsa-all-pools", False, ("m5-qsa",), "QSA ranking requires isolated m5-qsa engine"),
    TuningRule("top10", False, ("m5-top10",), "Parallel top10 requires isolated m5-top10 engine"),
    TuningRule("draftcap", True, ("m5-draftcap",), "Draft caps require the isolated m5-draftcap engine"),
    TuningRule("reduce10", False, ("m5-reduce",), "Ten-expert fusion requires the isolated m5-reduce engine"),
    TuningRule("sampling-view", False, ("m5-sampling",), "Sampling view requires the isolated m5-sampling engine"),
    TuningRule("hc-", True, ("m5-hc",), "HC kernels require the isolated m5-hc engine"),
    TuningRule("expert-group", False, ("m5-group",), "Expert grouping requires the isolated m5-group engine"),
    TuningRule("gate-up", True, ("m5-gate", "m5-gate-lanes"), "Gate fusion requires the isolated m5-gate engine"),
    TuningRule("head", True, ("m5-head",), "Vocabulary head tiling requires the isolated m5-head engine"),
    TuningRule("encoders", True, ("m5-encoders",), "Encoding threads require the isolated m5-encoders engine"),
    TuningRule("gdn-row", True, ("m5-gdn",), "GDN row grouping requires the isolated m5-gdn engine"),
)


def _validate_tuning_engine(engine: str, tuning: str) -> None:
    for rule in TUNING_RULES:
        matches = tuning.startswith(rule.setting) if rule.prefix else tuning == rule.setting
        if matches and engine not in rule.engines:
            raise ValueError(rule.message)


def _validate_metal_settings(
    engine: str,
    tensor_api: str,
    tuning: str,
    profile: bool,
) -> None:
    if tensor_api not in ("auto", "on", "off") or tuning not in TUNING:
        raise ValueError("Unknown Metal experiment setting")
    if (tuning != "stock" or profile) and engine not in (
        "m5-lab",
        "m5-trace",
        "m5-correctness",
        "m5-copy",
        "m5-reduce",
        "m5-sampling",
        "m5-hc",
        "m5-group",
        "m5-gate",
        "m5-gdn",
        "m5-lookup",
        "m5-gate-lanes",
        "m5-encoders",
        "m5-head",
        "m5-embedding",
        "m5-draftcap",
        "m5-top10",
        "m5-qsa",
        "m5-route-map",
        "m5-compact",
        "m5-compact-cols",
        "m5-small-stack",
        "m5-waits",
        "m5-segments",
        "m5-overlap",
    ):
        raise ValueError("GPU tuning and timing diagnostics require an isolated M5 engine")
    if (tuning.startswith("copy-") or tuning == "conv-direct") and engine not in (
        "m5-copy",
        "m5-reduce",
        "m5-sampling",
        "m5-hc",
        "m5-group",
        "m5-gate",
        "m5-gdn",
        "m5-lookup",
        "m5-gate-lanes",
        "m5-encoders",
        "m5-head",
        "m5-embedding",
        "m5-draftcap",
        "m5-top10",
        "m5-qsa",
        "m5-route-map",
        "m5-compact",
        "m5-compact-cols",
        "m5-small-stack",
        "m5-waits",
        "m5-segments",
        "m5-overlap",
    ):
        raise ValueError("Copy kernels require the isolated m5-copy engine")
    _validate_tuning_engine(engine, tuning)


def configure(
    environment: Mapping[str, str],
    engine: str,
    tensor_api: str = "auto",
    tuning: str = "stock",
    profile: bool = False,
) -> tuple[dict[str, str], MetalReceipt]:
    _validate_metal_settings(engine, tensor_api, tuning, profile)
    env = {
        k: v
        for k, v in environment.items()
        if not k.startswith(("GGML_METAL_", "GGML_M5_LAB_", "GGML_SCHED_DEBUG"))
        and k not in ("METAL_CAPTURE_ENABLED", "GGML_M5_HELPER_POOL", "GGML_M5_WAIT_TRACE")
    }
    flags = dict(TUNING[tuning])
    if tensor_api == "on":
        flags["GGML_METAL_TENSOR_ENABLE"] = "1"
    elif tensor_api == "off":
        flags["GGML_METAL_TENSOR_DISABLE"] = "1"
    if profile:
        flags["GGML_M5_LAB_PROFILE"] = "1"
    env.update(flags)
    return env, {
        "tensor_api": tensor_api,
        "tuning": tuning,
        "profile": profile,
        "variables": flags,
    }


def validate_confidence(value: float | None) -> None:
    if value is not None and (not math.isfinite(value) or not 0 <= value <= 1):
        raise ValueError("Draft confidence must be a finite probability from 0 to 1")
