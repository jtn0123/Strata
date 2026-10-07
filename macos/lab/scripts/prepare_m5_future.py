#!/usr/bin/env python3
"""Create reviewable future-experiment templates. Never runs inference, GPU tests or builds."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from engines import sha256
from lab import ROOT

PLAN = ROOT / "config/m5_future_plan.json"


def validate(plan):
    if plan["automatic_execution"] is not False or "on hold" not in plan["testing_status"]:
        raise ValueError("Preparation must explicitly hold testing with no automatic execution")
    ids = [e["id"] for e in plan["experiments"]]
    if len(ids) != len(set(ids)) or not ids: raise ValueError("Missing or duplicate experiment IDs")
    for e in plan["experiments"]:
        if any(d not in ids or ids.index(d) >= ids.index(e["id"]) for d in e["depends_on"]):
            raise ValueError("Dependencies must name earlier experiment templates")
        if e["kind"] == "native-candidate" and e["candidate_engine"] is None and e["future_run_command"] is not None:
            raise ValueError("Do not create a runnable no-op candidate")
        if not e["only_change"] or not e["proof"] or not e["stop_if"] or not e["limits"]:
            raise ValueError("Experiment needs scope, proof, stop criteria and limits")
    if plan["comparison"]["new_swap_required_bytes"] != 0 or plan["comparison"]["order"] != ["control","candidate","candidate","control"]:
        raise ValueError("Future gains require fresh matched controls and zero new swap")


def result_template(spec, plan):
    return {"schema":1,"experiment_id":spec["id"],"status":"not-run","testing_authorized":False,
        "implementation":spec["implementation"],"control_runs":[],"candidate_runs":[],
        "source_receipts":[],"model_hashes":[],"checks":{"passed":None,"failed":None},
        "metrics":{m:{"control":None,"candidate":None,"change_percent":None} for m in plan["comparison"]["metrics"]},
        "observations":{field:None for field in spec["result_fields"]},"raw_evidence":[],
        "decision":None,"limits":spec["limits"],"new_performance_claim":False}


def card(spec, plan):
    lines = ["# " + spec["title"],"", "Status: prepared; testing is on hold.","",spec["implementation"],"",
        "Hypothesis: " + spec["hypothesis"],"","Only change: " + spec["only_change"],"",
        "## Before testing","", *["- " + p for p in spec["prerequisites"]],"",
        "## Required evidence","",*["- " + p for p in spec["proof"]],"",
        "## Stop conditions","",*["- " + p for p in spec["stop_if"]],"",
        "## Record results","","Use `result-template.json`; all numbers remain empty until measured.","",
        plan["comparison"]["percentage_rules"],"",plan["comparison"]["adoption_gate"],"",
        "Historical results are reference only. Record a new complete matched baseline for a speed candidate.","",
        "## Limits","",spec["limits"],""]
    if spec["plan_command"]:
        lines += ["Plan-only command:","","```sh"," ".join(spec["plan_command"]),"```",""]
    if spec["future_run_command"]:
        lines += ["Future testing command, to be invoked only after the user's go-ahead:","","```sh",
            " ".join(spec["future_run_command"]),"```",""]
    else:
        lines += ["No executable candidate/testing command exists yet. Implement and validate the stated prerequisites first.",""]
    return "\n".join(lines)


def prepare(plan, folder):
    validate(plan)
    folder.mkdir(parents=True,exist_ok=False)
    for spec in plan["experiments"]:
        path = folder / spec["id"]; path.mkdir()
        (path / "protocol.json").write_text(json.dumps({"experiment":spec,"control":plan["control"],"comparison":plan["comparison"]},indent=2)+"\n")
        (path / "result-template.json").write_text(json.dumps(result_template(spec,plan),indent=2)+"\n")
        (path / "README.md").write_text(card(spec,plan))
    receipt = {"schema":1,"status":"prepared-not-tested","testing_status":plan["testing_status"],
        "plan_sha256":sha256(PLAN),"experiments":[e["id"] for e in plan["experiments"]],
        "models_loaded":False,"gpu_tests_run":False,"benchmarks_run":False,"builds_run_by_preparer":False,
        "services_changed":False,"automatic_execution":False}
    (folder / "preparation.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(f"Prepared {len(plan['experiments'])} experiment cards under {folder}; no testing performed")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prepare",action="store_true")
    args = ap.parse_args(argv)
    plan=json.loads(PLAN.read_text());validate(plan)
    print(plan["testing_status"])
    for e in plan["experiments"]:print(e["id"]+": "+e["implementation"])
    if args.prepare:
        folder = ROOT / "bench/plans" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-m5-future")
        prepare(plan,folder)


if __name__ == "__main__":
    main()
