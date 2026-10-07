#!/usr/bin/env python3
"""Plan small GPU correctness checks; --run is required to execute them."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os

from engines import sha256, verify_engine
from lab import ROOT
from metal_environment import TUNING, configure
from verify_q2 import check_case

PARAMS = r"type_a=(q2_0|q3_K|bf16|iq4_nl|iq4_xs|q5_K),type_b=f32,.*n=(1|2|3|4|5|6|7|8|9|13|16|32),"


def check(engine, tensor_api, tuning="stock"):
    pin = verify_engine(engine)
    binary = ROOT / pin["directory"] / "build/bin/test-backend-ops"
    env, flags = configure(os.environ, engine, tensor_api, tuning)
    folder = ROOT / "bench/features" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-m5-math-{engine}-{tensor_api}-{tuning}")
    folder.mkdir()
    record = {"schema": 1, "kind": "m5-synthetic-correctness", "status": "running", "engine": pin,
              "tester_sha256": sha256(binary), "metal_environment": flags, "params": PARAMS,
              "models_loaded": False, "timings_excluded_from_speed_results": True}
    try:
        result = check_case(binary, folder, "math", PARAMS, env=env)
        record["check"] = result
        text = (folder / "math.log").read_text()
        expected = f"has tensor            = {'true' if tensor_api == 'on' else 'false'}"
        if not result["passed"] or expected not in text or result["system_swap_growth_bytes"]:
            raise RuntimeError("GPU math, explicit Tensor API selection or memory check failed")
        if verify_engine(engine) != pin or sha256(binary) != record["tester_sha256"]:
            raise RuntimeError("Engine changed during GPU checks")
        record["status"] = "passed"
    except BaseException as error:
        record.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        (folder / "checks.json").write_text(json.dumps(record, indent=2) + "\n")
    return str((folder / "checks.json").relative_to(ROOT))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--engine", choices=["mtp-mma", "m5-lab", "m5-trace"], default="m5-lab")
    ap.add_argument("--tensor-api", choices=["on", "off"], nargs="+", default=["on", "off"])
    ap.add_argument("--tuning", choices=TUNING, nargs="+", default=["stock"])
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args(argv)
    for tensor in args.tensor_api:
        for tuning in args.tuning:
            configure({}, args.engine, tensor, tuning)
    print(f"GPU correctness plan: {args.engine}, Tensor API {args.tensor_api}, tuning {args.tuning}")
    if not args.run:
        print("Preparation only. No GPU test or model load. Add --run after the testing go-ahead.")
        return
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for tensor in args.tensor_api:
            for tuning in args.tuning:
                print(check(args.engine, tensor, tuning))


if __name__ == "__main__":
    main()
