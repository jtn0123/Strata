#!/usr/bin/env python3
"""Rebuild a compact scoreboard from immutable raw benchmark records."""
import json
from pathlib import Path
from lab import ROOT


def main():
    results = sorted((ROOT / "bench/results").glob("*/result.json"))
    lines = ["# Strata Mac experiment results", "",
             "Measured on this 48 GiB M5 Pro. Raw JSON, CSV, native logs, exact prompt IDs and 250 ms memory samples are saved beside each run. Earlier results stay unchanged.", "",
             "| Run | Prompt tokens | Output tok/s (median) | First token (median, s) | Input tok/s (median) | Peak RSS (GiB) | Peak swap (GiB) | Swap growth (GiB) | Status |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for path in results:
        record = json.loads(path.read_text())
        memory = record.get("memory", {})
        peak = memory.get("peak_rss_bytes", 0) / 1024**3
        swap = memory.get("swap_growth_bytes", 0) / 1024**3
        peak_swap = memory.get("peak_swap_bytes", 0) / 1024**3
        label = f"[{record['settings']['label']}](results/{path.parent.name}/result.json)"
        for summary in record.get("summary", []):
            lines.append(f"| {label} | {summary['prompt_tokens']} | {summary['median_generation_tok_s']:.2f} | {summary['median_ttft_s']:.3f} | {summary['median_prompt_tok_s']:.1f} | {peak:.2f} | {peak_swap:.2f} | {swap:.2f} | {record['status']} |")
        if not record.get("summary"):
            lines.append(f"| {label} | - | - | - | - | {peak:.2f} | {peak_swap:.2f} | {swap:.2f} | {record['status']}: {record.get('error', '')} |")
    comparisons = sorted((ROOT / "bench/results").glob("*/comparison.json"))
    if comparisons:
        lines += ["", "## Optimization 1: conversation caching", "",
                  "Matched follow-up prompts through the Strata adapter, caching off versus on. Same model/settings, alternating pair order, excluded warm-up pairs. This measures follow-up waiting, not fresh-prompt throughput.", "",
                  "| Model / run | History budget | First token off (s) | First token on (s) | Less waiting | Less total response time | Output speed change | Checks | Status |",
                  "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |"]
        for path in comparisons:
            record = json.loads(path.read_text())
            if record.get("kind") != "conversation-cache":
                continue
            checks = record.get("checks", [])
            count = f"{sum(c['passed'] for c in checks)}/{len(checks)}"
            label = f"[{record['settings']['model']} / {path.parent.name}](results/{path.parent.name}/comparison.json)"
            for summary in record.get("summary", []):
                off, on = summary["cache_off"], summary["cache_on"]
                lines.append(f"| {label} | {summary['history_budget']} | {off['median_ttft_s']:.3f} | {on['median_ttft_s']:.3f} | {summary['ttft_reduction_percent']:.1f}% | {summary['total_time_reduction_percent']:.1f}% | {summary['generation_increase_percent']:+.1f}% | {count} | {record['status']} |")
        lines += ["", "Reduction = 100 x (1 - cached duration / uncached duration). Output speed change = 100 x (cached rate / uncached rate - 1). Prompt cache is one engine slot; an unrelated chat may replace it. Memory samples cover both modes in the same process; paired RSS values are not isolated allocation measurements."]
    lines += ["", "## Interpretation", "",
              "- Compare changes within the same model, prompt hash, sampling settings and context. Model names ending Q2_0 or Q4_K_M describe compressed weights, not fewer model layers or experts.",
              "- Speed runs ignore EOS to generate a fixed output length. Separate normal chat checks test answer correctness and stop handling. Two sanity questions do not establish overall model quality.",
              "- No concurrent model downloads during speed runs. OS file caches are uncontrolled; these are not guaranteed cold SSD tests. The first request may include additional shader compilation.",
              "- RSS is a process measurement, not total GPU usage. Read the full-model native allocation log too. System disk reads include unrelated activity.",
              "- Swap growth is relative to the start of each run. Peak swap includes pages left swapped by earlier experiments; the 8K run inherited swap from the CPU draft test.",
              "- The default guard stops a run if swap grows by more than 2 GiB or available RAM stays below 384 MiB for four seconds. A stopped configuration is recorded as a failure, not a speed result.",
              "", "## Integration checks", ""]
    if (ROOT / "bench/PREDICTION.md").exists():
        lines.insert(lines.index("## Interpretation"), "[Optimization 2: prediction-helper percentages, tradeoffs and decision](PREDICTION.md)\n")
    for path in sorted((ROOT / "bench/results").glob("*-integration.json")):
        record = json.loads(path.read_text())
        passed = sum(c["passed"] for c in record["checks"])
        lines.append(f"- [{path.stem}](results/{path.name}): {passed}/{len(record['checks'])} checks passed.")
    for path in sorted((ROOT / "bench/results").glob("*-context-probe.json")):
        record = json.loads(path.read_text())
        lines.append(f"- [{path.stem}](results/{path.name}): {'passed' if record['passed'] else 'failed'}, varied records across {record['prompt_tokens']} input tokens.")
    for path in sorted((ROOT / "bench/results").glob("*-cache-api.json")):
        record = json.loads(path.read_text())
        passed = sum(c["passed"] for c in record["checks"])
        lines.append(f"- [{path.stem}](results/{path.name}): {passed}/{len(record['checks'])} real Strata HTTP follow-ups correct with confirmed native cache reuse.")
    lines += ["", "Initial SSD measurement: [raw data](results/ssd-initial.json). GGUF layouts: [full model](results/flash-gguf-inventory.json), [draft head](results/mtp-gguf-inventory.json).", ""]
    output = ROOT / "bench/RESULTS.md"
    output.write_text("\n".join(lines))
    print(output)


if __name__ == "__main__":
    main()
