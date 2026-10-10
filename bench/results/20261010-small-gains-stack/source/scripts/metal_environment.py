"""Keep Metal experiments explicit and independent of inherited debug flags."""
import math

TUNING = {
    "stock": {},
    'small-reduce': {'GGML_M5_LAB_CONV_DIRECT': '1', 'GGML_M5_LAB_REDUCE10': '1'},
    'small-top10': {'GGML_M5_LAB_CONV_DIRECT': '1', 'GGML_M5_LAB_TOP10': '1'},
    'small-reduce-top10': {'GGML_M5_LAB_CONV_DIRECT': '1', 'GGML_M5_LAB_REDUCE10': '1', 'GGML_M5_LAB_TOP10': '1'},
    'small-compact': {'GGML_M5_LAB_CONV_DIRECT': '1', 'GGML_M5_LAB_COMPACT_TILES': '1'},
    'small-reduce-compact': {'GGML_M5_LAB_CONV_DIRECT': '1', 'GGML_M5_LAB_REDUCE10': '1', 'GGML_M5_LAB_COMPACT_TILES': '1'},
    'small-top10-compact': {'GGML_M5_LAB_CONV_DIRECT': '1', 'GGML_M5_LAB_TOP10': '1', 'GGML_M5_LAB_COMPACT_TILES': '1'},
    'small-reduce-top10-compact': {'GGML_M5_LAB_CONV_DIRECT': '1', 'GGML_M5_LAB_REDUCE10': '1', 'GGML_M5_LAB_TOP10': '1', 'GGML_M5_LAB_COMPACT_TILES': '1'},
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
    "draftcap-tail": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_DRAFT_EARLY_STOP": "1"},
    "draftcap2": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_DRAFT_EARLY_STOP": "1", "GGML_M5_LAB_DRAFT_CAP": "2"},
    "draftcap3": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_DRAFT_EARLY_STOP": "1", "GGML_M5_LAB_DRAFT_CAP": "3"},
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
    "hc-down-ks1": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_HC_TENSOR": "1", "GGML_M5_LAB_HC_DOWN_SPLIT": "1"},
    "hc-down-ks2": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_HC_TENSOR": "1", "GGML_M5_LAB_HC_DOWN_SPLIT": "2"},
    "hc-down-ks4": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_HC_TENSOR": "1", "GGML_M5_LAB_HC_DOWN_SPLIT": "4"},
    "hc-down-ks8": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_HC_TENSOR": "1", "GGML_M5_LAB_HC_DOWN_SPLIT": "8"},
    "hc-down-ks16": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_HC_TENSOR": "1", "GGML_M5_LAB_HC_DOWN_SPLIT": "16"},
    "hc-up": {"GGML_M5_LAB_CONV_DIRECT": "1", "GGML_M5_LAB_HC_TENSOR": "2"},
}


def configure(environment, engine, tensor_api="auto", tuning="stock", profile=False):
    if tensor_api not in ("auto", "on", "off") or tuning not in TUNING:
        raise ValueError("Unknown Metal experiment setting")
    if (tuning != "stock" or profile) and engine not in ("m5-lab", "m5-trace", "m5-correctness", "m5-copy", "m5-reduce", "m5-sampling", "m5-hc", "m5-group", "m5-gate", "m5-gdn", "m5-lookup", "m5-gate-lanes", "m5-encoders", "m5-head", "m5-embedding", "m5-draftcap", "m5-top10", "m5-qsa", "m5-route-map", "m5-compact", "m5-compact-cols", "m5-small-stack"):
        raise ValueError("GPU tuning and timing diagnostics require an isolated M5 engine")
    if (tuning.startswith("copy-") or tuning == "conv-direct") and engine not in ("m5-copy", "m5-reduce", "m5-sampling", "m5-hc", "m5-group", "m5-gate", "m5-gdn", "m5-lookup", "m5-gate-lanes", "m5-encoders", "m5-head", "m5-embedding", "m5-draftcap", "m5-top10", "m5-qsa", "m5-route-map", "m5-compact", "m5-compact-cols", "m5-small-stack"):
        raise ValueError("Copy kernels require the isolated m5-copy engine")
    if tuning.startswith("small-") and engine != "m5-small-stack":
        raise ValueError("Small-gain combination requires isolated m5-small-stack engine")
    if tuning == "route-map" and engine != "m5-route-map":
        raise ValueError("Route-map reuse requires isolated m5-route-map engine")
    if tuning == "compact-tiles" and engine != "m5-compact":
        raise ValueError("Compact tile dispatch requires isolated m5-compact engine")
    if tuning == "compact-cols" and engine != "m5-compact-cols":
        raise ValueError("Column-first compact dispatch requires isolated m5-compact-cols engine")
    if tuning == "qsa-all-pools" and engine != "m5-qsa":
        raise ValueError("QSA ranking requires isolated m5-qsa engine")
    if tuning == "top10" and engine != "m5-top10":
        raise ValueError("Parallel top10 requires isolated m5-top10 engine")
    if tuning.startswith("draftcap") and engine != "m5-draftcap":
        raise ValueError("Draft caps require the isolated m5-draftcap engine")
    if tuning == "reduce10" and engine != "m5-reduce":
        raise ValueError("Ten-expert fusion requires the isolated m5-reduce engine")
    if tuning == "sampling-view" and engine != "m5-sampling":
        raise ValueError("Sampling view requires the isolated m5-sampling engine")
    if tuning.startswith("hc-") and engine != "m5-hc":
        raise ValueError("HC kernels require the isolated m5-hc engine")
    if tuning == "expert-group" and engine != "m5-group":
        raise ValueError("Expert grouping requires the isolated m5-group engine")
    if tuning.startswith("gate-up") and engine not in ("m5-gate", "m5-gate-lanes"):
        raise ValueError("Gate fusion requires the isolated m5-gate engine")
    if tuning.startswith("head") and engine != "m5-head":
        raise ValueError("Vocabulary head tiling requires the isolated m5-head engine")
    if tuning.startswith("encoders") and engine != "m5-encoders":
        raise ValueError("Encoding threads require the isolated m5-encoders engine")
    if tuning.startswith("gdn-row") and engine != "m5-gdn":
        raise ValueError("GDN row grouping requires the isolated m5-gdn engine")
    env = {k: v for k, v in environment.items()
           if not k.startswith(("GGML_METAL_", "GGML_M5_LAB_", "GGML_SCHED_DEBUG")) and k != "METAL_CAPTURE_ENABLED"}
    flags = dict(TUNING[tuning])
    if tensor_api == "on":
        flags["GGML_METAL_TENSOR_ENABLE"] = "1"
    elif tensor_api == "off":
        flags["GGML_METAL_TENSOR_DISABLE"] = "1"
    if profile:
        flags["GGML_M5_LAB_PROFILE"] = "1"
    env.update(flags)
    return env, {"tensor_api": tensor_api, "tuning": tuning, "profile": profile, "variables": flags}


def validate_confidence(value):
    if value is not None and (not math.isfinite(value) or not 0 <= value <= 1):
        raise ValueError("Draft confidence must be a finite probability from 0 to 1")
