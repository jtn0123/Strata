#!/usr/bin/env python3
"""Compare the smaller draft vocabulary, existing helper and unchanged engine."""
import argparse
from datetime import datetime, timezone
import fcntl
import json

from benchmark import run
from check_memory import assert_no_model_server, print_snapshot, snapshot
from draft_vocab import vocabulary_info
from engines import verify_engine
from lab import ROOT
from benchmark_metrics import METRICS, change, metrics

ORDER = ("plain", "full", "subset", "subset", "full", "plain")


def settings(profile, label, predict=256, repeats=2):
    return argparse.Namespace(model="flash", label=label, comparison_profile=profile,
        engine="baseline" if profile == "plain" else "draft-vocab",
        draft_vocab="106k" if profile == "subset" else "off", context=4096,
        batch=512, ubatch=512, cache_type="f16", spec="none" if profile == "plain" else "draft-mtp",
        draft=2, draft_placement="output", draft_model="mtp_q3", threads=8,
        temperature=0.6, extended_checks=True, repeats=repeats, warmups=1,
        predict=predict, prompts=[512, 2048], real_workloads=True, cached_workloads=True)


def compare(records):
    if len(records) != len(ORDER) or any(r["status"] != "passed" for r in records):
        raise ValueError("All six runs and their answer checks must pass")
    if [r["settings"]["comparison_profile"] for r in records] != list(ORDER):
        raise ValueError("Comparison order changed")
    excluded = {"label", "comparison_profile", "engine", "spec", "draft_vocab"}
    common = {k: v for k, v in records[0]["settings"].items() if k not in excluded}
    for record in records:
        profile = record["settings"]["comparison_profile"]
        expected = vars(settings(profile, "unused", common["predict"], common["repeats"]))
        if {k: v for k, v in record["settings"].items() if k != "label"} != {
                k: v for k, v in expected.items() if k != "label"}:
            raise ValueError("A run differs from its intended profile")
        if any(record[k] != records[0][k] for k in ("model", "runtime")):
            raise ValueError("Target model or runtime changed")
        if record.get("memory", {}).get("guard"):
            raise ValueError("Cannot adopt a result stopped by memory pressure")
        if profile == "subset":
            if record["draft_vocabulary"] != vocabulary_info():
                raise ValueError("Vocabulary pin changed")
            log = (ROOT / "bench/results" / record["run_id"] / "server.log").read_text()
            if "using draft vocabulary graph (106299 output rows)" not in log:
                raise ValueError("Subset graph was not used by backend sampling")
    candidate = [r for r in records if r["settings"]["comparison_profile"] != "plain"]
    if any(r["selected_engine"] != candidate[0]["selected_engine"] or
           r["draft_model"] != candidate[0]["draft_model"] for r in candidate):
        raise ValueError("Helper or candidate binary changed between full/subset runs")
    summaries = []
    fresh_keys = {(c["workload"], c["prompt_tokens"]) for c in records[0]["cases"]}
    for cached, keys in ((False, sorted(fresh_keys)), (True, [("cached-ledger", n) for n in (512, 2048)])):
        for name, length in keys:
            groups = {}
            for profile in set(ORDER):
                cases = [c for r in records if r["settings"]["comparison_profile"] == profile
                         for c in r["cached_cases" if cached else "cases"]]
                groups[profile] = [c for c in cases if not c["warmup"] and c["history_budget"] == length] if cached else [
                    c for c in cases if (c["workload"], c["prompt_tokens"]) == (name, length)]
            if any(len(cases) != common["repeats"] * 2 for cases in groups.values()):
                raise ValueError("Missing measured cases")
            hashes = {profile: sorted(c["prompt_sha256"] for c in cases) for profile, cases in groups.items()}
            if any(hashes[p] != hashes["plain"] for p in hashes):
                raise ValueError("Compared prompt tokens differ")
            if not cached and any(c["output_tokens"] != common["predict"] for cases in groups.values() for c in cases):
                raise ValueError("Fixed output counts differ")
            rates = {profile: metrics(cases, cached) for profile, cases in groups.items()}
            summaries.append({"workload": name, "input_budget": length, "cached": cached, "profiles": rates,
                "subset_vs_full": change(rates["full"], rates["subset"]),
                "subset_vs_plain": change(rates["plain"], rates["subset"])})
    return summaries


def render_report(record):
    lines = ["# Draft vocabulary comparison", "", f"Status: {record['status']}", "",
        "Full Flash-Next Q2_0 on the 48 GiB M5 Pro. All profiles use 4K context, batch/ubatch 512, F16 cache, "
        "8 CPU threads and temperature 0.6. Plain disables prediction; full/subset use the same isolated binary, "
        "Q3_K_S helper, two draft tokens and CPU helper body/GPU output. Subset limits only the helper's word list "
        "from 248,320 to 106,299 tokens. The target still verifies with its complete vocabulary.", "",
        f"Order: {', '.join(ORDER)}. One excluded warmup and {record['repeats']} measured repeats per workload per pass. "
        f"Fresh workloads emit exactly {record['predict']} tokens with EOS ignored for timing; answer checks and "
        "cached ledger replies stop normally. English code, prose and Chinese workloads are included. "
        "Cached measurements reuse the immediately preceding turn; no cross-session cache is added. "
        "Percentages below compare fresh measurements, not older runs. OS file cache and other apps are uncontrolled.", "",
        "| Workload / input | Plain TPS | Full helper TPS | Subset TPS | Subset vs full | Subset vs plain |",
        "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for row in record.get("summary", []):
        p = row["profiles"]
        lines.append(f"| {row['workload']} / {row['input_budget']} | {p['plain']['generation_tok_s']:.2f} | "
            f"{p['full']['generation_tok_s']:.2f} | {p['subset']['generation_tok_s']:.2f} | "
            f"{row['subset_vs_full']['generation_increase_percent']:+.2f}% | "
            f"{row['subset_vs_plain']['generation_increase_percent']:+.2f}% |")
    lines += ["", "| Workload / input | Plain first token (s) | Full first token (s) | Subset first token (s) | Plain reply (s) | Full reply (s) | Subset reply (s) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for row in record.get("summary", []):
        p = row["profiles"]
        lines.append(f"| {row['workload']} / {row['input_budget']} | " + " | ".join(
            f"{p[profile][key]:.3f}" for key in ("ttft_s", "wall_s") for profile in ("plain", "full", "subset")) + " |")
    lines += ["", "| Workload / input | Plain input TPS | Full input TPS | Subset input TPS | Full acceptance | Subset acceptance |",
        "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for row in record.get("summary", []):
        p = row["profiles"]
        acceptance = [f"{p[x]['draft_acceptance_percent']:.1f}%" if p[x]['draft_acceptance_percent'] is not None else "n/a" for x in ("full", "subset")]
        lines.append(f"| {row['workload']} / {row['input_budget']} | " + " | ".join(
            f"{p[x]['prompt_tok_s']:.1f}" for x in ("plain", "full", "subset")) + " | " + " | ".join(acceptance) + " |")
    lines += ["", "Raw runs retain exact weights/settings/source/binary hashes, token IDs, checks, logs and memory samples.", ""]
    for item in record["runs"]:
        lines.append(f"- [{item['profile']} / {item['run_id']}](../{item['run_id']}/result.json): "
            f"{item['status']}; new swap {item['memory'].get('swap_growth_bytes', 0) / 1024**3:.3f} GiB")
    if record.get("error"):
        lines += ["", record["error"]]
    return "\n".join(lines) + "\n"


def execute_plan(args):
    verify_engine("baseline")
    verify_engine("draft-vocab")
    vocabulary_info()
    assert_no_model_server()
    folder = ROOT / "bench/results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-vocab-comparison")
    folder.mkdir()
    record = {"schema": 1, "kind": "draft-vocabulary", "status": "running", "runs": [],
        "order": ORDER, "predict": args.predict, "repeats": args.repeats, "preflight": snapshot()}
    records = []
    try:
        for index, profile in enumerate(ORDER, 1):
            assert_no_model_server()
            result = run(settings(profile, f"vocab-{index}-{profile}", args.predict, args.repeats))
            records.append(result)
            record["runs"].append({"run_id": result["run_id"], "profile": profile,
                "status": result["status"], "memory": result.get("memory", {})})
            (folder / "comparison.json").write_text(json.dumps(record, indent=2) + "\n")
            if result["status"] != "passed":
                raise RuntimeError("Answer checks failed; comparison stopped")
        record["summary"] = compare(records)
        record["status"] = "passed"
    except BaseException as error:
        record["status"] = "failed"
        record["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        (folder / "comparison.json").write_text(json.dumps(record, indent=2) + "\n")
        (folder / "COMPARISON.md").write_text(render_report(record))
        print(f"Saved comparison: {folder}", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--predict", type=int, default=256)
    ap.add_argument("--repeats", type=int, default=2)
    args = ap.parse_args()
    if not 1 <= args.predict <= 1024 or args.repeats < 1:
        ap.error("Use 1-1024 output tokens and at least one measured repeat")
    print_snapshot(snapshot())
    print(f"Plan: {' / '.join(ORDER)}; {args.predict} output tokens, {args.repeats} measured repeats.")
    if not args.run:
        print("Preparation only. Add --run to load the model and benchmark.")
        return
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        execute_plan(args)


if __name__ == "__main__":
    main()
