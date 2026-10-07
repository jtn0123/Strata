"""Keep Metal experiments explicit and independent of inherited debug flags."""
import math

TUNING = {
    "stock": {},
    "bf16-row3": {"GGML_M5_LAB_BF16_MIN_ROWS": "3"},
    "q2-row2": {"GGML_M5_LAB_Q2_MIN_ROWS": "2"},
    "nt1": {"GGML_M5_LAB_NT_MAX": "1"},
    "nt2": {"GGML_M5_LAB_NT_MAX": "2"},
    "nsg4": {"GGML_M5_LAB_NSG": "4"},
    "nsg8": {"GGML_M5_LAB_NSG": "8"},
}


def configure(environment, engine, tensor_api="auto", tuning="stock", profile=False):
    if tensor_api not in ("auto", "on", "off") or tuning not in TUNING:
        raise ValueError("Unknown Metal experiment setting")
    if (tuning != "stock" or profile) and engine not in ("m5-lab", "m5-trace"):
        raise ValueError("GPU tuning and timing diagnostics require an isolated M5 engine")
    env = {k: v for k, v in environment.items()
           if not k.startswith(("GGML_METAL_", "GGML_M5_LAB_")) and k != "METAL_CAPTURE_ENABLED"}
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
