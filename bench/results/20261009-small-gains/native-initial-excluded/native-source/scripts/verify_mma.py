#!/usr/bin/env python3
"""Check few-row GPU math against the CPU reference without loading model weights."""
from datetime import datetime, timezone
import fcntl
import json
import os

from engines import sha256, verify_engine
from lab import ROOT
from verify_q2 import check_case


def main():
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        engine = verify_engine("mtp-mma")
        binary = ROOT / engine["directory"] / "build/bin/test-backend-ops"
        folder = ROOT / "bench/features" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-mma-math")
        folder.mkdir()
        record = {"schema": 1, "kind": "synthetic-correctness", "engine": engine, "tester_sha256": sha256(binary),
                  "models_loaded": False, "benchmarks_run": False, "checks": [], "status": "running"}
        previous = os.environ.get("GGML_METAL_TENSOR_DISABLE")
        try:
            for disabled in (False, True):
                if disabled:
                    os.environ["GGML_METAL_TENSOR_DISABLE"] = "1"
                else:
                    os.environ.pop("GGML_METAL_TENSOR_DISABLE", None)
                name = "tensor-off" if disabled else "tensor-on"
                params = r"type_a=(q2_0|q3_K|bf16|iq4_nl|iq4_xs|q5_K),type_b=f32,.*n=(1|2|3|4|5|8|9|13|16),"
                result = check_case(binary, folder, name, params)
                result["tensor_api_disabled"] = disabled
                record["checks"].append(result)
                if not result["passed"]:
                    raise RuntimeError("Few-row GPU math check failed")
            record["status"] = "passed"
        except BaseException as error:
            record.update(status="failed", error=f"{type(error).__name__}: {error}")
            raise
        finally:
            if previous is None:
                os.environ.pop("GGML_METAL_TENSOR_DISABLE", None)
            else:
                os.environ["GGML_METAL_TENSOR_DISABLE"] = previous
            (folder / "checks.json").write_text(json.dumps(record, indent=2) + "\n")
            print(f"Saved {folder}", flush=True)


if __name__ == "__main__":
    main()
