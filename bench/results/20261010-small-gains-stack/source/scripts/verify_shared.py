#!/usr/bin/env python3
"""Check shared-helper placement and standalone rejection before comparison."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import subprocess

from benchmark import run
from benchmark_shared import settings
from check_memory import assert_no_model_server
from engines import engine_binary, verify_engine
from lab import ROOT, model_path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--include-gpu", action="store_true")
    ap.add_argument("--gpu-only", action="store_true")
    ap.add_argument("--mixed-only", action="store_true")
    ap.add_argument("--batch", type=int, choices=[128, 256, 512], default=512)
    args = ap.parse_args()
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert_no_model_server()
        engine = verify_engine("mtp-shared")
        folder = ROOT / "bench/features" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-mtp-shared")
        folder.mkdir()
        record = {"status": "running", "engine": engine, "runs": [],
            "note": "Feature trials are excluded from the matched comparison. Standalone helper must exit cleanly "
            "without a target. Positive checks cover Unicode, English/Chinese arithmetic/JSON, Python, edited labels "
            "and cached ledger recall at greedy and normal sampling."}
        try:
            command = [str(engine_binary("mtp-shared")), "-m", str(model_path("mtp_shared_q3")),
                "-c", "128", "-b", "32", "-ub", "32", "-ngl", "0", "-fit", "off",
                "-lm", "mmap", "-lzm", "on", "--spec-type", "none", "--no-webui"]
            with (folder / "standalone.log").open("w") as log:
                result = subprocess.run(command, stdout=log, stderr=log, timeout=120)
            record["standalone"] = {"command": command, "exit_code": result.returncode}
            if result.returncode <= 0 or "without embeddings or output requires a target context" not in (folder / "standalone.log").read_text():
                raise AssertionError("Standalone helper did not reject the missing target cleanly")
            profiles = ("shared-mixed",) if args.mixed_only else (("shared-gpu",) if args.gpu_only else (
                ("shared-cpu", "shared-gpu") if args.include_gpu else ("shared-cpu",)))
            for profile in profiles:
                assert_no_model_server()
                trial = settings(profile, "feature-" + profile, predict=64, repeats=1)
                trial.warmups = 0
                trial.batch = trial.ubatch = args.batch
                if profile == "shared-mixed":
                    trial.draft_placement = "mixed"
                result = run(trial)
                record["runs"].append({"profile": profile, "run_id": result["run_id"],
                    "status": result["status"], "memory": result.get("memory", {})})
                if result["status"] != "passed":
                    raise AssertionError(f"{profile} failed answer checks")
                if "borrowing target embeddings/output; draft KV remains separate" not in (
                        ROOT / "bench/results" / result["run_id"] / "server.log").read_text():
                    raise AssertionError("Sharing did not activate")
            record["status"] = "passed"
        except BaseException as error:
            record.update(status="failed", error=f"{type(error).__name__}: {error}")
            raise
        finally:
            (folder / "checks.json").write_text(json.dumps(record, indent=2) + "\n")
            print(f"Saved {folder}", flush=True)


if __name__ == "__main__":
    main()
