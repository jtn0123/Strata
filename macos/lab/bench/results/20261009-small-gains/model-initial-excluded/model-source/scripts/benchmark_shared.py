#!/usr/bin/env python3
"""Isolate weight sharing, then GPU placement, with fresh unchanged controls."""
import argparse
from datetime import datetime, timezone
import fcntl
import json

from benchmark import run
from benchmark_vocab import change, metrics
from check_memory import assert_no_model_server, print_snapshot, snapshot
from engines import verify_engine
from lab import ROOT


def plan(include_gpu, gpu_batch=128, include_mixed=False):
    half = ("plain", "full", "shared-cpu")
    if include_mixed:
        half += ("shared-mixed",)
    elif include_gpu:
        half += ("shared-small", "shared-gpu") if gpu_batch != 512 else ("shared-gpu",)
    return half + tuple(reversed(half))


def settings(profile, label, predict=128, repeats=2, gpu_batch=128):
    shared = profile.startswith("shared-")
    batch = gpu_batch if profile in ("shared-small", "shared-gpu") else 512
    return argparse.Namespace(model="flash", label=label, comparison_profile=profile,
        engine="mtp-shared" if shared else "baseline", draft_vocab="off", context=4096,
        batch=batch, ubatch=batch, cache_type="f16", spec="none" if profile == "plain" else "draft-mtp",
        draft=2, draft_placement=("mixed" if profile == "shared-mixed" else (
            "gpu" if profile == "shared-gpu" else "output")),
        draft_model=("mtp_shared_packed_q3" if profile == "shared-mixed" else (
            "mtp_shared_q3" if shared else "mtp_q3")), threads=8,
        temperature=0.6, extended_checks=True, repeats=repeats, warmups=1,
        predict=predict, prompts=[512, 2048], real_workloads=True, cached_workloads=True)


def compare(records, order, gpu_batch=128):
    if len(records) != len(order) or any(r["status"] != "passed" for r in records):
        raise ValueError("Every run and answer check must pass")
    if [r["settings"]["comparison_profile"] for r in records] != list(order):
        raise ValueError("Profile order changed")
    common = records[0]["settings"]
    for record in records:
        expected = vars(settings(record["settings"]["comparison_profile"], record["settings"]["label"],
                                 common["predict"], common["repeats"], gpu_batch))
        if record["settings"] != expected or any(record[k] != records[0][k] for k in ("model", "runtime")):
            raise ValueError("Settings, target or runtime differs from the plan")
        if record.get("memory", {}).get("guard"):
            raise ValueError("A run stopped on memory pressure")
        if record["settings"]["comparison_profile"].startswith("shared-"):
            log = (ROOT / "bench/results" / record["run_id"] / "server.log").read_text()
            if "borrowing target embeddings/output; draft KV remains separate" not in log:
                raise ValueError("Weight borrowing did not activate")
    profiles = tuple(dict.fromkeys(order))
    for profile in profiles:
        paired = [r for r in records if r["settings"]["comparison_profile"] == profile]
        if any(r["selected_engine"] != paired[0]["selected_engine"] or
               r.get("draft_model") != paired[0].get("draft_model") for r in paired):
            raise ValueError("Binary or helper changed between paired passes")
    rows = []
    keys = sorted({(c["workload"], c["prompt_tokens"]) for c in records[0]["cases"]})
    for cached, workloads in ((False, keys), (True, [("cached-ledger", n) for n in (512, 2048)])):
        for name, length in workloads:
            groups = {}
            for profile in profiles:
                cases = [c for r in records if r["settings"]["comparison_profile"] == profile
                         for c in r["cached_cases" if cached else "cases"]]
                groups[profile] = [c for c in cases if not c["warmup"] and c["history_budget"] == length] if cached else [
                    c for c in cases if (c["workload"], c["prompt_tokens"]) == (name, length)]
            if any(len(cases) != common["repeats"] * 2 for cases in groups.values()):
                raise ValueError("Missing measured cases")
            hashes = {p: sorted(c["prompt_sha256"] for c in cases) for p, cases in groups.items()}
            if any(hashes[p] != hashes["plain"] for p in profiles):
                raise ValueError("Prompt tokens differ")
            if not cached and any(c["output_tokens"] != common["predict"] for cases in groups.values() for c in cases):
                raise ValueError("Fixed output counts differ")
            rates = {p: metrics(cases, cached) for p, cases in groups.items()}
            row = {"workload": name, "input_budget": length, "cached": cached, "profiles": rates,
                   "sharing_vs_full": change(rates["full"], rates["shared-cpu"]),
                   "sharing_vs_plain": change(rates["plain"], rates["shared-cpu"])}
            if "shared-gpu" in profiles:
                reference = "shared-small" if "shared-small" in profiles else "shared-cpu"
                row["gpu_vs_shared_cpu"] = change(rates[reference], rates["shared-gpu"])
                row["gpu_vs_plain"] = change(rates["plain"], rates["shared-gpu"])
                if "shared-small" in profiles:
                    row["small_batch_vs_shared_cpu"] = change(rates["shared-cpu"], rates["shared-small"])
            if "shared-mixed" in profiles:
                row["mixed_vs_shared_cpu"] = change(rates["shared-cpu"], rates["shared-mixed"])
                row["mixed_vs_plain"] = change(rates["plain"], rates["shared-mixed"])
            rows.append(row)
    return rows


def render(record):
    profiles = tuple(dict.fromkeys(record["order"]))
    lines = ["# Shared helper comparison", "", f"Status: {record['status']}", "",
        "Full Flash-Next Q2_0 on the 48 GiB M5 Pro, 4K context, F16 cache, "
        "8 threads, temperature 0.6. Plain has prediction off. Full uses the selected self-contained Q3 helper, "
        "CPU body/GPU output and two draft tokens. Shared-cpu removes only the helper's embeddings/output "
        "and borrows the target tables while retaining CPU body placement. Draft KV stays separate. "
        "Target weights/graph are unchanged; the borrowed Q5_K output changes "
        "draft precision from the helper's Q3_K. Plain/full/shared-cpu use batch/ubatch 512. "
        "No vocabulary subset or GPU-limit override is used.", "",
        f"Order: {', '.join(record['order'])}. One excluded warmup and {record['repeats']} measured repeats "
        f"per workload per pass; {record['predict']} output tokens for fresh fixed-length timings. "
        "Normal-EOS checks and cached ledger replies retain their natural output lengths. "
        "Cache means the immediately preceding turn, without cross-session caching. "
        "Keep other suites separate because their binaries, profiles and measurement conditions can differ.", "",
        "| Workload / input | " + " | ".join(p + " TPS" for p in profiles) + " | Sharing vs full | Placement vs plain |",
        "| --- | " + " | ".join("---:" for _ in profiles) + " | ---: | ---: |"]
    description = ("Shared-mixed retains batch 512, uses a byte-verified experts-first helper layout, keeps "
        "its experts on CPU and moves its small dense/attention operations to GPU. Automatic CPU-op offload "
        "is disabled so those experts stay on CPU during prefill. Its Metal mapped-weight span is about 45.6 MiB, "
        "versus 1,183 MiB for the same placement with the interleaved file. Target weights remain on Metal.") if "shared-mixed" in profiles else (
        f"Shared-small uses batch {record['gpu_batch']} with CPU body placement; shared-gpu changes only its body "
        "placement. Their comparison isolates GPU placement. GPU vs plain compares the complete profile, "
        "including its smaller processing batches.") if "shared-gpu" in profiles else "Only CPU-body weight sharing is included."
    lines[4:4] = [description, ""]
    for row in record.get("summary", []):
        gpu = row.get("mixed_vs_plain", row.get("gpu_vs_plain", {})).get("generation_increase_percent")
        lines.append(f"| {row['workload']} / {row['input_budget']} | " + " | ".join(
            f"{row['profiles'][p]['generation_tok_s']:.2f}" for p in profiles) +
            f" | {row['sharing_vs_full']['generation_increase_percent']:+.2f}% | " +
            (f"{gpu:+.2f}%" if gpu is not None else "n/a") + " |")
    for key, title in (("ttft_s", "First token, seconds"), ("wall_s", "Complete reply, seconds"),
                       ("prompt_tok_s", "Input tokens/second"), ("draft_acceptance_percent", "Draft acceptance, percent")):
        lines += ["", title, "", "| Workload / input | " + " | ".join(profiles) + " |",
                  "| --- | " + " | ".join("---:" for _ in profiles) + " |"]
        for row in record.get("summary", []):
            values = [row["profiles"][p][key] for p in profiles]
            lines.append(f"| {row['workload']} / {row['input_budget']} | " + " | ".join(
                f"{v:.3f}" if v is not None else "n/a" for v in values) + " |")
    lines += ["", "Raw records include exact source/binary/helper pins, answers, token IDs, native logs and memory samples.", ""]
    for item in record["runs"]:
        lines.append(f"- [{item['profile']} / {item['run_id']}](../{item['run_id']}/result.json): {item['status']}; "
                     f"new swap {item['memory'].get('swap_growth_bytes', 0)/1024**3:.3f} GiB")
    if record.get("error"):
        lines += ["", record["error"]]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--include-gpu", action="store_true")
    ap.add_argument("--include-mixed", action="store_true")
    ap.add_argument("--gpu-batch", type=int, choices=[128, 256, 512], default=128)
    ap.add_argument("--predict", type=int, default=128)
    ap.add_argument("--repeats", type=int, default=2)
    args = ap.parse_args()
    if args.include_gpu and args.include_mixed:
        ap.error("Compare full GPU and mixed placement in separate experiments")
    if not 1 <= args.predict <= 1024 or args.repeats < 1:
        ap.error("Use 1-1024 output tokens and at least one measured repeat")
    order = plan(args.include_gpu, args.gpu_batch, args.include_mixed)
    print_snapshot(snapshot())
    print("Plan: " + " / ".join(order), flush=True)
    if not args.run:
        print("Preparation only. Add --run to load models and benchmark.")
        return
    with (ROOT / "bench/.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        verify_engine("baseline")
        verify_engine("mtp-shared")
        assert_no_model_server()
        folder = ROOT / "bench/results" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-shared-comparison")
        folder.mkdir()
        record = {"schema": 1, "kind": "mtp-shared", "status": "running", "order": order, "runs": [],
                  "predict": args.predict, "repeats": args.repeats, "gpu_batch": args.gpu_batch, "preflight": snapshot()}
        records = []
        try:
            for index, profile in enumerate(order, 1):
                assert_no_model_server()
                result = run(settings(profile, f"shared-{index}-{profile}", args.predict, args.repeats, args.gpu_batch))
                records.append(result)
                record["runs"].append({"run_id": result["run_id"], "profile": profile,
                    "status": result["status"], "memory": result.get("memory", {})})
                (folder / "comparison.json").write_text(json.dumps(record, indent=2) + "\n")
                if result["status"] != "passed":
                    raise RuntimeError("Answer checks failed; comparison stopped")
            record["summary"] = compare(records, order, args.gpu_batch)
            record["status"] = "passed"
        except BaseException as error:
            record.update(status="failed", error=f"{type(error).__name__}: {error}")
            raise
        finally:
            (folder / "comparison.json").write_text(json.dumps(record, indent=2) + "\n")
            (folder / "COMPARISON.md").write_text(render(record))
            print(f"Saved {folder}", flush=True)


if __name__ == "__main__":
    main()
